import json
from typing import Any, Dict, List, Optional

from agents import Runner

from services.tools import get_framework_snippets_for_framework


def build_framework_analyzer_agent(framework_collection):
    """
    Framework Analyzer Agent (Diagramm-konform):
    - nimmt Anforderungen + use_case_text entgegen
    - holt pro Framework relevante Snippets aus Chroma
    - holt zusätzlich Factsheet (D1..D6) falls vorhanden
    - gibt strukturiertes JSON zurück: framework_context[]
    """

    class _FrameworkAnalyzer:
        name = "FrameworkAnalyzerAgent"

        def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            # Erwartete Felder
            frameworks: List[str] = payload.get("frameworks") or []
            use_case_text: str = payload.get("use_case_text") or ""
            n_results: int = int(payload.get("n_results", 3))

            framework_context: List[Dict[str, Any]] = []

            for fw in frameworks:
                snippets = get_framework_snippets_for_framework(
                    framework_collection=framework_collection,
                    framework_name=fw,
                    query_text=use_case_text,
                    n_results=n_results,
                )

                # Factsheet zusätzlich (falls du es willst)
                facts = _get_factsheet(framework_collection, fw)

                framework_context.append({
                    "framework": fw,
                    "factsheet": facts,      # kann None sein
                    "snippets": snippets or [],
                })

            return {
                "framework_context": framework_context
            }

    return _FrameworkAnalyzer()


def _get_factsheet(framework_collection, framework_name: str) -> Optional[Dict[str, Any]]:
    """
    Sucht das Factsheet-Dokument (is_factsheet=True) für ein Framework.
    """
    try:
        res = framework_collection.get(
            where={"framework": framework_name, "is_factsheet": True},
            include=["documents", "metadatas"],
            limit=1,
        )
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        if not docs or not metas:
            return None

        meta = metas[0] if isinstance(metas[0], dict) else {}
        return {
            "text": docs[0],
            "metadata": meta,
        }
    except Exception:
        return None
