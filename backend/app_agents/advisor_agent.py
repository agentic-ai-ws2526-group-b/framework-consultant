from agents import Agent

def build_advisor_agent() -> Agent:
    return Agent(
        name="AdvisorAgent",
        instructions=(
            "Du bist der Berater-Agent.\n"
            "Du erhältst das validierte JSON.\n"
            "Gib es 1:1 als JSON zurück (keine Umformatierung, kein Extra-Text).\n"
            "Antwort NUR als JSON."
        ),
    )
