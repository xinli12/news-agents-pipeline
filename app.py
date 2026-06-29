import asyncio
import os
import threading
import time

import streamlit as st
from dotenv import load_dotenv

from agents.coordinator import NewsAnalysisCoordinator

load_dotenv()

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]


st.set_page_config(
    page_title="NewsLens Multi-Agent Desk",
    page_icon=":newspaper:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Premium Custom Styling
st.markdown(
    """
    <style>
    :root {
        --ink: #172026;
        --muted: #60707c;
        --line: #d9e1e7;
        --paper: #ffffff;
        --surface: #f5f7fa;
        --teal: #0f766e;
        --navy: #1f3a5f;
        --amber: #b7791f;
        --red: #b91c1c;
    }
    .stApp {
        background: var(--surface);
        color: var(--ink);
    }
    .block-container {
        padding-top: 2rem;
        max-width: 1280px;
    }
    h1, h2, h3 {
        letter-spacing: 0;
    }
    div[data-testid="stMetric"] {
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.8rem 1rem;
    }
    div[data-testid="stForm"] {
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 1rem;
    }
    textarea, input {
        background: #ffffff !important;
        color: var(--ink) !important;
        border: 1px solid var(--line) !important;
    }
    textarea::placeholder, input::placeholder {
        color: #738391 !important;
        opacity: 1 !important;
    }
    section.main div[data-testid="stTextArea"] label p,
    div[data-testid="stMain"] div[data-testid="stTextArea"] label p,
    div[data-testid="stTextArea"] div[data-testid="stMarkdownContainer"] p {
        color: var(--ink) !important;
        font-weight: 650 !important;
    }
    div.stButton > button[kind="primary"] {
        background: var(--teal) !important;
        border-color: var(--teal) !important;
        color: #ffffff !important;
    }
    button[data-testid="stBaseButton-primary"] {
        background: var(--teal) !important;
        border-color: var(--teal) !important;
        color: #ffffff !important;
    }
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        background: var(--teal) !important;
        border-color: var(--teal) !important;
        color: #ffffff !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: #0b5f59 !important;
        border-color: #0b5f59 !important;
    }
    button[data-testid="stBaseButton-primary"]:hover {
        background: #0b5f59 !important;
        border-color: #0b5f59 !important;
        color: #ffffff !important;
    }
    button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
        background: #0b5f59 !important;
        border-color: #0b5f59 !important;
        color: #ffffff !important;
    }
    .briefing-band {
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 1.1rem 1.25rem;
        margin: 0.8rem 0 1rem;
    }
    .desk-title {
        font-size: 2.25rem;
        line-height: 1.1;
        font-weight: 760;
        margin-bottom: 0.25rem;
        color: var(--ink);
    }
    .desk-subtitle {
        color: var(--muted);
        font-size: 1rem;
        margin-bottom: 1.2rem;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 0.18rem 0.55rem;
        margin: 0 0.35rem 0.35rem 0;
        background: #fff;
        color: var(--muted);
        font-size: 0.83rem;
        white-space: nowrap;
    }
    .status-chip.good { color: var(--teal); border-color: #9bd4ce; }
    .status-chip.warn { color: var(--amber); border-color: #e5c477; }
    .status-chip.bad { color: var(--red); border-color: #efb4b4; }
    .source-line {
        border-left: 3px solid var(--line);
        padding: 0.4rem 0 0.4rem 0.8rem;
        margin: 0.45rem 0;
    }
    .small-muted {
        color: var(--muted);
        font-size: 0.86rem;
    }

    /* Pipeline Status Indicator & Controls styling */
    .status-indicator {
        padding: 0.8rem 1rem;
        border-radius: 8px;
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
    }
    .status-indicator.running {
        background: #e0f2fe;
        color: #0369a1;
        border: 1px solid #bae6fd;
        animation: pulse 2s infinite ease-in-out;
    }
    .status-indicator.paused {
        background: #fef3c7;
        color: #d97706;
        border: 1px solid #fde68a;
    }
    .status-indicator.stopped {
        background: #f3f4f6;
        color: #4b5563;
        border: 1px solid #e5e7eb;
    }
    .status-indicator.completed {
        background: #ecfdf5;
        color: #047857;
        border: 1px solid #a7f3d0;
    }
    .status-indicator.failed {
        background: #fef2f2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
    }

    /* Stepper Styling */
    .stepper-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.5rem;
        overflow-x: auto;
        gap: 0.5rem;
    }
    .step-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 90px;
        text-align: center;
        padding: 0.4rem;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    .step-card.queued {
        color: #9ca3af;
    }
    .step-card.running {
        color: #0369a1;
        background: #f0f9ff;
        font-weight: bold;
        box-shadow: 0 0 0 2px #bae6fd;
    }
    .step-card.paused {
        color: #d97706;
        background: #fffbeb;
        box-shadow: 0 0 0 2px #fde68a;
    }
    .step-card.completed {
        color: #0f766e;
    }
    .step-card.skipped {
        color: #9ca3af;
        opacity: 0.65;
    }
    .step-card.failed {
        color: #b91c1c;
        background: #fef2f2;
        box-shadow: 0 0 0 2px #fca5a5;
    }
    .step-card.stopped {
        color: #4b5563;
        opacity: 0.8;
    }
    .step-badge {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 2px solid currentColor;
        font-size: 0.9rem;
        margin-bottom: 0.25rem;
        background: #ffffff;
    }
    .step-card.completed .step-badge {
        background: #e6f4f2;
        border-color: #0f766e;
        color: #0f766e;
    }
    .step-card.running .step-badge {
        background: #0369a1;
        color: #ffffff;
        border-color: #0369a1;
        animation: pulse-badge 1.5s infinite ease-in-out;
    }
    .step-card.paused .step-badge {
        background: #d97706;
        color: #ffffff;
        border-color: #d97706;
    }
    .step-card.failed .step-badge {
        background: #b91c1c;
        color: #ffffff;
        border-color: #b91c1c;
    }
    .step-card.skipped .step-badge {
        border-style: dashed;
        background: #f3f4f6;
    }
    .step-label {
        font-size: 0.75rem;
        white-space: nowrap;
    }
    .step-connector {
        flex-grow: 1;
        height: 2px;
        background: var(--line);
        min-width: 15px;
    }

    /* Progressive loading state cards */
    .loading-card {
        background: rgba(255, 255, 255, 0.65);
        backdrop-filter: blur(8px);
        border: 1px dashed var(--line);
        border-radius: 12px;
        padding: 2.5rem 2rem;
        text-align: center;
        margin: 1.5rem 0;
        color: var(--muted);
    }
    .loading-card h3 {
        margin-bottom: 0.5rem;
        color: var(--ink);
        font-size: 1.25rem;
    }
    .loading-card p {
        font-size: 0.95rem;
        max-width: 500px;
        margin: 0 auto;
    }

    @keyframes pulse {
        0% { opacity: 0.8; }
        50% { opacity: 1; }
        100% { opacity: 0.8; }
    }
    @keyframes pulse-badge {
        0% { transform: scale(1); }
        50% { transform: scale(1.08); }
        100% { transform: scale(1); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def clamp_score(value: float | int | None) -> float:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def join_or_dash(items: list[str] | None) -> str:
    return ", ".join(items or []) or "-"


def render_chips(items: list[tuple[str, str]]) -> None:
    html = []
    for label, state in items:
        html.append(f'<span class="status-chip {state}">{label}</span>')
    st.markdown("".join(html), unsafe_allow_html=True)


def render_evidence_items(
    evidence: list[dict], heading: str = "Evidence", max_items: int = 4
) -> None:
    st.markdown(f"**{heading}**")
    if not evidence:
        st.caption("No evidence trail provided.")
        return

    for item in evidence[:max_items]:
        source = item.get("source") or "Unknown source"
        title = item.get("title") or ""
        url = item.get("url") or ""
        published = item.get("published_date") or ""
        bias = item.get("bias_category") or ""
        quote = item.get("quote") or ""
        meta = " | ".join(part for part in [published, bias] if part)
        link = f"[{source}]({url})" if url else source
        st.markdown(
            f'<div class="source-line">{link}<br>'
            f'<span class="small-muted">{title} {meta}</span></div>',
            unsafe_allow_html=True,
        )
        if quote:
            st.caption(f'"{quote}"')

    if len(evidence) > max_items:
        st.caption(f"{len(evidence) - max_items} more evidence items")


def render_input_review(review: dict) -> None:
    if not review:
        return
    issue = review.get("input_issue_type", "clear_news_query")
    auto_modified = review.get("auto_modified", False)
    needs_confirm = review.get("needs_user_confirmation", False)
    confidence = clamp_score(review.get("confidence", 1.0))
    chips = [(issue.replace("_", " ").title(), "good")]
    if auto_modified:
        chips.append(("Auto neutralized", "warn"))
    if needs_confirm:
        chips.append(("Broad query", "warn"))
    chips.append(
        (f"Input confidence {confidence:.0%}", "good" if confidence > 0.75 else "warn")
    )
    render_chips(chips)

    message = review.get("user_message") or review.get("rejection_reason")
    if message:
        st.caption(message)

    options = review.get("suggested_options") or []
    if options:
        with st.expander("Suggested query refinements", expanded=False):
            for option in options:
                st.markdown(f"- {option}")


def article_rows(articles: list[dict]) -> list[dict]:
    rows = []
    for article in articles:
        rows.append(
            {
                "Publisher": article.get("source", ""),
                "Title": article.get("title", ""),
                "URL": article.get("url", ""),
                "Perspective": article.get("bias_category", ""),
                "Scale": article.get("media_scale", ""),
                "Type": article.get("media_type", ""),
                "Outlet Group": article.get("outlet_group", ""),
                "Wire": article.get("wire_service") or "",
                "Reliability": clamp_score(article.get("source_reliability_score")),
                "Objectivity": clamp_score(article.get("objectivity_score")),
                "Summary": article.get("summary", ""),
            }
        )
    return rows


def render_source_table(articles: list[dict]) -> None:
    if not articles:
        st.info("No analyzed sources available.")
        return

    import pandas as pd

    df = pd.DataFrame(article_rows(articles))
    st.dataframe(
        df,
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
            "Reliability": st.column_config.ProgressColumn(
                "Reliability", min_value=0.0, max_value=1.0, format="%.2f"
            ),
            "Objectivity": st.column_config.ProgressColumn(
                "Objectivity", min_value=0.0, max_value=1.0, format="%.2f"
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def render_landscape(articles_data: dict) -> None:
    articles = articles_data.get("articles", [])
    if not articles:
        st.info("No source landscape to display.")
        return

    import pandas as pd

    rows = article_rows(articles)
    df = pd.DataFrame(rows)
    total = len(rows)
    avg_rel = sum(row["Reliability"] for row in rows) / total
    avg_obj = sum(row["Objectivity"] for row in rows) / total
    source_balance = articles_data.get("source_balance") or {}

    cols = st.columns(4)
    cols[0].metric("Sources", total)
    cols[1].metric("Avg reliability", f"{avg_rel:.0%}")
    cols[2].metric("Avg objectivity", f"{avg_obj:.0%}")
    cols[3].metric("Search status", articles_data.get("search_status", "verified"))

    if articles_data.get("verification_summary"):
        st.info(articles_data["verification_summary"])

    if source_balance:
        with st.expander("Candidate pool balance", expanded=False):
            st.json(source_balance)

    chart_col_1, chart_col_2 = st.columns(2)
    with chart_col_1:
        st.markdown("#### Source mix")
        counts = df["Perspective"].value_counts().reset_index()
        counts.columns = ["Perspective", "Count"]
        st.bar_chart(counts, x="Perspective", y="Count", color="Perspective")
    with chart_col_2:
        st.markdown("#### Reliability vs objectivity")
        st.scatter_chart(
            df,
            x="Reliability",
            y="Objectivity",
            color="Perspective",
            size="Reliability",
        )


def render_public_summary(results: dict) -> None:
    public_report = results.get("public_report") or {}
    audit_warnings = results.get("audit_warnings") or []
    articles_data = results.get("articles") or {}
    review = results.get("review_result") or {}
    recruitment = results.get("recruitment") or {}

    if audit_warnings:
        st.warning(
            "Some audit checks did not fully pass. The report is shown with unresolved caveats."
        )

    with st.container(border=True):
        st.markdown(f"## {public_report.get('title', 'News briefing')}")
        lead = public_report.get("lead_paragraph") or "No public summary was generated."
        st.write(lead)

        takeaways = public_report.get("key_takeaways") or []
        if takeaways:
            st.markdown("#### Key takeaways")
            for takeaway in takeaways:
                st.markdown(f"- {takeaway}")

    chips = []
    status = str(articles_data.get("search_status", "verified")).lower()
    chips.append(
        (f"Search: {status}", "good" if status in {"verified", "corrected"} else "warn")
    )
    complexity = recruitment.get("complexity_level")
    if complexity:
        chips.append(
            (f"Complexity: {complexity}", "good" if complexity == "low" else "warn")
        )
    if review.get("suggested_query_formulation"):
        chips.append((f"Query: {review.get('suggested_query_formulation')}", "good"))
    render_chips(chips)

    if public_report.get("narrative_summary"):
        with st.expander("Narrative synthesis", expanded=True):
            st.write(public_report["narrative_summary"])

    if public_report.get("future_outlook"):
        with st.expander("What to watch next", expanded=True):
            st.write(public_report["future_outlook"])

    editor_report = results.get("public_editor_report")
    if editor_report:
        with st.expander("Full public editor report", expanded=False):
            st.markdown(editor_report, unsafe_allow_html=True)


def render_consensus_and_timeline(facts: dict) -> None:
    consensus = facts.get("consensus_facts", [])
    st.markdown("### Consensus facts")
    if not consensus:
        st.info("No cross-verified consensus facts were extracted.")
    for idx, item in enumerate(consensus, 1):
        with st.expander(
            f"{idx}. {item.get('claim', 'Untitled fact')}", expanded=idx <= 2
        ):
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(
                    f"**Sources:** {join_or_dash(item.get('supporting_sources'))}"
                )
                render_evidence_items(item.get("evidence", []))
            with cols[1]:
                score = clamp_score(item.get("cross_verification_score"))
                st.metric("Cross-check", f"{score:.0%}")
                st.progress(score)

    st.markdown("### Timeline")
    structured_timeline = facts.get("timeline") or []
    if structured_timeline:
        for event in structured_timeline:
            with st.expander(
                f"{event.get('date', 'Date unknown')} - {event.get('event', '')}",
                expanded=False,
            ):
                render_evidence_items(
                    event.get("evidence", []), heading="Timeline evidence"
                )
    else:
        timeline = facts.get("timeline_events") or []
        if not timeline:
            st.info("No timeline was extracted.")
        for event in timeline:
            st.markdown(f"- {event}")


def render_disputes(facts: dict) -> None:
    disputes = facts.get("disputed_claims") or []
    st.markdown("### Disputes")
    if not disputes:
        st.success(
            "No major contradictory claims were identified in the selected sources."
        )
        return

    for idx, item in enumerate(disputes, 1):
        with st.expander(
            f"{idx}. {item.get('claim', 'Contested claim')}", expanded=idx == 1
        ):
            left, right = st.columns(2)
            with left:
                st.markdown("#### Side A")
                st.write(item.get("side_a_assertion", ""))
                st.caption(f"Sources: {join_or_dash(item.get('side_a_sources'))}")
                render_evidence_items(
                    item.get("side_a_evidence", []), "Side A evidence", 3
                )
            with right:
                st.markdown("#### Side B")
                st.write(item.get("side_b_assertion", ""))
                st.caption(f"Sources: {join_or_dash(item.get('side_b_sources'))}")
                render_evidence_items(
                    item.get("side_b_evidence", []), "Side B evidence", 3
                )


def render_perspectives(narratives: dict) -> None:
    profiles = narratives.get("profiles") or []
    st.markdown("### Perspectives")
    if not profiles:
        st.info("No perspective profiles were found.")
        return

    cols = st.columns(min(3, len(profiles)))
    for idx, profile in enumerate(profiles):
        with cols[idx % len(cols)]:
            title = profile.get("perspective_group", "Perspective")
            if profile.get("is_speculative"):
                title = f"{title} (speculative)"
            with st.container(border=True):
                st.markdown(f"#### {title}")
                st.write(profile.get("core_narrative", ""))
                st.markdown("**Arguments**")
                for arg in profile.get("key_arguments", []):
                    st.markdown(f"- {arg}")
                omissions = profile.get("notable_omissions") or []
                if omissions:
                    st.markdown("**Notable omissions**")
                    for omission in omissions:
                        st.markdown(f"- {omission}")
                if profile.get("common_emotional_triggers"):
                    st.caption(
                        "Framing terms: "
                        + ", ".join(profile.get("common_emotional_triggers", []))
                    )

    if narratives.get("key_rhetorical_differences"):
        st.info(narratives["key_rhetorical_differences"])


def render_experts_and_outlook(experts: dict, outlook: dict) -> None:
    st.markdown("### Expert analysis")
    opinions = experts.get("expert_opinions") or []
    if not opinions:
        st.info(
            experts.get("roundtable_summary") or "No expert panel opinions available."
        )
    else:
        for idx, opinion in enumerate(opinions, 1):
            with st.expander(
                f"{idx}. {opinion.get('expert_name', 'Expert')} - {opinion.get('expertise_area', '')}",
                expanded=idx == 1,
            ):
                st.write(opinion.get("commentary", ""))
                if opinion.get("cited_references"):
                    st.markdown("**Cited anchors**")
                    for ref in opinion.get("cited_references", []):
                        st.markdown(f"- {ref}")
                if opinion.get("recommended_reading_or_context"):
                    st.markdown("**Context to review**")
                    for item in opinion.get("recommended_reading_or_context", []):
                        st.markdown(f"- {item}")
        if experts.get("roundtable_summary"):
            st.success(experts["roundtable_summary"])

    st.markdown("### Future outlook")
    if (
        outlook.get("most_likely_scenario")
        and outlook.get("most_likely_scenario") != "N/A"
    ):
        st.markdown("**Most likely scenario**")
        st.write(outlook["most_likely_scenario"])
    else:
        st.info("No future outlook scenarios available.")

    for scenario in outlook.get("alternative_scenarios") or []:
        with st.expander(
            scenario.get("scenario_title", "Alternative scenario"), expanded=False
        ):
            if scenario.get("likelihood_band"):
                st.caption(scenario["likelihood_band"])
            st.write(scenario.get("description", ""))
            for trigger in scenario.get("trigger_conditions", []):
                st.markdown(f"- {trigger}")

    indicators = outlook.get("monitoring_indicators") or []
    if indicators:
        st.markdown("**Monitoring indicators**")
        for indicator in indicators:
            st.markdown(f"- {indicator}")
    if outlook.get("confidence_statement"):
        st.caption(outlook["confidence_statement"])


def render_recruitment(recruitment: dict) -> None:
    if not recruitment:
        return
    st.markdown("### Recruitment decision")
    cols = st.columns(4)
    cols[0].metric("Dispute", "Yes" if recruitment.get("recruit_dispute") else "No")
    cols[1].metric(
        "Perspective", "Yes" if recruitment.get("recruit_perspective") else "No"
    )
    cols[2].metric("Expert", "Yes" if recruitment.get("recruit_expert") else "No")
    cols[3].metric(
        "Outlook", "Yes" if recruitment.get("recruit_future_outlook") else "No"
    )
    st.write(recruitment.get("recruitment_justification", ""))
    if recruitment.get("perspective_axis"):
        st.caption(f"Perspective axis: {recruitment['perspective_axis']}")
    if recruitment.get("expert_domains"):
        st.caption("Expert domains: " + ", ".join(recruitment["expert_domains"]))


def render_audit_trail(results: dict) -> None:
    warnings = results.get("audit_warnings") or []
    logs = results.get("editor_logs") or []
    if warnings:
        st.markdown("### Unresolved warnings")
        for warning in warnings:
            st.warning(f"{warning.get('agent')}: {warning.get('feedback')}")
            fixes = warning.get("recommended_fixes") or []
            if fixes:
                with st.expander("Recommended fixes", expanded=False):
                    for fix in fixes:
                        st.markdown(f"- {fix}")

    st.markdown("### Audit loop")
    if not logs:
        st.info("No audit logs were recorded.")
        return

    import pandas as pd

    rows = [
        {
            "Agent": log.get("agent", ""),
            "Step": log.get("step", ""),
            "Attempt": log.get("attempt", ""),
            "Approved": log.get("approved", False),
            "Feedback": log.get("feedback", ""),
        }
        for log in logs
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for log in logs:
        approved = log.get("approved", False)
        label = "approved" if approved else "rejected"
        with st.expander(
            f"{log.get('agent', 'agent')} attempt {log.get('attempt', '')}: {label}",
            expanded=not approved,
        ):
            feedback_items = log.get("audit_feedback") or []
            if feedback_items:
                st.markdown("**Audit feedback**")
                for item in feedback_items:
                    st.markdown(f"- {item}")
            fixes = log.get("recommended_fixes") or []
            if fixes:
                st.markdown("**Recommended fixes**")
                for fix in fixes:
                    st.markdown(f"- {fix}")


def worker_thread_fn(
    topic: str,
    enable_editor: bool,
    model_name: str,
    bypass_input_check: bool,
    shared_state: dict,
):
    """Background worker that executes the multi-agent analysis loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    coordinator = NewsAnalysisCoordinator()

    async def progress_callback(step: str, message: str, payload: dict | None = None):
        shared_state["progress_logs"].append(
            {"step": step, "message": message, "timestamp": time.time()}
        )
        shared_state["current_step"] = message
        # Short sleep to yield control to other async tasks
        await asyncio.sleep(0.01)

    try:
        results = loop.run_until_complete(
            coordinator.analyze(
                topic=topic,
                progress_callback=progress_callback,
                enable_editor=enable_editor,
                control_state=shared_state,
                results_dict=shared_state["results"],
                model_name=model_name,
                bypass_input_check=bypass_input_check,
            )
        )
        if shared_state["control"].get("stopped"):
            shared_state["status"] = "stopped"
        else:
            shared_state["status"] = "completed"
            shared_state["results"] = results
    except Exception as exc:
        if shared_state["control"].get("stopped"):
            shared_state["status"] = "stopped"
        else:
            shared_state["status"] = "failed"
            shared_state["error"] = str(exc)
    finally:
        loop.close()


def render_progress_stepper(step_statuses: dict):
    """Renders a beautiful stepper showing the progression of the news agent pipeline."""
    steps = [
        ("review", "Input Check"),
        ("search", "Source Search"),
        ("recruiter", "Orchestrator"),
        ("fact_bias", "Fact Extraction"),
        ("dispute", "Dispute Map"),
        ("bias_agent", "Perspectives"),
        ("expert", "Expert Panel"),
        ("outlook", "Future Outlook"),
        ("public_report", "Briefing Writer"),
        ("public_editor", "Dashboard Editor"),
    ]

    html = ['<div class="stepper-container">']
    for idx, (key, label) in enumerate(steps):
        status = step_statuses.get(key, "queued")

        badge = "○"
        if status == "completed":
            badge = "✓"
        elif status == "running":
            badge = "●"
        elif status == "paused":
            badge = "⏸"
        elif status == "skipped":
            badge = "—"
        elif status == "failed":
            badge = "✗"
        elif status == "stopped":
            badge = "⏹"

        html.append(
            f'<div class="step-card {status}">'
            f'<span class="step-badge">{badge}</span>'
            f'<span class="step-label">{label}</span>'
            f"</div>"
        )
        if idx < len(steps) - 1:
            html.append('<div class="step-connector"></div>')

    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_qa_tab(results: dict) -> None:
    st.markdown("### Ask a follow-up")

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    if not (chat_prompt := st.chat_input("Ask about the current report")):
        return

    st.session_state["chat_messages"].append({"role": "user", "content": chat_prompt})
    with st.chat_message("user"):
        st.write(chat_prompt)

    with st.chat_message("assistant"):
        status = st.empty()
        status.markdown("Consulting the report context...")
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types as genai_types

            from agents.qa_agent import get_qa_agent

            qa_agent = get_qa_agent()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def get_response():
                session_service = InMemorySessionService()
                session_id = "qa_session"
                await session_service.create_session(
                    app_name="news_app", user_id="user", session_id=session_id
                )

                history_text = "\n".join(
                    f"{m['role']}: {m['content']}"
                    for m in st.session_state["chat_messages"][:-1]
                )
                articles = (results.get("articles") or {}).get("articles", [])
                articles_text = "\n".join(
                    f"Article #{idx}\n"
                    f"Title: {article.get('title', '')}\n"
                    f"Source: {article.get('source', '')}\n"
                    f"URL: {article.get('url', '')}\n"
                    f"Snippet: {article.get('full_content_snippet', '')}\n---"
                    for idx, article in enumerate(articles, 1)
                )

                prompt = (
                    f"Topic: {results.get('topic', '')}\n"
                    f"Consensus Facts & Disputes: {results.get('facts', {})}\n"
                    f"Media Narratives: {results.get('narratives', {})}\n"
                    f"Expert Commentary: {results.get('experts', {})}\n"
                    f"Raw Articles:\n{articles_text}\n"
                    f"History:\n{history_text}\n"
                    f"User Question: {chat_prompt}"
                )

                runner = Runner(
                    agent=qa_agent,
                    app_name="news_app",
                    session_service=session_service,
                )
                answer = ""
                async for event in runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=genai_types.Content(
                        role="user", parts=[genai_types.Part.from_text(text=prompt)]
                    ),
                ):
                    if event.is_final_response():
                        answer = event.content.parts[0].text
                        break
                return answer or "No response received."

            answer = loop.run_until_complete(get_response())
            status.write(answer)
            st.session_state["chat_messages"].append(
                {"role": "assistant", "content": answer}
            )
        except Exception as exc:
            status.error(f"Q&A failed: {exc}")


# --- Header and Info Desk Title ---
st.markdown(
    '<div class="desk-title">NewsLens Multi-Agent Desk</div>', unsafe_allow_html=True
)
st.markdown(
    '<div class="desk-subtitle">Search, verify, compare perspectives, and audit a news topic before reading the final briefing.</div>',
    unsafe_allow_html=True,
)

with st.expander("Settings", expanded=False):
    settings_col_1, settings_col_2 = st.columns([2, 1])
    with settings_col_1:
        api_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Uses GEMINI_API_KEY or GOOGLE_API_KEY from the environment when empty.",
        )
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        model_display = st.selectbox(
            "Model Selection",
            options=[
                "Gemini 3.5 Flash (High)",
                "Gemini 3.1 Flash Lite (Low-Cost)",
                "Gemini 3.5 Pro (Premium)",
                "Gemma 2 9B (Open Source)",
            ],
            index=0,
            help="Select the underlying AI model for the agents.",
        )
        MODEL_MAPPING = {
            "Gemini 3.5 Flash (High)": "gemini-3.5-flash",
            "Gemini 3.1 Flash Lite (Low-Cost)": "gemini-3.1-flash-lite",
            "Gemini 3.5 Pro (Premium)": "gemini-3.5-pro",
            "Gemma 2 9B (Open Source)": "gemma2-9b-it",
        }
        selected_model = MODEL_MAPPING[model_display]
    with settings_col_2:
        enable_editor = st.toggle(
            "Allow audit revisions",
            value=True,
            help="Each audited stage can revise up to two times before the safest available output is flagged.",
        )


def start_workflow(
    topic_query: str,
    model_name: str,
    enable_editor_flag: bool,
    bypass_input_check: bool = False,
):
    shared_state = {
        "status": "running",
        "topic": topic_query,
        "current_step": "Spawning pipeline...",
        "progress_logs": [
            {
                "step": "init",
                "message": "Initializing news intelligence desk...",
                "timestamp": time.time(),
            }
        ],
        "results": {
            "reviewed": True,
            "topic": topic_query,
            "optimized_query": topic_query,
            "review_result": {},
            "articles": {},
            "recruitment": {},
            "facts": {},
            "narratives": {},
            "experts": {},
            "outlook": {},
            "public_report": {},
            "public_editor_report": "",
            "editor_logs": [],
            "audit_warnings": [],
            "is_approved": True,
        },
        "control": {"paused": False, "stopped": False},
        "step_statuses": {
            "review": "queued",
            "search": "queued",
            "recruiter": "queued",
            "fact_bias": "queued",
            "dispute": "queued",
            "bias_agent": "queued",
            "expert": "queued",
            "outlook": "queued",
            "public_report": "queued",
            "public_editor": "queued",
        },
        "error": None,
        "model_name": model_name,
    }
    st.session_state["shared_state"] = shared_state
    st.session_state.pop("chat_messages", None)

    # Spawn worker thread
    thread = threading.Thread(
        target=worker_thread_fn,
        args=(
            topic_query,
            enable_editor_flag,
            model_name,
            bypass_input_check,
            shared_state,
        ),
        daemon=True,
    )
    thread.start()


with st.form("analysis_form"):
    topic = st.text_area(
        "Topic, headline, URL, or article text",
        placeholder="Example: Keir Starmer latest resignation rumors",
        height=90,
    )
    submit = st.form_submit_button(
        "Run analysis", type="primary", use_container_width=True
    )

if submit:
    if not topic.strip():
        st.warning("Enter a topic, headline, URL, or article excerpt.")
    else:
        with st.spinner("Checking input suitability..."):
            import asyncio

            from agents.coordinator import NewsAnalysisCoordinator

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                coordinator = NewsAnalysisCoordinator()
                review_result = loop.run_until_complete(
                    coordinator.run_input_check(topic.strip(), selected_model)
                )
            except Exception as e:
                st.error(f"Input Check Agent error: {e}")
                review_result = None
            finally:
                loop.close()

        if review_result:
            is_news = review_result.get("is_news_relevant", True)
            needs_confirm = review_result.get("needs_user_confirmation", False)
            auto_mod = review_result.get("auto_modified", False)
            suggested_options = review_result.get("suggested_options") or []
            issue_type = review_result.get("input_issue_type", "clear_news_query")

            if (
                issue_type != "clear_news_query"
                or not is_news
                or needs_confirm
                or auto_mod
                or suggested_options
            ):
                st.session_state["awaiting_confirmation"] = True
                st.session_state["review_result"] = review_result
                st.session_state["original_topic"] = topic.strip()
                st.session_state["confirmed_model"] = selected_model
                st.rerun()
            else:
                st.session_state["awaiting_confirmation"] = False
                start_workflow(
                    topic.strip(),
                    selected_model,
                    enable_editor,
                    bypass_input_check=True,
                )
                st.rerun()

# Render interactive validation confirmation box
if st.session_state.get("awaiting_confirmation"):
    review = st.session_state["review_result"]
    original_topic = st.session_state["original_topic"]
    confirmed_model = st.session_state["confirmed_model"]

    with st.container(border=True):
        st.warning(
            "⚠️ **Input validation check required**: The Input Check Agent flagged this query."
        )

        issue_type = review.get("input_issue_type", "unsuitable")
        user_msg = (
            review.get("user_message")
            or review.get("rejection_reason")
            or "This query needs refinement."
        )
        st.markdown(f"**Issue Detected**: {issue_type.replace('_', ' ').title()}")
        st.info(f"**Message**: {user_msg}")

        suggested_q = review.get("suggested_query_formulation", original_topic)
        if suggested_q != original_topic:
            st.markdown(f"**Suggested Formulation**: `{suggested_q}`")

        options = review.get("suggested_options") or []

        btn_cols = st.columns([1, 1, 1])

        if suggested_q != original_topic:
            if btn_cols[0].button(
                "Use suggested query", type="primary", use_container_width=True
            ):
                st.session_state["awaiting_confirmation"] = False
                start_workflow(
                    suggested_q, confirmed_model, enable_editor, bypass_input_check=True
                )
                st.rerun()

        if btn_cols[1].button(
            "Continue with original", type="secondary", use_container_width=True
        ):
            st.session_state["awaiting_confirmation"] = False
            start_workflow(
                original_topic, confirmed_model, enable_editor, bypass_input_check=True
            )
            st.rerun()

        if btn_cols[2].button("Cancel", type="secondary", use_container_width=True):
            st.session_state["awaiting_confirmation"] = False
            st.rerun()

        if options:
            st.markdown("### Suggested refinement paths:")
            for idx, option in enumerate(options, 1):
                if st.button(
                    f"Option {idx}: {option}",
                    key=f"opt_btn_{idx}",
                    use_container_width=True,
                ):
                    st.session_state["awaiting_confirmation"] = False
                    start_workflow(
                        option, confirmed_model, enable_editor, bypass_input_check=True
                    )
                    st.rerun()


# --- Display Content Area ---
if "shared_state" not in st.session_state:
    st.info(
        "Enter a news topic above and click 'Run analysis' to start the multi-agent workflow."
    )
    st.stop()

state = st.session_state["shared_state"]
status = state["status"]
results = state["results"]
review = results.get("review_result") or {}
step_statuses = state.get("step_statuses") or {}

# Check for immediate exits (Input Rejection or early search failures)
if results.get("reviewed") is False:
    st.error("Input check rejected this request.")
    render_input_review(review)
    if review.get("suggested_query_formulation"):
        st.info(f"Suggested query: {review['suggested_query_formulation']}")
    st.stop()

if results.get("search_failed"):
    st.warning("Search could not establish enough credible support for this topic.")
    render_input_review(review)
    search_result = results.get("search_result") or results.get("articles") or {}
    st.markdown(f"**Query used:** {results.get('optimized_query', '')}")
    st.markdown(
        f"**Search status:** {search_result.get('search_status', 'unverified')}"
    )
    if search_result.get("verification_summary"):
        st.info(search_result["verification_summary"])
    for warning in search_result.get("warnings", []):
        st.warning(warning)
    render_audit_trail(results)
    st.stop()


# --- Left Sidebar UI Layout ---
with st.sidebar:
    st.markdown("### Workflow Progress & Control")

    if status == "running":
        st.markdown(
            f'<div class="status-indicator running">⚙️ Pipeline Running:<br>'
            f"<strong>{state.get('current_step', 'Processing')}</strong></div>",
            unsafe_allow_html=True,
        )
    elif status == "paused":
        st.markdown(
            '<div class="status-indicator paused">⏸️ Pipeline Paused</div>',
            unsafe_allow_html=True,
        )
    elif status == "stopped":
        st.markdown(
            '<div class="status-indicator stopped">⏹️ Pipeline Stopped (Showing Partial Results)</div>',
            unsafe_allow_html=True,
        )
    elif status == "completed":
        st.markdown(
            '<div class="status-indicator completed">✅ Pipeline Completed Successfully</div>',
            unsafe_allow_html=True,
        )
    elif status == "failed":
        st.markdown(
            f'<div class="status-indicator failed">❌ Pipeline Failed: {state.get("error")}</div>',
            unsafe_allow_html=True,
        )

    # Sidebar controls
    btn_cols = st.columns(2)
    # Pause/Resume Button
    if status == "running":
        if btn_cols[0].button(
            "Pause",
            key="pause_btn",
            type="secondary",
            use_container_width=True,
        ):
            state["control"]["paused"] = True
            state["status"] = "paused"
            st.rerun()
    elif status == "paused":
        if btn_cols[0].button(
            "Resume",
            key="resume_btn",
            type="primary",
            use_container_width=True,
        ):
            state["control"]["paused"] = False
            state["status"] = "running"
            st.rerun()

    # Stop Button
    if status in ["running", "paused"]:
        if btn_cols[1].button(
            "Stop", key="stop_btn", type="primary", use_container_width=True
        ):
            state["control"]["stopped"] = True
            state["control"]["paused"] = False  # Unblock loop
            state["status"] = "stopped"
            st.rerun()

    st.markdown("### Stepper")
    render_progress_stepper(step_statuses)

    # Collapsible Logs
    with st.expander("Execution Logs", expanded=True):
        logs = state.get("progress_logs", [])
        for log in reversed(logs):
            t_str = time.strftime(
                "%H:%M:%S", time.localtime(log.get("timestamp", time.time()))
            )
            st.markdown(f"`{t_str}` - {log.get('message')}")


# --- Tabs Area with Progressive Loading ---
(
    tab_briefing,
    tab_sources,
    tab_facts,
    tab_perspectives,
    tab_experts,
    tab_audit,
    tab_qa,
) = st.tabs(
    [
        "Briefing",
        "Sources",
        "Facts & Timeline",
        "Perspectives & Disputes",
        "Expert & Outlook",
        "Audit Trail",
        "Q&A",
    ]
)

with tab_briefing:
    public_report = results.get("public_report") or {}
    if not public_report:
        st.markdown(
            '<div class="loading-card">'
            "<h3>⏳ Public Briefing Draft In Progress</h3>"
            "<p>The Public Reporter Agent will compile the final executive summary once all prior analytical modules (Facts, Perspectives, Experts) finish processing.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        render_public_summary(results)
        render_recruitment(results.get("recruitment") or {})

with tab_sources:
    articles_data = results.get("articles") or {}
    if not articles_data or not articles_data.get("articles"):
        st.markdown(
            '<div class="loading-card">'
            "<h3>🔍 Source Crawling In Progress</h3>"
            "<p>The Search Agent is currently querying credible global news databases and checking source reliability...</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        render_landscape(articles_data)
        st.divider()
        render_source_table(articles_data.get("articles", []))

with tab_facts:
    facts_data = results.get("facts") or {}
    if not facts_data or (
        not facts_data.get("consensus_facts")
        and not facts_data.get("timeline")
        and not facts_data.get("timeline_events")
    ):
        st.markdown(
            '<div class="loading-card">'
            "<h3>📊 Factual Consensus Extraction Pending</h3>"
            "<p>The Fact & Consensus Analyzer will parse the crawled source articles to extract cross-verified consensus statements and chronological event timelines...</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        render_consensus_and_timeline(facts_data)

with tab_perspectives:
    recruitment = results.get("recruitment") or {}
    recruit_dispute = recruitment.get("recruit_dispute", True)
    recruit_perspective = recruitment.get("recruit_perspective", True)

    if not recruitment:
        st.markdown(
            '<div class="loading-card">'
            "<h3>⚖️ Perspective Analysis Pending</h3>"
            "<p>Waiting for the Orchestrator (Recruiter Agent) to finalize which analytical modules are needed for this topic.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        # Disputes Module
        if recruit_dispute:
            facts_data = results.get("facts") or {}
            disputes = facts_data.get("disputed_claims") or []
            if not disputes and step_statuses.get("dispute") in ["queued", "running"]:
                st.markdown(
                    '<div class="loading-card">'
                    "<h3>🔍 Mapping Contested Claims...</h3>"
                    "<p>The Dispute Agent is active, extracting contradicting assertions from opposing source angles.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                render_disputes(facts_data)
        else:
            st.info(
                "Dispute mapping was skipped for this topic (recruiter determined it is non-recruited)."
            )

        st.divider()

        # Perspectives Module
        if recruit_perspective:
            narratives = results.get("narratives") or {}
            profiles = narratives.get("profiles") or []
            if not profiles and step_statuses.get("bias_agent") in [
                "queued",
                "running",
            ]:
                st.markdown(
                    '<div class="loading-card">'
                    "<h3>⚖️ Profiling Media Framing...</h3>"
                    "<p>The Perspective Agent is active, comparing narratives, loaded keywords, and omissions across outlets.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                render_perspectives(narratives)
        else:
            st.info(
                "Media perspective profiling was skipped for this topic (recruiter determined it is non-recruited)."
            )

with tab_experts:
    recruitment = results.get("recruitment") or {}
    recruit_expert = recruitment.get("recruit_expert", True)
    recruit_outlook = recruitment.get("recruit_future_outlook", True)

    if not recruitment:
        st.markdown(
            '<div class="loading-card">'
            "<h3>💡 Expert Assessment Pending</h3>"
            "<p>Waiting for the Orchestrator (Recruiter Agent) to decide if expert roundtable or scenario modeling is needed.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        # Expert roundtable
        if recruit_expert:
            expert_data = results.get("experts") or {}
            opinions = expert_data.get("expert_opinions") or []
            if not opinions and step_statuses.get("expert") in ["queued", "running"]:
                st.markdown(
                    '<div class="loading-card">'
                    "<h3>🎓 Convening Expert Roundtable...</h3>"
                    "<p>The Expert Agent is drafting domain analysis referencing constitutional, political, and economic frameworks.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                render_experts_and_outlook(expert_data, results.get("outlook") or {})
        else:
            st.info("Expert Roundtable was skipped for this topic.")
            st.divider()
            # Render Outlook separately if expert was skipped but outlook is recruited
            if recruit_outlook:
                outlook = results.get("outlook") or {}
                scenarios = outlook.get("alternative_scenarios") or []
                if not scenarios and step_statuses.get("outlook") in [
                    "queued",
                    "running",
                ]:
                    st.markdown(
                        '<div class="loading-card">'
                        "<h3>🔮 Generating Future Scenarios...</h3>"
                        "<p>The Future Outlook Agent is modeling likelihood bands and monitoring indicators.</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("### Future outlook")
                    if (
                        outlook.get("most_likely_scenario")
                        and outlook.get("most_likely_scenario") != "N/A"
                    ):
                        st.markdown("**Most likely scenario**")
                        st.write(outlook["most_likely_scenario"])
                    # alternative scenarios
                    for scenario in outlook.get("alternative_scenarios") or []:
                        with st.expander(
                            scenario.get("scenario_title", "Alternative scenario"),
                            expanded=False,
                        ):
                            if scenario.get("likelihood_band"):
                                st.caption(scenario["likelihood_band"])
                            st.write(scenario.get("description", ""))
                            for trigger in scenario.get("trigger_conditions", []):
                                st.markdown(f"- {trigger}")
                    indicators = outlook.get("monitoring_indicators") or []
                    if indicators:
                        st.markdown("**Monitoring indicators**")
                        for ind in indicators:
                            st.markdown(f"- {ind}")
            else:
                st.info("Future scenario modeling was skipped for this topic.")

with tab_audit:
    render_audit_trail(results)

with tab_qa:
    if status not in ["completed", "stopped"]:
        st.markdown(
            '<div class="loading-card">'
            "<h3>💬 Follow-up Q&A Locked</h3>"
            "<p>The interactive Q&A assistant will unlock once the workflow finishes or is stopped, allowing you to ask follow-up questions about the report.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        render_qa_tab(results)


# --- Polling / Auto-rerun Loop for Active Running status ---
if status in ["running", "paused"]:
    time.sleep(0.5)
    st.rerun()
