import os
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agents import Runner

from services.utils import debug_print, extract_json, ensure_final_shape
from services.chroma_client import get_chroma_client, get_collections
from services.tools import build_tool_functions, query_bosch_use_cases
from services.scoring_peer import score_frameworks

from app_agents.requirements_agent import build_requirements_agent
from app_agents.profiler_agent import build_profiler_agent
from app_agents.usecase_analyzer_agent import build_usecase_analyzer_agent
from app_agents.decision_agent import build_decision_agent
from app_agents.control_agent import build_control_agent
from app_agents.advisor_agent import build_advisor_agent
from app_agents.framework_analyzer_agent import build_framework_analyzer_agent

# ✅ neu
try:
    from app_agents.scoring_agent import build_scoring_agent, run_scoring, scoring_agent_user_message
except Exception:
    build_scoring_agent = None
    run_scoring = None
    scoring_agent_user_message = None


# -----------------------------------------
# ENV
# -----------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in .env")


# -----------------------------------------
# Chroma
# -----------------------------------------
chroma_client = get_chroma_client()
usecase_collection, framework_collection = get_collections(chroma_client)

search_bosch_use_cases_tool, search_framework_docs_tool = build_tool_functions(
    usecase_collection=usecase_collection,
    framework_collection=framework_collection,
)


# -----------------------------------------
# FastAPI
# -----------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------
# Models
# -----------------------------------------
class AgentRequest(BaseModel):
    agent_type: Optional[str] = None
    priorities: List[str] = Field(default_factory=list)
    use_case: Optional[str] = None
    experience_level: Optional[str] = None
    learning_preference: Optional[str] = None
    force_frameworks: Optional[bool] = False
    chat_question: Optional[str] = None


class AgentResponse(BaseModel):
    answer: str


# -----------------------------------------
# Helpers
# -----------------------------------------
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


def _normalize_top_to_100(items: List[Dict[str, Any]], score_key: str = "score", pct_key: str = "match_percent") -> None:
    if not items:
        return
    items.sort(key=lambda x: float(x.get(score_key, 0.0)), reverse=True)
    mx = float(items[0].get(score_key, 0.0))
    if mx <= 0:
        for it in items:
            it[pct_key] = 0
        return
    for it in items:
        s = float(it.get(score_key, 0.0))
        it[pct_key] = int(round((s / mx) * 100))


def _best_percent(framework_recs: List[Dict[str, Any]]) -> int:
    if not framework_recs:
        return 0
    return max(int(x.get("match_percent", 0)) for x in framework_recs)


def _snippets_empty(framework_context: List[Dict[str, Any]]) -> bool:
    if not framework_context:
        return True
    for item in framework_context:
        sn = item.get("snippets") or []
        if len(sn) > 0:
            return False
    return True


# -----------------------------------------
# Agents (constructed)
# -----------------------------------------
RequirementsAgent = build_requirements_agent()
ProfilerAgent = build_profiler_agent()
UseCaseAnalyzerAgent = build_usecase_analyzer_agent(search_bosch_use_cases_tool)
DecisionAgent = build_decision_agent()
ControlAgent = build_control_agent()
AdvisorAgent = build_advisor_agent()
FrameworkAnalyzerAgent = build_framework_analyzer_agent(framework_collection)

# ✅ neu: ScoringAgent als echter Runner-Step (wenn verfügbar)
ScoringAgent = build_scoring_agent() if build_scoring_agent else None


# -----------------------------------------
# Scoring via Runner (Agent) mit Fallback
# -----------------------------------------
def _score_via_runner(req: AgentRequest) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Gibt zurück: (top3_recs, full_ranked)
    top3_recs enthält framework, score, match_percent
    """
    payload = {
        "agent_type": req.agent_type or "unknown",
        "priorities": req.priorities or [],
        "use_case_text": req.use_case or "",
        "experience_level": req.experience_level,
        "learning_preference": req.learning_preference,
    }

    # 1) Runner ScoringAgent (diagramm-konform)
    if ScoringAgent and scoring_agent_user_message:
        try:
            rS = Runner.run_sync(
                ScoringAgent,
                [{"role": "user", "content": scoring_agent_user_message(payload)}],
            )
            parsed = extract_json(rS.final_output or "")
            top3 = parsed.get("framework_recommendations", []) or []
            full_ranked = parsed.get("framework_candidates", []) or []
            return top3, full_ranked
        except Exception as e:
            debug_print("ScoringAgent Runner failed, fallback to score_frameworks()", str(e))

    # 2) Fallback: deine scoring_peer.py direkt
    ranked_simple = score_frameworks(
        agent_type=payload["agent_type"],
        priorities=payload["priorities"],
        use_case_text=payload["use_case_text"],
        skill_level=payload["experience_level"],
    )
    top3_simple = ranked_simple[:3] if ranked_simple else []
    top3 = []
    for fw in top3_simple:
        s = float(fw.get("score", 0.0))
        top3.append({
            "framework": fw.get("framework"),
            "score": s,
            "match_percent": int(round(s * 100)),
        })
    return top3, ranked_simple or []


# -----------------------------------------
# Loop orchestrator (FrameworkAnalyzer ↔ Scoring ↔ Control-ish)
# -----------------------------------------
def _framework_loop(req: AgentRequest) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Loop max 2 Iterationen:
    - holt Scores
    - holt Framework Kontext (Snippets/Factsheet)
    - wenn Kontext leer ODER best_score < threshold -> mehr Snippets und nochmal
    Returns: (top3_scored, full_ranked, framework_context)
    """
    threshold = 60
    n_results = 3

    top3_scored: List[Dict[str, Any]] = []
    full_ranked: List[Dict[str, Any]] = []
    framework_context: List[Dict[str, Any]] = []

    for attempt in range(2):
        top3_scored, full_ranked = _score_via_runner(req)

        fw_names = [x.get("framework") for x in top3_scored if x.get("framework")]
        fw_ctx_obj = FrameworkAnalyzerAgent.run({
            "frameworks": fw_names,
            "use_case_text": req.use_case,
            "n_results": n_results,
        })
        framework_context = (fw_ctx_obj or {}).get("framework_context", []) or []

        best = _best_percent(top3_scored)
        empty = _snippets_empty(framework_context)

        debug_print("FrameworkLoop", {
            "attempt": attempt + 1,
            "n_results": n_results,
            "best_match_percent": best,
            "snippets_empty": empty,
        })

        if (not empty) and (best >= threshold):
            break

        # sonst: Kontext erweitern und nochmal
        n_results = min(8, n_results + 3)

    return top3_scored, full_ranked, framework_context


# -----------------------------------------
# Endpoints
# -----------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/use-cases")
def use_cases(req: AgentRequest):
    try:
        if not req.agent_type or not (req.use_case and req.use_case.strip()):
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
        _normalize_top_to_100(top, score_key="score", pct_key="match_percent")

        return {
            "use_cases": top,
            "suggest_show_frameworks": False if top else True,
            "best_score": top[0]["score"] if top else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    try:
        debug_print("Request /agent", req.dict())

        # CHAT immer erlaubt
        if req.chat_question and req.chat_question.strip():
            r_chat = Runner.run_sync(
                AdvisorAgent,
                [{"role": "user", "content": req.chat_question.strip()}],
            )
            return AgentResponse(answer=r_chat.final_output or "")

        # Empfehlungen brauchen Pflichtfelder
        if not req.agent_type or not (req.use_case and req.use_case.strip()):
            raise HTTPException(status_code=400, detail="agent_type und use_case erforderlich für Empfehlungen")

        # 1) Requirements
        r1 = Runner.run_sync(
            RequirementsAgent,
            [{"role": "user", "content": json.dumps(req.dict(), ensure_ascii=False)}],
        )
        requirements = extract_json(r1.final_output or "")
        debug_print("RequirementsAgent", requirements)

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
        debug_print("ProfilerAgent", profiler)

        # 3) UseCaseAnalyzer (Routing)
        query = requirements.get("requirements_summary") or build_query(req)
        r3 = Runner.run_sync(UseCaseAnalyzerAgent, [{"role": "user", "content": query}])
        use_case_result = extract_json(r3.final_output or "")
        debug_print("UseCaseAnalyzer", use_case_result)

        suggest = use_case_result.get("suggest_show_frameworks") if isinstance(use_case_result, dict) else True
        want_frameworks = bool(req.force_frameworks) or bool(suggest)

        if want_frameworks:
            # 4+5) Loop: FrameworkAnalyzer ↔ ScoringAgent
            top3_scored, full_ranked, framework_context = _framework_loop(req)

            # Map scoring per name
            score_by_name: Dict[str, Dict[str, Any]] = {
                str(x.get("framework")): x for x in top3_scored if x.get("framework")
            }

            # Decision input (kompatibel)
            frameworks_for_llm: List[Dict[str, Any]] = []
            for item in framework_context:
                name = item.get("framework")
                if not name:
                    continue
                sc = score_by_name.get(str(name), {})
                frameworks_for_llm.append({
                    "framework": name,
                    "snippets": item.get("snippets", []),
                    "factsheet": item.get("factsheet"),
                    "score": sc.get("score"),
                    "match_percent": sc.get("match_percent"),
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
                for t in decision_texts["framework_texts"]:
                    if isinstance(t, dict) and t.get("framework"):
                        texts_by_name[str(t["framework"])] = t

            framework_recs: List[Dict[str, Any]] = []
            for fw in top3_scored:
                name = fw.get("framework")
                if not name:
                    continue
                t = texts_by_name.get(str(name), {})
                s = float(fw.get("score", 0.0))
                framework_recs.append({
                    "framework": name,
                    "score": s,
                    "match_percent": int(fw.get("match_percent", int(round(s * 100)))),
                    "description": t.get("description", ""),
                    "match_reason": t.get("match_reason", ""),
                    "pros": t.get("pros", []),
                    "cons": t.get("cons", []),
                    "recommendation": t.get("recommendation", ""),
                })

            final_obj = {
                "mode": "frameworks",
                "agent_recommendations": [],
                "framework_recommendations": framework_recs,
                "framework_ranked_full": full_ranked,
            }

        else:
            # Use cases path
            use_cases_list = []
            if isinstance(use_case_result, dict) and isinstance(use_case_result.get("use_cases"), list):
                use_cases_list = use_case_result["use_cases"]

            agent_recs = []
            for uc in use_cases_list[:3]:
                if isinstance(uc, dict):
                    agent_recs.append({
                        "title": uc.get("title", "Bosch Use Case"),
                        "summary": uc.get("summary", ""),
                        "score": float(uc.get("score", 0.0)),
                        "match_percent": uc.get("match_percent"),
                        "metadata": uc.get("metadata", {}),
                    })

            final_obj = {
                "mode": "agents",
                "agent_recommendations": agent_recs,
                "framework_recommendations": [],
            }

        # Control
        r5 = Runner.run_sync(
            ControlAgent,
            [{"role": "user", "content": json.dumps(final_obj, ensure_ascii=False)}],
        )
        controlled = extract_json(r5.final_output or "")
        controlled = ensure_final_shape(controlled)
        debug_print("ControlAgent", controlled)

        # Advisor
        r6 = Runner.run_sync(
            AdvisorAgent,
            [{"role": "user", "content": json.dumps(controlled, ensure_ascii=False)}],
        )
        out = extract_json(r6.final_output or "")
        out = ensure_final_shape(out)
        debug_print("Final", out)

        return AgentResponse(answer=json.dumps(out, ensure_ascii=False))

    except HTTPException:
        raise
    except Exception as e:
        error_obj = ensure_final_shape({
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": [],
            "error": str(e),
        })
        return AgentResponse(answer=json.dumps(error_obj, ensure_ascii=False))
