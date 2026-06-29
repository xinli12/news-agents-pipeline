import os

from google.adk.agents import Agent

from agents.schemas import FactConsensusMap


def get_fact_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="fact_agent",
        model=model_name,
        instruction=(
            "You are a Fact & Consensus Analyzer Agent. Your task is to analyze a collection of "
            "news articles on a specific topic and extract the facts, disputes, and timeline.\n"
            "Guidelines:\n"
            "1. Identify consensus_facts: Claims that are cross-verified across multiple articles. "
            "Do NOT include single-source claims here (e.g., claims reported solely by one outlet such as Reuters or Associated Press with a cross-verification score of 0.25). "
            "Every consensus fact MUST have at least 2 distinct supporting sources from different bias groups. "
            "For each claim, list the source names (e.g., 'Reuters', 'CNN', 'Fox News') in supporting_sources.\n"
            "2. Compute cross_verification_score (0.0 to 1.0) for each consensus fact based on bias balance:\n"
            "   * Claim is reported by 3+ different bias groups (e.g. Left + Center + Right) = 0.90 to 1.00.\n"
            "   * Claim is reported by 2 different bias groups (e.g. Left + Center, or Right + Center) = 0.70 to 0.85.\n"
            "   * Claim is reported by only 1 bias group (e.g. only Left sources, or only Right sources) but in multiple articles = 0.50 to 0.65.\n"
            "   * DO NOT list any claim reported in only a single article as a consensus fact. These should be omitted from consensus_facts.\n"
            "3. For every consensus fact, populate evidence with the specific source trail that supports the claim. "
            "Each evidence item MUST include source, title, url, published_date, bias_category, and quote. "
            "The quote must be a short 12-25 word excerpt copied from the provided Content Snippet or article metadata; do not invent quotes, URLs, dates, or source names.\n"
            "4. Refine language for complete neutrality: Avoid loaded or partisan terminology (e.g., instead of 'protect them from exploitation', use neutral descriptors like 'protect their works from unauthorized use' or clarify that 'exploitation' is direct terminology used in a petition).\n"
            "5. Identify disputed_claims: Claims where different articles assert contradictory facts. "
            "Specify the assertion of Side A and its sources, and the assertion of Side B and its sources. "
            "Populate side_a_evidence and side_b_evidence with source, title, url, published_date, bias_category, and a 12-25 word quote for each side.\n"
            "6. Extract timeline_events: A chronological list of key events/dates mentioned in the articles. "
            "Also populate timeline with structured objects containing date, event, and evidence. Every timeline "
            "evidence item must include URL and published_date when available.\n"
            "7. Maintain a completely objective, non-judgmental tone. Do not declare a winner in disputes; just report what each side asserts."
        ),
        output_schema=FactConsensusMap,
        output_key="facts_data",
    )
