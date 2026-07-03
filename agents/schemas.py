import pydantic


# --- Input Reviewer Model ---
class TopicReviewResult(pydantic.BaseModel):
    is_safe: bool
    is_news_relevant: bool
    suggested_query_formulation: str
    rejection_reason: str | None = None
    input_issue_type: str = "clear_news_query"
    user_message: str = ""
    suggested_options: list[str] = pydantic.Field(default_factory=list)
    auto_modified: bool = False
    needs_user_confirmation: bool = False
    confidence: float = 1.0


# --- Search & Categorizer Models ---
class Article(pydantic.BaseModel):
    title: str
    url: str
    source: str
    published_date: str
    bias_category: str  # "Left", "Center", "Right", "Independent", "Unknown"
    media_scale: str  # "Local", "National", "International"
    media_type: str  # "Mainstream", "Independent"
    summary: str
    full_content_snippet: str
    source_reliability_score: float  # 0.0 to 1.0
    objectivity_score: float  # 0.0 to 1.0
    outlet_group: str = ""
    wire_service: str | None = None
    duplicate_cluster: str = ""
    selection_rationale: str = ""


class ArticleList(pydantic.BaseModel):
    topic: str
    articles: list[Article]
    query_used: str = ""
    corrected_query: str | None = None
    search_status: str = "verified"
    verification_summary: str = ""
    source_balance: dict[str, int] = pydantic.Field(default_factory=dict)
    warnings: list[str] = pydantic.Field(default_factory=list)
    wire_groups: list[str] = pydantic.Field(default_factory=list)


# --- Fact & Consensus Models ---
class EvidenceItem(pydantic.BaseModel):
    source: str
    title: str = ""
    url: str
    published_date: str = ""
    bias_category: str = ""
    quote: str = ""


class FactItem(pydantic.BaseModel):
    claim: str
    supporting_sources: list[str] = pydantic.Field(default_factory=list)
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    explanation: str  # Explains why this claim is considered a fact based on evidence.
    cross_verification_score: float = 0.0


class DisputeItem(pydantic.BaseModel):
    claim: str
    dispute_question: str = ""
    side_a_assertion: str
    side_a_sources: list[str] = pydantic.Field(default_factory=list)
    side_a_evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    side_a_support_level: str = ""
    side_b_assertion: str
    side_b_sources: list[str] = pydantic.Field(default_factory=list)
    side_b_evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    side_b_support_level: str = ""
    evidence_warning: str = ""


class TimelineEvent(pydantic.BaseModel):
    date: str
    event: str
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)


class FactConsensusMap(pydantic.BaseModel):
    consensus_facts: list[FactItem] = pydantic.Field(default_factory=list)
    timeline_events: list[str] = pydantic.Field(default_factory=list)
    timeline: list[TimelineEvent] = pydantic.Field(default_factory=list)


# --- Perspective & Narrative Models ---
class NarrativeProfile(pydantic.BaseModel):
    perspective_group: str  # "Left-Leaning", "Right-Leaning", "Centrist", "Independent"
    core_narrative: str
    key_arguments: list[str]
    common_emotional_triggers: list[str]
    notable_omissions: list[str]  # Facts mentioned elsewhere but ignored by this group
    representative_sources: list[str] = pydantic.Field(default_factory=list)
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    is_speculative: bool = False
    support_status: str = ""
    analytical_inference: str = ""
    unsupported_warning: str = ""


class PerspectiveProfile(pydantic.BaseModel):
    classification_axis: str = ""
    profiles: list[NarrativeProfile]
    key_rhetorical_differences: str
    unsupported_perspectives: list[str] = pydantic.Field(default_factory=list)


# --- Expert Panel Models ---
class ExpertOpinion(pydantic.BaseModel):
    expert_name: str  # The professional title/role of the expert (e.g. "Political & Constitutional Law Analyst") instead of a person's name
    expertise_area: str  # e.g., "Political Science", "Economics", "Media Literacy"
    commentary: str
    recommended_reading_or_context: list[str]  # Recommended reading or background context, formatted as Markdown links ([Description](URL)) or URLs
    cited_references: list[str]  # References/sources cited, formatted as Markdown links ([Title](URL)) or URLs
    supporting_evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)


class ExpertDomainSelection(pydantic.BaseModel):
    domains: list[str]  # 2-3 professional role titles, e.g. "Constitutional Law Specialist"
    selection_rationale: str = ""


class RoundtableSummary(pydantic.BaseModel):
    roundtable_summary: str


class ExpertPanelCommentary(pydantic.BaseModel):
    expert_opinions: list[ExpertOpinion]
    roundtable_summary: str


# --- Public Summary Report Model ---
class ReportTakeaway(pydantic.BaseModel):
    point: str
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)


class PublicReport(pydantic.BaseModel):
    title: str
    lead_paragraph: str
    key_takeaways: list[ReportTakeaway]
    narrative_summary: str
    future_outlook: str


# --- Recruiter Agent Models ---
class RecruitmentResult(pydantic.BaseModel):
    recruit_dispute: bool
    recruit_perspective: bool
    recruit_expert: bool
    recruit_future_outlook: bool
    recruitment_justification: str
    complexity_level: str = "moderate"
    recruited_agents: list[str] = pydantic.Field(default_factory=list)
    skipped_agents: list[str] = pydantic.Field(default_factory=list)


# --- Generic Audit Agent Model ---
class AuditResult(pydantic.BaseModel):
    is_approved: bool
    audit_feedback: list[str] = pydantic.Field(default_factory=list)
    recommended_fixes: list[str] = pydantic.Field(default_factory=list)


# --- Future Outlook Models ---
class ScenarioItem(pydantic.BaseModel):
    scenario_title: str
    description: str
    trigger_conditions: list[str] = pydantic.Field(default_factory=list)
    likelihood_band: str = ""
    supporting_evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    assumptions: list[str] = pydantic.Field(default_factory=list)


class FutureOutlookResult(pydantic.BaseModel):
    most_likely_scenario: ScenarioItem | None = None
    alternative_scenarios: list[ScenarioItem] = pydantic.Field(default_factory=list)
    monitoring_indicators: list[str] = pydantic.Field(default_factory=list)
    confidence_statement: str = ""
    time_horizon: str = ""


# --- Dispute Agent Models ---
class DisputeList(pydantic.BaseModel):
    disputed_claims: list[DisputeItem]


# --- Public Editor Models ---
class PublicEditorOutput(pydantic.BaseModel):
    markdown_report: str
    unresolved_warnings: list[str] = pydantic.Field(default_factory=list)
