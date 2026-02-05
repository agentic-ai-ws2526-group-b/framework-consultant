from agents import Agent

def build_profiler_agent() -> Agent:
    return Agent(
        name="ProfilerAgent",
        instructions=(
            "Du bist der Profiler-Agent. "
            "Du erhältst requirements_summary + user attributes. "
            "Gib ein JSON zurück mit:\n"
            "{\n"
            '  "persona_name": "string",\n'
            '  "communication_style": "string",\n'
            '  "tone_guidelines": ["string", ...]\n'
            "}\n"
            "Antwort NUR als JSON."
        ),
    )
