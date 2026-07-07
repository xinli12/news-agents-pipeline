"""Helpers for compact, traceable analysis context bundles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

TRACEABILITY_FIELDS = (
    "source",
    "title",
    "url",
    "published_date",
    "bias_category",
    "neutrality",
    "outlet_group",
    "wire_service",
    "duplicate_cluster",
    "selection_rationale",
)

TOP_LEVEL_FIELDS = (
    "topic",
    "query_used",
    "corrected_query",
    "search_status",
    "verification_summary",
    "source_balance",
    "warnings",
    "wire_groups",
)

EVIDENCE_FIELDS = (
    "source",
    "title",
    "url",
    "published_date",
    "bias_category",
    "quote",
)

ARTICLE_EVIDENCE_KEYS = (
    "evidence",
    "supporting_evidence",
    "quote",
    "quotes",
    "representative_sources",
    "supporting_sources",
)

SNIPPET_FALLBACK_FIELDS = (
    "full_content_snippet",
    "content_snippet",
    "snippet",
)


def compact_article(article: dict, max_summary_chars: int = 700) -> dict:
    """Return a compact article dict that keeps citation traceability fields."""
    article_data = _as_dict(article)
    compact: dict[str, Any] = {}

    for field in TRACEABILITY_FIELDS:
        _set_if_present(compact, field, article_data.get(field))

    _set_if_present(
        compact,
        "summary",
        _truncate_text(article_data.get("summary"), max_summary_chars),
    )
    _set_if_present(
        compact,
        "full_content_snippet",
        _compact_snippet(article_data, max_summary_chars),
    )

    for field in ARTICLE_EVIDENCE_KEYS:
        _set_if_present(
            compact,
            field,
            _compact_evidence_value(article_data.get(field), max_summary_chars),
        )

    return compact


def build_compact_articles_data(
    articles_data: dict,
    max_articles: int | None = None,
    max_summary_chars: int = 700,
) -> dict:
    """Build compact articles_data without changing the source object."""
    source_data = _as_dict(articles_data)
    articles = list(source_data.get("articles") or [])
    if max_articles is None:
        included_articles = articles
    else:
        included_articles = articles[: max(0, int(max_articles))]

    compact: dict[str, Any] = {}
    for field in TOP_LEVEL_FIELDS:
        _set_if_present(compact, field, source_data.get(field))

    compact["article_count_available"] = len(articles)
    compact["article_count_included"] = len(included_articles)
    compact["articles"] = [
        compact_article(article, max_summary_chars=max_summary_chars)
        for article in included_articles
    ]
    return compact


def article_context_stats(
    articles_data: dict,
    max_articles: int | None = None,
    max_summary_chars: int = 700,
) -> dict:
    """Return approximate JSON-size stats for full and compact article context."""
    source_data = _as_dict(articles_data)
    compact_data = build_compact_articles_data(
        source_data,
        max_articles=max_articles,
        max_summary_chars=max_summary_chars,
    )
    original_json_chars = _json_size(source_data)
    compact_json_chars = _json_size(compact_data)
    reduction_chars = max(0, original_json_chars - compact_json_chars)
    reduction_ratio = (
        round(reduction_chars / original_json_chars, 4)
        if original_json_chars
        else 0.0
    )

    return {
        "article_count": len(source_data.get("articles") or []),
        "compact_article_count": len(compact_data.get("articles") or []),
        "original_json_chars": original_json_chars,
        "compact_json_chars": compact_json_chars,
        "reduction_chars": reduction_chars,
        "reduction_ratio": reduction_ratio,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    target[key] = value


def _compact_snippet(article_data: Mapping[str, Any], max_chars: int) -> str:
    for field in SNIPPET_FALLBACK_FIELDS:
        snippet = _truncate_text(article_data.get(field), max_chars)
        if snippet:
            return snippet
    return ""


def _compact_evidence_value(value: Any, max_chars: int) -> Any:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, list):
        compact_list = [
            _compact_evidence_value(item, max_chars)
            for item in value
        ]
        return [item for item in compact_list if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return _compact_evidence_value(list(value), max_chars)
    if isinstance(value, Mapping) or hasattr(value, "model_dump") or hasattr(value, "dict"):
        item = _as_dict(value)
        compact = {
            field: _truncate_text(item.get(field), max_chars)
            if field == "quote"
            else item.get(field)
            for field in EVIDENCE_FIELDS
            if item.get(field) not in (None, "", [], {})
        }
        return compact or None
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    return value


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    limit = max(0, int(max_chars))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str))
