from agents import Agent

def build_usecase_analyzer_agent(search_bosch_use_cases_tool) -> Agent:
    return Agent(
        name="UseCaseAnalyzer",
        instructions=(
            "Du bist der Use-Case Analyzer.\n"
            "Nutze search_bosch_use_cases, um passende Bosch Use Cases zu finden.\n"
            "Gib NUR JSON zurück:\n"
            "{\n"
            '  "use_cases": [{"title":"...","summary":"...","score":0.0,"metadata":{}}],\n'
            '  "suggest_show_frameworks": boolean,\n'
            '  "reason": "string"\n'
            "}\n"
            "Regel: suggest_show_frameworks=true, wenn es keine Use Cases gibt oder der beste Score < 0.35."
        ),
        tools=[search_bosch_use_cases_tool],
    )
