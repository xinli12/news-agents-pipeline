"""Audit criteria for each pipeline stage.

Each constant is injected into a stage-specific audit agent that reviews the
worker agent's output and either approves it or requests a bounded revision.
"""

INPUT_AUDIT_CRITERIA = (
    "1. The suggested query formulation must be neutral, objective, and stripped of emotional/loaded language.\n"
    "2. Unsafe inputs must be correctly flagged (is_safe: false).\n"
    "3. If the input is broad, verify that narrowing-down options are provided.\n"
    "4. Ensure no obvious typos or non-news queries are passed through without correction/rejection."
)

SEARCH_AUDIT_CRITERIA = (
    "1. Ideological balance (Left, Right, Center, Independent) is preferred but optional. DO NOT reject if the search query simply returns limited viewpoints or articles.\n"
    "2. Wire service grouping should be checked, but do not reject if grouping is not applicable or minor.\n"
    "3. Verify search_status, verification_summary, warnings, query_used, and corrected_query are populated consistently.\n"
    "4. Crucially: Do not invent articles if unsupported by search. Only reject if the Search Agent invents completely fake articles or fails to return any results for a known topic."
)

RECRUITER_AUDIT_CRITERIA = "1. Verify recruitment decisions: only recruit Dispute, Expert, Perspective, and Future Outlook agents if needed. Keep simple topics non-recruited."

FACT_AUDIT_CRITERIA = (
    "1. Verify factual neutrality: no evaluative adjectives or loaded terms.\n"
    "2. Each consensus fact must have at least two independent sources and a valid, detailed explanation of why it is considered a fact.\n"
    "3. Verify dates and timelines are chronologically consistent and cited accurately with URLs and short quotes.\n"
    "4. Verify the structured timeline includes evidence objects, not only uncited prose."
)

DISPUTE_AUDIT_CRITERIA = (
    "1. Verify schema compliance with DisputeList and DisputeItem, including claim, side assertions, "
    "source lists, and evidence fields.\n"
    "2. Maintain neutral, non-loaded language; do not validate either side or use judgmental wording.\n"
    "3. Verify source traceability: evidence should include source, title when available, quote or snippet, "
    "and URL where available. Do not approve hallucinated quotes, URLs, dates, sources, or claims.\n"
    "4. Reject invented or unsupported counter-sides. If one side is weak, under-supported, or absent in "
    "the source set, the output must explicitly warn about unsupported or weak evidence.\n"
    "5. Check that duplicated wire-service reposts or same-cluster articles are not treated as independent "
    "confirmation when metadata reveals duplication.\n"
    "6. Prefer genuine material conflicts over minor wording differences, and require cautious language when "
    "evidence is incomplete."
)

PERSPECTIVE_AUDIT_CRITERIA = (
    "1. Verify schema compliance with PerspectiveProfile and NarrativeProfile, including profiles, "
    "classification_axis when available, evidence, and key_rhetorical_differences.\n"
    "2. Describe narrative frames objectively, respectfully, and with neutral, non-loaded language; avoid "
    "over-generalizing political, social, national, or stakeholder groups.\n"
    "3. Verify source traceability: reported perspectives should include representative sources, quote or "
    "snippet evidence, and URL where available. Do not approve hallucinated groups, quotes, URLs, sources, "
    "or claims.\n"
    "4. Ensure the selected classification axis fits the article set, such as ideology, stakeholder role, "
    "geopolitical position, industry role, geography, affected group, or media ecosystem.\n"
    "5. Check that evidence-backed reporting is clearly distinguished from analytical inference or likely "
    "concern. Unsupported or theoretically important perspectives must be marked as speculative or "
    "'not enough source support found', not presented as reported news.\n"
    "6. Ensure there is sufficient diversity of sources and perspectives for the topic, or explicit warnings "
    "for missing, weak, or unsupported evidence.\n"
    "7. Ensure notable omissions are logically based on comparisons across source-supported perspectives."
)

EXPERT_AUDIT_CRITERIA = (
    "1. Ensure the expert's commentary stays within their designated professional domain and matches the news topic context.\n"
    "2. Ensure the commentary cites specific external regulations, economic indicators, or ethical codes.\n"
    "3. Maintain academic, non-partisan commentary."
)

OUTLOOK_AUDIT_CRITERIA = (
    "1. Verify scenario divergence: Most-likely vs Alternative Scenarios must represent distinct logical paths.\n"
    "2. Ensure trigger conditions are specific and observable.\n"
    "3. Use probabilistic language instead of false certainty.\n"
    "4. Ensure scenarios cite upstream evidence and state assumptions/time horizon."
)

PUBLIC_REPORTER_AUDIT_CRITERIA = (
    "1. Ensure the public summary only summarizes upstream verified facts, disputes, expert commentary, and scenarios.\n"
    "2. Ensure it does not introduce new factual claims, stronger certainty, or unsupported causal claims.\n"
    "3. Preserve material caveats, unresolved audit warnings, and uncertainty in public-friendly language.\n"
    "4. Every key takeaway must carry an evidence trail (source, URL, quote) copied from upstream outputs."
)

PUBLIC_EDITOR_AUDIT_CRITERIA = (
    "1. Ensure the highly condensed executive summary is at the absolute top of the page.\n"
    "2. Ensure all detailed sections (disputes, narratives, expert opinions, timeline, scenarios) are folded inside HTML '<details>' and '<summary>' tags.\n"
    "3. Verify there are no raw system JSONs, developer-facing debug strings, or internal agent annotations.\n"
    "4. Ensure key claims link to their source articles (markdown links) and the report ends with a Sources section listing the cited URLs."
)
