# Source Transparency / Source Influence Agent Design

## Purpose

The Source Transparency Agent is an optional NewsLens agent that maps evidence-backed information about media outlets behind a news topic. It helps users understand public ownership, funding model, government affiliation, institutional context, potential conflict-of-interest context, source bias, reliability, objectivity, and coverage trends across the articles already gathered by the Search Agent.

Recommended product names:

- Source Transparency Agent
- Source Influence Agent

Avoid names such as "Deep Mining Agent" in product UI. That name implies invasive investigation, covert extraction, or speculative discovery of undisclosed influence. The feature should instead present transparent, public, cited institutional context and evidence-backed relationships.

## Product Scope

The agent answers questions such as:

- Which outlets appeared in the current article set?
- What public ownership or affiliation information is available for those outlets?
- Are any outlets publicly owned, nonprofit, state-funded, government-operated, privately owned, or part of a larger media group when public evidence supports that statement?
- How do reliability and objectivity scores compare across ownership types?
- Are coverage patterns or narrative frames clustered by outlet type, bias category, geography, or source group?
- Which influence relationships are directly verified, cautiously inferred from public records, or unknown?

The output should support media literacy and source transparency. It should not label outlets as coordinated, captured, paid, or institutionally directed unless a cited public source directly supports the exact relationship.

## Claim Boundaries

The agent can claim:

- A relationship is `verified` when supported by explicit public evidence, such as an outlet's about page, annual report, corporate filing, regulator record, Wikidata statement with source references, or reputable secondary source.
- A relationship is `inferred` only when the inference is narrow, mechanical, and clearly explained, such as deriving a parent company from a public SEC filing or matching an outlet domain to an already verified parent entity.
- A relationship is `unknown` when evidence is unavailable, conflicting, too weak, or not checked.
- A trend appears in the analyzed source set when it is derived from the provided articles or from a named optional dataset such as GDELT.
- A narrative alignment exists when multiple outlets use similar framing, source selection, or issue emphasis in the analyzed evidence.

The agent cannot claim:

- Non-public financial support, undisclosed sponsorship, intelligence affiliation, political control, or coordinated editorial direction without direct public evidence.
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

## Architecture Split

The feature should be designed as a small pipeline of separable responsibilities rather than one agent that searches, enriches, reasons, audits, and visualizes at once.

### Outlet Aggregator

The Outlet Aggregator is deterministic code over existing `articles_data`. It should not call external services or make ownership claims.

Responsibilities:

- Normalize outlets from `source` and URL domain.
- Group articles by outlet, outlet group, wire service, and duplicate cluster.
- Compute article counts, publication windows, average reliability scores, average objectivity scores, bias category distribution, media type distribution, and media scale distribution.
- Preserve evidence trails back to article titles, URLs, published dates, summaries, and snippets.
- Flag weak independence when many articles share a `wire_service` or `duplicate_cluster`.

### Optional Ownership Lookup Helpers

Ownership Lookup Helpers are optional post-MVP helpers behind explicit feature flags. They should be deterministic fetchers and parsers, not synthesis agents.

Potential helpers:

- `ENABLE_WIKIDATA_SOURCE_LOOKUP`: public outlet/entity metadata.
- `ENABLE_SEC_EDGAR_SOURCE_LOOKUP`: public-company parent, ticker, CIK, and filing evidence.
- `ENABLE_GDELT_SOURCE_TRENDS`: wider volume and trend analysis beyond the selected source set.

Each helper should return raw or lightly normalized evidence with source URLs, lookup timestamps, entity identifiers, and caveats. If a helper cannot verify a relationship, it should return `unknown` rather than guessing.

### Source Influence Agent

The Source Influence Agent performs cautious synthesis over the Outlet Aggregator output and any enabled helper results. It should explain source transparency and coverage patterns, not discover unsupported ownership or affiliation claims.

Responsibilities:

- Summarize public ownership, funding model, government affiliation, institutional context, and potential conflict-of-interest context only when supported by evidence.
- Distinguish `verified`, `inferred`, and `unknown` relationship status.
- Compare coverage patterns across outlet groups without claiming causation.
- Produce `SourceInfluenceMap` for downstream UI rendering.

### Influence Audit Agent

The Influence Audit Agent reviews the synthesized map for safety, traceability, and calibrated uncertainty before display.

Responsibilities:

- Reject unsupported ownership, funding, affiliation, or coordination claims.
- Verify that evidence-backed relationships include URLs.
- Confirm that `unknown` values are not framed as suspicious.
- Confirm that ownership and government funding are presented as context, not proof of editorial intent.

## MVP-First Implementation

The MVP should be `articles_data`-only. It should not call Wikidata, SEC EDGAR, GDELT, search engines, scraping helpers, or any new external lookup service.

Use only existing article fields:

- `source`
- `url`
- `published_date`
- `bias_category`
- `source_reliability_score`
- `objectivity_score`
- `outlet_group`
- `wire_service`
- `duplicate_cluster`
- `summary`
- `full_content_snippet`

MVP outputs should focus on:

- Source transparency summaries based on the current source set.
- Coverage pattern visualizations grouped by outlet, source type, bias category, wire service, and duplicate cluster.
- Evidence trails back to current articles.
- Explicit `unknown` ownership, funding, and affiliation fields unless already present in supplied article evidence.

MVP outputs should not:

- Make public ownership, funding model, government affiliation, or institutional-context claims that cannot be supported by the supplied article data.
- Infer editorial intent from ownership type.
- Treat repeated wire copy as independent narrative alignment.
- Treat missing ownership information as suspicious.

## Data Source Strategy

### 1. Reuse Existing `articles_data` First

The first version should start and stop with the articles already selected by Search Agent:

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

This keeps the feature cheap, deterministic, and aligned with the current pipeline. The Outlet Aggregator can group by source name or normalized domain, then compute first-pass outlet profiles, article counts, reliability/objectivity averages, publication timing, source-type summaries, and coverage patterns.

### 2. Optional Wikidata Lookup, Post-MVP

Wikidata can enrich outlet profiles with public entity metadata:

- Parent organization
- Owner
- Operator
- Country
- Inception date
- Official website
- Political alignment claims, only when explicitly sourced and treated cautiously

Use Wikidata as a starting point, not as final truth. Preserve statement references when available. Mark unsourced or weakly sourced values as `inferred` or `unknown`, not `verified`.

### 3. Optional SEC EDGAR Lookup, Post-MVP

SEC EDGAR can enrich profiles for US public companies and listed parent companies:

- Parent company legal name
- Ticker and CIK
- Public-company status
- Relevant filing URLs
- Segment or subsidiary references, when explicitly present

The agent should not infer editorial influence from public-company ownership. It can say that a parent company is publicly traded when supported by filings.

### 4. Optional GDELT Lookup, Post-MVP

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
- Use neutral terms such as public ownership, funding model, government affiliation, institutional context, potential conflict-of-interest context, and evidence-backed relationship.
- Avoid loaded terms such as "puppet", "front", "controlled by", or "propaganda network" unless directly quoted from a cited source and contextualized neutrally.
- Include limitations for each material claim.
- Prefer concise uncertainty over broad inference.

## Influence Audit Agent Criteria

The Influence Audit Agent should verify the `SourceInfluenceMap` before dashboard display.

Proposed audit criteria:

1. Schema compliance: output must match `SourceInfluenceMap`, with nested outlet profiles, links, trends, and narrative alignment items shaped correctly.
2. Evidence traceability: every ownership, funding, affiliation, and influence link must include evidence URLs or be marked `unknown`.
3. Claim status discipline: relationships must be labeled `verified`, `inferred`, or `unknown`; speculative relationships must not be presented as facts.
4. No unsupported institutional claims: reject or require revision for claims about non-public support, undisclosed control, or coordination without direct evidence.
5. Neutral language: reject conspiracy framing, loaded labels, guilt-by-association, or claims that ownership alone proves editorial intent.
6. Data-source separation: observations from `articles_data`, Wikidata, SEC EDGAR, and GDELT must be distinguishable.
7. Confidence calibration: confidence scores must decrease when evidence is stale, indirect, missing URLs, based on weak entity matching, or derived from a narrow article set.
8. Duplicate and wire caution: duplicated wire-service content must not be treated as independent alignment evidence.
9. Unknowns and caveats: missing ownership or funding data must be surfaced as unknown, not interpreted as suspicious.
10. Safety and fairness: outlet descriptions must avoid defamatory claims and should use cautious wording for public figures, companies, governments, and civil society groups.

## Streamlit UI Proposal

The Streamlit dashboard can add a future optional section or tab after the current Sources and Perspectives & Disputes views. The UI should make evidence and uncertainty visible.

### MVP Visualization Plan

The MVP UI should visualize source transparency and coverage patterns from `articles_data` only.

1. Outlet profile table
   - One row per normalized outlet.
   - Columns: outlet, domain, article count, outlet group, media type, media scale, bias category, average reliability, average objectivity, wire service, duplicate cluster count, first published date, latest published date, and caveats.

2. Reliability vs objectivity scatter grouped by outlet/source type
   - X-axis: objectivity score.
   - Y-axis: source reliability score.
   - Color: outlet group or media type.
   - Shape or outline: wire-service or duplicate-cluster flag.
   - Size: article count.

3. Narrative framing bar chart or table
   - Group snippets or summaries by bias category, outlet group, or media type.
   - Show frame labels, representative phrases, outlet counts, and article counts.
   - Avoid presenting similar wording as coordination when wire-service duplication or shared factual reporting explains it.

4. Publication timeline by outlet group
   - Show article publication dates grouped by outlet group, media type, or bias category.
   - Flag clustered publication patterns as observed timing only, not evidence of coordination.

5. Evidence ledger for any ownership, funding, or affiliation claim
   - In MVP, this is usually empty or marked `unknown` unless the supplied article data itself contains support.
   - Each non-unknown claim must show evidence URL, quote or snippet, status, confidence, and limitation.

### Ownership and Affiliation Table, Post-MVP

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

### Reliability vs Objectivity Scatter, Post-MVP Enriched

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

### Narrative Trend Timeline, Post-MVP Enriched

Purpose: show how coverage and narrative emphasis changed over time.

Suggested rows or bands:

- Article volume by day or week
- Narrative labels from `NarrativeAlignmentItem`
- Ownership type clusters
- Optional GDELT trend overlays, clearly labeled

Interactions:

- Toggle between current article set and optional wider trend source.
- Click a trend item to see representative articles and evidence.

### Influence Links and Evidence Ledger, Post-MVP Enriched

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

- Do not infer non-public support, undisclosed owners, institutional direction, or coordination without direct evidence.
- Distinguish `verified`, `inferred`, and `unknown` for every material relationship.
- Avoid conspiracy framing.
- Avoid guilt-by-association.
- Show confidence scores and evidence URLs.
- Treat ownership as context, not as proof of bias or falsehood.
- Ownership is context, not proof of editorial intent.
- State funding is context, not proof of propaganda.
- Unknown ownership is not suspicious by itself.
- Similar wording is not coordination if wire-service duplication, shared factual reporting, common press releases, or normal news-cycle behavior explains it.
- Treat state funding, public broadcasting, nonprofit funding, philanthropic support, and advertising models as descriptive facts unless evidence supports a stronger claim.
- Do not use weak source matching to connect similarly named entities.
- Make stale, missing, conflicting, or single-source evidence explicit.
- Prefer "public records identify X as owner" over "X influences outlet Y" unless influence is directly documented.

## Recruitment Rules

Suggested Recruiter criteria for this optional agent:

Recruit when:

- The topic is about media, AI/platform disputes, geopolitics, elections, public policy, war, sanctions, corporate litigation, or state media.
- The source set has many outlet types, such as wire services, local outlets, national outlets, international outlets, public broadcasters, advocacy outlets, trade publications, or independent publications.
- The source set shows clear relevance for public ownership, funding model, government affiliation, institutional context, or potential conflict-of-interest context.
- Perspective or dispute analysis would benefit from separating article-level framing from outlet-level context.

Skip when:

- The topic is a simple science update, weather event, sports score, commodity factual update, or routine market update.
- The source set has low diversity or too few outlets to compare responsibly.
- The available article data cannot support meaningful source transparency beyond the existing Sources tab.
- The user needs a fast factual briefing more than a source-context analysis.

## MVP Implementation Plan

No code should be implemented in this design phase. A future implementation can proceed in small, testable steps.

1. Add schemas only
   - Add the proposed Pydantic models to `agents/schemas.py`.
   - Unit test default values, required fields, and enum-like status behavior.

2. Build an `articles_data`-only Outlet Aggregator
   - Create a new agent that groups outlets from existing article data.
   - Produce outlet profiles with article counts, reliability/objectivity averages, bias categories, publication timing, duplicate/wire caveats, and `unknown` ownership fields.
   - Unit test aggregation behavior without network calls.

3. Build an MVP Source Influence Agent over aggregator output
   - Produce source transparency and coverage pattern summaries from `articles_data` only.
   - Avoid unsupported public ownership, funding model, government affiliation, or institutional-context claims.
   - Unit test that unknown ownership remains unknown without evidence.

4. Add Influence Audit Agent criteria
   - Add a dedicated criteria block to the coordinator.
   - Verify it flags missing evidence URLs for non-unknown relationships.
   - Unit test audit prompt construction or criteria routing where practical.

5. Add optional recruitment
   - Extend recruitment output only after the basic agent is stable.
   - Recruit this agent for topics where source transparency is useful, such as media criticism, geopolitical coverage, public broadcasters, corporate disputes, or topics with many outlet types.
   - Keep it skipped for simple factual queries.

6. Add Streamlit read-only display
   - Add outlet profile table, reliability/objectivity scatter, framing table, publication timeline, and evidence ledger first.
   - Display `unknown` and caveats prominently.
   - Keep ownership/funding/affiliation claims empty or unknown unless supported by article evidence.

7. Add optional Wikidata enrichment behind a flag
   - Use deterministic lookup helpers.
   - Cache lookup results where appropriate.
   - Require evidence URLs or source references before marking relationships `verified`.
   - Add tests with mocked responses.

8. Add optional SEC EDGAR enrichment
   - Restrict to public companies and known parent entities.
   - Store filing URLs and entity identifiers.
   - Add tests with fixture filings or mocked API responses.

9. Add optional GDELT trend analysis
   - Keep GDELT trends separate from current article-set trends.
   - Add date-window controls.
   - Add tests for trend item construction and source-basis labeling.

10. Add end-to-end verification
   - Run unit and integration tests.
   - Add a focused Streamlit or Playwright check only after UI implementation.
   - Confirm all claims include status, confidence, caveats, and evidence URLs.

## Non-Goals for MVP

- No graph database.
- No automated claim that ownership causes editorial framing.
- No paid or private data-provider dependency.
- No non-public affiliation detection.
- No social-media network analysis.
- No deployment changes.

## Open Questions

- Should the agent be recruited by default for all high-complexity topics, or only when the user enables a source-transparency option?
- Should Wikidata and SEC EDGAR enrichment be controlled by separate feature flags?
- Should the UI live inside the Sources tab or become a new optional Source Influence tab?
- How should confidence scores be calibrated across direct outlet pages, corporate filings, Wikidata, and secondary reporting?
