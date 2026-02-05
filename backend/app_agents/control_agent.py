from agents import Agent

def build_control_agent() -> Agent:
    return Agent(
        name="ControlAgent",
        instructions=(
            "Du bist der Kontrollagent.\n"
            "Prüfe, ob die Antwort valides JSON ist und erwartete Felder existieren.\n"
            "Wenn etwas fehlt oder ungültig ist, korrigiere minimal.\n"
            "Antwort NUR als JSON."
        ),
    )
