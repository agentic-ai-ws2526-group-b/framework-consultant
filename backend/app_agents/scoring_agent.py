# backend/app_agents/scoring_agent.py
import json
from typing import Any, Dict, List, Optional

from agents import Agent  # falls dein Agents-SDK das so exportiert
from services.scoring_peer import score_frameworks


SCORING_SYSTEM = """
Du bist der ScoringAgent.
Du berechnest deterministisch Framework-Scores über die interne Funktion score_frameworks().
Du gibst IMMER valides JSON zurück mit den Keys:
- framework_candidates: Liste aller Frameworks mit score (0..1)
- framework_recommendations: Top-3 mit framework, score, match_percent
- meta: optional (z.B. threshold info)
Kein Fließtext außerhalb von JSON.
"""


def build_scoring_agent() -> Agent:
    return Agent(
        name="ScoringAgent",
        instructions=SCORING_SYSTEM,
        model="gpt-4.1-mini",  # wird kaum genutzt, da wir deterministisch arbeiten
    )


def run_scoring(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministische Scoring-Funktion. Kann auch ohne Runner verwendet werden.
    """
    agent_type = payload.get("agent_type") or "unknown"
    priorities = payload.get("priorities") or []
    use_case_text = payload.get("use_case_text") or ""
    skill_level = payload.get("experience_level")

    ranked = score_frameworks(
        agent_type=agent_type,
        priorities=priorities,
        use_case_text=use_case_text,
        skill_level=skill_level,
    )

    top3 = ranked[:3] if ranked else []
    recs: List[Dict[str, Any]] = []
    for fw in top3:
        s = float(fw.get("score", 0.0))
        recs.append({
            "framework": fw.get("framework"),
            "score": s,
            "match_percent": int(round(s * 100)),
        })

    return {
        "framework_candidates": ranked,
        "framework_recommendations": recs,
        "meta": {
            "source": "services.scoring_peer.score_frameworks"
        }
    }


def scoring_agent_user_message(payload: Dict[str, Any]) -> str:
    """
    Payload wird als user content an Runner gesendet.
    Der Agent selbst soll nur JSON zurückgeben.
    """
    out = run_scoring(payload)
    return json.dumps(out, ensure_ascii=False)
