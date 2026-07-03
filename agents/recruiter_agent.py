
from google.adk.agents import Agent

from agents.config import resolve_model
from agents.schemas import RecruitmentResult


def get_recruiter_agent(model_name: str | None = None) -> Agent:
    model_name = resolve_model(model_name)
    return Agent(
        name="recruiter_agent",
        model=model_name,
        instruction=(
            "You are the Recruiter Agent. Your job is to analyze the gathered news articles and "
            "determine which specialized analysis modules (Dispute Agent, Expert Agent, Perspective Agent, "
            "and Future Outlook Agent) should be recruited for this news topic, balancing the depth "
            "of analysis with computational cost.\n\n"
            "Recruitment Criteria:\n"
            "1. Dispute Agent (recruit_dispute): Set to true only if there are direct contradictions, "
            "factual disagreements, or opposing stances in the articles (e.g. Side A vs Side B). "
            "Do not recruit for non-controversial or straightforward reporting.\n"
            "2. Perspective Agent (recruit_perspective): Set to true if different political, regional, "
            "commercial, or interest groups frame the event differently.\n"
            "3. Expert Agent (recruit_expert): Set to true if the topic requires deep domain-specific "
            "expert commentary (e.g. Constitutional Law, Macroeconomics, Media Ethics, Artificial Intelligence, "
            "Public Health) to understand.\n"
            "4. Future Outlook Agent (recruit_future_outlook): Set to true if the news topic is an ongoing "
            "event with a high likelihood of future developments, policy decisions, or market shifts.\n"
            "5. Cost-Control Rule: For simple, low-complexity, or non-controversial news (e.g., celebrity gossip, "
            "sports scores, minor entertainment, direct announcements), set ALL recruitment flags to false.\n"
            "6. Populate complexity_level as 'low', 'moderate', or 'high'. Populate recruited_agents and "
            "skipped_agents with the exact module names and briefly explain the cost/depth tradeoff in "
            "recruitment_justification.\n"
            "NOTE: Do not decide what specific expert domains or perspective classification axes are needed; "
            "the specialized agents will determine their focus dynamically."
        ),
        output_schema=RecruitmentResult,
        output_key="recruitment_result",
    )
