
from google.adk.agents import Agent

from agents.config import resolve_model
from agents.schemas import FutureOutlookResult


def get_outlook_agent(model_name: str | None = None) -> Agent:
    model_name = resolve_model(model_name)
    return Agent(
        name="outlook_agent",
        model=model_name,
        instruction=(
            "You are the Future Outlook Agent. Your job is to project potential future development "
            "scenarios for this news event based on historical precedents, policy implications, and "
            "the consensus/disputed facts gathered.\n\n"
            "Guidelines:\n"
            "1. Populate 'most_likely_scenario' as a full structured scenario: scenario_title, a detailed "
            "description explaining why it has the highest probability, trigger_conditions, likelihood_band "
            "(e.g. 'most likely'), assumptions, and supporting_evidence containing exact EvidenceItem objects "
            "copied from upstream facts/disputes/narratives; do not invent evidence.\n"
            "2. Define 1-2 'alternative_scenarios' that are logically divergent from the most likely one, "
            "including the specific trigger conditions (e.g. policy changes, election results, economic shift) "
            "that could lead to those scenarios.\n"
            "For each alternative scenario, populate likelihood_band using cautious language such as "
            "'lower probability', 'plausible if triggers occur', or 'high uncertainty'. Also populate "
            "supporting_evidence with exact upstream EvidenceItem objects and assumptions with explicit "
            "uncertainties or dependencies.\n"
            "3. Provide a list of 'monitoring_indicators'—concrete signs or metrics that users should watch "
            "to determine which scenario is unfolding.\n"
            "4. Populate time_horizon with the forecast window and confidence_statement with a concise caveat "
            "about evidence limits and uncertainty.\n"
            "5. Maintain a professional, analytical tone and avoid absolute statements of certainty; use "
            "probabilistic language."
        ),
        output_schema=FutureOutlookResult,
        output_key="outlook_data",
    )
