import argparse
import asyncio
import logging
import os
import re
import sys

from dotenv import load_dotenv
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from agents.app_utils.run_metrics import STEP_KEYS, STEP_LABELS
from agents.coordinator import NewsAnalysisCoordinator

# Configure logging to print SDK info and harness stderr logs
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Load environment variables (e.g., GEMINI_API_KEY / GOOGLE_API_KEY)
load_dotenv()

# Bypass proxy for local connections (critical for on-the-fly websocket servers spawned by the SDK)
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

# Map GOOGLE_API_KEY to GEMINI_API_KEY if not explicitly set
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]

console = Console()


def pipeline_progress_fraction(step_statuses: dict) -> float:
    """Fraction of the pipeline's fixed step list that's completed/running, 0.0-1.0."""
    completed = 0.0
    for key in STEP_KEYS:
        status = step_statuses.get(key, "queued")
        if status in ("completed", "skipped"):
            completed += 1.0
        elif status in ("running", "paused"):
            completed += 0.5
    return min(1.0, completed / len(STEP_KEYS))


def active_step_label(step_statuses: dict, fallback: str) -> str:
    for key in STEP_KEYS:
        if step_statuses.get(key) in ("running", "paused"):
            return STEP_LABELS.get(key, key)
    return fallback


def make_score_meter(score: float, width: int = 10) -> str:
    """Helper to draw a colored progress bar/meter for scores between 0.0 and 1.0."""
    filled = round(score * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    percent = f"{score * 100:.0f}%"

    if score >= 0.80:
        color = "green"
    elif score >= 0.60:
        color = "yellow"
    else:
        color = "red"

    return f"[{color}]{bar}[/{color}] {percent}"


def format_evidence_items(evidence: list[dict], max_items: int = 3) -> str:
    lines = []
    for item in (evidence or [])[:max_items]:
        source = escape(item.get("source", "Unknown source"))
        title = escape(item.get("title", ""))
        url = escape(item.get("url", ""))
        published = escape(item.get("published_date", ""))
        bias = escape(item.get("bias_category", ""))
        quote = escape(item.get("quote", ""))
        meta = ", ".join(part for part in [published, bias] if part)
        meta_text = f" ({meta})" if meta else ""

        if url:
            lines.append(f"• {source}: {url}\n  {title}{meta_text}")
        else:
            lines.append(f"• {source}: {title}{meta_text}")
        if quote:
            lines.append(f'  Quote: "{quote}"')

    if evidence and len(evidence) > max_items:
        lines.append(f"• +{len(evidence) - max_items} more evidence items")
    return "\n".join(lines) or "No evidence trail available."


def render_recruitment_panel(recruitment: dict) -> None:
    """Mirrors the Streamlit Briefing tab's recruitment decision block."""
    if not recruitment:
        return
    table = Table(title="[bold]Recruitment Decision[/bold]", expand=True)
    table.add_column("Module", style="cyan")
    table.add_column("Status", justify="center")
    for label, recruit_key in (
        ("Dispute Agent", "recruit_dispute"),
        ("Perspective Agent", "recruit_perspective"),
        ("Expert Agent", "recruit_expert"),
        ("Future Outlook Agent", "recruit_future_outlook"),
    ):
        recruited = recruitment.get(recruit_key, True)
        status = "[green]Recruited[/green]" if recruited else "[dim]Skipped[/dim]"
        table.add_row(label, status)
    console.print(table)

    justification = recruitment.get("recruitment_justification", "")
    if justification:
        console.print(
            Panel(
                escape(justification),
                title="[bold]Recruitment Rationale[/bold]",
                border_style="dim",
                expand=True,
            )
        )
    console.print()


def render_public_report_panel(public_report: dict) -> None:
    """Mirrors the Streamlit Briefing tab's public report/summary block."""
    if not public_report:
        return
    title = public_report.get("title") or "News briefing"
    lines = [
        escape(public_report.get("lead_paragraph") or "No public summary was generated.")
    ]

    takeaways = public_report.get("key_takeaways") or []
    if takeaways:
        lines.append("\n[bold]Key Takeaways[/bold]")
        for takeaway in takeaways:
            if isinstance(takeaway, dict):
                point = escape(takeaway.get("point", ""))
                sources = ", ".join(
                    escape(item.get("source", "Source"))
                    for item in takeaway.get("evidence") or []
                    if item.get("url")
                )
                line = f"• {point}"
                if sources:
                    line += f" [dim]({sources})[/dim]"
            else:
                line = f"• {escape(str(takeaway))}"
            lines.append(line)

    if public_report.get("narrative_summary"):
        lines.append(
            f"\n[bold]Perspective Synthesis:[/bold] {escape(public_report['narrative_summary'])}"
        )
    if public_report.get("future_outlook"):
        lines.append(
            f"\n[bold]What To Watch Next:[/bold] {escape(public_report['future_outlook'])}"
        )

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold]{escape(title)}[/bold]",
            border_style="green",
            expand=True,
        )
    )
    console.print()


def render_outlook_panel(outlook: dict) -> None:
    """Mirrors the Streamlit Expert & Outlook tab's future scenarios block."""
    if not outlook:
        return
    most_likely = outlook.get("most_likely_scenario")
    alternatives = outlook.get("alternative_scenarios") or []
    if not (isinstance(most_likely, dict) and most_likely) and not alternatives:
        return

    console.print("[bold yellow]━━━ Future Outlook & Scenarios ━━━[/bold yellow]\n")

    if isinstance(most_likely, dict) and most_likely:
        console.print(
            Panel(
                f"{escape(most_likely.get('description', ''))}\n\n"
                f"[dim]Likelihood: {escape(most_likely.get('likelihood_band', ''))}[/dim]",
                title=f"[bold]Most Likely: {escape(most_likely.get('scenario_title', ''))}[/bold]",
                border_style="green",
                expand=True,
            )
        )

    for alt in alternatives:
        console.print(
            Panel(
                f"{escape(alt.get('description', ''))}\n\n"
                f"[dim]Likelihood: {escape(alt.get('likelihood_band', ''))}[/dim]",
                title=f"[bold]Alternative: {escape(alt.get('scenario_title', ''))}[/bold]",
                border_style="yellow",
                expand=True,
            )
        )

    indicators = outlook.get("monitoring_indicators") or []
    if indicators:
        console.print(
            Panel(
                "\n".join(f"• {escape(indicator)}" for indicator in indicators),
                title="[bold]Monitoring Indicators[/bold]",
                border_style="dim",
                expand=True,
            )
        )
    console.print()


def render_audit_trail_panel(
    editor_logs: list[dict], audit_warnings: list[dict]
) -> None:
    """Mirrors the Streamlit "Why trust this analysis?" panel's log table and unresolved warnings."""
    if not editor_logs and not audit_warnings:
        return

    console.print("[bold]━━━ Audit Trail ━━━[/bold]\n")

    if audit_warnings:
        for warning in audit_warnings:
            console.print(
                f"[bold yellow]⚠[/bold yellow] {escape(warning.get('agent', 'Agent'))}: "
                f"{escape(warning.get('feedback', ''))}"
            )
        console.print()

    if editor_logs:
        table = Table(title="[bold]Audit Log[/bold]", expand=True)
        table.add_column("Agent", style="cyan")
        table.add_column("Attempt", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Feedback")
        for log in editor_logs:
            approved = log.get("approved")
            if approved is True:
                status = "[green]Approved[/green]"
            elif approved is False:
                status = "[red]Needs revision[/red]"
            else:
                status = "[yellow]Warning[/yellow]"
            table.add_row(
                escape(str(log.get("agent", ""))),
                str(log.get("attempt", "")),
                status,
                escape(str(log.get("feedback", "")))[:160],
            )
        console.print(table)
        console.print()


_DETAILS_SUMMARY_RE = re.compile(r"<details>\s*\n<summary>(.*?)</summary>", re.DOTALL)


def _flatten_report_html(markdown_report: str) -> str:
    """Rich's Markdown renderer drops raw HTML, so turn the report's folded
    <details>/<summary> blocks into plain headings before rendering in the terminal."""
    text = _DETAILS_SUMMARY_RE.sub(lambda m: f"\n### {m.group(1)}\n", markdown_report)
    return text.replace("</details>", "")


def render_dashboard_report_panel(markdown_report: str) -> None:
    """Mirrors the Streamlit Briefing tab's folded 'Full public editor report'."""
    if not markdown_report:
        return
    console.print("[bold]━━━ Consolidated Dashboard Report ━━━[/bold]\n")
    console.print(
        Panel(
            Markdown(_flatten_report_html(markdown_report)),
            border_style="dim",
            expand=True,
        )
    )
    console.print()


async def run_cli(topic: str):
    console.print("\n[bold blue]📰 NewsLens Multi-Agent Desk[/bold blue]")
    console.print(f'[bold dim]Topic:[/bold dim] [yellow]"{topic}"[/yellow]')
    console.print(
        "[bold dim]Mode:[/bold dim] [magenta]Live DuckDuckGo News Search[/magenta]\n"
    )

    coordinator = NewsAnalysisCoordinator()
    control_state: dict = {}

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold green]{task.fields[label]}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    progress_task = progress.add_task("pipeline", total=100, label="Starting...")

    async def progress_callback(step: str, message: str, payload: dict | None = None):
        step_statuses = control_state.get("step_statuses", {})
        progress.update(
            progress_task,
            completed=pipeline_progress_fraction(step_statuses) * 100,
            label=active_step_label(step_statuses, message),
        )

        # Determine icon based on step status
        if step.endswith("_complete") or step == "editor_approved":
            icon = "✅"
        elif step == "editor_rejected" or step == "review_failed":
            icon = "⚠️"
        else:
            icon = "🔹"

        console.print(f"{icon} [bold green]{message}[/bold green]")

        if payload:
            if step == "search_complete":
                # Render the articles table
                sources_table = Table(
                    title="[bold]Analyzed Articles & References[/bold]", expand=True
                )
                sources_table.add_column("#", width=3, justify="center")
                sources_table.add_column("Title & URL", style="cyan")
                sources_table.add_column("Source", style="green")
                sources_table.add_column("Bias Rating", justify="center")
                sources_table.add_column("Tone Neutrality", justify="center")

                for idx, art in enumerate(payload.get("articles", []), 1):
                    bias = art.get("bias_category", "Unknown")
                    bias_color = (
                        "red"
                        if bias == "Right"
                        else "blue"
                        if bias == "Left"
                        else "green"
                        if bias == "Center"
                        else "magenta"
                    )

                    title_url = f"[bold]{art.get('title', '')}[/bold]\n[dim]{art.get('url', '')}[/dim]"
                    raw_neutrality = art.get("neutrality", "Unknown")
                    if raw_neutrality == "HIGH_NEUTRALITY":
                        neutrality = "High Neutrality"
                        neut_color = "green"
                    elif raw_neutrality == "MEDIUM_NEUTRALITY":
                        neutrality = "Medium Neutrality"
                        neut_color = "orange"
                    elif raw_neutrality == "LOW_NEUTRALITY":
                        neutrality = "Low Neutrality"
                        neut_color = "red"
                    else:
                        neutrality = raw_neutrality
                        neut_color = "white"

                    sources_table.add_row(
                        str(idx),
                        title_url,
                        art.get("source", ""),
                        f"[bold {bias_color}]{bias}[/bold {bias_color}]",
                        f"[bold {neut_color}]{neutrality}[/bold {neut_color}]",
                    )
                console.print(sources_table)
                console.print()

            elif step == "fact_bias_complete":
                # Render consensus facts, disputed claims, and chronological timeline
                facts_data = payload.get("facts", {})
                narratives_data = payload.get("narratives", {})

                consensus_table = Table(
                    title="[bold green]Consensus Facts (Cross-Verified)[/bold green]",
                    expand=True,
                )
                consensus_table.add_column("Fact/Claim", style="cyan")
                consensus_table.add_column("Supporting Sources", style="dim green")
                consensus_table.add_column("Evidence Trail", style="dim")
                consensus_table.add_column("Cross-Verification Score", justify="right")

                for item in facts_data.get("consensus_facts", []):
                    sources = ", ".join(item.get("supporting_sources", []))
                    evidence = format_evidence_items(item.get("evidence", []))
                    meter = make_score_meter(item.get("cross_verification_score", 0.0))
                    consensus_table.add_row(
                        item.get("claim", ""), sources, evidence, meter
                    )

                dispute_table = Table(
                    title="[bold red]Contested Claims & Disputes[/bold red]",
                    expand=True,
                )
                dispute_table.add_column("Topic/Claim", style="bold cyan")
                dispute_table.add_column("Side A Assertion (Sources)", style="red")
                dispute_table.add_column("Side B Assertion (Sources)", style="blue")

                for item in facts_data.get("disputed_claims", []):
                    side_a_evidence = format_evidence_items(
                        item.get("side_a_evidence", []), max_items=2
                    )
                    side_b_evidence = format_evidence_items(
                        item.get("side_b_evidence", []), max_items=2
                    )
                    side_a = (
                        f"{item.get('side_a_assertion', '')}\n"
                        f"[dim]Sources: {', '.join(item.get('side_a_sources', []))}[/dim]\n"
                        f"[dim]Evidence:\n{side_a_evidence}[/dim]"
                    )
                    side_b = (
                        f"{item.get('side_b_assertion', '')}\n"
                        f"[dim]Sources: {', '.join(item.get('side_b_sources', []))}[/dim]\n"
                        f"[dim]Evidence:\n{side_b_evidence}[/dim]"
                    )
                    dispute_table.add_row(item.get("claim", ""), side_a, side_b)

                timeline_text = "\n".join(
                    [f"• {event}" for event in facts_data.get("timeline_events", [])]
                )
                timeline_panel = Panel(
                    timeline_text or "No timeline events extracted.",
                    title="[bold blue]Chronological Timeline of Events[/bold blue]",
                    border_style="blue",
                    expand=True,
                )

                console.print(consensus_table)
                console.print()
                console.print(dispute_table)
                console.print()
                console.print(timeline_panel)
                console.print()

                console.print(
                    "[bold magenta]━━━ Media Perspectives & Narrative Framing ━━━[/bold magenta]\n"
                )
                for profile in narratives_data.get("profiles", []):
                    group = profile.get("perspective_group", "Unknown")
                    color = (
                        "red"
                        if "Right" in group
                        else "blue"
                        if "Left" in group
                        else "green"
                        if "Centr" in group
                        else "magenta"
                    )

                    args = "\n".join(
                        [f"  - {arg}" for arg in profile.get("key_arguments", [])]
                    )
                    triggers = ", ".join(profile.get("common_emotional_triggers", []))
                    omissions = (
                        "\n".join(
                            [f"  - {om}" for om in profile.get("notable_omissions", [])]
                        )
                        or "  - None identified"
                    )

                    profile_content = (
                        f"[bold underline]Core Narrative:[/bold underline]\n{profile.get('core_narrative', '')}\n\n"
                        f"[bold underline]Key Arguments Highlighted:[/bold underline]\n{args}\n\n"
                        f"[bold underline]Emotional Triggers / Loaded Terms:[/bold underline] [italic]{triggers}[/italic]\n\n"
                        f"[bold underline]Notable Omissions (What they left out):[/bold underline]\n{omissions}"
                    )

                    console.print(
                        Panel(
                            profile_content,
                            title=f"[bold {color}]{group} Outlets[/bold {color}]",
                            border_style=color,
                            expand=True,
                        )
                    )
                    console.print()

                rhetoric_panel = Panel(
                    narratives_data.get("key_rhetorical_differences", ""),
                    title="[bold yellow]Rhetorical & Linguistic Contrast Summary[/bold yellow]",
                    border_style="yellow",
                    expand=True,
                )
                console.print(rhetoric_panel)
                console.print()

            elif step == "expert_complete":
                # Render expert panel opinions
                experts_data = payload
                console.print(
                    "[bold yellow]━━━ Expert Roundtable Panel Review ━━━[/bold yellow]\n"
                )

                expert_cards = []
                for opinion in experts_data.get("expert_opinions", []):
                    exp_name = opinion.get("expert_name", "")
                    exp_field = opinion.get("expertise_area", "")
                    exp_text = opinion.get("commentary", "")
                    citations = (
                        "\n".join(
                            [f"• {c}" for c in opinion.get("cited_references", [])]
                        )
                        or "• None cited"
                    )
                    readings = "\n".join(
                        [
                            f"• {r}"
                            for r in opinion.get("recommended_reading_or_context", [])
                        ]
                    )

                    card_content = (
                        f"[bold italic]{exp_field}[/bold italic]\n\n"
                        f"{exp_text}\n\n"
                        f"[bold underline]Citations/Anchored Materials:[/bold underline]\n{citations}\n\n"
                        f"[bold underline]Recommended Context/Resources:[/bold underline]\n{readings}"
                    )
                    expert_cards.append(
                        Panel(
                            card_content,
                            title=f"[bold cyan]{exp_name}[/bold cyan]",
                            border_style="cyan",
                            width=38,
                        )
                    )

                console.print(Columns(expert_cards, expand=True))
                console.print()

                summary_panel = Panel(
                    experts_data.get("roundtable_summary", ""),
                    title="[bold green]Roundtable Synthesis[/bold green]",
                    border_style="green",
                    expand=True,
                )
                console.print(summary_panel)
                console.print()

            elif step == "outlook_complete":
                render_outlook_panel(payload if isinstance(payload, dict) else {})

            elif step == "recruiter_complete":
                render_recruitment_panel(payload)

            elif step == "public_report_complete":
                render_public_report_panel(payload)

            elif step == "public_editor_complete":
                render_dashboard_report_panel(payload if isinstance(payload, str) else "")

            elif step == "editor_complete":
                is_approved = payload.get("is_approved", True)
                editor_logs = payload.get("editor_logs", [])
                audit_warnings = payload.get("audit_warnings", [])
                if not is_approved and editor_logs:
                    last_log = editor_logs[-1]
                    feedback = last_log.get("feedback", "")
                    suggestions = "\n".join(
                        [f"• {s}" for s in last_log.get("suggestions", [])]
                    )
                    console.print(
                        Panel(
                            f"[bold red]⚠️  WARNING: Editor-in-Chief Audit Loop Rejected This Draft[/bold red]\n\n"
                            f"[bold]Feedback:[/bold] {feedback}\n"
                            f"[bold]Revision Directives:[/bold]\n{suggestions}",
                            title="Editor-in-Chief Disclaimer",
                            border_style="yellow",
                            expand=True,
                        )
                    )
                    console.print()
                render_audit_trail_panel(editor_logs, audit_warnings)

    try:
        with progress:
            results = await coordinator.analyze(
                topic, progress_callback, control_state=control_state
            )
            progress.update(progress_task, completed=100, label="Done")

        # Check if the audit input check rejected the query
        if not results.get("input_checked", True):
            input_check = results["input_check_result"]
            console.print("\n[bold red]✖ Input Check Rejected![/bold red]")
            console.print(
                Panel(
                    f"[bold]Action:[/bold] {input_check.get('action', 'reject_with_confirmation')}\n"
                    f"[bold]Reason:[/bold] {input_check.get('explanation', 'Not news-relevant or safe.')}\n\n"
                    f"{input_check.get('notification_message', '')}",
                    title="Input Moderation Audit Result",
                    border_style="red",
                )
            )
            return

        input_check_res = results.get("input_check_result", {})
        if input_check_res.get("action") == "accept_with_notification":
            console.print(
                Panel(
                    f"[bold yellow]⚠️ Input Validation Note[/bold yellow]\n\n"
                    f"{input_check_res.get('notification_message')}",
                    title="Input Validation Warning",
                    border_style="yellow",
                )
            )

        # Check for sparse pool warning
        search_res = results.get("articles") or {}
        search_status_val = str(search_res.get("search_status") or "").lower()
        if search_status_val == "moderate":
            console.print(
                Panel(
                    "[bold yellow]⚠️ Sparse News Pool[/bold yellow]\n\n"
                    "Very few unique search sources (3 to 5 unique articles) were found for this query. "
                    "Downstream analysis may be thin or limited.",
                    title="Search Notice",
                    border_style="yellow",
                )
            )

        if results.get("search_failed"):
            search_result = results.get("search_result", {})
            warnings = "\n".join(
                [f"• {warning}" for warning in search_result.get("warnings", [])]
            )
            console.print(
                "\n[bold yellow]Search verification stopped the pipeline.[/bold yellow]"
            )
            console.print(
                Panel(
                    f"[bold]Query:[/bold] {results.get('optimized_query', topic)}\n"
                    f"[bold]Status:[/bold] {search_result.get('search_status', 'unverified')}\n\n"
                    f"{search_result.get('verification_summary', 'No sufficiently corroborated sources were found.')}\n\n"
                    f"{warnings}",
                    title="Search Authenticity Screen",
                    border_style="yellow",
                )
            )
            return

        console.print("[bold green]✔ Analysis Complete![/bold green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✖ Error during analysis:[/bold red] {e!s}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-agent News Bias & Consensus Analyzer CLI"
    )
    parser.add_argument(
        "--topic",
        type=str,
        required=True,
        help="The news topic or headline to search and analyze.",
    )
    args = parser.parse_args()

    # Check for Gemini API key
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        console.print(
            "[bold red]Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.[/bold red]\n"
            "Please create a [bold].env[/bold] file or export the variable to run the agent.\n"
            "You can obtain a free key from Google AI Studio at: https://aistudio.google.com/app/api-keys"
        )
        sys.exit(1)

    asyncio.run(run_cli(args.topic))


if __name__ == "__main__":
    main()
