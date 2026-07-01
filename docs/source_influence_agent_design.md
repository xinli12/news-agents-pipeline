# Source Influence Agent Design

## Purpose

The Source Influence Agent is an optional NewsLens agent that maps evidence-backed information about media outlets behind a news topic. It helps users understand visible ownership, funding, government affiliation, source bias, reliability, objectivity, and coverage trends across the articles already gathered by the Search Agent.

Recommended product names:

- Source Influence Agent
- Ownership & Influence Mapping Agent

Avoid names such as "Deep Mining Agent" because they imply covert investigation or speculation. The agent should present transparent, public, cited relationships rather than claims about hidden backers or undisclosed influence.

## Product Scope

The agent answers questions such as:

- Which outlets appeared in the current article set?
- What public ownership or affiliation information is available for those outlets?
- Are any outlets publicly owned, nonprofit, state-funded, government-operated, privately owned, or part of a larger media group?
- How do reliability and objectivity scores compare across ownership types?
- Are coverage patterns or narrative frames clustered by outlet type, bias category, geography, or source group?
- Which influence relationships are directly verified, cautiously inferred from public records, or unknown?

The output should support media literacy and source transparency. It should not label outlets as coordinated, captured, paid off, or secretly controlled unless a cited public source directly supports the exact relationship.

## Claim Boundaries

The agent can claim:

- A relationship is `verified` when supported by explicit public evidence, such as an outlet's about page, annual report, corporate filing, regulator record, Wikidata statement with source references, or reputable secondary source.
- A relationship is `inferred` only when the inference is narrow, mechanical, and clearly explained, such as deriving a parent company from a public SEC filing or matching an outlet domain to an already verified parent entity.
- A relationship is `unknown` when evidence is unavailable, conflicting, too weak, or not checked.
- A trend appears in the analyzed source set when it is derived from the provided articles or from a named optional dataset such as GDELT.
- A narrative alignment exists when multiple outlets use similar framing, source selection, or issue emphasis in the analyzed evidence.

The agent cannot claim:

- Hidden financial support, covert sponsorship, intelligence affiliation, political control, or coordinated editorial direction without direct public evidence.
- That ownership alone proves bias, unreliability, propaganda, or editorial intent.
- That shared language across outlets proves coordination when wire-service reuse, common facts, press releases, or normal news cycles could explain the overlap.
- That absence of public ownership data implies concealment.
- That a government affiliation is improper, covert, or editorially determinative unless cited evidence says so.

Every material relationship and trend should include evidence URLs, confidence scores, and a status of `verified`, `inferred`, or `unknown`.

## Pipeline Fit

This should be an optional downstream agent, recruited only when the topic benefits from source transparency. It should run after Search Agent enrichment because the first input should be the existing `articles_data` structure.

Suggested optional output key:

```text
source_influence_data
```

Suggested inputs:

- `topic`
- `articles_data`
- Optional `bias_data` from Perspective Agent for narrative comparison
- Optional external lookup results, if enabled

Suggested output:

- `SourceInfluenceMap`, audited by a dedicated Influence Audit Agent

This design does not require immediate changes to `app.py`, `agents/`, `schemas.py`, or tests.

## Data Source Strategy

### 1. Reuse Existing `articles_data` First

The MVP should start from the articles already selected by Search Agent:

- `source`
- `url`
- `title`
- `published_date`
- `bias_category`
- `media_scale`
- `media_type`
- `source_reliability_score`
- `objectivity_score`
- `outlet_group`
- `wire_service`
- `duplicate_cluster`
- `summary`
- `full_content_snippet`

This keeps the feature cheap, deterministic, and aligned with the current pipeline. The agent can aggregate by source name or normalized domain, then compute first-pass outlet profiles, article counts, reliability/objectivity averages, and coverage patterns.

### 2. Optional Wikidata Lookup

Wikidata can enrich outlet profiles with public entity metadata:

- Parent organization
- Owner
- Operator
- Country
- Inception date
- Official website
- Political alignment claims, only when explicitly sourced and treated cautiously

Use Wikidata as a starting point, not as final truth. Preserve statement references when available. Mark unsourced or weakly sourced values as `inferred` or `unknown`, not `verified`.

### 3. Optional SEC EDGAR Lookup

SEC EDGAR can enrich profiles for US public companies and listed parent companies:

- Parent company legal name
- Ticker and CIK
- Public-company status
- Relevant filing URLs
- Segment or subsidiary references, when explicitly present

The agent should not infer editorial influence from public-company ownership. It can say that a parent company is publicly traded when supported by filings.

### 4. Optional GDELT Lookup

GDELT can support wider trend analysis when the current article set is too narrow:

- Topic volume over time
- Outlet or country coverage frequency
- Tone or theme changes
- Cross-outlet narrative timing

GDELT-derived trends should be labeled as external trend analysis and separated from trends observed only in `articles_data`.

## Proposed Pydantic Schemas

These schemas are proposals for a later implementation. They intentionally separate outlet metadata, evidence-backed influence links, topic coverage trends, and narrative alignment.

```python
from typing import Literal

import pydantic

from agents.schemas import EvidenceItem


EvidenceStatus = Literal["verified", "inferred", "unknown"]
OwnershipType = Literal[
    "public_company",
    "private_company",
    "nonprofit",
    "public_broadcaster",
    "state_owned",
    "government_agency",
    "cooperative",
    "individual",
    "mixed",
    "unknown",
]


class OutletProfile(pydantic.BaseModel):
    outlet_name: str
    normalized_domain: str = ""
    country: str = ""
    ownership_type: OwnershipType = "unknown"
    parent_company: str = ""
    owner_names: list[str] = pydantic.Field(default_factory=list)
    funding_sources: list[str] = pydantic.Field(default_factory=list)
    government_affiliations: list[str] = pydantic.Field(default_factory=list)
    bias_category: str = ""
    media_scale: str = ""
    media_type: str = ""
    article_count: int = 0
    average_reliability_score: float | None = None
    average_objectivity_score: float | None = None
    transparency_status: EvidenceStatus = "unknown"
    confidence_score: float = 0.0
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    evidence_urls: list[str] = pydantic.Field(default_factory=list)
    caveats: list[str] = pydantic.Field(default_factory=list)


class InfluenceLink(pydantic.BaseModel):
    source_entity: str
    target_entity: str
    link_type: Literal[
        "owns",
        "owned_by",
        "funds",
        "funded_by",
        "operates",
        "operated_by",
        "affiliated_with",
        "licensed_by",
        "publishes",
        "syndicates",
        "unknown",
    ]
    status: EvidenceStatus = "unknown"
    confidence_score: float = 0.0
    explanation: str = ""
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    evidence_urls: list[str] = pydantic.Field(default_factory=list)
    limitations: list[str] = pydantic.Field(default_factory=list)


class CoverageTrendItem(pydantic.BaseModel):
    trend_label: str
    time_window: str = ""
    source_basis: Literal["articles_data", "gdelt", "mixed"] = "articles_data"
    outlet_names: list[str] = pydantic.Field(default_factory=list)
    ownership_types: list[OwnershipType] = pydantic.Field(default_factory=list)
    article_count: int = 0
    observed_pattern: str
    confidence_score: float = 0.0
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    evidence_urls: list[str] = pydantic.Field(default_factory=list)
    caveats: list[str] = pydantic.Field(default_factory=list)


class NarrativeAlignmentItem(pydantic.BaseModel):
    narrative_label: str
    aligned_outlets: list[str] = pydantic.Field(default_factory=list)
    alignment_basis: Literal[
        "headline_similarity",
        "shared_claims",
        "shared_framing",
        "shared_omissions",
        "wire_or_syndication",
        "unknown",
    ] = "unknown"
    ownership_types: list[OwnershipType] = pydantic.Field(default_factory=list)
    representative_phrases: list[str] = pydantic.Field(default_factory=list)
    status: EvidenceStatus = "unknown"
    confidence_score: float = 0.0
    evidence: list[EvidenceItem] = pydantic.Field(default_factory=list)
    evidence_urls: list[str] = pydantic.Field(default_factory=list)
    caveats: list[str] = pydantic.Field(default_factory=list)


class SourceInfluenceMap(pydantic.BaseModel):
    topic: str
    generated_from: list[Literal["articles_data", "wikidata", "sec_edgar", "gdelt"]] = pydantic.Field(
        default_factory=list
    )
    outlet_profiles: list[OutletProfile] = pydantic.Field(default_factory=list)
    influence_links: list[InfluenceLink] = pydantic.Field(default_factory=list)
    coverage_trends: list[CoverageTrendItem] = pydantic.Field(default_factory=list)
    narrative_alignments: list[NarrativeAlignmentItem] = pydantic.Field(default_factory=list)
    unknowns: list[str] = pydantic.Field(default_factory=list)
    caveats: list[str] = pydantic.Field(default_factory=list)
    overall_confidence_score: float = 0.0
```

## Source Influence Agent Prompt Principles

The agent instruction should require:

- Use `articles_data` as the primary evidence base.
- Normalize outlets conservatively by domain and source name.
- Mark ownership and funding information as `unknown` unless supported by public evidence.
- Separate source-set observations from optional external lookup results.
- Treat wire services and duplicate clusters as weak evidence of independent narrative alignment.
- Avoid loaded terms such as "puppet", "front", "controlled by", "propaganda network", or "secret backer" unless directly quoted from a cited source and contextualized neutrally.
- Include limitations for each material claim.
- Prefer concise uncertainty over broad inference.

## Influence Audit Agent Criteria

The Influence Audit Agent should verify the `SourceInfluenceMap` before dashboard display.

Proposed audit criteria:

1. Schema compliance: output must match `SourceInfluenceMap`, with nested outlet profiles, links, trends, and narrative alignment items shaped correctly.
2. Evidence traceability: every ownership, funding, affiliation, and influence link must include evidence URLs or be marked `unknown`.
3. Claim status discipline: relationships must be labeled `verified`, `inferred`, or `unknown`; speculative relationships must not be presented as facts.
4. No hidden-backer speculation: reject or require revision for claims about covert support, undisclosed control, or hidden coordination without direct evidence.
5. Neutral language: reject conspiracy framing, loaded labels, guilt-by-association, or claims that ownership alone proves editorial intent.
6. Data-source separation: observations from `articles_data`, Wikidata, SEC EDGAR, and GDELT must be distinguishable.
7. Confidence calibration: confidence scores must decrease when evidence is stale, indirect, missing URLs, based on weak entity matching, or derived from a narrow article set.
8. Duplicate and wire caution: duplicated wire-service content must not be treated as independent alignment evidence.
9. Unknowns and caveats: missing ownership or funding data must be surfaced as unknown, not interpreted as suspicious.
10. Safety and fairness: outlet descriptions must avoid defamatory claims and should use cautious wording for public figures, companies, governments, and civil society groups.

## Streamlit UI Proposal

The Streamlit dashboard can add a future optional section or tab after the current Sources and Perspectives & Disputes views. The UI should make evidence and uncertainty visible.

### Ownership and Affiliation Table

Purpose: show one row per outlet.

Suggested columns:

- Outlet
- Domain
- Ownership type
- Parent company or owner
- Funding or government affiliation
- Bias category
- Reliability
- Objectivity
- Status: verified, inferred, or unknown
- Confidence
- Evidence links
- Caveats

Interactions:

- Filter by ownership type, confidence band, country, and status.
- Expand a row to show evidence snippets and limitations.
- Highlight `unknown` rather than hiding it.

### Reliability vs Objectivity Scatter

Purpose: preserve the existing source landscape while adding ownership context.

Suggested encoding:

- X-axis: objectivity score
- Y-axis: source reliability score
- Color: ownership type
- Shape or outline: status, such as verified, inferred, unknown
- Size: article count
- Tooltip: outlet, parent company, bias category, article count, confidence, evidence count

Important caveat text:

- Ownership type is contextual metadata, not proof of editorial behavior.

### Narrative Trend Timeline

Purpose: show how coverage and narrative emphasis changed over time.

Suggested rows or bands:

- Article volume by day or week
- Narrative labels from `NarrativeAlignmentItem`
- Ownership type clusters
- Optional GDELT trend overlays, clearly labeled

Interactions:

- Toggle between current article set and optional wider trend source.
- Click a trend item to see representative articles and evidence.

### Influence Links and Evidence Ledger

Purpose: make every relationship auditable.

Suggested fields:

- Source entity
- Target entity
- Link type
- Status
- Confidence
- Explanation
- Evidence URL
- Evidence quote or snippet
- Source basis
- Limitation

Interactions:

- Filter to `verified` only.
- Filter by relationship type.
- Open evidence URLs in a new browser tab.
- Show a warning when links are inferred or unknown.

## Caveats and Safety Rules

The feature should always surface these rules in prompts, audit criteria, and UI copy:

- Do not infer hidden support, hidden owners, covert influence, or coordination without direct evidence.
- Distinguish `verified`, `inferred`, and `unknown` for every material relationship.
- Avoid conspiracy framing.
- Avoid guilt-by-association.
- Show confidence scores and evidence URLs.
- Treat ownership as context, not as proof of bias or falsehood.
- Treat state funding, public broadcasting, nonprofit funding, philanthropic support, and advertising models as descriptive facts unless evidence supports a stronger claim.
- Do not use weak source matching to connect similarly named entities.
- Make stale, missing, conflicting, or single-source evidence explicit.
- Prefer "public records identify X as owner" over "X influences outlet Y" unless influence is directly documented.

## MVP Implementation Plan

No code should be implemented in this design phase. A future implementation can proceed in small, testable steps.

1. Add schemas only
   - Add the proposed Pydantic models to `agents/schemas.py`.
   - Unit test default values, required fields, and enum-like status behavior.

2. Build an `articles_data`-only Source Influence Agent
   - Create a new agent that groups outlets from existing article data.
   - Produce outlet profiles with article counts, reliability/objectivity averages, bias categories, duplicate/wire caveats, and `unknown` ownership fields.
   - Unit test aggregation behavior without network calls.

3. Add Influence Audit Agent criteria
   - Add a dedicated criteria block to the coordinator.
   - Verify it flags missing evidence URLs for non-unknown relationships.
   - Unit test audit prompt construction or criteria routing where practical.

4. Add optional recruitment
   - Extend recruitment output only after the basic agent is stable.
   - Recruit this agent for topics where source transparency is useful, such as media criticism, geopolitical coverage, public broadcasters, corporate disputes, or topics with many outlet types.
   - Keep it skipped for simple factual queries.

5. Add Streamlit read-only display
   - Add ownership table and scatter plot first.
   - Display `unknown` and caveats prominently.
   - Add evidence ledger before adding trend timelines.

6. Add optional Wikidata enrichment behind a flag
   - Use deterministic lookup helpers.
   - Cache lookup results where appropriate.
   - Require evidence URLs or source references before marking relationships `verified`.
   - Add tests with mocked responses.

7. Add optional SEC EDGAR enrichment
   - Restrict to public companies and known parent entities.
   - Store filing URLs and entity identifiers.
   - Add tests with fixture filings or mocked API responses.

8. Add optional GDELT trend analysis
   - Keep GDELT trends separate from current article-set trends.
   - Add date-window controls.
   - Add tests for trend item construction and source-basis labeling.

9. Add end-to-end verification
   - Run unit and integration tests.
   - Add a focused Streamlit or Playwright check only after UI implementation.
   - Confirm all claims include status, confidence, caveats, and evidence URLs.

## Non-Goals for MVP

- No graph database.
- No automated claim that ownership causes editorial framing.
- No paid or private data-provider dependency.
- No hidden-affiliation detection.
- No social-media network analysis.
- No deployment changes.

## Open Questions

- Should the agent be recruited by default for all high-complexity topics, or only when the user enables a source-transparency option?
- Should Wikidata and SEC EDGAR enrichment be controlled by separate feature flags?
- Should the UI live inside the Sources tab or become a new optional Source Influence tab?
- How should confidence scores be calibrated across direct outlet pages, corporate filings, Wikidata, and secondary reporting?
