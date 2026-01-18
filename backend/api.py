import os
import json
from typing import List, Optional, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dotenv import load_dotenv
import chromadb
from openai import OpenAI

# ---------------------------
# Setup / ENV
# ---------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

# Collections
FRAMEWORK_DOCS_COLLECTION = os.getenv("FRAMEWORK_DOCS_COLLECTION", "framework_docs")
BOSCH_USE_CASES_COLLECTION = os.getenv("BOSCH_USE_CASES_COLLECTION", "bosch_use_cases")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

framework_collection = chroma_client.get_or_create_collection(FRAMEWORK_DOCS_COLLECTION)
bosch_usecase_collection = chroma_client.get_or_create_collection(BOSCH_USE_CASES_COLLECTION)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ok für lokalen Dev; später restriktiver machen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Models
# ---------------------------
class AgentRequest(BaseModel):
    agent_type: str = Field(..., description="z.B. Chatbot, Daten-Agent, Workflow-Agent ...")
    priorities: List[str] = Field(default_factory=list, description="z.B. speed, privacy, tools, rag ...")
    use_case: str = Field(..., description="Freitext Use Case")

    # Neue UI-Felder:
    experience_level: Optional[str] = Field(default=None, description="beginner|intermediate|expert")
    learning_preference: Optional[str] = Field(default=None, description="learn|simple")


class UseCaseCard(BaseModel):
    title: str
    summary: str
    score: float
    # Optional: Metadaten, falls du sie später anzeigen willst
    metadata: Optional[Dict[str, Any]] = None


class UseCaseResponse(BaseModel):
    use_cases: List[UseCaseCard]
    # UI-Hinweis: wenn keine passenden Use Cases existieren, kann UI direkt Framework-Screen zeigen
    suggest_show_frameworks: bool = False


class AgentResponse(BaseModel):
    answer: str  # JSON string, so wie du es im Frontend parse-st


# ---------------------------
# Helpers
# ---------------------------
def _safe_first(lst, default=None):
    return lst[0] if lst and len(lst) > 0 else default


def retrieve_context_from_framework_docs(query: str, n_results: int = 5) -> str:
    results = framework_collection.query(query_texts=[query], n_results=n_results)
    docs = _safe_first(results.get("documents", [[]]), [])
    if not docs:
        return "Keine relevanten Framework-Dokumente gefunden."
    return "\n\n---\n\n".join(docs)


def retrieve_bosch_use_cases(query: str, n_results: int = 5):
    """
    Holt die besten Matches aus der Bosch-Use-Case-Collection.
    Chroma liefert distances: je kleiner, desto ähnlicher.
    """
    results = bosch_usecase_collection.query(query_texts=[query], n_results=n_results)

    docs = _safe_first(results.get("documents", [[]]), [])
    metadatas = _safe_first(results.get("metadatas", [[]]), [])
    distances = _safe_first(results.get("distances", [[]]), [])

    return docs, metadatas, distances


def distance_to_score(distance: float) -> float:
    """
    Simple Mapping: distance (0..?) -> score (0..1).
    Je nachdem wie deine Embeddings/DB skaliert ist, kann man das später tunen.
    """
    if distance is None:
        return 0.0
    # konservatives Mapping: ab distance 1.0 deutlich schlechter
    score = 1.0 / (1.0 + float(distance))
    # clamp
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def requirements_agent(req: AgentRequest) -> Dict[str, Any]:
    """
    Minimaler Requirements-Agent: fasst Anforderungen zusammen.
    (Du hast bereits Debug-Ausgaben in deiner Konsole – ich halte es bewusst simpel/stabil.)
    """
    priorities_text = ", ".join(req.priorities) if req.priorities else "keine besonderen"
    exp = req.experience_level or "unknown"
    learn = req.learning_preference or "unknown"

    requirements_summary = (
        f"Use Case: {req.use_case}. "
        f"Agententyp: {req.agent_type}. "
        f"Prioritäten: {priorities_text}. "
        f"Erfahrung: {exp}. "
        f"Präferenz: {learn}."
    )

    return {
        "requirements_summary": requirements_summary,
        "agent_role": f"{req.agent_type} für: {req.use_case}",
        "tasks": req.priorities,
    }


def decision_framework_agent(req: AgentRequest, context: str) -> Dict[str, Any]:
    """
    LLM erzeugt Top-3 Framework-Recommendations als JSON.
    """
    priorities_text = ", ".join(req.priorities) if req.priorities else "keine"
    exp = req.experience_level or "unknown"
    learn = req.learning_preference or "unknown"

    prompt = f"""
Du bist ein KI-Framework-Consultant.

Gegeben sind:
- Agententyp: {req.agent_type}
- Use Case: {req.use_case}
- Prioritäten: {priorities_text}
- Erfahrung: {exp}
- Lernpräferenz: {learn}

Nutze den Kontext (Dokumentation/Infos) unten.
Erstelle die TOP 3 Framework-Empfehlungen als streng gültiges JSON im Format:

{{
  "recommendations": [
    {{
      "framework": "string",
      "score": 0.0,
      "description": "string",
      "match_reason": "string"
    }}
  ]
}}

Wichtige Regeln:
- Antworte NUR mit JSON (kein Markdown).
- score ist 0.0 bis 1.0
- Beschreibung kurz, konkret, auf den Use Case bezogen.

KONTEXT:
{context}
""".strip()

    completion = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        messages=[
            {"role": "system", "content": "Du bist ein Experte für Agenten-Frameworks und triffst nachvollziehbare Empfehlungen."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw_text = completion.choices[0].message.content.strip()

    # Robust gegen ```json ... ```
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()

    # Validieren
    try:
        parsed = json.loads(raw_text)
        if "recommendations" not in parsed:
            raise ValueError("JSON enthält kein recommendations-Feld")
        return parsed
    except Exception:
        return {"recommendations": []}


# ---------------------------
# Routes
# ---------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "chroma_path": CHROMA_PATH,
        "framework_collection": FRAMEWORK_DOCS_COLLECTION,
        "bosch_use_cases_collection": BOSCH_USE_CASES_COLLECTION,
    }


@app.post("/use-cases", response_model=UseCaseResponse)
def get_use_cases(req: AgentRequest):
    """
    Bildschirm 4 (erster Teil):
    - Prüfe in Bosch Use Cases, ob es bereits passende Agenten/Use-Cases gibt.
    - Liefere Top-3 Use Cases zurück.
    """
    print(f">>> Request /use-cases: {req.model_dump()}")

    req_summary = requirements_agent(req)
    print(f">>> Requirements summary: {req_summary['requirements_summary']}")

    query = req_summary["requirements_summary"]
    docs, metadatas, distances = retrieve_bosch_use_cases(query, n_results=5)

    use_cases: List[UseCaseCard] = []

    for i, doc in enumerate(docs):
        md = metadatas[i] if i < len(metadatas) else {}
        dist = distances[i] if i < len(distances) else None

        # Erwartung: dein Ingest speichert Titel/Summary entweder im Metadata oder im Document.
        # Wir unterstützen beides.
        title = (md.get("title") if isinstance(md, dict) else None) or "Bosch Use Case"
        summary = (md.get("summary") if isinstance(md, dict) else None) or doc

        use_cases.append(
            UseCaseCard(
                title=title,
                summary=summary,
                score=distance_to_score(dist),
                metadata=md if isinstance(md, dict) else None,
            )
        )

    # Sortiere nach score absteigend und nimm Top-3
    use_cases = sorted(use_cases, key=lambda x: x.score, reverse=True)[:3]

    # Wenn quasi nix passt, schlage direkt Frameworks vor
    suggest_show_frameworks = len(use_cases) == 0 or (use_cases and use_cases[0].score < 0.45)

    print(f">>> UseCases returned: {len(use_cases)}, suggest_show_frameworks={suggest_show_frameworks}")
    return UseCaseResponse(use_cases=use_cases, suggest_show_frameworks=suggest_show_frameworks)


@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    """
    Framework-Empfehlungen (zweiter Teil Bildschirm 4):
    - Nutzt framework_docs Collection als Kontext
    - LLM erstellt Top-3 Frameworks als JSON
    """
    print(f">>> Request /agent: {req.model_dump()}")

    # Requirements zusammenfassen
    req_summary = requirements_agent(req)
    print(f">>> RequirementsAgent: {req_summary}")

    # Kontext aus Framework-Docs holen
    query = (
        f"Framework-Auswahl für Use Case: {req_summary['requirements_summary']}\n"
        f"Prioritäten: {', '.join(req.priorities) if req.priorities else 'keine'}\n"
        f"Agententyp: {req.agent_type}\n"
        f"Erfahrung: {req.experience_level or 'unknown'}\n"
        f"Lernpräferenz: {req.learning_preference or 'unknown'}"
    )
    print(f">>> Query an Chroma (framework_docs): {query}")

    context = retrieve_context_from_framework_docs(query, n_results=6)

    # LLM Entscheidung
    result_json = decision_framework_agent(req, context)

    # Backend liefert IMMER JSON-String im answer-Feld
    return AgentResponse(answer=json.dumps(result_json, ensure_ascii=False))
