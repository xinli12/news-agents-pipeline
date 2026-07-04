import asyncio
import html
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


def count_items(items: list | None) -> int:
    return len(items or [])

def friendly_agent_name(name: str | None) -> str:
    display_names = {
        "review_agent": "Input Check Agent",
        "review": "Input Check Agent",
        "search_agent": "Search Agent",
        "search": "Search Agent",
        "recruiter_agent": "Recruiter Agent",
        "recruiter": "Recruiter Agent",
        "fact_agent": "Fact & Consensus Agent",
        "fact_bias": "Fact & Consensus Agent",
        "dispute_agent": "Dispute Agent",
        "dispute": "Dispute Agent",
        "bias_agent": "Perspective Agent",
        "expert_agent": "Expert Agent",
        "expert": "Expert Agent",
        "outlook_agent": "Future Outlook Agent",
        "outlook": "Future Outlook Agent",
        "public_reporter_agent": "Public Reporter Agent",
        "public_report": "Public Reporter Agent",
        "public_editor_agent": "Public Editor Agent",
        "public_editor": "Public Editor Agent",
    }
    key = str(name or "")
    if key.endswith("_audit"):
        key = key.removesuffix("_audit")
    return display_names.get(key, key.replace("_", " ").title() or "Agent")


def approval_label(value: bool | None) -> str:
    if value is True:
        return "Approved"
    if value is False:
        return "Needs revision"
    return "Warning"


def feedback_preview(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def render_chips(items: list[tuple[str, str]]) -> None:
    chip_html = []
    for label, state in items:
        safe_label = html.escape(str(label))
        safe_state = html.escape(str(state))
        chip_html.append(f'<span class="status-chip {safe_state}">{safe_label}</span>')
    st.markdown("".join(chip_html), unsafe_allow_html=True)


def support_state(value: str | None, evidence: list[dict] | None) -> tuple[str, str]:
    support = str(value or "").strip()
    support_lower = support.lower()
    if not support:
        support = "Evidence attached" if evidence else "No evidence attached"
    if any(term in support_lower for term in ["weak", "under", "missing", "unsupported"]):
        return support, "warn"
    if evidence:
        return support, ""
    return support, "warn"


def evidence_balance_label(side_a_count: int, side_b_count: int) -> tuple[str, float]:
    if side_a_count == 0 and side_b_count == 0:
        return "No evidence attached", 0.0
    if side_a_count == 0 or side_b_count == 0:
        return "One side weakly supported", 0.25
    larger = max(side_a_count, side_b_count)
    smaller = min(side_a_count, side_b_count)
    if larger - smaller >= 2:
        return "Uneven evidence support", smaller / larger
    return "Reasonably balanced evidence", 1.0


def audit_entries_for(results: dict, agent_names: set[str]) -> list[dict]:
    logs = results.get("editor_logs") or []
    warnings = results.get("audit_warnings") or []
    entries = [
        {**log, "source": "audit log"}
        for log in logs
        if log.get("agent") in agent_names or log.get("step") in agent_names
    ]
    entries.extend(
        {**warning, "source": "unresolved warning"}
        for warning in warnings
        if warning.get("agent") in agent_names or warning.get("step") in agent_names
    )
    return entries


def render_compact_audit(entries: list[dict], heading: str) -> None:
    st.markdown(f"#### {heading}")
    if not entries:
        st.caption("No audit feedback recorded for this board yet.")
        return

    latest = entries[-3:]
    for entry in latest:
        approved = entry.get("approved")
        agent_label = friendly_agent_name(entry.get("agent") or entry.get("step"))
        status = approval_label(approved)
        feedback = entry.get("feedback") or "No detailed feedback provided."
        if approved is False:
            st.warning(f"{agent_label}: {status}")
        elif approved is True:
            st.success(f"{agent_label}: {status}")
        else:
            st.warning(f"{agent_label}: {status}")
        st.caption(feedback_preview(feedback))

        feedback_items = entry.get("audit_feedback") or []
        fixes = entry.get("recommended_fixes") or entry.get("suggestions") or []
        if feedback or feedback_items or fixes:
            with st.expander("Audit details", expanded=False):
                st.write(feedback)
                for item in feedback_items:
                    st.write(item)
                for fix in fixes:
                    st.write(fix)


def render_evidence_items(
    evidence: list[dict], heading: str = "Evidence", max_items: int = 4, show_bias: bool = True
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
        bias = (item.get("bias_category") or "") if show_bias else ""
        quote = item.get("quote") or ""
        meta = " | ".join(part for part in [published, bias] if part)
        link = f'<a href="{url}" target="_blank">{source}</a>' if url else source
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
    action = review.get("action", "accept")
    explanation = review.get("explanation", "")
    notification = review.get("notification_message", "")
    
    chips = [(action.replace("_", " ").title(), "good" if "accept" in action or action == "convert" else "warn")]
    if review.get("is_news_related") is True:
        chips.append(("News Relevant", "good"))
    else:
        chips.append(("Not News Relevant", "warn"))
    render_chips(chips)

    if explanation:
        st.markdown(f"**Decision Reason**: {explanation}")
    if notification:
        st.info(notification)


def article_rows(articles: list[dict]) -> list[dict]:
    rows = []
    for article in articles:
        rows.append(
            {
                "Publisher": article.get("source", ""),
                "Title": article.get("title", ""),
                "URL": article.get("url", ""),
                "Perspective": article.get("bias_category", ""),
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
    avg_obj = sum(row["Objectivity"] for row in rows) / total
    source_balance = articles_data.get("source_balance") or {}

    cols = st.columns(3)
    cols[0].metric("Sources", total)
    cols[1].metric("Avg objectivity", f"{avg_obj:.0%}")
    cols[2].metric("Search status", articles_data.get("search_status", "verified"))

    if articles_data.get("verification_summary"):
        st.info(articles_data["verification_summary"])

    if source_balance:
        with st.expander("Candidate pool balance", expanded=False):
            st.json(source_balance)

    st.markdown("#### Source mix")
    counts = df["Perspective"].value_counts().reset_index()
    counts.columns = ["Perspective", "Count"]
    st.bar_chart(counts, x="Perspective", y="Count", color="Perspective")


def render_public_summary(results: dict) -> None:
    public_report = results.get("public_report") or {}
    audit_warnings = results.get("audit_warnings") or []
    articles_data = results.get("articles") or {}
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
                if isinstance(takeaway, dict):
                    st.markdown(f"- {takeaway.get('point', '')}")
                    links = []
                    for item in takeaway.get("evidence") or []:
                        source = item.get("source") or "Source"
                        url = item.get("url") or ""
                        if url:
                            links.append(f"[{source}]({url})")
                    if links:
                        st.caption("Sources: " + " · ".join(links))
                else:
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
            st.markdown(
                f"**Sources:** {join_or_dash(item.get('supporting_sources'))}"
            )
            render_evidence_items(item.get("evidence", []), show_bias=False)
            explanation = item.get("explanation")
            if explanation:
                with st.expander("Why this is considered a fact", expanded=False):
                    st.write(explanation)

    st.markdown("### Timeline")
    structured_timeline = facts.get("timeline") or []
    if structured_timeline:
        for event in structured_timeline:
            with st.expander(
                f"{event.get('date', 'Date unknown')} - {event.get('event', '')}",
                expanded=False,
            ):
                render_evidence_items(
                    event.get("evidence", []), heading="Timeline evidence", show_bias=False
                )
    else:
        timeline = facts.get("timeline_events") or []
        if not timeline:
            st.info("No timeline was extracted.")
        for event in timeline:
            st.markdown(f"- {event}")


def render_disputes(facts: dict, results: dict | None = None) -> None:
    disputes = facts.get("disputed_claims") or []
    st.markdown("### Dispute board")
    st.caption(
        "Contested claims are shown without implying which side is correct. Evidence limits are called out when available."
    )
    if not disputes:
        st.success("No major disputes found in the selected sources.")
        if results:
            render_compact_audit(
                audit_entries_for(results, {"dispute_agent", "dispute"}),
                "Dispute Agent audit",
            )
        return

    metric_cols = st.columns(3)
    metric_cols[0].metric("Disputes", len(disputes))
    metric_cols[1].metric(
        "Side A evidence",
        sum(count_items(item.get("side_a_evidence")) for item in disputes),
    )
    metric_cols[2].metric(
        "Side B evidence",
        sum(count_items(item.get("side_b_evidence")) for item in disputes),
    )

    if results:
        render_compact_audit(
            audit_entries_for(results, {"dispute_agent", "dispute"}),
            "Dispute Agent audit",
        )

    for idx, item in enumerate(disputes, 1):
        title = item.get("dispute_question") or item.get("claim", "Contested claim")
        with st.expander(
            f"{idx}. {title}",
            expanded=idx == 1,
        ):
            if item.get("claim") and item.get("claim") != title:
                st.markdown(f"**Claim:** {item.get('claim')}")
            if item.get("evidence_warning"):
                st.warning(item["evidence_warning"])

            side_a_evidence = item.get("side_a_evidence", [])
            side_b_evidence = item.get("side_b_evidence", [])
            side_a_count = count_items(side_a_evidence)
            side_b_count = count_items(side_b_evidence)
            balance_label, balance_score = evidence_balance_label(
                side_a_count, side_b_count
            )
            st.markdown("#### Evidence balance")
            balance_cols = st.columns([1, 1, 2])
            balance_cols[0].metric("Side A evidence", side_a_count)
            balance_cols[1].metric("Side B evidence", side_b_count)
            with balance_cols[2]:
                st.caption(balance_label)
                st.progress(balance_score)

            left, right = st.columns(2)
            with left:
                st.markdown("#### Side A")
                side_a_support, side_a_state = support_state(
                    item.get("side_a_support_level"), side_a_evidence
                )
                render_chips(
                    [
                        (f"{count_items(side_a_evidence)} evidence items", side_a_state),
                        (side_a_support, side_a_state),
                    ]
                )
                st.write(item.get("side_a_assertion", ""))
                st.caption(f"Sources: {join_or_dash(item.get('side_a_sources'))}")
                render_evidence_items(side_a_evidence, "Side A evidence", 4)
            with right:
                st.markdown("#### Side B")
                side_b_support, side_b_state = support_state(
                    item.get("side_b_support_level"), side_b_evidence
                )
                render_chips(
                    [
                        (f"{count_items(side_b_evidence)} evidence items", side_b_state),
                        (side_b_support, side_b_state),
                    ]
                )
                st.write(item.get("side_b_assertion", ""))
                st.caption(f"Sources: {join_or_dash(item.get('side_b_sources'))}")
                render_evidence_items(side_b_evidence, "Side B evidence", 4)


def render_perspectives(narratives: dict, results: dict | None = None) -> None:
    profiles = narratives.get("profiles") or []
    st.markdown("### Perspective board")
    axis = narratives.get("classification_axis") or ""
    if axis:
        st.info(
            f"Selected perspective axis: {axis}. This grouping is based on the article set."
        )
    st.caption(
        "Narratives are grouped by the best-supported classification axis. Inferences are labelled separately from reported perspectives."
    )

    unsupported = narratives.get("unsupported_perspectives") or []
    if unsupported:
        with st.expander("Unsupported but relevant perspectives", expanded=True):
            for item in unsupported:
                st.warning(item)

    if results:
        render_compact_audit(
            audit_entries_for(results, {"bias_agent", "bias_agent_audit"}),
            "Perspective Agent audit",
        )

    if not profiles:
        st.info("No perspective profiles returned yet.")
        return

    import pandas as pd

    coverage_rows = []
    for profile in profiles:
        evidence = profile.get("evidence") or []
        representative_sources = profile.get("representative_sources") or []
        support_status = profile.get("support_status") or (
            "analytical inference"
            if profile.get("is_speculative")
            else "reported perspective from sources"
        )
        coverage_rows.append(
            {
                "Perspective group": profile.get("perspective_group", "Perspective"),
                "Support status": support_status,
                "Evidence": count_items(evidence),
                "Sources": count_items(representative_sources),
                "Inference?": "Yes"
                if profile.get("analytical_inference") or profile.get("is_speculative")
                else "No",
                "Unsupported warning?": "Yes"
                if profile.get("unsupported_warning")
                else "No",
            }
        )

    st.markdown("#### Coverage overview")
    st.dataframe(
        pd.DataFrame(coverage_rows),
        use_container_width=True,
        hide_index=True,
    )

    cols = st.columns(min(3, len(profiles)))
    for idx, profile in enumerate(profiles):
        with cols[idx % len(cols)]:
            title = profile.get("perspective_group", "Perspective")
            if profile.get("is_speculative"):
                title = f"{title} (speculative)"
            with st.container(border=True):
                st.markdown(f"#### {title}")
                support_status = profile.get("support_status") or (
                    "analytical inference"
                    if profile.get("is_speculative")
                    else "reported perspective from sources"
                )
                support_lower = support_status.lower()
                support_chip = "warn" if "inference" in support_lower else "good"
                chips = [(support_status, support_chip)]
                evidence = profile.get("evidence", [])
                evidence_state = "" if evidence else "warn"
                chips.append((f"{count_items(evidence)} evidence items", evidence_state))
                if profile.get("unsupported_warning"):
                    chips.append(("not enough source support found", "warn"))
                render_chips(chips)

                st.write(profile.get("core_narrative", ""))
                st.markdown("**Arguments**")
                for arg in profile.get("key_arguments", []):
                    st.markdown(f"- {arg}")

                if profile.get("analytical_inference"):
                    st.warning("Analytical inference, not direct reporting.")
                    st.write(profile["analytical_inference"])

                if profile.get("unsupported_warning"):
                    st.warning(profile["unsupported_warning"])

                omissions = profile.get("notable_omissions") or []
                if omissions:
                    st.markdown("**Notable omissions**")
                    for omission in omissions:
                        st.markdown(f"- {omission}")
                if profile.get("representative_sources"):
                    st.caption(
                        "Representative sources: "
                        + join_or_dash(profile.get("representative_sources"))
                    )
                if evidence:
                    with st.expander("Evidence trail", expanded=False):
                        render_evidence_items(evidence, "Perspective evidence", 4)
                if profile.get("common_emotional_triggers"):
                    st.caption(
                        "Framing terms: "
                        + ", ".join(profile.get("common_emotional_triggers", []))
                    )

    if narratives.get("key_rhetorical_differences"):
        st.info(narratives["key_rhetorical_differences"])


def render_scenario_details(scenario: dict) -> None:
    if scenario.get("likelihood_band"):
        st.caption(scenario["likelihood_band"])
    st.write(scenario.get("description", ""))
    triggers = scenario.get("trigger_conditions") or []
    if triggers:
        st.markdown("**Trigger conditions**")
        for trigger in triggers:
            st.markdown(f"- {trigger}")
    assumptions = scenario.get("assumptions") or []
    if assumptions:
        st.markdown("**Assumptions**")
        for assumption in assumptions:
            st.markdown(f"- {assumption}")
    render_evidence_items(scenario.get("supporting_evidence") or [], "Evidence", 3)


def render_outlook_scenarios(outlook: dict) -> None:
    most_likely = outlook.get("most_likely_scenario")
    if isinstance(most_likely, dict) and most_likely:
        st.markdown(
            f"**Most likely scenario: {most_likely.get('scenario_title', '')}**"
        )
        render_scenario_details(most_likely)
    elif isinstance(most_likely, str) and most_likely and most_likely != "N/A":
        st.markdown("**Most likely scenario**")
        st.write(most_likely)
    else:
        st.info("No future outlook scenarios available.")

    for scenario in outlook.get("alternative_scenarios") or []:
        with st.expander(
            scenario.get("scenario_title", "Alternative scenario"), expanded=False
        ):
            render_scenario_details(scenario)

    indicators = outlook.get("monitoring_indicators") or []
    if indicators:
        st.markdown("**Monitoring indicators**")
        for indicator in indicators:
            st.markdown(f"- {indicator}")
    if outlook.get("time_horizon"):
        st.caption(f"Time horizon: {outlook['time_horizon']}")
    if outlook.get("confidence_statement"):
        st.caption(outlook["confidence_statement"])


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
                if opinion.get("supporting_evidence"):
                    render_evidence_items(
                        opinion.get("supporting_evidence"),
                        heading="Supporting evidence",
                        show_bias=False,
                    )
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
    render_outlook_scenarios(outlook)


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


def render_audit_trail(results: dict) -> None:
    warnings = results.get("audit_warnings") or []
    logs = results.get("editor_logs") or []
    if warnings:
        st.markdown("### Unresolved warnings")
        for warning in warnings:
            agent_label = friendly_agent_name(warning.get("agent") or warning.get("step"))
            st.warning(f"{agent_label}: {warning.get('feedback')}")
            fixes = warning.get("recommended_fixes") or []
            if fixes:
                with st.expander("Recommended fixes", expanded=False):
                    for fix in fixes:
                        st.write(fix)

    st.markdown("### Audit loop")
    if not logs:
        st.info("No audit logs were recorded.")
        return

    import pandas as pd

    rows = [
        {
            "Agent": friendly_agent_name(log.get("agent")),
            "Stage": friendly_agent_name(log.get("step")),
            "Attempt": log.get("attempt", ""),
            "Status": approval_label(log.get("approved")),
            "Feedback Preview": feedback_preview(log.get("feedback", "")),
        }
        for log in logs
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for log in logs:
        approved = log.get("approved", False)
        label = approval_label(approved)
        agent_label = friendly_agent_name(log.get("agent"))
        with st.expander(
            f"{agent_label} attempt {log.get('attempt', '')}: {label}",
            expanded=not approved,
        ):
            if log.get("feedback"):
                st.markdown("**Full feedback**")
                st.write(log["feedback"])
            feedback_items = log.get("audit_feedback") or []
            if feedback_items:
                st.markdown("**Audit feedback**")
                for item in feedback_items:
                    st.write(item)
            fixes = log.get("recommended_fixes") or []
            if fixes:
                st.markdown("**Recommended fixes**")
                for fix in fixes:
                    st.write(fix)


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

                import datetime
                now = datetime.datetime.now()
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                local_date = now.strftime('%B %d, %Y')
                utc_date = now_utc.strftime('%B %d, %Y')
                current_date_prefix = (
                    f"The current date is {local_date} (local system time) / {utc_date} (UTC). "
                    f"Note: news articles may be dated 1 day ahead or behind due to international timezone differences; "
                    f"treat such minor discrepancies as valid and current, not as future events or hallucinations.\n\n"
                )
                if hasattr(qa_agent, "instruction") and qa_agent.instruction and not qa_agent.instruction.startswith("The current date is"):
                    qa_agent.instruction = current_date_prefix + qa_agent.instruction

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
                "Gemma 4 (Open Source)",
                "Gemini 3.5 Flash (High)",
                "Gemini 3.1 Flash Lite (Low-Cost)",
                "Gemini 3.5 Pro (Premium)",
            ],
            index=0,
            help="Select the underlying AI model for the agents.",
        )
        MODEL_MAPPING = {
            "Gemini 3.5 Flash (High)": "gemini-3.5-flash",
            "Gemini 3.1 Flash Lite (Low-Cost)": "gemini-3.1-flash-lite",
            "Gemini 3.5 Pro (Premium)": "gemini-3.5-pro",
            "Gemma 4 (Open Source)": "gemma-4-26b-a4b-it",
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
        st.session_state["awaiting_confirmation"] = False
        start_workflow(
            topic.strip(),
            selected_model,
            enable_editor,
            bypass_input_check=False,
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
step_statuses = state.get("step_statuses") or {}

# Check for immediate exits (Input Rejection or early search failures)
if results.get("reviewed") is False:
    st.error("Input check rejected this request.")
    review = results.get("review_result") or {}
    render_input_review(review)
    st.stop()

if results.get("search_failed"):
    st.warning("Search could not establish enough credible support for this topic.")
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
    review_res = results.get("review_result") or {}
    if review_res.get("action") == "accept_with_notification":
        st.warning(f"⚠️ **Input validation note**: {review_res.get('notification_message')}")

    search_res = results.get("articles") or {}
    search_status_val = str(search_res.get("search_status") or "").lower()
    if search_status_val == "moderate":
        st.warning("⚠️ **Sparse News Pool**: Very few unique search sources (3 to 5 unique articles) were found for this topic. Downstream analysis may be thin or limited.")

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
            "<p>The Search Agent is currently querying credible global news databases and selecting reliable articles...</p>"
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
    facts_data = results.get("facts") or {}
    narratives = results.get("narratives") or {}
    dispute_count = count_items(facts_data.get("disputed_claims"))
    profile_count = count_items(narratives.get("profiles"))
    axis = narratives.get("classification_axis") or "Pending"

    if not recruitment:
        st.markdown(
            '<div class="loading-card">'
            "<h3>⚖️ Perspective Analysis Pending</h3>"
            "<p>Waiting for the Orchestrator (Recruiter Agent) to finalize which analytical modules are needed for this topic.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("### Perspectives & Disputes")
        overview_cols = st.columns(4)
        overview_cols[0].metric(
            "Dispute Agent", "Recruited" if recruit_dispute else "Skipped"
        )
        overview_cols[1].metric("Disputes", dispute_count)
        overview_cols[2].metric(
            "Perspective Agent", "Recruited" if recruit_perspective else "Skipped"
        )
        overview_cols[3].metric("Perspective groups", profile_count)
        if recruit_perspective:
            st.caption(f"Perspective axis: {axis}")

        # Disputes Module
        if recruit_dispute:
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
                render_disputes(facts_data, results)
        else:
            st.info(
                "Dispute Agent was skipped by the Recruiter Agent."
            )

        st.divider()

        # Perspectives Module
        if recruit_perspective:
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
                render_perspectives(narratives, results)
        else:
            st.info(
                "Perspective Agent was skipped by the Recruiter Agent."
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
                    render_outlook_scenarios(outlook)
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
