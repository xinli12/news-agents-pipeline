from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from difflib import SequenceMatcher
from itertools import pairwise
from typing import Any

UNKNOWN_VALUES = {
    "",
    "unknown",
    "n/a",
    "na",
    "none",
    "other",
    "other/non-political",
    "other non political",
}

# Full scraped article texts keyed by normalized URL. Populated by the scraper so
# quote verification can run against the full text instead of the short snippet
# that survives the search agent's structured output.
_FULL_TEXT_CACHE: dict[str, str] = {}
_FULL_TEXT_CACHE_MAX = 500


def register_article_full_text(url: str, text: str) -> None:
    """Registers the full scraped text of an article for later quote verification."""
    key = _normalize_url(url)
    if not key or not text:
        return
    if len(_FULL_TEXT_CACHE) >= _FULL_TEXT_CACHE_MAX:
        _FULL_TEXT_CACHE.pop(next(iter(_FULL_TEXT_CACHE)))
    _FULL_TEXT_CACHE[key] = text


def get_article_full_text(url: str) -> str:
    return _FULL_TEXT_CACHE.get(_normalize_url(url), "")


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    return {}


def _normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return url.strip().lower().rstrip("/")

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+$", "", parsed.path or "")
    return urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))


def _domain_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return ""
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _date_key(value: str) -> datetime | None:
    if not value or value.strip().lower() in UNKNOWN_VALUES:
        return None
    text = value.strip()
    iso_candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate).replace(tzinfo=None)
    except ValueError:
        pass

    for pattern in (
        r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
        r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b",
    ):
        match = re.search(pattern, text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _issue(
    issues: list[dict[str, str]],
    severity: str,
    path: str,
    message: str,
    fix: str | None = None,
) -> None:
    item = {"severity": severity, "path": path, "message": message}
    if fix:
        item["fix"] = fix
    issues.append(item)


def _article_text(article: dict[str, Any]) -> str:
    parts = [
        str(article.get(field, "") or "")
        for field in ("title", "summary", "full_content_snippet")
    ]
    parts.append(get_article_full_text(str(article.get("url", "") or "")))
    return " ".join(part for part in parts if part)


def _quote_match_score(quote: str, text: str) -> float:
    quote_norm = _normalize_text(quote)
    text_norm = _normalize_text(text)
    if not quote_norm:
        return 0.0
    if quote_norm in text_norm:
        return 1.0

    quote_words = quote_norm.split()
    text_words = text_norm.split()
    if not quote_words or not text_words:
        return 0.0

    window_size = len(quote_words)
    min_size = max(3, window_size - 3)
    max_size = min(len(text_words), window_size + 3)
    best = 0.0
    for size in range(min_size, max_size + 1):
        for start in range(0, max(1, len(text_words) - size + 1)):
            window = " ".join(text_words[start : start + size])
            best = max(best, SequenceMatcher(None, quote_norm, window).ratio())
            if best >= 0.9:
                return best
    return best


def _build_article_index(
    articles_data: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    raw_articles = list(_as_dict(articles_data).get("articles") or [])
    articles = [_as_dict(article) for article in raw_articles]
    index = {}
    for article in articles:
        key = _normalize_url(str(article.get("url", "") or ""))
        if key:
            index[key] = article
    return index, articles


def _source_key(article: dict[str, Any], evidence: dict[str, Any]) -> str:
    return (
        str(article.get("outlet_group") or "").strip().lower()
        or _domain_from_url(str(article.get("url", "") or ""))
        or str(article.get("source") or evidence.get("source") or "").strip().lower()
    )


def _verify_evidence_item(
    evidence: dict[str, Any],
    path: str,
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> dict[str, Any] | None:
    url = str(evidence.get("url", "") or "")
    if not url:
        _issue(
            issues,
            "error",
            path,
            "Evidence item is missing a URL.",
            "Use a URL copied from one of the searched articles.",
        )
        return None

    article = article_index.get(_normalize_url(url))
    if not article:
        _issue(
            issues,
            "error",
            path,
            "Evidence URL is not present in the searched article set.",
            "Replace the URL with one from articles_data or remove the unsupported claim.",
        )
        return None

    quote = str(evidence.get("quote", "") or "").strip()
    if not quote:
        _issue(
            issues,
            "error",
            path,
            "Evidence item is missing a quote.",
            "Copy a short quote from the article snippet used by the search agent.",
        )
    else:
        word_count = len(quote.split())
        if word_count < 8:
            _issue(
                issues,
                "warning",
                path,
                "Evidence quote is very short and may be hard to verify.",
                "Use a quote of roughly 12-25 words when possible.",
            )
        score = _quote_match_score(quote, _article_text(article))
        if score < 0.72:
            _issue(
                issues,
                "error",
                path,
                "Evidence quote does not match the cited article snippet closely enough.",
                "Copy the quote verbatim from the cited article's full_content_snippet, title, or summary.",
            )

    evidence_source = _normalize_text(str(evidence.get("source", "") or ""))
    article_source = _normalize_text(str(article.get("source", "") or ""))
    if evidence_source and article_source and evidence_source != article_source:
        _issue(
            issues,
            "warning",
            path,
            "Evidence source label differs from the searched article source.",
            "Keep the source label aligned with articles_data unless the alias is intentional.",
        )

    evidence_date = str(evidence.get("published_date", "") or "")
    article_date = str(article.get("published_date", "") or "")
    if evidence_date and article_date and evidence_date != article_date:
        evidence_day = _date_key(evidence_date)
        article_day = _date_key(article_date)
        if evidence_day and article_day and evidence_day.date() != article_day.date():
            _issue(
                issues,
                "warning",
                path,
                "Evidence published_date differs from the searched article date.",
                "Use the article published_date from articles_data.",
            )

    evidence_bias = _normalize_text(str(evidence.get("bias_category", "") or ""))
    article_bias = _normalize_text(str(article.get("bias_category", "") or ""))
    if evidence_bias and article_bias and evidence_bias != article_bias:
        _issue(
            issues,
            "warning",
            path,
            "Evidence bias_category differs from the searched article bias_category.",
            "Use the bias_category assigned in articles_data.",
        )

    return article


def _verify_evidence_list(
    evidence_items: list[Any],
    path: str,
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    verified = []
    for idx, evidence in enumerate(evidence_items or []):
        evidence_dict = _as_dict(evidence)
        article = _verify_evidence_item(
            evidence_dict, f"{path}.evidence[{idx}]", article_index, issues
        )
        if article:
            verified.append((evidence_dict, article))
    return verified


def _verify_consensus_facts(
    facts_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    for idx, fact in enumerate(facts_data.get("consensus_facts") or []):
        fact_dict = _as_dict(fact)
        path = f"facts.consensus_facts[{idx}]"
        evidence_items = fact_dict.get("evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                path,
                "Consensus fact has no evidence trail.",
                "Attach at least two evidence items from independent searched sources.",
            )
            continue

        verified = _verify_evidence_list(evidence_items, path, article_index, issues)
        source_keys = {_source_key(article, evidence) for evidence, article in verified}
        source_keys.discard("")
        if len(source_keys) < 2:
            _issue(
                issues,
                "error",
                path,
                "Consensus fact is not supported by at least two independent sources.",
                "Move this to disputed/uncertain claims or add another independent supporting article.",
            )




def _verify_disputes(
    container: dict[str, Any],
    path_prefix: str,
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    for idx, dispute in enumerate(container.get("disputed_claims") or []):
        dispute_dict = _as_dict(dispute)
        path = f"{path_prefix}.disputed_claims[{idx}]"
        for side in ("side_a", "side_b"):
            evidence_items = dispute_dict.get(f"{side}_evidence") or []
            if not evidence_items:
                _issue(
                    issues,
                    "error",
                    f"{path}.{side}_evidence",
                    f"{side} is missing evidence for a disputed claim.",
                    "Attach at least one URL and quote for each side of the dispute.",
                )
                continue
            _verify_evidence_list(
                evidence_items, f"{path}.{side}", article_index, issues
            )


def _verify_timeline(
    facts_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    if facts_data.get("timeline_events") and not facts_data.get("timeline"):
        _issue(
            issues,
            "error",
            "facts.timeline",
            "timeline_events were provided without structured timeline evidence.",
            "Populate timeline with date, event, and evidence objects for each key event.",
        )

    parsed_dates: list[tuple[int, datetime]] = []
    for idx, event in enumerate(facts_data.get("timeline") or []):
        event_dict = _as_dict(event)
        path = f"facts.timeline[{idx}]"
        evidence_items = event_dict.get("evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                path,
                "Timeline event is missing evidence.",
                "Attach at least one evidence item with URL, published_date, and quote.",
            )
        else:
            _verify_evidence_list(evidence_items, path, article_index, issues)

        date = _date_key(str(event_dict.get("date", "") or ""))
        if date:
            parsed_dates.append((idx, date))

    for (_left_idx, left_date), (right_idx, right_date) in pairwise(parsed_dates):
        if right_date < left_date:
            _issue(
                issues,
                "error",
                f"facts.timeline[{right_idx}].date",
                "Timeline events are not in chronological order.",
                "Sort structured timeline events from earliest to latest.",
            )


def _verify_narratives(
    narratives_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    for idx, profile in enumerate(narratives_data.get("profiles") or []):
        profile_dict = _as_dict(profile)
        path = f"narratives.profiles[{idx}]"
        evidence_items = profile_dict.get("evidence") or []
        if not evidence_items and not profile_dict.get("is_speculative"):
            _issue(
                issues,
                "error",
                path,
                "Non-speculative narrative profile has no evidence.",
                "Attach representative article evidence or mark the profile as speculative.",
            )
            continue
        _verify_evidence_list(evidence_items, path, article_index, issues)


def _reference_citation_found(citation: str, reference_text_norm: str) -> bool:
    citation_norm = _normalize_text(citation)
    if not citation_norm:
        return False
    if citation_norm in reference_text_norm:
        return True
    content_words = [word for word in citation_norm.split() if len(word) > 3]
    if not content_words:
        return False
    hits = sum(1 for word in content_words if word in reference_text_norm)
    return hits / len(content_words) >= 0.6


def _is_hyperlink(text: str) -> bool:
    t = text.lower()
    if t.startswith("http://") or t.startswith("https://"):
        return True
    if "[" in t and "]" in t and "(" in t and ")" in t:
        try:
            inner = t.split("(", 1)[1].split(")", 1)[0]
            if "http://" in inner or "https://" in inner:
                return True
        except IndexError:
            pass
    return False


def _verify_experts(
    experts_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
    reference_text: str = "",
) -> None:
    for idx, opinion in enumerate(experts_data.get("expert_opinions") or []):
        opinion_dict = _as_dict(opinion)
        path = f"experts.expert_opinions[{idx}]"
        cited_references = opinion_dict.get("cited_references") or []
        if not cited_references:
            _issue(
                issues,
                "error",
                path,
                "Expert opinion does not cite any sources or references.",
                "Populate cited_references with authoritative sources or markdown links.",
            )
        else:
            for ref_idx, citation in enumerate(cited_references):
                citation_str = str(citation).strip()
                if not _is_hyperlink(citation_str):
                    _issue(
                        issues,
                        "warning",
                        f"{path}.cited_references[{ref_idx}]",
                        "Cited reference is not formatted as a markdown link or URL.",
                        "Format reference as a clickable markdown link like [Title](URL) or a valid URL.",
                    )

        recommended_reading = opinion_dict.get("recommended_reading_or_context") or []
        for ref_idx, item in enumerate(recommended_reading):
            item_str = str(item).strip()
            if not _is_hyperlink(item_str):
                _issue(
                    issues,
                    "warning",
                    f"{path}.recommended_reading_or_context[{ref_idx}]",
                    "Recommended reading is not formatted as a markdown link or URL.",
                    "Format recommended reading as a clickable markdown link like [Title](URL) or a valid URL.",
                )

        evidence_items = opinion_dict.get("supporting_evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                path,
                "Expert opinion has no supporting evidence from verified facts.",
                "Attach upstream evidence items that the commentary relies on.",
            )
            continue
        _verify_evidence_list(evidence_items, path, article_index, issues)


def _verify_outlook(
    outlook_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    if not outlook_data.get("time_horizon"):
        _issue(
            issues,
            "warning",
            "outlook.time_horizon",
            "Future outlook does not state a time horizon.",
            "State the forecast horizon, such as 'next 30-90 days'.",
        )

    most_likely = _as_dict(outlook_data.get("most_likely_scenario"))
    if not most_likely:
        _issue(
            issues,
            "error",
            "outlook.most_likely_scenario",
            "Most-likely scenario is missing.",
            "Populate most_likely_scenario as a structured scenario with evidence.",
        )
    else:
        evidence_items = most_likely.get("supporting_evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                "outlook.most_likely_scenario.supporting_evidence",
                "Most-likely scenario has no supporting evidence.",
                "Attach upstream evidence items that justify the scenario.",
            )
        else:
            _verify_evidence_list(
                evidence_items, "outlook.most_likely_scenario", article_index, issues
            )

    for idx, scenario in enumerate(outlook_data.get("alternative_scenarios") or []):
        scenario_dict = _as_dict(scenario)
        path = f"outlook.alternative_scenarios[{idx}]"
        evidence_items = scenario_dict.get("supporting_evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                path,
                "Alternative scenario has no supporting evidence.",
                "Attach upstream evidence items that support the scenario logic.",
            )
        else:
            _verify_evidence_list(evidence_items, path, article_index, issues)


def _verify_public_report(
    report_data: dict[str, Any],
    article_index: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    takeaways = report_data.get("key_takeaways") or []
    if not takeaways:
        _issue(
            issues,
            "error",
            "report.key_takeaways",
            "Public report has no key takeaways.",
            "Provide 3-5 takeaways, each backed by upstream evidence.",
        )
    for idx, takeaway in enumerate(takeaways):
        takeaway_dict = _as_dict(takeaway)
        path = f"report.key_takeaways[{idx}]"
        evidence_items = takeaway_dict.get("evidence") or []
        if not evidence_items:
            _issue(
                issues,
                "error",
                path,
                "Key takeaway has no evidence trail.",
                "Attach at least one EvidenceItem copied from upstream verified outputs.",
            )
            continue
        _verify_evidence_list(evidence_items, path, article_index, issues)





def verify_analysis_evidence(
    articles_data: dict[str, Any],
    *,
    facts_data: dict[str, Any] | None = None,
    dispute_data: dict[str, Any] | None = None,
    narratives_data: dict[str, Any] | None = None,
    experts_data: dict[str, Any] | None = None,
    outlook_data: dict[str, Any] | None = None,
    report_data: dict[str, Any] | None = None,
    reference_text: str = "",
) -> dict[str, Any]:
    article_index, articles = _build_article_index(articles_data)
    issues: list[dict[str, str]] = []

    if not article_index:
        _issue(
            issues,
            "error",
            "articles",
            "No searchable article index is available for evidence verification.",
            "Run Search Agent successfully before auditing evidence-bearing outputs.",
        )

    if facts_data:
        facts_dict = _as_dict(facts_data)
        _verify_consensus_facts(facts_dict, article_index, issues)
        _verify_timeline(facts_dict, article_index, issues)

    if dispute_data:
        _verify_disputes(_as_dict(dispute_data), "disputes", article_index, issues)

    if narratives_data:
        _verify_narratives(_as_dict(narratives_data), article_index, issues)

    if experts_data:
        _verify_experts(
            _as_dict(experts_data), article_index, issues, reference_text=reference_text
        )

    if outlook_data:
        _verify_outlook(_as_dict(outlook_data), article_index, issues)

    if report_data:
        _verify_public_report(_as_dict(report_data), article_index, issues)

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    checked_urls = {
        _normalize_url(str(article.get("url", "") or "")) for article in articles
    }
    checked_urls.discard("")

    return {
        "passed": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "checked_article_count": len(checked_urls),
        "issue_count": len(issues),
        "issues": issues,
        "summary": (
            "Evidence verification passed"
            if error_count == 0
            else f"Evidence verification found {error_count} blocking issue(s)"
        ),
    }


def format_verification_report(report: dict[str, Any], max_issues: int = 20) -> str:
    trimmed = dict(report)
    issues = list(trimmed.get("issues") or [])
    if len(issues) > max_issues:
        trimmed["issues"] = issues[:max_issues]
        trimmed["truncated_issue_count"] = len(issues) - max_issues
    return json.dumps(trimmed, ensure_ascii=True, indent=2)
