import os

from google.adk.agents import Agent

from agents.schemas import DisputeList


def get_dispute_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="dispute_agent",
        model=model_name,
        instruction=(
            "You are the Dispute Agent. Your job is to analyze the news articles and extract active "
            "controversies or contested claims where different sources present conflicting assertions.\n\n"
            "Guidelines:\n"
            "1. Identify disputed claims: Points where different articles assert contradictory facts.\n"
            "2. For each dispute, fill out Side A and Side B assertions, including the sources supporting each side.\n"
            "3. Ground each assertion in evidence: Populate side_a_evidence and side_b_evidence with source, "
            "title, url, published_date, bias_category, and a short verbatim quote (12-25 words) from the articles.\n"
            "4. Symmetrical, Neutral Language: Present both sides with equal depth, avoiding taking a side "
            "or using biased adjectives (e.g. use 'claims' or 'asserts' instead of 'falsely claims' or 'reveals the truth')."
        ),
        output_schema=DisputeList,
        output_key="disputes_data",
    )
