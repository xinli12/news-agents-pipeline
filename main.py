import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

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


async def run_cli(topic: str):
    console.print(
        "\n[bold blue]📰 Unbiased News Analysis Multi-Agent System[/bold blue]"
    )
    console.print(f'[bold dim]Topic:[/bold dim] [yellow]"{topic}"[/yellow]')
    console.print(
        "[bold dim]Mode:[/bold dim] [magenta]Live DuckDuckGo News Search[/magenta]\n"
    )

    coordinator = NewsAnalysisCoordinator()

    # Callback to display progress using Rich status spinner
    status_spinner = None

    async def progress_callback(step: str, message: str, payload: dict | None = None):
        nonlocal status_spinner
        if status_spinner:
            status_spinner.stop()

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
                sources_table.add_column("Scale", justify="center")
                sources_table.add_column("Type", justify="center")
                sources_table.add_column("Source Reliability", justify="center")
                sources_table.add_column("Snippet Objectivity", justify="center")

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
                    rel_meter = make_score_meter(
                        art.get("source_reliability_score", 0.0), width=6
                    )
                    obj_meter = make_score_meter(
                        art.get("objectivity_score", 0.0), width=6
                    )

                    sources_table.add_row(
                        str(idx),
                        title_url,
                        art.get("source", ""),
                        f"[bold {bias_color}]{bias}[/bold {bias_color}]",
                        art.get("media_scale", ""),
                        art.get("media_type", ""),
                        rel_meter,
                        obj_meter,
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

            elif step == "editor_complete":
                is_approved = payload.get("is_approved", True)
                editor_logs = payload.get("editor_logs", [])
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

        # Restart spinner if not a terminal step
        if not step.endswith("_complete") and step not in [
            "editor_approved",
            "editor_rejected",
            "review_failed",
        ]:
            status_spinner = console.status(
                "[bold green]Working...[/bold green]", spinner="dots"
            )
            status_spinner.start()

    try:
        results = await coordinator.analyze(topic, progress_callback)
        if status_spinner:
            status_spinner.stop()

        # Check if the audit review rejected the query
        if not results.get("reviewed", True):
            review = results["review_result"]
            console.print("\n[bold red]✖ Input Review Rejected![/bold red]")
            console.print(
                Panel(
                    f"[bold]Rejection Reason:[/bold] {review.get('rejection_reason', 'Not news-relevant or safe.')}\n\n"
                    f"[bold]Suggested Query:[/bold] {review.get('suggested_query_formulation', '')}",
                    title="Input Moderation Audit Result",
                    border_style="red",
                )
            )
            return

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
        if status_spinner:
            status_spinner.stop()
        console.print(f"\n[bold red]✖ Error during analysis:[/bold red] {e!s}")
        sys.exit(1)


def display_results(results: dict):
    # Print Editor-in-Chief warnings if not approved
    is_approved = results.get("is_approved", True)
    editor_logs = results.get("editor_logs", [])
    if not is_approved and editor_logs:
        last_log = editor_logs[-1]
        feedback = last_log.get("feedback", "")
        suggestions = "\n".join([f"• {s}" for s in last_log.get("suggestions", [])])
        console.print(
            Panel(
                f"[bold red]⚠️  WARNING: Editor-in-Chief Audit Loop Rejected This Draft[/bold red]\n\n"
                f"[bold]Feedback:[/bold] {feedback}\n"
                f"[bold]Revision Directives:[/bold]\n{suggestions}",
                title="Editor-in-Chief Disclaimer",
                border_style="yellow",
            )
        )
        console.print()

    # --- 1. Fact & Consensus Map ---
    facts_data = results["facts"]

    consensus_table = Table(
        title="[bold green]Consensus Facts (Cross-Verified)[/bold green]", expand=True
    )
    consensus_table.add_column("Fact/Claim", style="cyan")
    consensus_table.add_column("Supporting Sources", style="dim green")
    consensus_table.add_column("Evidence Trail", style="dim")
    consensus_table.add_column("Cross-Verification Score", justify="right")

    for item in facts_data.get("consensus_facts", []):
        sources = ", ".join(item.get("supporting_sources", []))
        evidence = format_evidence_items(item.get("evidence", []))
        meter = make_score_meter(item.get("cross_verification_score", 0.0))
        consensus_table.add_row(item.get("claim", ""), sources, evidence, meter)

    dispute_table = Table(
        title="[bold red]Contested Claims & Disputes[/bold red]", expand=True
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

    # --- 2. Timeline ---
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

    # --- 3. Perspective & Narrative Profiler ---
    narratives_data = results["narratives"]

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

        args = "\n".join([f"  - {arg}" for arg in profile.get("key_arguments", [])])
        triggers = ", ".join(profile.get("common_emotional_triggers", []))
        omissions = (
            "\n".join([f"  - {om}" for om in profile.get("notable_omissions", [])])
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

    # --- 4. Expert Roundtable ---
    experts_data = results["experts"]
    console.print("[bold yellow]━━━ Expert Roundtable Panel Review ━━━[/bold yellow]\n")

    expert_cards = []
    for opinion in experts_data.get("expert_opinions", []):
        exp_name = opinion.get("expert_name", "")
        exp_field = opinion.get("expertise_area", "")
        exp_text = opinion.get("commentary", "")
        citations = (
            "\n".join([f"• {c}" for c in opinion.get("cited_references", [])])
            or "• None cited"
        )
        readings = "\n".join(
            [f"• {r}" for r in opinion.get("recommended_reading_or_context", [])]
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

    # --- 5. Sources References ---
    articles_data = results["articles"]
    sources_table = Table(
        title="[bold]Analyzed Articles & References[/bold]", expand=True
    )
    sources_table.add_column("#", width=3, justify="center")
    sources_table.add_column("Title & URL", style="cyan")
    sources_table.add_column("Source", style="green")
    sources_table.add_column("Bias Rating", justify="center")
    sources_table.add_column("Scale", justify="center")
    sources_table.add_column("Type", justify="center")
    sources_table.add_column("Source Reliability", justify="center")
    sources_table.add_column("Snippet Objectivity", justify="center")

    for idx, art in enumerate(articles_data.get("articles", []), 1):
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

        title_url = (
            f"[bold]{art.get('title', '')}[/bold]\n[dim]{art.get('url', '')}[/dim]"
        )
        rel_meter = make_score_meter(art.get("source_reliability_score", 0.0), width=6)
        obj_meter = make_score_meter(art.get("objectivity_score", 0.0), width=6)

        sources_table.add_row(
            str(idx),
            title_url,
            art.get("source", ""),
            f"[bold {bias_color}]{bias}[/bold {bias_color}]",
            art.get("media_scale", ""),
            art.get("media_type", ""),
            rel_meter,
            obj_meter,
        )

    console.print(sources_table)
    console.print()


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
