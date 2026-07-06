# Demo Claims Alignment

This note keeps the demo story aligned with the current implementation on `origin/main`.

## Supported Claims

| Claim | Current evidence |
| --- | --- |
| Adaptive recruitment | `agents/recruiter_agent.py` emits `RecruitmentResult`; `agents/coordinator.py` skips Dispute, Perspective, Expert, and Outlook stages when recruitment flags are false. |
| Dynamic expert panel | `agents/expert_agent.py` selects 2-3 domains; `agents/coordinator.py` creates one domain expert per selected domain and runs them in parallel. |
| Schema-constrained outputs | `agents/schemas.py` defines Pydantic schemas for search, facts, disputes, perspectives, experts, public report, recruitment, audits, and outlook. |
| Audit loop | `agents/coordinator.py` wraps input check, search, recruiter, fact, dispute, perspective, expert, outlook, and public report stages with bounded audit attempts. |
| Deterministic evidence verification | `agents/evidence_verifier.py` checks cited URLs, quote match, source/date/bias consistency, timeline evidence, and public-report evidence. |
| Search dedupe and wire collapse | `agents/search_agent.py` removes duplicate URLs and collapses likely wire-service/reprint clusters before article selection. |
| Deterministic public editor report | `agents/report_renderer.py` builds the folded report without another LLM call. |
| Refresh-safe snapshots | `agents/app_utils/run_store.py` saves and restores local display snapshots; `app.py` restores the latest snapshot without resuming backend work. |

## Careful Wording For Demo

- Source analysis currently means article-level perspective/bias signals and tone-neutrality labels. The app does not expose a separate formal source reliability score or media-scale score.
- Runtime cost is estimated from token counts unless provider usage metadata is captured by a later metrics rewrite. Treat displayed cost as diagnostic, not billing-grade.
- FastAPI and Docker entrypoints exist, but live deployment still depends on local/cloud credentials such as Gemini or Google auth plus optional `LOGS_BUCKET_NAME`.
- The Streamlit UI no longer has Q&A or a primary Audit Trail tab. Trust evidence is shown in a collapsed diagnostics expander.

## Deferred Claims

- Actual provider token/cost capture should be handled in a future actual-run-metrics rewrite.
- Runtime cost optimization modes should be rebuilt later against the native ADK streaming coordinator.
- A formal eval contract pack and multimodal support are not part of the current demo-ready implementation.
