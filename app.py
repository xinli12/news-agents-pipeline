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
        max-width: 1600px;
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
    .status-indicator.stopping {
        background: #fff7ed;
        color: #c2410c;
        border: 1px solid #fed7aa;
        animation: pulse 2s infinite ease-in-out;
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
    .progress-panel {
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 1rem 1.15rem;
        margin: 1rem 0 1.25rem;
    }
    .progress-caption {
        color: var(--muted);
        font-size: 0.88rem;
        margin-top: 0.35rem;
    }
    .stop-callout {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-radius: 8px;
        padding: 0.65rem 0.8rem;
        color: #9a3412;
        font-size: 0.9rem;
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
    .step-card.stopping .step-badge {
        background: #c2410c;
        color: #ffffff;
        border-color: #c2410c;
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


PIPELINE_STEPS = [
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

ACTIVE_RUN_STATUSES = {"running", "paused", "stopping"}
CONTENT_LOADING_STATUSES = {"running", "paused"}


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


def render_loading_card(title: str, body: str) -> None:
    st.markdown(
        '<div class="loading-card">'
        f"<h3>{html.escape(title)}</h3>"
        f"<p>{html.escape(body)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def is_active_run(status: str | None) -> bool:
    return str(status or "") in CONTENT_LOADING_STATUSES


def step_progress_fraction(step_statuses: dict, run_status: str | None) -> float:
    if run_status == "completed":
        return 1.0

    completed_count = 0.0
    for step_key, _ in PIPELINE_STEPS:
        step_status = step_statuses.get(step_key, "queued")
        if step_status in {"completed", "skipped"}:
            completed_count += 1.0
        elif step_status in {"running", "paused"}:
            completed_count += 0.5

    return min(1.0, completed_count / max(len(PIPELINE_STEPS), 1))


def active_step_label(step_statuses: dict, fallback: str | None = None) -> str:
    for step_key, label in PIPELINE_STEPS:
        if step_statuses.get(step_key) in {"running", "paused"}:
            return label
    return fallback or "Waiting for next step"


def run_status_copy(
    status: str | None, step_statuses: dict, current_step: str | None
) -> tuple[str, str, str]:
    detail = current_step or active_step_label(step_statuses)
    status_key = str(status or "running")
    if status_key == "running":
        return "running", "Pipeline running", detail
    if status_key == "paused":
        return "paused", "Pipeline paused", detail
    if status_key == "stopping":
        return (
            "stopping",
            "Stopping analysis",
            "Stop requested. Waiting for the active agent call to unwind.",
        )
    if status_key == "stopped":
        return "stopped", "Pipeline stopped", "Showing partial results from this run."
    if status_key == "completed":
        return "completed", "Pipeline completed", "Final briefing is ready."
    if status_key == "failed":
        return "failed", "Pipeline failed", detail
    return "running", "Pipeline status", detail


def request_stop(state: dict) -> None:
    state.setdefault("control", {})["stopped"] = True
    state.setdefault("control", {})["paused"] = False
    state["status"] = "stopping"
    state["current_step"] = "Stop requested. Waiting for the active agent call to unwind."
    state.setdefault("progress_logs", []).append(
        {
            "step": "stop_requested",
            "message": "Stop requested by user.",
            "timestamp": time.time(),
        }
    )


def display_run_status(state: dict) -> str:
    results = state.get("results") or {}
    if results.get("reviewed") is False:
        return "Input Rejected"
    if results.get("search_failed"):
        return "Search Failed"
    return str(state.get("status", "")).title()


def render_primary_progress(state: dict) -> None:
    status = state.get("status")
    step_statuses = state.get("step_statuses") or {}
    results = state.get("results") or {}
    status_class, title, detail = run_status_copy(
        status, step_statuses, state.get("current_step")
    )
    progress_status = status
    if results.get("reviewed") is False:
        status_class = "failed"
        title = "Input check rejected"
        detail = "The request did not pass the input check."
        progress_status = "failed"
    elif results.get("search_failed"):
        status_class = "failed"
        title = "Source search failed"
        detail = "Search could not establish enough credible support for this topic."
        progress_status = "failed"

    progress = step_progress_fraction(step_statuses, progress_status)

    with st.container(border=True):
        st.markdown(
            f'<div class="status-indicator {html.escape(status_class)}">'
            f"<div><strong>{html.escape(title)}</strong><br>"
            f"<span>{html.escape(detail)}</span></div></div>",
            unsafe_allow_html=True,
        )
        st.progress(progress)
        st.markdown(
            f'<div class="progress-caption">{int(progress * 100)}% complete · '
            f"Current step: {html.escape(active_step_label(step_statuses, detail))}</div>",
            unsafe_allow_html=True,
        )

        if status in {"running", "paused"}:
            stop_col, copy_col = st.columns([1, 2])
            if stop_col.button(
                "Stop analysis now",
                key="main_stop_btn",
                type="primary",
                use_container_width=True,
            ):
                request_stop(state)
                st.rerun()
            copy_col.markdown(
                '<div class="stop-callout">Stop is applied immediately in the UI. '
                "The current agent call may finish before the backend fully stops.</div>",
                unsafe_allow_html=True,
            )
        elif status == "stopping":
            st.warning(
                "Stop requested. The UI is no longer treating this as a normal running state."
            )


def render_run_notices(results: dict) -> None:
    review_res = results.get("review_result") or {}
    if review_res.get("action") == "accept_with_notification":
        st.warning(
            f"⚠️ **Input validation note**: {review_res.get('notification_message')}"
        )

    search_res = results.get("articles") or {}
    search_status_val = str(search_res.get("search_status") or "").lower()
    if search_status_val == "moderate":
        st.warning(
            "⚠️ **Sparse News Pool**: Very few unique search sources (3 to 5 unique articles) were found for this topic. Downstream analysis may be thin or limited."
        )


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
    with st.expander(heading, expanded=False):
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
        raw_neutrality = article.get("neutrality", "")
        if raw_neutrality == "HIGH_NEUTRALITY":
            neutrality = "High Neutrality"
        elif raw_neutrality == "MEDIUM_NEUTRALITY":
            neutrality = "Medium Neutrality"
        elif raw_neutrality == "LOW_NEUTRALITY":
            neutrality = "Low Neutrality"
        else:
            neutrality = raw_neutrality

        rows.append(
            {
                "Publisher": article.get("source", ""),
                "Title": article.get("title", ""),
                "URL": article.get("url", ""),
                "Perspective": article.get("bias_category", ""),
                "Tone Neutrality": neutrality,
                "Summary": article.get("summary", ""),
            }
        )
    return rows


def render_source_table(articles: list[dict]) -> None:
    if not articles:
        st.info("No analyzed sources available.")
        return

    html_lines = []
    html_lines.append("<style>")
    html_lines.append("  .source-table-container { max-height: 450px; overflow-y: auto; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 6px; margin-top: 10px; }")
    html_lines.append("  .source-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }")
    html_lines.append("  .source-table th { position: sticky; top: 0; z-index: 10; background-color: var(--secondary-background-color, #f8f9fa); border-bottom: 2px solid rgba(128, 128, 128, 0.2); padding: 8px 10px; text-align: left; font-weight: 600; }")
    html_lines.append("  .source-table td { border-bottom: 1px solid rgba(128, 128, 128, 0.15); padding: 8px 10px; vertical-align: top; word-wrap: break-word; word-break: break-word; }")
    html_lines.append("  .badge { display: inline-block; padding: 2px 6px; font-size: 0.75rem; font-weight: 600; border-radius: 4px; text-align: center; }")
    html_lines.append("  .badge-left { background-color: rgba(30, 144, 255, 0.15); color: #1e90ff; }")
    html_lines.append("  .badge-right { background-color: rgba(220, 20, 60, 0.15); color: #dc143c; }")
    html_lines.append("  .badge-center { background-color: rgba(255, 140, 0, 0.15); color: #ff8c00; }")
    html_lines.append("  .badge-other { background-color: rgba(128, 128, 128, 0.15); color: #808080; }")
    html_lines.append("  .neut-high { color: #2e7d32; font-weight: bold; }")
    html_lines.append("  .neut-med { color: #ef6c00; font-weight: bold; }")
    html_lines.append("  .neut-low { color: #c62828; font-weight: bold; }")
    html_lines.append("  .expandable-text { position: relative; }")
    html_lines.append("  .full-text { display: none; }")
    html_lines.append("  .toggle-checkbox:checked ~ .full-text { display: inline; }")
    html_lines.append("  .toggle-checkbox:checked ~ .truncated-text { display: none; }")
    html_lines.append("  .toggle-label { color: #1e90ff; cursor: pointer; font-size: 0.8rem; font-weight: 600; display: inline-block; margin-top: 2px; }")
    html_lines.append("  .toggle-label::before { content: 'Show more'; }")
    html_lines.append("  .toggle-checkbox:checked ~ .toggle-label::before { content: 'Show less'; }")
    html_lines.append("</style>")
    html_lines.append("<div class='source-table-container'>")
    html_lines.append("<table class='source-table'>")
    html_lines.append("  <thead>")
    html_lines.append("    <tr>")
    html_lines.append("      <th style='width: 15%;'>Publisher</th>")
    html_lines.append("      <th style='width: 35%;'>Title</th>")
    html_lines.append("      <th style='width: 15%;'>Perspective</th>")
    html_lines.append("      <th style='width: 15%;'>Neutrality</th>")
    html_lines.append("      <th style='width: 20%;'>Summary</th>")
    html_lines.append("    </tr>")
    html_lines.append("  </thead>")
    html_lines.append("  <tbody>")

    for idx, article in enumerate(articles):
        publisher = article.get("source", "")
        title = article.get("title", "")
        url = article.get("url", "")
        perspective = article.get("bias_category", "")

        raw_neutrality = str(article.get("neutrality", "")).strip(" ,\"'").upper().replace(" ", "_")
        if raw_neutrality == "HIGH_NEUTRALITY":
            neutrality = "High Neutrality"
            neut_class = "neut-high"
        elif raw_neutrality == "MEDIUM_NEUTRALITY":
            neutrality = "Medium Neutrality"
            neut_class = "neut-med"
        elif raw_neutrality == "LOW_NEUTRALITY":
            neutrality = "Low Neutrality"
            neut_class = "neut-low"
        else:
            neutrality = article.get("neutrality", "")
            neut_class = ""

        if perspective == "Left":
            badge_class = "badge-left"
        elif perspective == "Right":
            badge_class = "badge-right"
        elif perspective == "Center":
            badge_class = "badge-center"
        else:
            badge_class = "badge-other"

        summary = article.get("summary", "")

        if len(summary) > 120:
            truncated = summary[:120]
            last_space = truncated.rfind(" ")
            if last_space > 80:
                truncated = truncated[:last_space]
            remaining = summary[len(truncated):]

            summary_html = (
                f"<div class='expandable-text'>"
                f"<input type='checkbox' id='toggle-{idx}' class='toggle-checkbox' style='display: none;'>"
                f"<span class='truncated-text'>{truncated}...</span>"
                f"<span class='full-text'>{truncated}{remaining}</span>"
                f"<label for='toggle-{idx}' class='toggle-label'></label>"
                f"</div>"
            )
        else:
            summary_html = summary

        title_html = f"<a href='{url}' target='_blank' style='text-decoration: none; color: inherit; font-weight: 500;'>{title}</a>" if url else title

        html_lines.append(
            f"<tr>"
            f"<td>{publisher}</td>"
            f"<td>{title_html}</td>"
            f"<td><span class='badge {badge_class}'>{perspective}</span></td>"
            f"<td><span class='{neut_class}'>{neutrality}</span></td>"
            f"<td>{summary_html}</td>"
            f"</tr>"
        )

    html_lines.append("  </tbody>")
    html_lines.append("</table>")
    html_lines.append("</div>")

    st.markdown("".join(html_lines), unsafe_allow_html=True)


def render_landscape(articles_data: dict) -> None:
    articles = articles_data.get("articles", [])
    if not articles:
        st.info("No source landscape to display.")
        return

    import pandas as pd

    rows = article_rows(articles)
    df = pd.DataFrame(rows)
    total = len(rows)
    source_balance = articles_data.get("source_balance") or {}

    st.metric("Sources", total)

    if articles_data.get("verification_summary"):
        st.info(articles_data["verification_summary"])

    if source_balance:
        with st.expander("Candidate pool balance", expanded=False):
            st.json(source_balance)

    st.markdown("#### Source mix")
    counts = df["Perspective"].value_counts().reset_index()
    counts.columns = ["Perspective", "Count"]

    import altair as alt

    chart = (
        alt.Chart(counts)
        .mark_arc()
        .encode(
            theta=alt.Theta(field="Count", type="quantitative"),
            color=alt.Color(
                field="Perspective",
                type="nominal",
                scale=alt.Scale(
                    domain=["Left", "Right", "Center", "Other/Non-Political"],
                    range=["blue", "red", "orange", "gray"],
                ),
            ),
            tooltip=["Perspective", "Count"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


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

    structured_timeline = facts.get("timeline") or []
    timeline = facts.get("timeline_events") or []
    timeline_count = len(structured_timeline) if structured_timeline else len(timeline)

    if timeline_count >= 2:
        st.markdown("### Timeline")
        if structured_timeline:
            for event in structured_timeline:
                with st.expander(
                    f"{event.get('date', 'Date unknown')} - {event.get('event', '')}",
                    expanded=False,
                ):
                    render_evidence_items(
                        event.get("evidence", []),
                        heading="Timeline evidence",
                        show_bias=False,
                    )
        else:
            for event in timeline:
                st.markdown(f"- {event}")
    elif timeline_count == 1:
        with st.expander("Timeline detail", expanded=False):
            st.caption(
                "Only one timeline event was extracted, so it is shown as supporting detail."
            )
            if structured_timeline:
                event = structured_timeline[0]
                st.markdown(
                    f"**{event.get('date', 'Date unknown')}** - {event.get('event', '')}"
                )
                render_evidence_items(
                    event.get("evidence", []),
                    heading="Timeline evidence",
                    show_bias=False,
                )
            else:
                st.markdown(f"- {timeline[0]}")
    else:
        st.caption("No multi-event timeline was extracted.")


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


def has_fact_content(facts: dict) -> bool:
    return any(
        facts.get(key)
        for key in (
            "consensus_facts",
            "timeline",
            "timeline_events",
            "disputed_claims",
        )
    )


def render_sources_section(results: dict, status: str) -> None:
    st.markdown("### Sources")
    articles_data = results.get("articles") or {}
    articles = articles_data.get("articles") or []
    if not articles:
        if is_active_run(status):
            render_loading_card(
                "Source search in progress",
                "The Search Agent is selecting and checking credible source articles for this run.",
            )
        else:
            st.info("No analyzed sources are available for this run.")
        return

    render_landscape(articles_data)
    st.divider()
    render_source_table(articles)


def render_facts_disputes_perspectives_section(
    results: dict, step_statuses: dict, status: str
) -> None:
    st.markdown("### Facts, disputes, and perspectives")
    facts_data = results.get("facts") or {}
    narratives = results.get("narratives") or {}
    recruitment = results.get("recruitment") or {}

    if has_fact_content(facts_data):
        render_consensus_and_timeline(facts_data)
    elif is_active_run(status):
        render_loading_card(
            "Factual consensus extraction pending",
            "The Fact & Consensus Analyzer will extract cross-verified facts and timeline details once sources are ready.",
        )
    else:
        st.info("No facts, disputes, or perspectives are available for this run.")

    if not recruitment:
        if is_active_run(status):
            st.caption("Dispute and perspective recruitment is pending.")
        return

    recruit_dispute = recruitment.get("recruit_dispute", True)
    recruit_perspective = recruitment.get("recruit_perspective", True)
    dispute_count = count_items(facts_data.get("disputed_claims"))
    profile_count = count_items(narratives.get("profiles"))
    axis = narratives.get("classification_axis") or "Pending"

    st.markdown("#### Analysis module coverage")
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

    if recruit_dispute:
        disputes = facts_data.get("disputed_claims") or []
        dispute_step = step_statuses.get("dispute")
        if (
            not disputes
            and dispute_step in ["queued", "running"]
            and is_active_run(status)
        ):
            render_loading_card(
                "Mapping contested claims",
                "The Dispute Agent is extracting contradictory assertions from the selected sources.",
            )
        elif not disputes and (
            status in {"stopping", "stopped"} or dispute_step == "stopped"
        ):
            st.info("No dispute output is available from this partial run.")
        else:
            render_disputes(facts_data, results)
    else:
        st.info("Dispute Agent was skipped by the Recruiter Agent.")

    st.divider()

    if recruit_perspective:
        profiles = narratives.get("profiles") or []
        perspective_step = step_statuses.get("bias_agent")
        if (
            not profiles
            and perspective_step in ["queued", "running"]
            and is_active_run(status)
        ):
            render_loading_card(
                "Profiling media framing",
                "The Perspective Agent is comparing narratives, framing terms, and omissions across outlets.",
            )
        elif not profiles and (
            status in {"stopping", "stopped"} or perspective_step == "stopped"
        ):
            st.info("No perspective output is available from this partial run.")
        else:
            render_perspectives(narratives, results)
    else:
        st.info("Perspective Agent was skipped by the Recruiter Agent.")


def render_expert_outlook_section(
    results: dict, step_statuses: dict, status: str
) -> None:
    st.markdown("### Expert and outlook")
    recruitment = results.get("recruitment") or {}
    if not recruitment:
        if is_active_run(status):
            render_loading_card(
                "Expert assessment pending",
                "The Recruiter Agent will decide whether expert roundtable or scenario modeling is needed.",
            )
        else:
            st.info("No expert or outlook analysis is available for this run.")
        return

    recruit_expert = recruitment.get("recruit_expert", True)
    recruit_outlook = recruitment.get("recruit_future_outlook", True)

    if recruit_expert:
        expert_data = results.get("experts") or {}
        opinions = expert_data.get("expert_opinions") or []
        expert_step = step_statuses.get("expert")
        if (
            not opinions
            and expert_step in ["queued", "running"]
            and is_active_run(status)
        ):
            render_loading_card(
                "Convening expert roundtable",
                "The Expert Agent is drafting domain analysis from the verified source record.",
            )
        elif not opinions and (
            status in {"stopping", "stopped"} or expert_step == "stopped"
        ):
            st.info("No expert output is available from this partial run.")
        else:
            render_experts_and_outlook(expert_data, results.get("outlook") or {})
        return

    st.info("Expert Roundtable was skipped for this topic.")
    if not recruit_outlook:
        st.info("Future scenario modeling was skipped for this topic.")
        return

    outlook = results.get("outlook") or {}
    scenarios = outlook.get("alternative_scenarios") or []
    outlook_step = step_statuses.get("outlook")
    if not scenarios and outlook_step in ["queued", "running"] and is_active_run(status):
        render_loading_card(
            "Generating future scenarios",
            "The Future Outlook Agent is modeling likelihood bands and monitoring indicators.",
        )
    elif not scenarios and (
        status in {"stopping", "stopped"} or outlook_step == "stopped"
    ):
        st.info("No future outlook output is available from this partial run.")
    else:
        st.markdown("#### Future outlook")
        render_outlook_scenarios(outlook)


def render_key_facts_summary(facts: dict, status: str) -> None:
    consensus = facts.get("consensus_facts") or []
    if not consensus:
        if is_active_run(status):
            st.caption("Key facts will appear after fact extraction completes.")
        else:
            st.info("No key facts summary is available.")
        return

    for item in consensus[:5]:
        claim = item.get("claim") if isinstance(item, dict) else str(item)
        if claim:
            st.markdown(f"- {claim}")
            if isinstance(item, dict) and item.get("supporting_sources"):
                st.caption(f"Sources: {join_or_dash(item.get('supporting_sources'))}")
    if len(consensus) > 5:
        st.caption(f"{len(consensus) - 5} additional consensus facts in Analysis details.")


def render_briefing_column(results: dict, status: str) -> None:
    st.markdown("## Briefing")
    audit_warnings = results.get("audit_warnings") or []
    if audit_warnings:
        st.warning(
            "Some audit checks did not fully pass. The briefing is shown with unresolved caveats."
        )

    public_report = results.get("public_report") or {}
    title = public_report.get("title") or "News briefing"
    st.markdown(f"### {title}")

    st.markdown("#### TL;DR")
    lead = public_report.get("lead_paragraph")
    if lead:
        st.write(lead)
    elif is_active_run(status):
        render_loading_card(
            "Briefing in progress",
            "The Public Reporter Agent will draft the TL;DR after the analytical modules finish.",
        )
    else:
        st.info("No TL;DR was generated for this run.")

    st.markdown("#### Key takeaways")
    takeaways = public_report.get("key_takeaways") or []
    if takeaways:
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
    elif is_active_run(status):
        st.caption("Key takeaways are pending.")
    else:
        st.info("No key takeaways were generated.")

    st.markdown("#### Key facts summary")
    render_key_facts_summary(results.get("facts") or {}, status)

    if public_report.get("narrative_summary"):
        with st.expander("Narrative synthesis", expanded=False):
            st.write(public_report["narrative_summary"])

    if public_report.get("future_outlook"):
        with st.expander("What to watch next", expanded=False):
            st.write(public_report["future_outlook"])

    editor_report = results.get("public_editor_report")
    if editor_report:
        with st.expander("Full public editor report", expanded=False):
            st.markdown(editor_report, unsafe_allow_html=True)


def render_analysis_details_column(
    results: dict, step_statuses: dict, status: str
) -> None:
    st.markdown("## Analysis details")
    tab_sources, tab_facts, tab_expert = st.tabs([
        "Sources",
        "Facts, Disputes & Perspectives",
        "Expert & Outlook"
    ])
    with tab_sources:
        render_sources_section(results, status)
    with tab_facts:
        render_facts_disputes_perspectives_section(results, step_statuses, status)
    with tab_expert:
        render_expert_outlook_section(results, step_statuses, status)


def render_diagnostics(results: dict, state: dict) -> None:
    audit_count = len(results.get("audit_warnings") or []) + len(
        results.get("editor_logs") or []
    )
    diagnostics_label = "Diagnostics"
    if audit_count:
        diagnostics_label = f"Diagnostics ({audit_count} audit items)"

    with st.expander(diagnostics_label, expanded=False):
        diag_cols = st.columns(3)
        diag_cols[0].metric("Run status", display_run_status(state))
        diag_cols[1].metric("Model", state.get("model_name", ""))
        diag_cols[2].metric("Topic", state.get("topic", ""))

        recruitment = results.get("recruitment") or {}
        if recruitment:
            render_recruitment(recruitment)
            st.divider()

        render_audit_trail(results)


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
    html = ['<div class="stepper-container">']
    for idx, (key, label) in enumerate(PIPELINE_STEPS):
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
        elif status == "stopping":
            badge = "!"

        html.append(
            f'<div class="step-card {status}">'
            f'<span class="step-badge">{badge}</span>'
            f'<span class="step-label">{label}</span>'
            f"</div>"
        )
        if idx < len(PIPELINE_STEPS) - 1:
            html.append('<div class="step-connector"></div>')

    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


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
    previous_state = st.session_state.get("shared_state") or {}
    if previous_state.get("status") in ACTIVE_RUN_STATUSES:
        previous_state.setdefault("control", {})["stopped"] = True
        previous_state.setdefault("control", {})["paused"] = False

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

render_primary_progress(state)

# Check for immediate exits (Input Rejection or early search failures)
if results.get("reviewed") is False:
    st.error("Input check rejected this request.")
    review = results.get("review_result") or {}
    render_input_review(review)
    render_diagnostics(results, state)
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
    render_diagnostics(results, state)
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
    elif status == "stopping":
        st.markdown(
            '<div class="status-indicator stopping">⏳ Stop Requested</div>',
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
            "Stop now", key="stop_btn", type="primary", use_container_width=True
        ):
            request_stop(state)
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


render_run_notices(results)

analysis_col, briefing_col = st.columns([3, 1], gap="large")
with analysis_col:
    render_analysis_details_column(results, step_statuses, status)
with briefing_col:
    render_briefing_column(results, status)

render_diagnostics(results, state)



# --- Polling / Auto-rerun Loop for Active Running status ---
if status in ACTIVE_RUN_STATUSES:
    time.sleep(0.5)
    st.rerun()
