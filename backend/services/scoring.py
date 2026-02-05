# services/scoring.py
from typing import Any, Dict, List, Optional, Tuple

DIMS = ["D1", "D2", "D3", "D4", "D5", "D6"]

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

def avg_weights(priorities: List[str]) -> Dict[str, float]:
    if not priorities:
        return {d: 1.0 for d in DIMS}
    vecs = [PRIORITY_WEIGHTS_BY_KEY.get(p, {d: 1.0 for d in DIMS}) for p in priorities]
    out = {d: 0.0 for d in DIMS}
    for v in vecs:
        for d in DIMS:
            out[d] += float(v.get(d, 1.0))
    n = float(len(vecs))
    return {d: out[d] / n for d in DIMS}

def get_agent_mult(agent_type: str) -> Dict[str, float]:
    return AGENT_TYPE_MULTIPLIERS.get(agent_type, {d: 1.0 for d in DIMS})

def get_skill_mult(skill_level: Optional[str]) -> Dict[str, float]:
    if not skill_level:
        return {d: 1.0 for d in DIMS}
    return SKILL_MULTIPLIERS.get(skill_level, {d: 1.0 for d in DIMS})

def score_dims(
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

def load_framework_factsheets(framework_collection) -> List[Dict[str, Any]]:
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
        desc = docs[i] if i < len(docs) and isinstance(docs[i], str) else ""
        out.append({"framework": fw, "dims": dims, "factsheet_text": desc, "url": meta.get("url")})

    dedup: Dict[str, Dict[str, Any]] = {}
    for item in out:
        dedup[item["framework"]] = item
    return list(dedup.values())

def rank_all_frameworks(req, framework_collection) -> List[Dict[str, Any]]:
    facts = load_framework_factsheets(framework_collection)
    if not facts:
        return []

    weights = avg_weights(req.priorities or [])
    a_mult = get_agent_mult(req.agent_type or "unknown")
    s_mult = get_skill_mult(req.experience_level)

    scored: List[Tuple[Dict[str, Any], float, Dict[str, float]]] = []
    for fw in facts:
        total, per_dim = score_dims(fw["dims"], weights, a_mult, s_mult)
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
