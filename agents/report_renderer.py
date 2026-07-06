"""Deterministic Markdown renderer for the consolidated public editor report.

Folding upstream agent output into <details> blocks and building a Sources
section is pure templating with no judgment call left to make -- every field
here was already produced and audited by an upstream agent. Routing it
through another LLM call only added latency, cost, and a chance of mangled
HTML, so this assembles the report directly instead.
"""

from __future__ import annotations

from typing import Any


def _evidence_link(item: dict) -> str:
    source = item.get("source") or "Source"
    url = item.get("url") or ""
    return f"[{source}]({url})" if url else str(source)


def _format_evidence_list(evidence: list[dict] | None) -> str:
    lines = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        line = f"  - {_evidence_link(item)}"
        if item.get("title"):
            line += f" — {item['title']}"
        if item.get("quote"):
            line += f': "{item["quote"]}"'
        lines.append(line)
    return "\n".join(lines)


def _details(summary: str, body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>\n"


def _render_disputes(disputed_claims: list[dict]) -> str:
    if not disputed_claims:
        return ""
    sections = []
    for item in disputed_claims:
        block = [
            f"**{item.get('claim') or item.get('dispute_question') or 'Disputed claim'}**",
            f"- Side A: {item.get('side_a_assertion', '')}",
            _format_evidence_list(item.get("side_a_evidence")),
            f"- Side B: {item.get('side_b_assertion', '')}",
            _format_evidence_list(item.get("side_b_evidence")),
        ]
        if item.get("evidence_warning"):
            block.append(f"> {item['evidence_warning']}")
        sections.append("\n".join(part for part in block if part))
    return _details("Disputed Claims", "\n\n---\n\n".join(sections))


def _render_narratives(profiles: list[dict]) -> str:
    if not profiles:
        return ""
    sections = []
    for profile in profiles:
        block = [
            f"**{profile.get('perspective_group', 'Perspective')}**",
            profile.get("core_narrative", ""),
        ]
        block.extend(f"- {arg}" for arg in profile.get("key_arguments") or [])
        omissions = profile.get("notable_omissions") or []
        if omissions:
            block.append(f"_Notable omissions_: {', '.join(omissions)}")
        sections.append("\n".join(part for part in block if part))
    return _details("Media Narratives & Perspectives", "\n\n---\n\n".join(sections))


def _render_experts(expert_data: dict) -> str:
    opinions = expert_data.get("expert_opinions") or []
    if not opinions:
        return ""
    sections = []
    for opinion in opinions:
        refs = ", ".join(opinion.get("cited_references") or [])
        block = [
            f"**{opinion.get('expert_name', 'Expert')}** ({opinion.get('expertise_area', '')})",
            opinion.get("commentary", ""),
        ]
        if refs:
            block.append(f"_Cites_: {refs}")
        sections.append("\n\n".join(part for part in block if part))
    body = "\n\n---\n\n".join(sections)
    summary = expert_data.get("roundtable_summary", "")
    if summary:
        body += f"\n\n**Roundtable synthesis**: {summary}"
    return _details("Expert Roundtable", body)


def _render_timeline(facts_data: dict) -> str:
    timeline = facts_data.get("timeline") or []
    if not timeline:
        return ""
    lines = [f"- **{event.get('date', '')}**: {event.get('event', '')}" for event in timeline]
    return _details("Timeline", "\n".join(lines))


def _render_outlook(outlook_data: dict) -> str:
    scenarios = []
    if outlook_data.get("most_likely_scenario"):
        scenarios.append(("Most likely", outlook_data["most_likely_scenario"]))
    for alternative in outlook_data.get("alternative_scenarios") or []:
        scenarios.append(("Alternative", alternative))
    if not scenarios:
        return ""
    sections = []
    for label, scenario in scenarios:
        triggers = ", ".join(scenario.get("trigger_conditions") or [])
        block = [
            f"**{label}: {scenario.get('scenario_title', '')}** ({scenario.get('likelihood_band', '')})",
            scenario.get("description", ""),
        ]
        if triggers:
            block.append(f"_Triggers_: {triggers}")
        sections.append("\n\n".join(part for part in block if part))
    body = "\n\n---\n\n".join(sections)
    indicators = outlook_data.get("monitoring_indicators") or []
    if indicators:
        body += "\n\n**Monitoring indicators**: " + ", ".join(indicators)
    return _details("Future Outlook & Scenarios", body)


def _collect_sources(
    *evidence_lists: list[dict] | None, articles_data: dict | None = None
) -> list[dict]:
    seen: dict[str, dict] = {}
    for evidence_list in evidence_lists:
        for item in evidence_list or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if url and url not in seen:
                seen[url] = item
    for article in (articles_data or {}).get("articles") or []:
        url = article.get("url")
        if url and url not in seen:
            seen[url] = {
                "source": article.get("source", ""),
                "title": article.get("title", ""),
                "url": url,
                "published_date": article.get("published_date", ""),
            }
    return list(seen.values())


def render_public_editor_report(
    topic: str,
    public_report: dict | None,
    facts_data: dict | None,
    narratives_data: dict | None,
    expert_data: dict | None,
    outlook_data: dict | None,
    articles_data: dict | None,
    audit_warnings: list[dict] | None,
) -> dict[str, Any]:
    """Assembles the consolidated, folded public editor report with no LLM call."""
    public_report = public_report or {}
    facts_data = facts_data or {}
    narratives_data = narratives_data or {}
    expert_data = expert_data or {}
    outlook_data = outlook_data or {}
    articles_data = articles_data or {}
    audit_warnings = audit_warnings or []

    unresolved_warnings = [
        f"{warning.get('agent', 'Agent')}: {warning.get('feedback', '')}"
        for warning in audit_warnings
    ]

    lines: list[str] = []

    if unresolved_warnings:
        lines.append("> [!WARNING]")
        lines.append(
            "> Some sections were not fully approved by the audit agents. "
            "Review the details below before relying on this report."
        )
        lines.append("")

    lines.append(f"# {public_report.get('title') or topic}")
    lines.append("")
    if public_report.get("lead_paragraph"):
        lines.append(public_report["lead_paragraph"])
        lines.append("")

    lines.append("## Executive Summary")
    for takeaway in public_report.get("key_takeaways") or []:
        evidence_links = ", ".join(
            _evidence_link(item)
            for item in takeaway.get("evidence") or []
            if item.get("url")
        )
        line = f"- {takeaway.get('point', '')}"
        if evidence_links:
            line += f" ({evidence_links})"
        lines.append(line)
    if public_report.get("narrative_summary"):
        lines.append(f"\n**Perspective synthesis**: {public_report['narrative_summary']}")
    if public_report.get("future_outlook"):
        lines.append(f"\n**What to watch next**: {public_report['future_outlook']}")
    lines.append("")

    for section in (
        _render_disputes(facts_data.get("disputed_claims") or []),
        _render_narratives(narratives_data.get("profiles") or []),
        _render_experts(expert_data),
        _render_timeline(facts_data),
        _render_outlook(outlook_data),
    ):
        if section:
            lines.append(section)

    sources = _collect_sources(
        *(fact.get("evidence") for fact in facts_data.get("consensus_facts") or []),
        *(
            dispute.get("side_a_evidence")
            for dispute in facts_data.get("disputed_claims") or []
        ),
        *(
            dispute.get("side_b_evidence")
            for dispute in facts_data.get("disputed_claims") or []
        ),
        *(profile.get("evidence") for profile in narratives_data.get("profiles") or []),
        *(
            opinion.get("supporting_evidence")
            for opinion in expert_data.get("expert_opinions") or []
        ),
        articles_data=articles_data,
    )
    if sources:
        lines.append("## Sources")
        for item in sources:
            date = f" ({item['published_date']})" if item.get("published_date") else ""
            title = f" — {item['title']}" if item.get("title") else ""
            lines.append(f"- [{item.get('source', 'Source')}]({item['url']}){title}{date}")

    return {
        "markdown_report": "\n".join(lines).strip() + "\n",
        "unresolved_warnings": unresolved_warnings,
    }
