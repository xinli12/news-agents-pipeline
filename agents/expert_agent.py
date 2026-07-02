import os
import re

from google.adk.agents import Agent

from agents.schemas import ExpertDomainSelection, ExpertOpinion, RoundtableSummary


def _resolve_model(model_name: str | None) -> str:
    if model_name is None:
        return os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return model_name


def domain_slug(domain: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return slug[:40] or "expert"


def get_expert_domain_selector(model_name: str | None = None) -> Agent:
    return Agent(
        name="expert_domain_selector",
        model=_resolve_model(model_name),
        instruction=(
            "You are the Expert Panel Recruiter. Analyze the news topic, its consensus facts, and its "
            "disputes, and select the 2-3 most appropriate academic/professional expert domains needed to "
            "analyze this topic in depth.\n"
            "Guidelines:\n"
            "1. Each domain must be a concrete professional role title (e.g. 'Constitutional Law Specialist', "
            "'Macroeconomic Policy Analyst', 'Public Health Specialist', 'AI Governance Researcher').\n"
            "2. Pick domains that cover distinct, complementary angles of the story; avoid overlapping roles.\n"
            "3. Briefly justify the selection in selection_rationale."
        ),
        output_schema=ExpertDomainSelection,
        output_key="expert_domains_data",
    )


def search_authoritative_data(query: str) -> str:
    """Searches the web for authoritative academic papers, official regulatory standards, economic data, or industry guidelines.

    Args:
        query: The search query, e.g., 'CPI inflation rate US 2024' or 'FDA pharmaceutical trial regulations'.
    """
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return f"No authoritative sources found for query: {query}"
            output = []
            for r in results:
                title = r.get("title", "N/A")
                url = r.get("href", "") or r.get("url", "")
                body = r.get("body", "N/A")
                output.append(f"Title: {title}\nURL: {url}\nSnippet: {body}\n---")
            return "\n".join(output)
    except Exception as e:
        return f"Error executing DuckDuckGo search: {e!s}"


def get_domain_expert_agent(domain: str, model_name: str | None = None) -> Agent:
    return Agent(
        name=f"expert_{domain_slug(domain)}",
        model=_resolve_model(model_name),
        instruction=(
            f"You are an expert commentator with the professional role: '{domain}'. You are participating in "
            "a roundtable analyzing a news topic and its media coverage. Write ONE professional commentary "
            "strictly from your domain's perspective. DO NOT use a personal name; you are identified solely by "
            "your professional role.\n\n"
            "Guidelines:\n"
            "1. Web Search & Citations: You MUST use your `search_authoritative_data` tool to search for real external "
            "sources (e.g. regulatory codes, official statistics, academic studies, industry standards) to back up your commentary. "
            "Locate and cite real, verifiable information with URLs.\n"
            "2. Tone: Highly scholarly, analytical, and non-partisan.\n\n"
            "You must provide:\n"
            f"- expert_name: Exactly '{domain}'.\n"
            "- expertise_area: The general area of expertise (e.g., 'Political Science', 'Economics').\n"
            "- commentary: A deep, 3-4 sentence analytical critique grounded in specific indices, rules, or standards. "
            "Reference key findings or data points retrieved via your search tool.\n"
            "- cited_references: A list of specific sources, regulations, or studies you cited. Format each reference "
            "as a clickable Markdown link (e.g. `[Title or Source Name](URL)`) using the URLs retrieved via search.\n"
            "- recommended_reading_or_context: A list of 1-3 recommended external readings (reports, data dashboards, or briefs) "
            "relevant to your commentary, formatted as clickable Markdown links (e.g. `[Description](URL)`) using URLs retrieved via search.\n"
            "- supporting_evidence: Reuse 1-3 exact EvidenceItem objects from the upstream Consensus, Disputes, "
            "or Media Narratives. Do not invent URLs, dates, source names, or quotes. If no upstream evidence "
            "supports a point, explicitly narrow the commentary instead of adding an unsupported claim."
        ),
        tools=[search_authoritative_data],
        output_schema=ExpertOpinion,
        output_key="expert_opinion_data",
    )


def get_roundtable_summarizer(model_name: str | None = None) -> Agent:
    return Agent(
        name="roundtable_summarizer",
        model=_resolve_model(model_name),
        instruction=(
            "You are the Expert Roundtable Moderator. You are given the individual commentaries of a panel of "
            "domain experts on a news topic. Write a concise roundtable_summary (3-5 sentences) that synthesizes "
            "where the expert perspectives converge, where they diverge, and what the combined analysis implies. "
            "Do not introduce any new factual claims, evidence, or opinions beyond what the experts stated. "
            "Keep the tone scholarly and non-partisan."
        ),
        output_schema=RoundtableSummary,
        output_key="roundtable_summary_data",
    )
