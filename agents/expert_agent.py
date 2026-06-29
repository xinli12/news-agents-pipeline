import os

from google.adk.agents import Agent

from agents.schemas import ExpertPanelCommentary


def get_expert_agent(
    expert_domains: list[str] | None = None, model_name: str | None = None
) -> Agent:
    if expert_domains:
        domains_str = "\n".join(
            f"{idx}. {domain}" for idx, domain in enumerate(expert_domains, 1)
        )
        domain_instruction = (
            f"The recruited expert perspectives for this topic are:\n{domains_str}\n\n"
        )
        name_instruction = "Must be exactly the role title listed above."
    else:
        domain_instruction = (
            "First, analyze the news topic and consensus/disputes, and dynamically identify 2-3 most "
            "appropriate academic/professional expert domains needed to analyze this topic (e.g., Public Health "
            "Specialist, Constitutional Law Specialist, Macroeconomic Policy Analyst, AI Researcher).\n\n"
        )
        name_instruction = "Must be the professional title/role of the expert you identified (e.g. 'Public Health Specialist')."

    instruction = (
        "You are an Expert Roundtable Agent. Your job is to host a panel debate/discussion with "
        "academic/professional perspectives commenting on the news topic and its media coverage, anchoring their opinions "
        "in the provided reference materials or professional standards. DO NOT use personal names for these experts; "
        "refer to them solely by their professional roles.\n\n"
        f"{domain_instruction}"
        "Guidelines:\n"
        "1. For each expert role, write a professional commentary from their specific domain perspective.\n"
        "2. Anchored Materials: Where possible, anchor opinions in the provided Constitutional/Regulatory framework, "
        "Economic Data Indicators, or Media Literacy & Ethics standards. If the expert domain is outside these three "
        "(e.g., Artificial Intelligence Specialist, Public Health Expert), use general scientific, industry, or professional "
        "ethical standards relevant to that field.\n"
        "3. Tone: Ensure the tone is highly scholarly, analytical, and non-partisan.\n\n"
        "For each expert perspective, you must provide:\n"
        f"- expert_name: {name_instruction}\n"
        "- expertise_area: The general area of expertise (e.g., 'Political Science', 'Economics', 'Medicine', 'Computer Science').\n"
        "- commentary: A deep, 3-4 sentence analytical critique, highly grounded in specific indices, rules, or standards.\n"
        "- cited_references: A list of specific rules, laws, concepts, or indicators cited from the reference materials."
    )

    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="expert_agent",
        model=model_name,
        instruction=instruction,
        output_schema=ExpertPanelCommentary,
        output_key="expert_data",
    )
