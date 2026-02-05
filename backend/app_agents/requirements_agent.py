from agents import Agent

def build_requirements_agent() -> Agent:
    return Agent(
        name="RequirementsAgent",
        instructions=(
            "Du bist der Anforderungsagent. "
            "Du bekommst Nutzereingaben (agent_type, priorities, use_case, experience_level, learning_preference). "
            "Gib ein JSON zurück mit:\n"
            "{\n"
            '  "requirements_summary": "string",\n'
            '  "agent_role": "string",\n'
            '  "tasks": ["string", ...]\n'
            "}\n"
            "Antwort NUR als JSON."
        ),
    )
