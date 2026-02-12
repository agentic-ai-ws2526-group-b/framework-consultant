import streamlit as st
import requests
import json
from typing import Any, Dict, List

# =====================================================
# CONFIG
# =====================================================

st.set_page_config(page_title="Berater für KI-Agenten", layout="wide")

DEFAULT_BACKEND = "http://localhost:8000"

PRIORITY_OPTIONS = [
    {"key": "speed", "label": "Schnell & leichtgewichtig ⚡"},
    {"key": "tools", "label": "Viele Integrationen / Tools 🔌"},
    {"key": "memory", "label": "Gute Gedächtnisfunktionen 🧠"},
    {"key": "rag", "label": "Dokumenten-Suche (RAG) 📄"},
    {"key": "privacy", "label": "Datenschutzfreundlich 🔒"},
    {"key": "multi", "label": "Multi-Agent-Fähig 🤖"},
]

# Anzeige-Werte
AGENT_TYPES_DISPLAY = [
    "Chatbot",
    "Daten-Agent",
    "Workflow-Agent",
    "Analyse-Agent",
    "Multi-Agent-System",
    "Ich weiß es nicht",
]

# Mapping Anzeige → Backend-Wert
AGENT_TYPE_MAP = {
    "Chatbot": "Chatbot",
    "Daten-Agent": "Daten-Agent",
    "Workflow-Agent": "Workflow-Agent",
    "Analyse-Agent": "Analyse-Agent",
    "Multi-Agent-System": "Multi-Agent-System",
    "Ich weiß es nicht": "unknown",
}

EXPERIENCE_LEVELS = {
    "beginner": "Anfänger",
    "intermediate": "Fortgeschritten",
    "expert": "Experte",
}

LEARNING_PREFS = {
    "learn": "Etwas dazu lernen",
    "simple": "Einfache Lösung",
}

USE_CASES_PATH = "/use-cases"
AGENT_PATH = "/agent"


# =====================================================
# HELPER
# =====================================================

def pct(score):
    try:
        return max(0, min(100, round(float(score) * 100)))
    except:
        return 0


def api_post(path, payload):
    url = DEFAULT_BACKEND.rstrip("/") + path
    r = requests.post(url, json=payload, timeout=90)

    try:
        data = r.json()
    except:
        raise RuntimeError("Backend liefert kein gültiges JSON.")

    if not r.ok:
        raise RuntimeError(data.get("detail") or data.get("error") or f"HTTP {r.status_code}")

    return data


def parse_frameworks(data):
    if isinstance(data.get("framework_recommendations"), list):
        return data["framework_recommendations"]

    try:
        parsed = json.loads(data.get("answer") or "{}")
        return parsed.get("framework_recommendations", [])
    except:
        return []


def render_usecase_cards(items: List[Dict[str, Any]]):
    cols = st.columns(3)
    for i, uc in enumerate(items[:9]):
        with cols[i % 3]:
            title = uc.get("title", "—")
            summary = uc.get("summary", "")
            score = uc.get("match_percent", pct(uc.get("score")))
            st.markdown(f"### {title}")
            st.caption(summary[:400] + ("…" if len(summary) > 400 else ""))
            st.markdown(
                f"<div style='color:#E20015;font-weight:bold'>{score}% Match</div>",
                unsafe_allow_html=True,
            )


def render_framework_cards(items: List[Dict[str, Any]]):
    cols = st.columns(3)
    for i, fw in enumerate(items[:9]):
        with cols[i % 3]:
            name = fw.get("framework", "—")
            desc = fw.get("description", "")
            score = fw.get("match_percent", pct(fw.get("score")))
            st.markdown(f"### {name}")
            st.caption(desc[:400] + ("…" if len(desc) > 400 else ""))
            st.markdown(
                f"<div style='color:#E20015;font-weight:bold'>{score}% Match</div>",
                unsafe_allow_html=True,
            )


# =====================================================
# STATE
# =====================================================

if "phase" not in st.session_state:
    st.session_state.phase = "form"

if "usecases" not in st.session_state:
    st.session_state.usecases = []

if "frameworks" not in st.session_state:
    st.session_state.frameworks = []

if "last_payload" not in st.session_state:
    st.session_state.last_payload = None


# =====================================================
# HEADER
# =====================================================

st.title("Berater für KI-Agenten")
st.caption("Interaktive Empfehlung von Bosch-Agenten oder technischen Frameworks")

tab_template, tab_chat = st.tabs(["Vorlage", "Chat-Assistent"])


# =====================================================
# TEMPLATE FLOW
# =====================================================

with tab_template:

    if st.session_state.phase == "form":

        st.subheader("Was soll dein Agent tun?")
        agent_display = st.selectbox(
            "Agententyp",
            AGENT_TYPES_DISPLAY,
            index=None,
            placeholder="Bitte auswählen..."
        )

        st.subheader("Was ist dir wichtig?")
        priorities = []
        for opt in PRIORITY_OPTIONS:
            if st.checkbox(opt["label"]):
                priorities.append(opt["key"])

        st.subheader("Wie gut schätzt du dich im Erstellen von Agenten ein?")
        experience = st.selectbox(
            "Erfahrungslevel",
            list(EXPERIENCE_LEVELS.keys()),
            index=None,
            placeholder="Bitte auswählen...",
            format_func=lambda x: EXPERIENCE_LEVELS[x],
        )

        st.subheader("Willst du etwas dazu lernen oder eine einfache Lösung?")
        learning = st.selectbox(
            "Lernpräferenz",
            list(LEARNING_PREFS.keys()),
            index=None,
            placeholder="Bitte auswählen...",
            format_func=lambda x: LEARNING_PREFS[x],
        )

        st.subheader("Erläutere deinen Use-Case")
        use_case = st.text_area("Beschreibe deinen Use Case", height=140)

        if st.button("Vorschläge erhalten →", type="primary"):

            if not agent_display or not experience or not learning or not use_case.strip():
                st.error("Bitte alle Pflichtfelder ausfüllen.")
            else:

                payload = {
                    "agent_type": AGENT_TYPE_MAP[agent_display],
                    "priorities": priorities,
                    "use_case": use_case,
                    "experience_level": experience,
                    "learning_preference": learning,
                }

                st.session_state.last_payload = payload

                try:
                    with st.spinner("Lädt..."):
                        data = api_post(USE_CASES_PATH, payload)
                        usecases = data.get("use_cases", [])
                        suggest_frameworks = data.get("suggest_show_frameworks", True)

                        if usecases and suggest_frameworks is False:
                            st.session_state.usecases = usecases
                            st.session_state.phase = "usecases"
                        else:
                            data_fw = api_post(AGENT_PATH, {**payload, "force_frameworks": True})
                            st.session_state.frameworks = parse_frameworks(data_fw)
                            st.session_state.phase = "frameworks"

                    st.rerun()

                except Exception as e:
                    st.error(str(e))

    elif st.session_state.phase == "usecases":

        st.subheader("Passende Bosch-Agenten / Use Cases")
        render_usecase_cards(st.session_state.usecases)

        if st.button("Passt nicht – Frameworks anzeigen"):
            payload = st.session_state.last_payload
            with st.spinner("Lädt Frameworks..."):
                data_fw = api_post(AGENT_PATH, {**payload, "force_frameworks": True})
                st.session_state.frameworks = parse_frameworks(data_fw)
                st.session_state.phase = "frameworks"
            st.rerun()

    elif st.session_state.phase == "frameworks":

        st.subheader("Framework-Empfehlungen")
        render_framework_cards(st.session_state.frameworks)


# =====================================================
# CHAT (unverändert vereinfacht)
# =====================================================

with tab_chat:

    st.markdown("## Interaktiver Assistent")

    # =====================================================
    # STATE INITIALISIERUNG
    # =====================================================

    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 0

    if "wizard_data" not in st.session_state:
        st.session_state.wizard_data = {
            "agent_type": None,
            "priorities": [],
            "experience_level": None,
            "learning_preference": None,
            "use_case": ""
        }

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "show_usecases" not in st.session_state:
        st.session_state.show_usecases = False

    if "show_frameworks" not in st.session_state:
        st.session_state.show_frameworks = False

    data = st.session_state.wizard_data
    step = st.session_state.wizard_step


    # =====================================================
    # STEP 1 – AGENT
    # =====================================================

    st.markdown("### 1️⃣ Was soll dein Agent tun?")

    agent_options = [
        "Chatbot",
        "Daten-Agent",
        "Workflow-Agent",
        "Analyse-Agent",
        "Multi-Agent-System",
        "Ich weiß es nicht"
    ]

    selected_agent = st.radio(
        "Agententyp auswählen",
        agent_options,
        index=None,
        key="wizard_agent"
    )

    if selected_agent:
        data["agent_type"] = "unknown" if selected_agent == "Ich weiß es nicht" else selected_agent

    if st.button("Weiter", key="next1"):
        if not data["agent_type"]:
            st.error("Bitte Agententyp auswählen.")
        else:
            st.session_state.wizard_step = 1
            st.rerun()


    # =====================================================
    # STEP 2 – PRIORITÄTEN
    # =====================================================

    if step >= 1:

        st.markdown("### 2️⃣ Was ist dir wichtig?")

        prios = []
        for opt in PRIORITY_OPTIONS:
            if st.checkbox(opt["label"], key=f"prio_{opt['key']}"):
                prios.append(opt["key"])

        data["priorities"] = prios

        if st.button("Weiter", key="next2"):
            st.session_state.wizard_step = 2
            st.rerun()


    # =====================================================
    # STEP 3 – ERFAHRUNG
    # =====================================================

    if step >= 2:

        st.markdown("### 3️⃣ Erfahrungslevel")

        exp = st.radio(
            "Erfahrungslevel",
            list(EXPERIENCE_LEVELS.values()),
            index=None,
            key="wizard_exp"
        )

        if exp:
            for k, v in EXPERIENCE_LEVELS.items():
                if v == exp:
                    data["experience_level"] = k

        if st.button("Weiter", key="next3"):
            if not data["experience_level"]:
                st.error("Bitte Erfahrungslevel auswählen.")
            else:
                st.session_state.wizard_step = 3
                st.rerun()


    # =====================================================
    # STEP 4 – LERNPRÄFERENZ
    # =====================================================

    if step >= 3:

        st.markdown("### 4️⃣ Lernpräferenz")

        learn = st.radio(
            "Lernpräferenz",
            list(LEARNING_PREFS.values()),
            index=None,
            key="wizard_learn"
        )

        if learn:
            for k, v in LEARNING_PREFS.items():
                if v == learn:
                    data["learning_preference"] = k

        if st.button("Weiter", key="next4"):
            if not data["learning_preference"]:
                st.error("Bitte Lernpräferenz auswählen.")
            else:
                st.session_state.wizard_step = 4
                st.rerun()


    # =====================================================
    # STEP 5 – USE CASE
    # =====================================================

    if step >= 4:

        st.markdown("### 5️⃣ Beschreibe deinen Use Case")

        data["use_case"] = st.text_area(
            "Use Case",
            value=data["use_case"]
        )

        if st.button("Vorschläge erhalten →"):

            if not all([
                data["agent_type"],
                data["experience_level"],
                data["learning_preference"],
                data["use_case"].strip()
            ]):
                st.error("Bitte alle Pflichtfelder ausfüllen.")
            else:
                try:
                    result = api_post("/use-cases", data)
                    usecases = result.get("use_cases", [])
                    suggest_frameworks = result.get("suggest_show_frameworks", True)

                    if usecases and suggest_frameworks is False:
                        st.session_state.usecase_results = usecases
                        st.session_state.show_usecases = True
                        st.session_state.show_frameworks = False
                    else:
                        fw = api_post("/agent", {**data, "force_frameworks": True})
                        parsed = json.loads(fw["answer"])
                        st.session_state.framework_results = parsed.get("framework_recommendations", [])
                        st.session_state.show_frameworks = True
                        st.session_state.show_usecases = False

                    st.rerun()

                except Exception as e:
                    st.error(str(e))


    # =====================================================
    # USE CASE ERGEBNISSE
    # =====================================================

    if st.session_state.get("show_usecases"):

        st.markdown("## Passende Bosch-Agenten")

        render_usecase_cards(st.session_state.get("usecase_results", []))

        if st.button("Passt nicht – Frameworks anzeigen"):

            try:
                fw = api_post("/agent", {**data, "force_frameworks": True})
                parsed = json.loads(fw["answer"])

                st.session_state.framework_results = parsed.get("framework_recommendations", [])
                st.session_state.show_frameworks = True
                st.session_state.show_usecases = False

                st.rerun()

            except Exception as e:
                st.error(str(e))


    # =====================================================
    # FRAMEWORK ERGEBNISSE
    # =====================================================

    if st.session_state.get("show_frameworks"):

        st.markdown("## Framework-Empfehlungen")

        frameworks = st.session_state.get("framework_results", [])

        if frameworks:
            render_framework_cards(frameworks)
        else:
            st.warning("Keine Framework-Empfehlungen gefunden.")


    # =====================================================
    # GLOBALER CHAT (LLM)
    # =====================================================

    st.divider()
    st.markdown("## Fragen stellen")

    chat_input = st.text_input("Stelle eine Frage")

    if st.button("Frage senden"):
        if chat_input:
            st.session_state.chat_history.append(("Du", chat_input))

            response = api_post("/agent", {
                "chat_question": chat_input
            })

            st.session_state.chat_history.append(("Assistent", response["answer"]))
            st.rerun()

    for role, msg in st.session_state.chat_history:
        st.markdown(f"**{role}:** {msg}")
