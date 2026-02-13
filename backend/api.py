import os
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agents import Runner

from services.utils import debug_print, extract_json, ensure_final_shape
from services.chroma_client import get_chroma_client, get_collections
from services.tools import build_tool_functions, query_bosch_use_cases, get_framework_snippets_for_framework
from services.scoring_peer import score_frameworks

from app_agents.requirements_agent import build_requirements_agent
from app_agents.profiler_agent import build_profiler_agent
from app_agents.usecase_analyzer_agent import build_usecase_analyzer_agent
from app_agents.decision_agent import build_decision_agent
from app_agents.control_agent import build_control_agent
from app_agents.advisor_agent import build_advisor_agent


# =========================================
# ENV
# =========================================

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in .env")


# =========================================
# CHROMA
# =========================================

chroma_client = get_chroma_client()
usecase_collection, framework_collection = get_collections(chroma_client)

search_bosch_use_cases_tool, search_framework_docs_tool = build_tool_functions(
    usecase_collection=usecase_collection,
    framework_collection=framework_collection,
)


# =========================================
# FASTAPI
# =========================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================
# MODELS
# =========================================

class AgentRequest(BaseModel):
    agent_type: Optional[str] = None
    priorities: List[str] = Field(default_factory=list)
    use_case: Optional[str] = None
    experience_level: Optional[str] = None
    learning_preference: Optional[str] = None
    force_frameworks: Optional[bool] = False

    # 🔥 Chat ist komplett unabhängig
    chat_question: Optional[str] = None


class AgentResponse(BaseModel):
    answer: str


# =========================================
# HELPERS
# =========================================

def build_query(req: AgentRequest) -> str:
    return (
        f"Use Case: {req.use_case or ''}\n"
        f"Agententyp: {req.agent_type or 'unknown'}\n"
        f"Prioritäten: {', '.join(req.priorities) if req.priorities else 'keine'}\n"
        f"Experience Level: {req.experience_level or 'unknown'}\n"
        f"Learning Preference: {req.learning_preference or 'unknown'}"
    )


def _match01(a: str, b: str) -> float:
    return 1.0 if (a or "").strip().lower() == (b or "").strip().lower() else 0.0


def _tag_match(priorities: List[str], meta_tags_csv: str) -> float:
    pr = set((priorities or []))
    tags = set(t.strip().lower() for t in (meta_tags_csv or "").split(",") if t.strip())
    if not pr or not tags:
        return 0.0
    return len(pr.intersection(tags)) / max(1, len(pr))


# =========================================
# AGENTS
# =========================================

RequirementsAgent = build_requirements_agent()
ProfilerAgent = build_profiler_agent()
UseCaseAnalyzerAgent = build_usecase_analyzer_agent(search_bosch_use_cases_tool)
DecisionAgent = build_decision_agent()
ControlAgent = build_control_agent()
AdvisorAgent = build_advisor_agent()


# =========================================
# ENDPOINTS
# =========================================

@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------------------
# USE CASES
# -----------------------------------------

@app.post("/use-cases")
def use_cases(req: AgentRequest):
    try:
        if not req.agent_type or not req.use_case:
            raise HTTPException(status_code=400, detail="agent_type und use_case erforderlich")

        query = build_query(req)

        res = query_bosch_use_cases(usecase_collection, query=query, n_results=15)
        use_cases_list = res.get("use_cases", []) or []

        scored = []
        for uc in use_cases_list:
            meta = uc.get("metadata", {}) or {}
            sim = float(uc.get("score") or 0.0)

            exp_m = _match01(req.experience_level, meta.get("experience_level"))
            learn_m = _match01(req.learning_preference, meta.get("learning_preference"))
            tag_m = _tag_match(req.priorities or [], meta.get("tags", ""))

            final = 0.80 * sim + 0.10 * exp_m + 0.10 * learn_m + 0.05 * tag_m
            final = max(0.0, min(1.0, final))

            scored.append({**uc, "score": final})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:3]

        # 🔥 Relative Normalisierung → bester = 100%
        if top:
            max_score = top[0]["score"]
            if max_score > 0:
                for uc in top:
                    normalized = uc["score"] / max_score
                    uc["match_percent"] = int(round(normalized * 100))
            else:
                for uc in top:
                    uc["match_percent"] = 0

        return {
            "use_cases": top,
            "suggest_show_frameworks": False if top else True,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------
# AGENT (Framework + Chat)
# -----------------------------------------

@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):

    try:
        debug_print("Request /agent", req.dict())

        # =====================================================
        # CHAT MODE (funktioniert IMMER)
        # =====================================================

        if req.chat_question and req.chat_question.strip():
            r_chat = Runner.run_sync(
                AdvisorAgent,
                [{"role": "user", "content": req.chat_question.strip()}],
            )
            return AgentResponse(answer=r_chat.final_output or "")

        # =====================================================
        # EMPFEHLUNGSMODUS
        # =====================================================

        if not req.agent_type or not req.use_case:
            raise HTTPException(
                status_code=400,
                detail="agent_type und use_case erforderlich für Empfehlung"
            )

        # 1) Requirements
        r1 = Runner.run_sync(
            RequirementsAgent,
            [{"role": "user", "content": json.dumps(req.dict(), ensure_ascii=False)}],
        )
        requirements = extract_json(r1.final_output or "")

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
        profiler = extract_json(r2.final_output or "")

        # 3) Deterministic ranking (DEIN scoring_peer bleibt unverändert)
        ranked_simple = score_frameworks(
            agent_type=req.agent_type,
            priorities=req.priorities or [],
            use_case_text=req.use_case,
            skill_level=req.experience_level,
        )

        top3 = ranked_simple[:3] if ranked_simple else []

        # --------------------------------------------
        # Framework-Kontext für DecisionAgent bauen
        # --------------------------------------------

        frameworks_for_llm: List[Dict[str, Any]] = []

        for fw in top3:
            name = fw["framework"]

            snippets = get_framework_snippets_for_framework(
                framework_collection,
                name,
                req.use_case,
                n_results=2,
            )

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
            "frameworks": frameworks_for_llm,
        }

        r4 = Runner.run_sync(
            DecisionAgent,
            [{"role": "user", "content": json.dumps(decision_payload, ensure_ascii=False)}],
        )

        decision_texts = extract_json(r4.final_output or "")
        debug_print("DecisionAgent(Texts)", decision_texts)

        texts_by_name: Dict[str, Dict[str, Any]] = {}

        if isinstance(decision_texts, dict) and isinstance(decision_texts.get("framework_texts"), list):
            for item in decision_texts["framework_texts"]:
                if isinstance(item, dict) and item.get("framework"):
                    texts_by_name[str(item["framework"])] = item

        # --------------------------------------------
        # Final Framework-Recommendations bauen
        # --------------------------------------------

        framework_recs: List[Dict[str, Any]] = []

        for fw in top3:
            name = fw["framework"]
            t = texts_by_name.get(name, {})
            s = float(fw.get("score", 0.0))

            framework_recs.append({
                "framework": name,
                "score": s,  # bleibt dein normierter Score (0..1)
                "match_percent": int(round(s * 100)),  # → bleibt korrekt
                "description": t.get("description", ""),
                "match_reason": t.get("match_reason", ""),
                "pros": t.get("pros", []),
                "cons": t.get("cons", []),
                "recommendation": t.get("recommendation", ""),
                "url": fw.get("url"),
            })

        final_obj = {
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": framework_recs,
        }

        return AgentResponse(answer=json.dumps(final_obj, ensure_ascii=False))

    except Exception as e:
        error_obj = {
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": [],
            "error": str(e),
        }
        return AgentResponse(answer=json.dumps(error_obj, ensure_ascii=False))

