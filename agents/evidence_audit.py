from collections.abc import Mapping, Sequence
from typing import Any

from agents.evidence_tools import (
    normalize_text_for_matching,
    score_source_independence,
    summarize_evidence_completeness,
    summarize_side_evidence,
    validate_evidence_item,
)

ARTICLE_KEY_FIELDS = ("url", "title", "source")
ARTICLE_SNIPPET_FIELDS = (
    "full_content_snippet",
    "summary",
    "body",
    "snippet",
    "content",
    "text",
)
MISSING_FIELD_KEYS = ("source", "url", "quote")
EMPTY_SUMMARY = {
    "total_evidence_items_checked": 0,
    "missing_source_count": 0,
    "missing_url_count": 0,
    "missing_quote_count": 0,
    "quote_match_warning_count": 0,
    "one_sided_dispute_count": 0,
    "wire_duplicate_warning_count": 0,
    "reported_perspective_without_evidence_count": 0,
    "completeness_label": "none",
}


def _as_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _evidence_items(value: object) -> list[dict]:
    items = []
    for item in _as_list(value):
        evidence_item = _as_mapping(item)
        if evidence_item:
            items.append(evidence_item)
        elif _string_value(item):
            items.append({"quote": _string_value(item)})
    return items


def _preview(value: object, fallback: str) -> str:
    text = " ".join(_string_value(value).split())
    if not text:
        return fallback
    return text if len(text) <= 90 else f"{text[:87].rstrip()}..."


def _article_rows(articles_data: object) -> list:
    data = _as_mapping(articles_data)
    if data:
        return _as_list(data.get("articles"))
    return _as_list(articles_data)


def _append_lookup_entry(lookup: dict, key: str, entry: dict) -> None:
    existing = lookup.get(key)
    if existing is None:
        lookup[key] = entry
    elif isinstance(existing, list):
        lookup[key] = [*existing, entry]
    else:
        lookup[key] = [existing, entry]


def build_article_lookup(articles_data: dict) -> dict:
    """Build a deterministic article lookup keyed by URL, title, and source."""
    lookup: dict[str, Any] = {}

    for article in _article_rows(articles_data):
        article_data = _as_mapping(article)
        if not article_data:
            continue

        entry = {
            key: value
            for key, value in article_data.items()
            if key in ARTICLE_KEY_FIELDS or key in ARTICLE_SNIPPET_FIELDS
        }
        snippets = [
            _string_value(article_data.get(field))
            for field in ARTICLE_SNIPPET_FIELDS
            if _string_value(article_data.get(field))
        ]
        if snippets and not _string_value(entry.get("snippet")):
            entry = {**entry, "snippet": " ".join(snippets)}

        for field in ARTICLE_KEY_FIELDS:
            key = _string_value(article_data.get(field))
            if key:
                _append_lookup_entry(lookup, key, entry)

    return lookup


def _has_quote_match_warning(validation: dict) -> bool:
    return any(
        "quote not found in article snippets" in warning
        for warning in validation.get("warnings", [])
    )


def _base_summary(total_items: int = 0) -> dict:
    summary = dict(EMPTY_SUMMARY)
    summary["total_evidence_items_checked"] = total_items
    return summary


def _status_for(total_items: int, warnings: Sequence[str]) -> str:
    if warnings:
        return "warnings"
    if total_items == 0:
        return "not_available"
    return "passed"


def _validate_evidence_collection(
    evidence_items: list[dict],
    article_lookup: dict,
    context: str,
) -> dict:
    lookup = article_lookup or None
    warnings = []
    missing_counts = dict.fromkeys(MISSING_FIELD_KEYS, 0)
    quote_match_warning_count = 0

    for index, evidence in enumerate(evidence_items, start=1):
        validation = validate_evidence_item(evidence, lookup)
        for field in validation.get("missing_fields", []):
            if field in missing_counts:
                missing_counts[field] += 1
        if _has_quote_match_warning(validation):
            quote_match_warning_count += 1
        for warning in validation.get("warnings", []):
            warnings.append(f"{context} evidence {index}: {warning}")

    completeness = summarize_evidence_completeness(evidence_items)
    summary = {
        **_base_summary(len(evidence_items)),
        "missing_source_count": missing_counts["source"],
        "missing_url_count": missing_counts["url"],
        "missing_quote_count": missing_counts["quote"],
        "quote_match_warning_count": quote_match_warning_count,
        "completeness": completeness,
        "completeness_label": completeness["completeness_label"],
    }
    return {"summary": summary, "warnings": warnings}


def _combine_summaries(*summaries: dict) -> dict:
    combined = dict(EMPTY_SUMMARY)
    for summary in summaries:
        for key in (
            "total_evidence_items_checked",
            "missing_source_count",
            "missing_url_count",
            "missing_quote_count",
            "quote_match_warning_count",
            "one_sided_dispute_count",
            "wire_duplicate_warning_count",
            "reported_perspective_without_evidence_count",
        ):
            combined[key] += int(summary.get(key) or 0)

    total = combined["total_evidence_items_checked"]
    complete = total - (
        combined["missing_source_count"]
        + combined["missing_url_count"]
        + combined["missing_quote_count"]
    )
    if total == 0:
        combined["completeness_label"] = "none"
    elif complete == total:
        combined["completeness_label"] = "strong"
    elif complete <= 0:
        combined["completeness_label"] = "weak"
    else:
        combined["completeness_label"] = "partial"
    return combined


def _claim_label(item: dict, index: int, fallback: str) -> str:
    return _preview(
        item.get("claim") or item.get("event") or item.get("dispute_question"),
        f"{fallback} {index}",
    )


def audit_fact_evidence(facts_data: dict, articles_data: dict) -> dict:
    """Audit consensus fact and structured timeline evidence."""
    facts = _as_mapping(facts_data)
    article_lookup = build_article_lookup(articles_data)
    warnings = []
    all_evidence = []
    consensus_facts = [_as_mapping(item) for item in _as_list(facts.get("consensus_facts"))]
    timeline_items = [_as_mapping(item) for item in _as_list(facts.get("timeline"))]

    for index, fact in enumerate(consensus_facts, start=1):
        evidence_items = _evidence_items(fact.get("evidence"))
        if not evidence_items:
            warnings.append(f"Consensus fact {index} has no evidence attached")
        all_evidence.extend(evidence_items)

    for index, event in enumerate(timeline_items, start=1):
        evidence_items = _evidence_items(event.get("evidence"))
        if not evidence_items:
            warnings.append(f"Timeline item {index} has no evidence attached")
        all_evidence.extend(evidence_items)

    validation = _validate_evidence_collection(
        all_evidence, article_lookup, "Fact/timeline"
    )
    warnings = [*warnings, *validation["warnings"]]
    summary = {
        **validation["summary"],
        "consensus_facts_checked": len(consensus_facts),
        "timeline_items_checked": len(timeline_items),
        "items_without_evidence_count": sum(
            1
            for item in [*consensus_facts, *timeline_items]
            if not _evidence_items(item.get("evidence"))
        ),
    }

    total_items = summary["total_evidence_items_checked"]
    return {
        "status": _status_for(total_items, warnings),
        "summary": summary,
        "warnings": warnings,
    }


def audit_dispute_evidence(facts_data: dict, articles_data: dict) -> dict:
    """Audit dispute side evidence, balance, completeness, and independence."""
    facts = _as_mapping(facts_data)
    article_lookup = build_article_lookup(articles_data)
    disputes = [_as_mapping(item) for item in _as_list(facts.get("disputed_claims"))]
    warnings = []
    all_evidence = []
    dispute_summaries = []
    one_sided_dispute_count = 0
    wire_duplicate_warning_count = 0

    for index, dispute in enumerate(disputes, start=1):
        side_a_evidence = _evidence_items(dispute.get("side_a_evidence"))
        side_b_evidence = _evidence_items(dispute.get("side_b_evidence"))
        combined_evidence = [*side_a_evidence, *side_b_evidence]
        all_evidence.extend(combined_evidence)

        side_summary = summarize_side_evidence(side_a_evidence, side_b_evidence)
        completeness = summarize_evidence_completeness(combined_evidence)
        independence = score_source_independence(combined_evidence)
        label = _claim_label(dispute, index, "Dispute")

        if side_summary["balance_label"] in {"one_sided", "no_evidence"}:
            one_sided_dispute_count += 1
            for warning in side_summary["warnings"]:
                warnings.append(f"{label}: {warning}")

        for warning in independence.get("warnings", []):
            wire_duplicate_warning_count += 1
            warnings.append(f"{label}: {warning}")

        dispute_summaries.append(
            {
                "claim": label,
                "side_balance": side_summary["balance_label"],
                "evidence_items_checked": len(combined_evidence),
                "completeness_label": completeness["completeness_label"],
                "source_independence": independence["independence_label"],
            }
        )

    validation = _validate_evidence_collection(all_evidence, article_lookup, "Dispute")
    warnings = [*warnings, *validation["warnings"]]
    summary = {
        **validation["summary"],
        "disputes_checked": len(disputes),
        "one_sided_dispute_count": one_sided_dispute_count,
        "wire_duplicate_warning_count": wire_duplicate_warning_count,
        "dispute_summaries": dispute_summaries,
    }

    total_items = summary["total_evidence_items_checked"]
    return {
        "status": _status_for(total_items, warnings),
        "summary": summary,
        "warnings": warnings,
    }


def _is_reported_perspective(profile: dict) -> bool:
    support_status = normalize_text_for_matching(profile.get("support_status", ""))
    return "reported" in support_status and "perspective" in support_status


def audit_perspective_evidence(narratives: dict, articles_data: dict) -> dict:
    """Audit reported perspective profiles for traceable source evidence."""
    narrative_data = _as_mapping(narratives)
    article_lookup = build_article_lookup(articles_data)
    profiles = [_as_mapping(item) for item in _as_list(narrative_data.get("profiles"))]
    warnings = []
    all_evidence = []
    profile_summaries = []
    reported_without_evidence_count = 0

    for index, profile in enumerate(profiles, start=1):
        evidence_items = _evidence_items(profile.get("evidence"))
        all_evidence.extend(evidence_items)
        group = _preview(profile.get("perspective_group"), f"Profile {index}")

        if _is_reported_perspective(profile) and not evidence_items:
            reported_without_evidence_count += 1
            warnings.append(
                f"{group}: marked as a reported perspective but has no evidence attached"
            )

        completeness = summarize_evidence_completeness(evidence_items)
        profile_summaries.append(
            {
                "perspective_group": group,
                "support_status": _string_value(profile.get("support_status")),
                "evidence_items_checked": len(evidence_items),
                "completeness_label": completeness["completeness_label"],
            }
        )

    validation = _validate_evidence_collection(
        all_evidence, article_lookup, "Perspective"
    )
    warnings = [*warnings, *validation["warnings"]]
    summary = {
        **validation["summary"],
        "profiles_checked": len(profiles),
        "reported_perspective_without_evidence_count": (
            reported_without_evidence_count
        ),
        "profile_summaries": profile_summaries,
    }

    total_items = summary["total_evidence_items_checked"]
    return {
        "status": _status_for(total_items, warnings),
        "summary": summary,
        "warnings": warnings,
    }


def run_deterministic_evidence_audit(
    facts_data: dict,
    narratives: dict,
    articles_data: dict,
) -> dict:
    """Run deterministic, non-blocking evidence checks over pipeline outputs."""
    fact_evidence = audit_fact_evidence(facts_data, articles_data)
    dispute_evidence = audit_dispute_evidence(facts_data, articles_data)
    perspective_evidence = audit_perspective_evidence(narratives, articles_data)

    warnings = [
        *fact_evidence.get("warnings", []),
        *dispute_evidence.get("warnings", []),
        *perspective_evidence.get("warnings", []),
    ]
    summary = _combine_summaries(
        fact_evidence.get("summary", {}),
        dispute_evidence.get("summary", {}),
        perspective_evidence.get("summary", {}),
    )

    if warnings:
        status = "warnings"
    elif summary["total_evidence_items_checked"] == 0:
        status = "not_available"
    else:
        status = "passed"

    return {
        "status": status,
        "summary": summary,
        "warnings": warnings,
        "fact_evidence": fact_evidence,
        "dispute_evidence": dispute_evidence,
        "perspective_evidence": perspective_evidence,
    }
