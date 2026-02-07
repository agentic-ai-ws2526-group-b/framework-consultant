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
    agent_type: str
    priorities: List[str] = Field(default_factory=list)
    use_case: str
    experience_level: Optional[str] = None
    learning_preference: Optional[str] = None
    force_frameworks: Optional[bool] = False


class AgentResponse(BaseModel):
    answer: str


# -----------------------------------------
# Helpers
# -----------------------------------------
def build_query(req: AgentRequest) -> str:
    return (
        f"Use Case: {req.use_case}\n"
        f"Agententyp: {req.agent_type}\n"
        f"Prioritäten: {', '.join(req.priorities) if req.priorities else 'keine'}\n"
        f"Experience Level: {req.experience_level or 'unknown'}\n"
        f"Learning Preference: {req.learning_preference or 'unknown'}"
    )


# -----------------------------------------
# Agents (constructed)
# -----------------------------------------
RequirementsAgent = build_requirements_agent()
ProfilerAgent = build_profiler_agent()
UseCaseAnalyzerAgent = build_usecase_analyzer_agent(search_bosch_use_cases_tool)
DecisionAgent = build_decision_agent()
ControlAgent = build_control_agent()
AdvisorAgent = build_advisor_agent()


# -----------------------------------------
# Endpoints
# -----------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


def _match01(a: str, b: str) -> float:
    return 1.0 if (a or "").strip().lower() == (b or "").strip().lower() else 0.0

def _tag_match(priorities: List[str], meta_tags_csv: str) -> float:
    pr = set((priorities or []))
    tags = set(t.strip().lower() for t in (meta_tags_csv or "").split(",") if t.strip())
    if not pr or not tags:
        return 0.0
    # priorities keys: rag/tools/multi/privacy/speed/memory
    return len(pr.intersection(tags)) / max(1, len(pr))

@app.post("/use-cases")
def use_cases(req: AgentRequest):
    try:
        query = build_query(req)

        # Mehr Kandidaten holen -> stabileres Top3 nach Boosting
        res = query_bosch_use_cases(usecase_collection, query=query, n_results=15)
        use_cases_list = res.get("use_cases", []) or []

        scored = []
        for uc in use_cases_list:
            meta = uc.get("metadata", {}) or {}
            sim = float(uc.get("score") or 0.0)  # 0..1 aus distance_to_score

            exp_m = _match01(req.experience_level, meta.get("experience_level"))
            learn_m = _match01(req.learning_preference, meta.get("learning_preference"))
            tag_m = _tag_match(req.priorities or [], meta.get("tags", ""))

            # Weighted blend (Similarity dominiert)
            final = 0.80 * sim + 0.10 * exp_m + 0.10 * learn_m + 0.05 * tag_m
            final = max(0.0, min(1.0, final))

            scored.append({**uc, "score": final, "match_percent": int(round(final * 100))})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:3]
        best = top[0]["score"] if top else None

        # ✅ UI-Logik: wenn wir Use Cases haben, sollen sie angezeigt werden
        # -> suggest_show_frameworks MUSS dann false sein
        suggest_show_frameworks = False if top else True

        return {
            "use_cases": top,
            "suggest_show_frameworks": suggest_show_frameworks,
            "best_score": best,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





@app.post("/agent", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    try:
        debug_print("Request /agent", req.dict())

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

        # 3) UseCaseAnalyzer
        query = requirements.get("requirements_summary") or build_query(req)
        r3 = Runner.run_sync(UseCaseAnalyzerAgent, [{"role": "user", "content": query}])
        use_case_result = extract_json(r3.final_output or "")
        debug_print("UseCaseAnalyzer", use_case_result)

        suggest = use_case_result.get("suggest_show_frameworks") if isinstance(use_case_result, dict) else True
        want_frameworks = bool(req.force_frameworks) or bool(suggest)

        # 4) Deterministic framework ranking (matrix)
        ranked_simple = score_frameworks(
            agent_type=req.agent_type,
            priorities=req.priorities or [],
            use_case_text=req.use_case,
            skill_level=req.experience_level,
        )

        # top3 frameworks
        top3 = ranked_simple[:3] if ranked_simple else []


        if want_frameworks:
            frameworks_for_llm: List[Dict[str, Any]] = []
            for fw in top3:
                name = fw["framework"]
                snippets = get_framework_snippets_for_framework(framework_collection, name, req.use_case, n_results=2)
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

            framework_recs: List[Dict[str, Any]] = []
            for fw in top3:
                name = fw["framework"]
                t = texts_by_name.get(name, {})
                framework_recs.append({
                    "framework": name,
                    "score": float(fw["score"]),  # 0..1
                    "description": t.get("description", ""),
                    "match_reason": t.get("match_reason", ""),
                    "pros": t.get("pros", []),
                    "cons": t.get("cons", []),
                    "recommendation": t.get("recommendation", ""),
                    "match_percent": int(round(float(fw["score"]) * 100)),
                    "url": None,  # optional: kannst du weiterhin aus Chroma-Factsheet meta ziehen, wenn du willst
                })


            final_obj = {
                "mode": "frameworks",
                "agent_recommendations": [],
                "framework_recommendations": framework_recs,
            }
        else:
            use_cases_list = []
            if isinstance(use_case_result, dict) and isinstance(use_case_result.get("use_cases"), list):
                use_cases_list = use_case_result["use_cases"]

            agent_recs = []
            for uc in use_cases_list[:3]:
                if isinstance(uc, dict):
                    agent_recs.append({
                        "title": uc.get("title", "Bosch Use Case"),
                        "summary": uc.get("summary", ""),
                        "score": uc.get("score", 0.0),
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

    except Exception as e:
        error_obj = ensure_final_shape({
            "mode": "frameworks",
            "agent_recommendations": [],
            "framework_recommendations": [],
            "error": str(e),
        })
        return AgentResponse(answer=json.dumps(error_obj, ensure_ascii=False))
