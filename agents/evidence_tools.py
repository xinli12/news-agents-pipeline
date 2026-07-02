import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping

REQUIRED_EVIDENCE_FIELDS = ("source", "title", "url", "quote")
SNIPPET_FIELDS = (
    "full_content_snippet",
    "snippet",
    "body",
    "summary",
    "content",
    "text",
    "quote",
)
QUOTE_MATCH_WARNING_THRESHOLD = 0.45
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "said",
    "says",
    "should",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "would",
}


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _field_value(item: object, field: str) -> str:
    if isinstance(item, Mapping):
        return _string_value(item.get(field))
    return _string_value(getattr(item, field, ""))


def normalize_text_for_matching(text: str) -> str:
    """Normalize text for deterministic quote and metadata matching."""
    decomposed = unicodedata.normalize("NFKD", _string_value(text).casefold())
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    alphanumeric_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return " ".join(alphanumeric_text.split())


def _tokens_for_matching(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(normalize_text_for_matching(text))
    meaningful_tokens = [
        token
        for token in tokens
        if token not in STOP_WORDS and (len(token) > 2 or token.isdigit())
    ]
    return meaningful_tokens or tokens


def quote_match_score(quote: str, snippet: str) -> float:
    """Return a deterministic 0.0-1.0 fuzzy match score for a quote/snippet pair."""
    normalized_quote = normalize_text_for_matching(quote)
    normalized_snippet = normalize_text_for_matching(snippet)

    if not normalized_quote or not normalized_snippet:
        return 0.0
    if normalized_quote == normalized_snippet or normalized_quote in normalized_snippet:
        return 1.0

    quote_tokens = Counter(_tokens_for_matching(normalized_quote))
    snippet_tokens = Counter(_tokens_for_matching(normalized_snippet))
    quote_total = sum(quote_tokens.values())
    snippet_total = sum(snippet_tokens.values())
    if quote_total == 0 or snippet_total == 0:
        return 0.0

    overlap = sum(
        min(count, snippet_tokens.get(token, 0))
        for token, count in quote_tokens.items()
    )
    if overlap == 0:
        return 0.0

    recall = overlap / quote_total
    precision = overlap / snippet_total
    return round(min((recall * 0.8) + (precision * 0.2), 1.0), 3)


def _iter_snippets(value: object) -> Iterable[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            yield stripped
        return

    if isinstance(value, Mapping):
        for field in SNIPPET_FIELDS:
            snippet = _string_value(value.get(field))
            if snippet:
                yield snippet
        return

    if isinstance(value, Iterable):
        for entry in value:
            yield from _iter_snippets(entry)


def _candidate_article_entries(
    evidence: Mapping[str, object],
    article_lookup: Mapping[object, object],
) -> list[tuple[str, object]]:
    preferred_keys = {
        normalize_text_for_matching(_string_value(evidence.get(field)))
        for field in ("url", "title", "source")
        if _string_value(evidence.get(field))
    }

    if not preferred_keys:
        return [(str(key), value) for key, value in article_lookup.items()]

    matched_entries = [
        (str(key), value)
        for key, value in article_lookup.items()
        if normalize_text_for_matching(str(key)) in preferred_keys
    ]
    return matched_entries or [(str(key), value) for key, value in article_lookup.items()]


def validate_evidence_item(
    evidence: dict,
    article_lookup: dict | None = None,
) -> dict:
    """Validate evidence metadata and optionally match its quote to article snippets."""
    evidence_data: Mapping[str, object] = (
        evidence if isinstance(evidence, Mapping) else {}
    )
    field_presence = {
        field: bool(_field_value(evidence_data, field))
        for field in REQUIRED_EVIDENCE_FIELDS
    }
    missing_fields = [
        field for field, is_present in field_presence.items() if not is_present
    ]
    warnings = [f"missing {field}" for field in missing_fields]

    if not field_presence["quote"]:
        return {
            "status": "invalid",
            "score": 0.0,
            "warnings": warnings,
            "field_presence": field_presence,
            "missing_fields": missing_fields,
            "quote_match_score": 0.0,
            "matched_article_key": None,
        }

    completeness_score = sum(field_presence.values()) / len(REQUIRED_EVIDENCE_FIELDS)
    quote_score = None
    matched_article_key = None

    if article_lookup is not None:
        article_data = article_lookup if isinstance(article_lookup, Mapping) else {}
        candidates = [
            (key, snippet)
            for key, value in _candidate_article_entries(evidence_data, article_data)
            for snippet in _iter_snippets(value)
        ]
        if candidates:
            quote = _field_value(evidence_data, "quote")
            scored_candidates = [
                (quote_match_score(quote, snippet), key) for key, snippet in candidates
            ]
            quote_score, matched_article_key = max(
                scored_candidates, key=lambda item: item[0]
            )
            if quote_score < QUOTE_MATCH_WARNING_THRESHOLD:
                warnings.append(
                    f"quote not found in article snippets (best score {quote_score:.3f})"
                )
        else:
            quote_score = 0.0
            warnings.append("quote lookup did not contain candidate snippets")

    score = completeness_score if quote_score is None else completeness_score * quote_score
    status = "valid" if not warnings else "warning"

    return {
        "status": status,
        "score": round(score, 3),
        "warnings": warnings,
        "field_presence": field_presence,
        "missing_fields": missing_fields,
        "quote_match_score": quote_score,
        "matched_article_key": matched_article_key,
    }


def summarize_evidence_completeness(evidence_items: list[dict]) -> dict:
    """Summarize source, URL, and quote completeness for a list of evidence items."""
    items = evidence_items or []
    total_items = len(items)
    with_source = sum(1 for item in items if _field_value(item, "source"))
    with_url = sum(1 for item in items if _field_value(item, "url"))
    with_quote = sum(1 for item in items if _field_value(item, "quote"))
    complete_items = sum(
        1
        for item in items
        if _field_value(item, "source")
        and _field_value(item, "url")
        and _field_value(item, "quote")
    )

    if total_items == 0:
        completeness_label = "none"
    elif complete_items == 0:
        completeness_label = "weak"
    elif complete_items == total_items:
        completeness_label = "strong"
    else:
        completeness_label = "partial"

    return {
        "total_items": total_items,
        "with_source": with_source,
        "with_url": with_url,
        "with_quote": with_quote,
        "complete_items": complete_items,
        "completeness_label": completeness_label,
    }


def _normalized_distinct_count(items: list[dict], field: str) -> int:
    return len(
        {
            normalize_text_for_matching(value)
            for item in items
            if (value := _field_value(item, field))
        }
    )


def _metadata_counter(items: list[dict], field: str) -> Counter[str]:
    return Counter(value for item in items if (value := _field_value(item, field)))


def _independence_key(item: dict) -> str:
    duplicate_cluster = normalize_text_for_matching(_field_value(item, "duplicate_cluster"))
    if duplicate_cluster:
        return f"cluster:{duplicate_cluster}"

    outlet_group = normalize_text_for_matching(_field_value(item, "outlet_group"))
    if outlet_group:
        return f"group:{outlet_group}"

    source = normalize_text_for_matching(_field_value(item, "source"))
    if source:
        return f"source:{source}"

    return ""


def score_source_independence(evidence_items: list[dict]) -> dict:
    """Score whether evidence appears to come from independent source material."""
    items = evidence_items or []
    total_items = len(items)
    distinct_sources = _normalized_distinct_count(items, "source")
    distinct_outlet_groups = _normalized_distinct_count(items, "outlet_group")
    distinct_duplicate_clusters = _normalized_distinct_count(items, "duplicate_cluster")
    distinct_independence_keys = len(
        {key for item in items if (key := _independence_key(item))}
    )
    wire_service_counts = _metadata_counter(items, "wire_service")
    duplicate_cluster_counts = _metadata_counter(items, "duplicate_cluster")

    warnings = []
    for service, count in sorted(wire_service_counts.items()):
        if count > 1:
            warnings.append(
                f"wire_service '{service}' appears on {count} evidence items"
            )
    for cluster, count in sorted(duplicate_cluster_counts.items()):
        if count > 1:
            warnings.append(
                f"duplicate_cluster '{cluster}' appears on {count} evidence items"
            )

    if total_items == 0:
        score = 0.0
        independence_label = "none"
    else:
        raw_score = distinct_independence_keys / total_items
        score = round(raw_score, 3)
        if raw_score >= 1.0 and distinct_sources > 1:
            independence_label = "strong"
        elif raw_score >= 2 / 3:
            independence_label = "partial"
        else:
            independence_label = "weak"

    return {
        "total_items": total_items,
        "distinct_sources": distinct_sources,
        "distinct_outlet_groups": distinct_outlet_groups,
        "distinct_duplicate_clusters": distinct_duplicate_clusters,
        "distinct_independence_keys": distinct_independence_keys,
        "wire_service_counts": dict(sorted(wire_service_counts.items())),
        "duplicate_cluster_counts": dict(sorted(duplicate_cluster_counts.items())),
        "score": score,
        "independence_label": independence_label,
        "warnings": warnings,
    }


def summarize_side_evidence(
    side_a_evidence: list[dict],
    side_b_evidence: list[dict],
) -> dict:
    """Summarize evidence balance across two dispute sides."""
    side_a_items = side_a_evidence or []
    side_b_items = side_b_evidence or []
    side_a_count = len(side_a_items)
    side_b_count = len(side_b_items)
    warnings = []

    if side_a_count == 0 and side_b_count == 0:
        balance_label = "no_evidence"
        warnings.append("no evidence supplied for either side")
    elif side_a_count == 0 or side_b_count == 0:
        balance_label = "one_sided"
        missing_side = "side_a" if side_a_count == 0 else "side_b"
        warnings.append(f"{missing_side} has no evidence")
    elif abs(side_a_count - side_b_count) <= 1:
        balance_label = "balanced"
    else:
        balance_label = "uneven"
        warnings.append(
            f"evidence counts are uneven: side_a={side_a_count}, side_b={side_b_count}"
        )

    return {
        "side_a_count": side_a_count,
        "side_b_count": side_b_count,
        "balance_label": balance_label,
        "warnings": warnings,
        "side_a_completeness": summarize_evidence_completeness(side_a_items),
        "side_b_completeness": summarize_evidence_completeness(side_b_items),
    }
