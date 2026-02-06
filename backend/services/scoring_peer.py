# services/scoring_peer.py
from __future__ import annotations
from typing import Dict, List, Any, Optional

ALLOWED_FRAMEWORKS = {
    "Google ADK",
    "LangChain",
    "LangGraph",
    "OpenAI Agents SDK",
    "Claude Agent SDK",
    "Cognigy",
    "n8n",
    "CrewAI",
}

# IMPORTANT: enforce allowlist here
FRAMEWORKS = sorted(ALLOWED_FRAMEWORKS)

CAP: Dict[str, Dict[str, float]] = {
    "LangChain": {
        "rag": 0.95, "tools": 0.85, "workflow": 0.55, "multi_agent": 0.55,
        "enterprise": 0.70, "low_code": 0.20, "ecosystem": 0.95, "observability": 0.65,
        "privacy_onprem": 0.60, "ease_beginner": 0.75,
    },
    "LangGraph": {
        "rag": 0.75, "tools": 0.80, "workflow": 0.75, "multi_agent": 0.90,
        "enterprise": 0.70, "low_code": 0.15, "ecosystem": 0.70, "observability": 0.70,
        "privacy_onprem": 0.65, "ease_beginner": 0.40,
    },
    "Google ADK": {
        "rag": 0.60, "tools": 0.75, "workflow": 0.70, "multi_agent": 0.65,
        "enterprise": 0.80, "low_code": 0.25, "ecosystem": 0.65, "observability": 0.75,
        "privacy_onprem": 0.70, "ease_beginner": 0.65,
    },
    "n8n": {
        "rag": 0.30, "tools": 0.65, "workflow": 0.95, "multi_agent": 0.25,
        "enterprise": 0.70, "low_code": 0.90, "ecosystem": 0.70, "observability": 0.55,
        "privacy_onprem": 0.75, "ease_beginner": 0.80,
    },
    "CrewAI": {
        "rag": 0.50, "tools": 0.65, "workflow": 0.55, "multi_agent": 0.85,
        "enterprise": 0.55, "low_code": 0.15, "ecosystem": 0.55, "observability": 0.50,
        "privacy_onprem": 0.55, "ease_beginner": 0.45,
    },

    # TODO: Diese 3 musst du noch mit echten Werten befüllen,
    # sonst ranken sie praktisch "leer" oder werden rausgefiltert.
    "OpenAI Agents SDK": {
        "rag": 0.60, "tools": 0.75, "workflow": 0.70, "multi_agent": 0.75,
        "enterprise": 0.70, "low_code": 0.10, "ecosystem": 0.70, "observability": 0.60,
        "privacy_onprem": 0.45, "ease_beginner": 0.65,
    },
    "Claude Agent SDK": {
        "rag": 0.60, "tools": 0.70, "workflow": 0.60, "multi_agent": 0.65,
        "enterprise": 0.65, "low_code": 0.10, "ecosystem": 0.60, "observability": 0.55,
        "privacy_onprem": 0.50, "ease_beginner": 0.65,
    },
    "Cognigy": {
        "rag": 0.45, "tools": 0.85, "workflow": 0.75, "multi_agent": 0.35,
        "enterprise": 0.85, "low_code": 0.85, "ecosystem": 0.70, "observability": 0.75,
        "privacy_onprem": 0.60, "ease_beginner": 0.80,
    },
}

WEIGHTS: Dict[str, Dict[str, float]] = {
    "agent_type:chat_support": {"enterprise": 0.20, "low_code": 0.15, "tools": 0.15, "ease_beginner": 0.20, "observability": 0.10},
    "agent_type:data_document": {"rag": 0.35, "tools": 0.15, "observability": 0.10, "enterprise": 0.10},
    "agent_type:workflow": {"workflow": 0.40, "low_code": 0.20, "tools": 0.10, "enterprise": 0.10},
    "agent_type:research_analysis": {"tools": 0.20, "ecosystem": 0.20, "observability": 0.10, "multi_agent": 0.10},
    "agent_type:multi_agent": {"multi_agent": 0.45, "workflow": 0.10, "tools": 0.10, "observability": 0.10},

    "derived:rag_required": {"rag": 0.35, "tools": 0.10},
    "derived:automation_high": {"workflow": 0.30, "low_code": 0.15},
    "derived:multi_agent": {"multi_agent": 0.25},

    "skill:beginner": {"ease_beginner": 0.25, "low_code": 0.10},
    "skill:expert": {"multi_agent": 0.10, "workflow": 0.10, "observability": 0.10},

    "prio:Integration": {"workflow": 0.15, "tools": 0.10, "ecosystem": 0.10},
    "prio:RAG": {"rag": 0.20},
    "prio:Multi-Agent": {"multi_agent": 0.20},
    "prio:Datenschutz": {"privacy_onprem": 0.20, "enterprise": 0.10},
    "prio:Speed": {"low_code": 0.10, "workflow": 0.10, "tools": 0.05},
    "prio:Memory": {"rag": 0.10, "observability": 0.05},
}

def _dot(cap: Dict[str, float], w: Dict[str, float]) -> float:
    return sum(cap.get(k, 0.0) * v for k, v in w.items())

def map_agent_type_to_bucket(agent_type: str) -> str:
    t = (agent_type or "").strip().lower()
    if t in ("chatbot", "chat"):
        return "chat_support"
    if "workflow" in t:
        return "workflow"
    if "multi" in t:
        return "multi_agent"
    if "analyse" in t or "analysis" in t:
        return "research_analysis"
    if "daten" in t or "data" in t:
        return "data_document"
    return "chat_support"

def derive_flags(use_case_text: str, priorities: List[str], agent_type_bucket: str) -> Dict[str, bool]:
    text = (use_case_text or "").lower()
    pr = set(priorities or [])

    rag_required = ("rag" in pr) or any(k in text for k in ["dokument", "docs", "knowledge", "wiki", "sharepoint", "retrieval", "suche", "search"])
    automation_high = ("tools" in pr) or any(k in text for k in ["workflow", "automatis", "integration", "n8n"])
    multi_agent = ("multi" in pr) or (agent_type_bucket == "multi_agent") or any(k in text for k in ["multi-agent", "multi agent", "orchestr", "crew"])

    return {"rag_required": rag_required, "automation_high": automation_high, "multi_agent": multi_agent}

def score_frameworks(
    agent_type: str,
    priorities: List[str],
    use_case_text: str,
    skill_level: Optional[str],
) -> List[Dict[str, Any]]:
    agent_bucket = map_agent_type_to_bucket(agent_type)
    derived = derive_flags(use_case_text, priorities or [], agent_bucket)

    active: List[Dict[str, float]] = []
    active.append(WEIGHTS.get(f"agent_type:{agent_bucket}", {}))

    if derived.get("rag_required"):
        active.append(WEIGHTS["derived:rag_required"])
    if derived.get("automation_high"):
        active.append(WEIGHTS["derived:automation_high"])
    if derived.get("multi_agent"):
        active.append(WEIGHTS["derived:multi_agent"])

    s = (skill_level or "").lower()
    if s == "beginner":
        active.append(WEIGHTS["skill:beginner"])
    elif s == "expert":
        active.append(WEIGHTS["skill:expert"])

    # de-duplicate priorities
    for p in set(priorities or []):
        if p == "tools":
            active.append(WEIGHTS["prio:Integration"])
        elif p == "rag":
            active.append(WEIGHTS["prio:RAG"])
        elif p == "multi":
            active.append(WEIGHTS["prio:Multi-Agent"])
        elif p == "privacy":
            active.append(WEIGHTS["prio:Datenschutz"])
        elif p == "speed":
            active.append(WEIGHTS["prio:Speed"])
        elif p == "memory":
            active.append(WEIGHTS["prio:Memory"])

    raw_scores: Dict[str, float] = {}
    for fw in FRAMEWORKS:
        cap = CAP.get(fw)
        if not cap:
            # wenn du willst: continue oder neutral defaults
            continue
        total = 0.0
        for w in active:
            total += _dot(cap, w)
        total += 0.05  # baseline
        raw_scores[fw] = total

    mx = max(raw_scores.values()) if raw_scores else 1.0

    results: List[Dict[str, Any]] = []
    for name, val in raw_scores.items():
        norm = max(0.0, min(1.0, val / mx))
        results.append({"framework": name, "score": norm})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
