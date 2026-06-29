import os

from google.adk.agents import Agent

from agents.schemas import FutureOutlookResult


def get_outlook_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="outlook_agent",
        model=model_name,
        instruction=(
            "You are the Future Outlook Agent. Your job is to project potential future development "
            "scenarios for this news event based on historical precedents, policy implications, and "
            "the consensus/disputed facts gathered.\n\n"
            "Guidelines:\n"
            "1. Outline the 'most_likely_scenario' with a detailed explanation of why it has the highest "
            "probability, citing key facts as justification.\n"
            "2. Define 1-2 'alternative_scenarios' that are logically divergent from the most likely one, "
            "including the specific trigger conditions (e.g. policy changes, election results, economic shift) "
            "that could lead to those scenarios.\n"
            "For each alternative scenario, populate likelihood_band using cautious language such as "
            "'lower probability', 'plausible if triggers occur', or 'high uncertainty'.\n"
            "3. Provide a list of 'monitoring_indicators'—concrete signs or metrics that users should watch "
            "to determine which scenario is unfolding.\n"
            "4. Populate confidence_statement with a concise caveat about evidence limits and uncertainty.\n"
            "5. Maintain a professional, analytical tone and avoid absolute statements of certainty; use "
            "probabilistic language."
        ),
        output_schema=FutureOutlookResult,
        output_key="outlook_data",
    )
