# services/utils.py
import json
import re
from typing import Any, Dict

def debug_print(title: str, payload: Any) -> None:
    print(f">>> {title}: {payload}")

def extract_json(text: str) -> Dict[str, Any]:
    """Robust: extrahiert JSON aus Modell-Output."""
    if not text:
        return {}
    t = text.strip()

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

    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    return {}

def ensure_final_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    obj = obj or {}
    if obj.get("mode") not in ("agents", "frameworks"):
        obj["mode"] = "frameworks"
    obj.setdefault("agent_recommendations", [])
    obj.setdefault("framework_recommendations", [])
    return obj
