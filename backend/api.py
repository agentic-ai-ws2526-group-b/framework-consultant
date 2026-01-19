import os
import json
import re
from typing import Any, Dict, List, Optional

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


class AgentResponse(BaseModel):
    # JSON string, damit dein Frontend wie bisher JSON.parse(data.answer) machen kann
    answer: str


# -----------------------------------------
# Helper: Scoring + JSON parsing
# -----------------------------------------
def _distance_to_score(distance: Optional[float]) -> Optional[float]:
    """Heuristik distance -> similarity score in [0, 1]."""
    if distance is None:
        return None
    try:
        d = float(distance)
        s = 1.0 / (1.0 + d)
        return max(0.0, min(1.0, s))
    except Exception:
        return None


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


def _debug_print(title: str, payload: Any) -> None:
    print(f">>> {title}: {payload}")


# -----------------------------------------
# IMPORTANT FIX:
# Normal python functions for Chroma queries
# (so /use-cases can call them directly)
# -----------------------------------------
def _query_bosch_use_cases(query: str, n_results: int = 3) -> Dict[str, Any]:
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
                "title": (meta.get("title") if isinstance(meta, dict) else None) or "Bosch Use Case",
                "summary": docs[i],
                "distance": dist,
                "score": _distance_to_score(dist),
                "metadata": meta if isinstance(meta, dict) else {},
            }
        )
    return {"use_cases": out}


def _query_framework_docs(query: str, n_results: int = 3) -> Dict[str, Any]:
    results = framework_collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    return {"docs": docs}


# -----------------------------------------
# Tools (Agents SDK) -> wrap the normal functions
# -----------------------------------------
@function_tool
def search_bosch_use_cases(query: str, n_results: int = 3) -> Dict[str, Any]:
    """Search in Bosch use cases stored in ChromaDB."""
    return _query_bosch_use_cases(query=query, n_results=n_results)


@function_tool
def search_framework_docs(query: str, n_results: int = 3) -> Dict[str, Any]:
    """Search in framework docs stored in ChromaDB."""
    return _query_framework_docs(query=query, n_results=n_results)


# -----------------------------------------
# Agents (Agents SDK)
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

UseCaseAnalyzerAgent = Agent(
    name="UseCaseAnalyzer",
    instructions=(
        "Du bist der Use-Case Analyzer.\n"
        "Nutze search_bosch_use_cases, um passende Bosch Use Cases zu finden.\n"
        "Gib NUR JSON zurück:\n"
        "{\n"
        '  "use_cases": [{"title":"...","summary":"...","score":0.0,"metadata":{}}],\n'
        '  "suggest_show_frameworks": boolean,\n'
        '  "reason": "string"\n'
        "}\n"
        "Regel: suggest_show_frameworks=true, wenn es keine Use Cases gibt oder der beste Score < 0.35."
    ),
    tools=[search_bosch_use_cases],
)

FrameworkAnalyzerAgent = Agent(
    name="FrameworkAnalyzer",
    instructions=(
        "Du bist der Framework-Analyzer.\n"
        "Nutze search_framework_docs, um relevante Framework-Passagen zu holen.\n"
        "Leite daraus 2-4 Framework-Kandidaten ab und gib NUR JSON zurück:\n"
        "{\n"
        '  "framework_candidates": [{"framework":"...","fit_reason":"..."}]\n'
        "}\n"
    ),
    tools=[search_framework_docs],
)

DecisionAgent = Agent(
    name="DecisionAgent",
    instructions=(
        "Du bist der Decision Agent.\n"
        "Input enthält requirements_summary, profiler, use_cases(use_cases + suggest_show_frameworks), framework_candidates.\n"
        "POLICY: Wenn suggest_show_frameworks=false -> mode='agents' und agent_recommendations aus use_cases ableiten.\n"
        "Wenn suggest_show_frameworks=true -> mode='frameworks' und framework_recommendations erstellen.\n"
        "Gib NUR JSON zurück im Format:\n"
        "{\n"
        '  "mode": "agents" | "frameworks",\n'
        '  "agent_recommendations": [{"title":"...","summary":"...","score":0.0}],\n'
        '  "framework_recommendations": [{"framework":"...","score":0.0,"description":"...","match_reason":"..."}]\n'
        "}\n"
    ),
)

ControlAgent = Agent(
    name="ControlAgent",
    instructions=(
        "Du bist der Kontrollagent.\n"
        "Prüfe, ob die Antwort valides JSON ist und die Felder mode/agent_recommendations/framework_recommendations existieren.\n"
        "Wenn etwas fehlt oder ungültig ist, korrigiere minimal.\n"
        "Antwort NUR als JSON."
    ),
)

AdvisorAgent = Agent(
    name="AdvisorAgent",
    instructions=(
        "Du bist der Berater-Agent.\n"
        "Du erhältst das validierte JSON vom ControlAgent.\n"
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
    IMPORTANT: Uses direct python Chroma query (NOT the FunctionTool wrapper).
    """
    try:
        query = _build_query(req)

        res = _query_bosch_use_cases(query=query, n_results=3)
        use_cases_list = res.get("use_cases", [])

        best_score = None
        if use_cases_list and isinstance(use_cases_list[0], dict):
            best_score = use_cases_list[0].get("score")

        suggest_show_frameworks = True
        if best_score is not None and best_score >= 0.35:
            suggest_show_frameworks = False

        return {
            "use_cases": use_cases_list,
            "suggest_show_frameworks": suggest_show_frameworks,
            "best_score": best_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/frameworks")
def frameworks(req: AgentRequest):
    """
    Optional: direkter Endpoint für Framework-Infos.
    Nutzt FrameworkAnalyzerAgent (LLM + Chroma docs).
    """
    try:
        query = _build_query(req)
        fw_query = f"Framework-Auswahl für:\n{query}"

        r = Runner.run_sync(FrameworkAnalyzerAgent, [{"role": "user", "content": fw_query}])
        obj = _extract_json(r.final_output or "")
        return obj or {"framework_candidates": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    """
    Multi-Agent Orchestrierung über OpenAI Agents SDK.
    Liefert JSON als string in `answer`.
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

        # 3) UseCaseAnalyzer (LLM + tool)
        query = requirements.get("requirements_summary") or _build_query(req)
        r3 = Runner.run_sync(
            UseCaseAnalyzerAgent,
            [{"role": "user", "content": query}],
        )
        use_case_result = _extract_json(r3.final_output or "")
        _debug_print("UseCaseAnalyzer", use_case_result)

        # 4) FrameworkAnalyzer (LLM + tool)
        fw_query = (
            f"Framework-Auswahl für Use Case:\n{query}\n"
            f"Prioritäten: {', '.join(req.priorities) if req.priorities else 'keine'}\n"
            f"Agententyp: {req.agent_type}"
        )
        r4 = Runner.run_sync(
            FrameworkAnalyzerAgent,
            [{"role": "user", "content": fw_query}],
        )
        framework_candidates = _extract_json(r4.final_output or "")
        _debug_print("FrameworkAnalyzer", framework_candidates)

        # 5) Decision
        decision_payload = {
            "requirements_summary": requirements.get("requirements_summary", ""),
            "profiler": profiler,
            "use_cases": use_case_result,
            "framework_candidates": framework_candidates,
        }
        r5 = Runner.run_sync(
            DecisionAgent,
            [{"role": "user", "content": json.dumps(decision_payload, ensure_ascii=False)}],
        )
        decision = _extract_json(r5.final_output or "")
        _debug_print("DecisionAgent", decision)

        # 6) Control
        r6 = Runner.run_sync(
            ControlAgent,
            [{"role": "user", "content": json.dumps(decision, ensure_ascii=False)}],
        )
        controlled = _extract_json(r6.final_output or "")
        controlled = _ensure_final_shape(controlled)
        _debug_print("ControlAgent", controlled)

        # Extra safety: server-side policy, falls LLM Mist baut
        suggest = use_case_result.get("suggest_show_frameworks") if isinstance(use_case_result, dict) else None
        if suggest is False and controlled.get("mode") != "agents":
            controlled["mode"] = "agents"
        if suggest is True and controlled.get("mode") != "frameworks":
            controlled["mode"] = "frameworks"

        # 7) Advisor (final JSON)
        r7 = Runner.run_sync(
            AdvisorAgent,
            [{"role": "user", "content": json.dumps(controlled, ensure_ascii=False)}],
        )
        final_obj = _extract_json(r7.final_output or "")
        final_obj = _ensure_final_shape(final_obj)
        _debug_print("Final", final_obj)

        return AgentResponse(answer=json.dumps(final_obj, ensure_ascii=False))

    except Exception as e:
        error_obj = _ensure_final_shape({
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": [],
            "error": str(e),
        })
        return AgentResponse(answer=json.dumps(error_obj, ensure_ascii=False))
