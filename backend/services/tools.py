# services/tools.py
from typing import Any, Dict, List, Optional
from agents.tool import function_tool
import chromadb

DIMS = ["D1", "D2", "D3", "D4", "D5", "D6"]

def distance_to_score(distance: Optional[float]) -> Optional[float]:
    if distance is None:
        return None
    try:
        d = float(distance)
        s = 1.0 / (1.0 + d)
        return max(0.0, min(1.0, s))
    except Exception:
        return None

def query_bosch_use_cases(usecase_collection, query: str, n_results: int = 3) -> Dict[str, Any]:
    results = usecase_collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],  # explizit, robuster
    )
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    out: List[Dict[str, Any]] = []
    for i in range(len(docs)):
        meta = metas[i] if metas and i < len(metas) else {}
        dist = float(dists[i]) if dists and i < len(dists) and dists[i] is not None else None
        uc_id = ids[i] if ids and i < len(ids) else None

        out.append(
            {
                "id": uc_id,  # ✅ NEU: damit wir später documents/metas gezielt nachladen können
                "title": (meta.get("title") if isinstance(meta, dict) else None) or (meta.get("agent_name") if isinstance(meta, dict) else None) or "Bosch Use Case",
                "summary": docs[i],
                "distance": dist,
                "score": distance_to_score(dist),
                "metadata": meta if isinstance(meta, dict) else {},
            }
        )
    return {"use_cases": out}


def query_framework_docs(framework_collection, query: str, n_results: int = 3) -> Dict[str, Any]:
    results = framework_collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    out: List[Dict[str, Any]] = []
    for i in range(len(docs)):
        out.append({"text": docs[i], "meta": metas[i] if metas and i < len(metas) else {}})
    return {"docs": out}

def get_framework_snippets_for_framework(
    framework_collection,
    framework_name: str,
    query_text: str,
    n_results: int = 3,
) -> List[Dict[str, Any]]:
    """
    Queryt Chroma nach den relevantesten Chunks für ein bestimmtes Framework.
    Filtert Factsheets raus, weil die separat geholt werden.
    """
    try:
        res = framework_collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"framework": framework_name, "is_factsheet": False},
            include=["documents", "metadatas", "distances"],
        )

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        out = []
        for i in range(min(len(docs), len(metas), len(dists))):
            out.append({
                "text": docs[i],
                "metadata": metas[i],
                "distance": float(dists[i]),
            })
        return out
    except Exception:
        return []

def build_tool_functions(usecase_collection, framework_collection):
    @function_tool
    def search_bosch_use_cases(query: str, n_results: int = 3) -> Dict[str, Any]:
        return query_bosch_use_cases(usecase_collection, query=query, n_results=n_results)

    @function_tool
    def search_framework_docs(query: str, n_results: int = 3) -> Dict[str, Any]:
        return query_framework_docs(framework_collection, query=query, n_results=n_results)

    return search_bosch_use_cases, search_framework_docs
