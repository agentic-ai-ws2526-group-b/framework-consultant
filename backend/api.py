import os
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import chromadb

# OpenAI Agents SDK
from agents import Agent, Runner
from agents.tool import function_tool


# -----------------------------------------
# ENV
# -----------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in .env")


# -----------------------------------------
# Chroma
# -----------------------------------------
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
usecase_collection = chroma_client.get_or_create_collection("bosch_use_cases")
framework_collection = chroma_client.get_or_create_collection("framework_docs")


# -----------------------------------------
# FastAPI
# -----------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DEV ok; in PROD einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------
# Models
# -----------------------------------------
class AgentRequest(BaseModel):
    agent_type: str
    priorities: List[str] = Field(default_factory=list)
    use_case: str
    experience_level: Optional[str] = None
    learning_preference: Optional[str] = None

    # UI kann damit Frameworks erzwingen ("Passt nicht – Frameworks anzeigen")
    force_frameworks: Optional[bool] = False


class AgentResponse(BaseModel):
    # JSON string, damit dein Frontend JSON.parse(data.answer) machen kann
    answer: str


# -----------------------------------------
# Helpers
# -----------------------------------------
DIMS = ["D1", "D2", "D3", "D4", "D5", "D6"]


def _debug_print(title: str, payload: Any) -> None:
    print(f">>> {title}: {payload}")


def _extract_json(text: str) -> Dict[str, Any]:
    """Robust: extrahiert JSON aus Modell-Output."""
    if not text:
        return {}
    t = text.strip()

    # Codefence
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            candidate = parts[1].strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

    # Fallback: ersten JSON-Block suchen
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    return {}


def _ensure_final_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    obj = obj or {}
    if obj.get("mode") not in ("agents", "frameworks"):
        obj["mode"] = "frameworks"
    obj.setdefault("agent_recommendations", [])
    obj.setdefault("framework_recommendations", [])
    return obj


def _build_query(req: AgentRequest) -> str:
    return (
        f"Use Case: {req.use_case}\n"
        f"Agententyp: {req.agent_type}\n"
        f"Prioritäten: {', '.join(req.priorities) if req.priorities else 'keine'}\n"
        f"Experience Level: {req.experience_level or 'unknown'}\n"
        f"Learning Preference: {req.learning_preference or 'unknown'}"
    )


def _distance_to_similarity(distance: Optional[float]) -> Optional[float]:
    """Heuristik distance -> similarity score in [0, 1]. Nur als Debug / Vorfilter."""
    if distance is None:
        return None
    try:
        d = float(distance)
        s = 1.0 / (1.0 + d)
        return max(0.0, min(1.0, s))
    except Exception:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _tags_set(meta: Dict[str, Any]) -> set:
    raw = ""
    if isinstance(meta, dict):
        raw = meta.get("tags") or ""
    raw = _norm(raw)
    parts = [t.strip() for t in re.split(r"[,;|]", raw) if t.strip()]
    return set(parts)


def _has_any(text: str, kws: List[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in kws)


# -----------------------------------------
# Deterministic scoring (Bewertungsmatrix) – EXISTIEREND (Frameworks)
# -----------------------------------------
PRIORITY_WEIGHTS_BY_KEY: Dict[str, Dict[str, float]] = {
    "speed": {"D1": 2.5, "D2": 0.75, "D3": 0.75, "D4": 0.75, "D5": 0.75, "D6": 1.5},
    "tools": {"D1": 0.75, "D2": 2.5, "D3": 0.75, "D4": 0.75, "D5": 1.5, "D6": 0.75},
    "memory": {"D1": 0.75, "D2": 0.75, "D3": 2.0, "D4": 1.0, "D5": 0.75, "D6": 0.75},
    "rag": {"D1": 0.75, "D2": 0.75, "D3": 2.2, "D4": 1.0, "D5": 0.75, "D6": 0.75},
    "multi": {"D1": 0.8, "D2": 1.0, "D3": 1.0, "D4": 2.2, "D5": 1.2, "D6": 1.0},
    "privacy": {d: 1.0 for d in DIMS},
}

AGENT_TYPE_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "Workflow-Agent": {"D1": 1.2, "D2": 1.3, "D3": 1.0, "D4": 0.7, "D5": 0.8, "D6": 1.0},
    "Multi-Agent-System": {"D1": 0.8, "D2": 1.0, "D3": 1.0, "D4": 1.4, "D5": 1.2, "D6": 1.0},
    "Daten-Agent": {"D1": 1.0, "D2": 1.1, "D3": 1.4, "D4": 1.0, "D5": 1.0, "D6": 1.0},
    "Analyse-Agent": {"D1": 1.0, "D2": 1.0, "D3": 1.2, "D4": 1.0, "D5": 1.3, "D6": 1.0},
    "Chatbot": {"D1": 1.2, "D2": 1.0, "D3": 1.0, "D4": 1.0, "D5": 1.0, "D6": 1.1},
    "unknown": {d: 1.0 for d in DIMS},
}

SKILL_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "beginner": {"D1": 1.2, "D2": 1.0, "D3": 1.0, "D4": 1.0, "D5": 0.8, "D6": 1.4},
    "intermediate": {d: 1.0 for d in DIMS},
    "expert": {"D1": 1.0, "D2": 1.0, "D3": 1.0, "D4": 1.2, "D5": 1.4, "D6": 0.8},
}


def _avg_weights(priorities: List[str]) -> Dict[str, float]:
    if not priorities:
        return {d: 1.0 for d in DIMS}
    vecs = [PRIORITY_WEIGHTS_BY_KEY.get(p, {d: 1.0 for d in DIMS}) for p in priorities]
    out = {d: 0.0 for d in DIMS}
    for v in vecs:
        for d in DIMS:
            out[d] += float(v.get(d, 1.0))
    n = float(len(vecs))
    return {d: out[d] / n for d in DIMS}


def _get_agent_mult(agent_type: str) -> Dict[str, float]:
    return AGENT_TYPE_MULTIPLIERS.get(agent_type, {d: 1.0 for d in DIMS})


def _get_skill_mult(skill_level: Optional[str]) -> Dict[str, float]:
    if not skill_level:
        return {d: 1.0 for d in DIMS}
    return SKILL_MULTIPLIERS.get(skill_level, {d: 1.0 for d in DIMS})


def _score_framework_dims(
    dims: Dict[str, int],
    weights: Dict[str, float],
    agent_mult: Dict[str, float],
    skill_mult: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    per_dim: Dict[str, float] = {}
    total = 0.0
    for d in DIMS:
        base = float(dims.get(d, 0))
        contrib = base * weights[d] * agent_mult[d] * skill_mult[d]
        per_dim[d] = contrib
        total += contrib
    return total, per_dim


# -----------------------------------------
# NEW: Use-Case -> RAW DIMS (1..5) deterministisch aus Text/Metadata
# Ziel: dieselbe Bewertungsmatrix-Logik wie Frameworks nutzen
# -----------------------------------------
def _bucket_score(strong: bool, medium: bool, weak: bool) -> int:
    if strong:
        return 5
    if medium:
        return 4
    if weak:
        return 3
    return 2


def _use_case_raw_dims(doc_text: str, meta: Dict[str, Any]) -> Dict[str, int]:
    """
    Mappt Use Case auf D1..D6 Raw Scores (1..5) deterministisch.

    Interpretation der Dims (aus deinen PRIORITY_WEIGHTS):
      D1 = speed/time-to-value
      D2 = tools/integrations
      D3 = memory/rag/knowledge
      D4 = multi-agent/workflow orchestration
      D5 = privacy/compliance (bzw. governance/enterprise constraints)
      D6 = maturity/operational readiness
    """
    text = _norm(doc_text)
    tags = _tags_set(meta)
    maturity = _norm((meta or {}).get("maturity", "unknown"))

    exp = _norm((meta or {}).get("experience_level", "unknown"))
    learn = _norm((meta or {}).get("learning_preference", "unknown"))

    # D1 speed
    d1_strong = _has_any(text, ["low effort", "quick", "fast", "short time", "schnell", "geringem aufwand"])
    d1_medium = _has_any(text, ["standard", "template", "out of the box", "schnell umgesetzt", "kurz"])
    d1_weak = ("onboarding" in tags) or ("assistant" in tags)

    # D2 tools/integrations
    d2_strong = ("sharepoint" in tags) or _has_any(text, ["connector", "connectors", "integration", "integrationen", "sharepoint", "tools"])
    d2_medium = _has_any(text, ["sources", "quellen", "datenquellen", "api", "workflow"])
    d2_weak = ("search" in tags)

    # D3 rag/knowledge/memory
    d3_strong = ("rag" in tags) or ("documentation" in tags) or ("qa" in tags) or ("knowledge" in tags) or _has_any(text, ["rag", "retrieval", "dokument", "knowledge"])
    d3_medium = ("knowledge-management" in tags) or _has_any(text, ["handbuch", "manual", "spec", "wissensartikel", "troubleshooting"])
    d3_weak = ("search" in tags) or _has_any(text, ["suche", "search"])

    # D4 multi/workflow orchestration
    d4_strong = ("multi-agent" in tags) or _has_any(text, ["multi-agent", "orchestr", "planner"])
    d4_medium = ("workflow" in tags) or _has_any(text, ["workflow", "pipeline", "automation"])
    d4_weak = _has_any(text, ["agent"])

    # D5 privacy/compliance/governance
    d5_strong = ("privacy" in tags) or ("security" in tags) or ("compliance" in tags) or _has_any(text, ["privacy", "datenschutz", "compliance", "on-prem", "security"])
    d5_medium = _has_any(text, ["permissions", "berechtigung", "rechte", "access", "policy"])
    d5_weak = False

    # D6 maturity / operational readiness
    # positives evidence vs limitations
    d6_strong = ("production" in maturity) or _has_any(text, ["works very good", "very good", "gute ergebnisse", "effective", "in der praxis möglich"])
    d6_medium = _has_any(text, ["achieved", "implemented", "standard"]) or (maturity not in ["", "unknown"])
    d6_weak = _has_any(text, ["needs clarification", "must be clarified", "challenges", "müssen geklärt", "klarification", "connector- und berechtigungsfragen"])

    raw = {
        "D1": _bucket_score(d1_strong, d1_medium, d1_weak),
        "D2": _bucket_score(d2_strong, d2_medium, d2_weak),
        "D3": _bucket_score(d3_strong, d3_medium, d3_weak),
        "D4": _bucket_score(d4_strong, d4_medium, d4_weak),
        "D5": _bucket_score(d5_strong, d5_medium, d5_weak),
        "D6": _bucket_score(d6_strong, d6_medium, d6_weak),
    }

    # kleine deterministische Anpassungen aus Meta:
    if exp == "beginner":
        raw["D6"] = min(5, raw["D6"] + 1)  # Anfänger profitieren von reifen/klarem UC
    if learn == "simple":
        raw["D1"] = min(5, raw["D1"] + 1)  # simple -> schneller/time-to-value

    # clamp
    for d in DIMS:
        raw[d] = max(1, min(5, int(raw.get(d, 3))))

    return raw


# -----------------------------------------
# Chroma: Use Cases retrieval (Vorfilter) + Matrix-Ranking
# -----------------------------------------
def _retrieve_bosch_use_cases(query: str, n_results: int = 15) -> List[Dict[str, Any]]:
    """
    Nur Retrieval: holt Top-N Kandidaten (documents+metadatas+distances).
    Kein finales Ranking (das macht die Matrix).
    """
    results = usecase_collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    out: List[Dict[str, Any]] = []
    for i in range(len(docs)):
        meta = metas[i] if metas and i < len(metas) else {}
        dist = float(dists[i]) if dists and i < len(dists) and dists[i] is not None else None
        out.append(
            {
                "title": (meta.get("agent_name") if isinstance(meta, dict) else None) or "Bosch Use Case",
                "summary": docs[i],
                "distance": dist,
                "similarity": _distance_to_similarity(dist),
                "metadata": meta if isinstance(meta, dict) else {},
            }
        )
    return out


def _rank_bosch_use_cases_matrix(req: AgentRequest, query: str, retrieval_n: int = 15, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Finales Ranking: gleiche Matrix-Logik wie Frameworks.
    - Kandidaten kommen aus Chroma (retrieval_n)
    - Dann RAW Dims ableiten, Matrix score berechnen, nach score_total sortieren
    - match_percent relativ zu best innerhalb der Kandidaten (wie Framework-Ranking)
    """
    candidates = _retrieve_bosch_use_cases(query=query, n_results=retrieval_n)
    if not candidates:
        return []

    weights = _avg_weights(req.priorities or [])
    a_mult = _get_agent_mult(req.agent_type or "unknown")
    s_mult = _get_skill_mult(req.experience_level)

    scored: List[Tuple[Dict[str, Any], float, Dict[str, float], Dict[str, int]]] = []
    for uc in candidates:
        doc = uc.get("summary", "") or ""
        meta = uc.get("metadata", {}) or {}

        raw_dims = _use_case_raw_dims(doc_text=doc, meta=meta)
        total, per_dim = _score_framework_dims(raw_dims, weights, a_mult, s_mult)

        scored.append((uc, total, per_dim, raw_dims))

    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0][1] if scored else 1.0
    if best <= 0:
        best = 1.0

    out: List[Dict[str, Any]] = []
    for uc, total, per_dim, raw_dims in scored[:top_k]:
        match_percent = int(round((total / best) * 100))
        match_percent = max(0, min(100, match_percent))

        out.append({
            "title": uc.get("title", "Bosch Use Case"),
            "summary": uc.get("summary", ""),
            "score_total": total,
            "match_percent": match_percent,
            "score": float(match_percent) / 100.0,  # UI erwartet 0..1
            "metadata": uc.get("metadata", {}) or {},
            # Debug optional:
            "distance": uc.get("distance"),
            "similarity": uc.get("similarity"),
            "score_breakdown": {
                "per_dim": per_dim,
                "raw_dim_scores": raw_dims,
                "weights": weights,
                "agent_type_multipliers": a_mult,
                "skill_multipliers": s_mult,
            }
        })

    return out


# -----------------------------------------
# Chroma: Framework docs query (RAG)
# -----------------------------------------
def _query_framework_docs(query: str, n_results: int = 3) -> Dict[str, Any]:
    results = framework_collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    out: List[Dict[str, Any]] = []
    for i in range(len(docs)):
        out.append({
            "text": docs[i],
            "meta": metas[i] if metas and i < len(metas) else {}
        })
    return {"docs": out}


def _get_framework_snippets_for_framework(framework_name: str, query: str, n_results: int = 2) -> List[str]:
    """
    Holt kurze Text-Snippets aus framework_docs für ein spezifisches Framework.
    Wir filtern auf framework=<name> und is_factsheet=False (nur Doku-Chunks).
    """
    try:
        results = framework_collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"framework": framework_name, "is_factsheet": False},
        )
        docs = results.get("documents", [[]])[0]
        return [d for d in docs if isinstance(d, str)]
    except Exception:
        return []


# -----------------------------------------
# Tools (Agents SDK)
# -----------------------------------------
@function_tool
def search_framework_docs(query: str, n_results: int = 3) -> Dict[str, Any]:
    """Search in framework docs stored in ChromaDB."""
    return _query_framework_docs(query=query, n_results=n_results)


# -----------------------------------------
# Framework Factsheets Loader (bestehend)
# -----------------------------------------
def _load_framework_factsheets_from_chroma() -> List[Dict[str, Any]]:
    """
    Lädt ALLE Framework-Factsheets aus der Collection framework_docs.
    Voraussetzung: ingest_framework_docs.py hat Factsheets mit:
      - is_factsheet=True
      - framework=<name>
      - D1..D6 als flache Metadaten
    """
    try:
        got = framework_collection.get(
            where={"is_factsheet": True},
            include=["metadatas", "documents"],
        )
        metas = got.get("metadatas", []) or []
        docs = got.get("documents", []) or []

        out: List[Dict[str, Any]] = []
        for i in range(len(metas)):
            meta = metas[i] if isinstance(metas[i], dict) else {}
            fw = str(meta.get("framework") or "").strip()
            if not fw:
                continue

            dims = {d: int(meta.get(d, 3)) for d in DIMS}
            desc = ""
            if i < len(docs) and isinstance(docs[i], str):
                desc = docs[i]

            out.append({
                "framework": fw,
                "dims": dims,
                "factsheet_text": desc,
                "url": meta.get("url"),
            })

        dedup: Dict[str, Dict[str, Any]] = {}
        for item in out:
            dedup[item["framework"]] = item
        return list(dedup.values())
    except Exception as e:
        _debug_print("Factsheets load failed", str(e))
        return []


def _rank_all_frameworks(req: AgentRequest) -> List[Dict[str, Any]]:
    """
    Deterministisches Ranking über ALLE Frameworks (Factsheets aus Chroma).
    Gibt sortierte Liste zurück, inkl. match_percent & score(0..1) für UI.
    """
    facts = _load_framework_factsheets_from_chroma()
    if not facts:
        return []

    weights = _avg_weights(req.priorities or [])
    a_mult = _get_agent_mult(req.agent_type or "unknown")
    s_mult = _get_skill_mult(req.experience_level)

    scored: List[Tuple[Dict[str, Any], float, Dict[str, float]]] = []
    for fw in facts:
        total, per_dim = _score_framework_dims(fw["dims"], weights, a_mult, s_mult)
        scored.append((fw, total, per_dim))

    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0][1] if scored else 1.0
    if best <= 0:
        best = 1.0

    out: List[Dict[str, Any]] = []
    for fw, total, per_dim in scored:
        match_percent = int(round((total / best) * 100))
        match_percent = max(0, min(100, match_percent))

        out.append({
            "framework": fw["framework"],
            "dims": fw["dims"],
            "url": fw.get("url"),
            "score_total": total,
            "match_percent": match_percent,
            "score": float(match_percent) / 100.0,
            "score_breakdown": {
                "per_dim": per_dim,
                "raw_dim_scores": fw["dims"],
                "weights": weights,
                "agent_type_multipliers": a_mult,
                "skill_multipliers": s_mult,
            },
        })

    return out


# -----------------------------------------
# Agents (Agents SDK) – nur noch für Requirements/Profiler/Decision/Control/Advisor
# (Use-Case Ranking ist jetzt deterministisch via Matrix)
# -----------------------------------------
RequirementsAgent = Agent(
    name="RequirementsAgent",
    instructions=(
        "Du bist der Anforderungsagent. "
        "Du bekommst Nutzereingaben (agent_type, priorities, use_case, experience_level, learning_preference). "
        "Gib ein JSON zurück mit:\n"
        "{\n"
        '  "requirements_summary": "string",\n'
        '  "agent_role": "string",\n'
        '  "tasks": ["string", ...]\n'
        "}\n"
        "Antwort NUR als JSON."
    ),
)

ProfilerAgent = Agent(
    name="ProfilerAgent",
    instructions=(
        "Du bist der Profiler-Agent. "
        "Du erhältst requirements_summary + user attributes. "
        "Gib ein JSON zurück mit:\n"
        "{\n"
        '  "persona_name": "string",\n'
        '  "communication_style": "string",\n'
        '  "tone_guidelines": ["string", ...]\n'
        "}\n"
        "Antwort NUR als JSON."
    ),
)

DecisionAgent = Agent(
    name="DecisionAgent",
    instructions=(
        "Du bist der Decision Agent.\n"
        "WICHTIG (Hard Rules):\n"
        "- Du entscheidest NICHT über das Ranking/Order.\n"
        "- Du ermittelst KEINE Prozentwerte und rechnest nichts.\n"
        "- Du formulierst NUR Pro/Contra & Empfehlungstexte.\n"
        "- Du beziehst dich auf Use-Case & Persona.\n\n"
        "Input enthält:\n"
        "- persona (persona_name, communication_style, tone_guidelines)\n"
        "- requirements_summary\n"
        "- use_case_text\n"
        "- frameworks: Liste von Framework-Objekten in finaler Reihenfolge (nicht ändern)\n"
        "Gib NUR JSON zurück:\n"
        "{\n"
        '  "framework_texts":[\n'
        '     {"framework":"...","description":"...","match_reason":"...","pros":["..."],"cons":["..."],"recommendation":"..."}\n'
        "  ]\n"
        "}\n"
        "framework_texts MUSS gleiche Reihenfolge & Namen wie input.frameworks haben.\n"
        "Antwort NUR als JSON."
    ),
    tools=[search_framework_docs],
)

ControlAgent = Agent(
    name="ControlAgent",
    instructions=(
        "Du bist der Kontrollagent.\n"
        "Prüfe, ob die Antwort valides JSON ist und erwartete Felder existieren.\n"
        "Wenn etwas fehlt oder ungültig ist, korrigiere minimal.\n"
        "Antwort NUR als JSON."
    ),
)

AdvisorAgent = Agent(
    name="AdvisorAgent",
    instructions=(
        "Du bist der Berater-Agent.\n"
        "Du erhältst das validierte JSON.\n"
        "Gib es 1:1 als JSON zurück (keine Umformatierung, kein Extra-Text).\n"
        "Antwort NUR als JSON."
    ),
)


# -----------------------------------------
# Endpoints
# -----------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/use-cases")
def use_cases(req: AgentRequest):
    """
    Direkt-Endpoint für UI: zeigt Bosch Use Cases (Agenten) zuerst.
    NEU: Ranking via gleicher Bewertungsmatrix wie bei Frameworks.
    """
    try:
        query = _build_query(req)

        ranked_use_cases = _rank_bosch_use_cases_matrix(
            req=req,
            query=query,
            retrieval_n=15,
            top_k=3
        )

        best_score = ranked_use_cases[0]["score"] if ranked_use_cases else None

        # gleiche Regel wie vorher: wenn best < 0.35 -> Frameworks vorschlagen
        suggest_show_frameworks = True
        if best_score is not None and best_score >= 0.35:
            suggest_show_frameworks = False

        return {
            "use_cases": ranked_use_cases,
            "suggest_show_frameworks": suggest_show_frameworks,
            "best_score": best_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    """
    Orchestrierung:
      - Use Cases: deterministisch via Bewertungsmatrix (Chroma nur als Retrieval-Vorfilter)
      - Frameworks: deterministisch via Bewertungsmatrix über ALLE Frameworks (Factsheets in Chroma)
      - LLM: nur Requirements/Profiler + Pro/Contra/Empfehlungstexte (Hard Rules)
    """
    try:
        _debug_print("Request /agent", req.dict())

        # 1) Requirements
        r1 = Runner.run_sync(
            RequirementsAgent,
            [{"role": "user", "content": json.dumps(req.dict(), ensure_ascii=False)}],
        )
        requirements = _extract_json(r1.final_output or "")
        _debug_print("RequirementsAgent", requirements)

        # 2) Profiler
        profiler_payload = {
            "requirements_summary": requirements.get("requirements_summary", ""),
            "experience_level": req.experience_level,
            "learning_preference": req.learning_preference,
        }
        r2 = Runner.run_sync(
            ProfilerAgent,
            [{"role": "user", "content": json.dumps(profiler_payload, ensure_ascii=False)}],
        )
        profiler = _extract_json(r2.final_output or "")
        _debug_print("ProfilerAgent", profiler)

        # 3) Use Cases deterministisch ranken (Matrix)
        query_for_usecases = requirements.get("requirements_summary") or _build_query(req)
        ranked_use_cases = _rank_bosch_use_cases_matrix(
            req=req,
            query=query_for_usecases,
            retrieval_n=15,
            top_k=3
        )
        _debug_print("Ranked use cases (matrix)", ranked_use_cases)

        best_uc_score = ranked_use_cases[0]["score"] if ranked_use_cases else None

        # gleiche Regel: wenn keine UC oder best < 0.35 -> framework mode
        suggest_show_frameworks = True
        if best_uc_score is not None and best_uc_score >= 0.35:
            suggest_show_frameworks = False

        want_frameworks = bool(req.force_frameworks) or bool(suggest_show_frameworks)

        # 4) Framework ranking deterministisch über ALLE Frameworks
        ranked_fw = _rank_all_frameworks(req)
        _debug_print("Ranked frameworks count", len(ranked_fw))
        top3_fw = ranked_fw[:3] if ranked_fw else []

        if want_frameworks:
            # 5) RAG Snippets pro Top-Framework (optional, für bessere Texte)
            frameworks_for_llm: List[Dict[str, Any]] = []
            for fw in top3_fw:
                name = fw["framework"]
                snippets = _get_framework_snippets_for_framework(name, query=req.use_case, n_results=2)
                frameworks_for_llm.append({
                    "framework": name,
                    "snippets": snippets,
                    "url": fw.get("url"),
                    "priorities": req.priorities,
                    "agent_type": req.agent_type,
                    "experience_level": req.experience_level,
                    "learning_preference": req.learning_preference,
                })

            decision_payload = {
                "persona": profiler,
                "requirements_summary": requirements.get("requirements_summary", ""),
                "use_case_text": req.use_case,
                "frameworks": frameworks_for_llm,  # Reihenfolge ist final, LLM darf NICHT umsortieren
            }

            r4 = Runner.run_sync(
                DecisionAgent,
                [{"role": "user", "content": json.dumps(decision_payload, ensure_ascii=False)}],
            )
            decision_texts = _extract_json(r4.final_output or "")
            _debug_print("DecisionAgent(Texts)", decision_texts)

            # Merge LLM texts into deterministic ranking output
            texts_by_name: Dict[str, Dict[str, Any]] = {}
            if isinstance(decision_texts, dict) and isinstance(decision_texts.get("framework_texts"), list):
                for item in decision_texts["framework_texts"]:
                    if isinstance(item, dict) and item.get("framework"):
                        texts_by_name[str(item["framework"])] = item

            framework_recs: List[Dict[str, Any]] = []
            for fw in top3_fw:
                name = fw["framework"]
                t = texts_by_name.get(name, {})
                framework_recs.append({
                    "framework": name,
                    "score": fw["score"],  # 0..1 für UI
                    "description": t.get("description", ""),
                    "match_reason": t.get("match_reason", ""),
                    "pros": t.get("pros", []),
                    "cons": t.get("cons", []),
                    "recommendation": t.get("recommendation", ""),
                    "match_percent": fw.get("match_percent"),
                    "score_breakdown": fw.get("score_breakdown"),
                    "url": fw.get("url"),
                })

            final_obj = {
                "mode": "frameworks",
                "agent_recommendations": [],
                "framework_recommendations": framework_recs,
            }

        else:
            # Agents mode: Use Cases aus Matrix-Ranking
            agent_recs = []
            for uc in ranked_use_cases[:3]:
                agent_recs.append({
                    "title": uc.get("title", "Bosch Use Case"),
                    "summary": uc.get("summary", ""),
                    "score": uc.get("score", 0.0),
                    "match_percent": uc.get("match_percent", int(round((uc.get("score", 0.0) or 0.0) * 100))),
                    "score_breakdown": uc.get("score_breakdown"),
                    "metadata": uc.get("metadata", {}),
                })

            final_obj = {
                "mode": "agents",
                "agent_recommendations": agent_recs,
                "framework_recommendations": [],
            }

        # Control -> ensure JSON shape
        r5 = Runner.run_sync(
            ControlAgent,
            [{"role": "user", "content": json.dumps(final_obj, ensure_ascii=False)}],
        )
        controlled = _extract_json(r5.final_output or "")
        controlled = _ensure_final_shape(controlled)
        _debug_print("ControlAgent", controlled)

        # Advisor -> final
        r6 = Runner.run_sync(
            AdvisorAgent,
            [{"role": "user", "content": json.dumps(controlled, ensure_ascii=False)}],
        )
        out = _extract_json(r6.final_output or "")
        out = _ensure_final_shape(out)
        _debug_print("Final", out)

        return AgentResponse(answer=json.dumps(out, ensure_ascii=False))

    except Exception as e:
        error_obj = _ensure_final_shape({
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": [],
            "error": str(e),
        })
        return AgentResponse(answer=json.dumps(error_obj, ensure_ascii=False))
