from copy import deepcopy

from agents.app_utils.analysis_context import (
    article_context_stats,
    build_compact_articles_data,
    compact_article,
)


def _article(**overrides):
    data = {
        "source": "Reuters",
        "title": "Policy update draws response",
        "url": "https://example.com/policy-update",
        "published_date": "2026-07-01",
        "bias_category": "Center",
        "neutrality": "HIGH_NEUTRALITY",
        "outlet_group": "example.com",
        "wire_service": "Reuters",
        "duplicate_cluster": "Reuters: policy update draws response",
        "selection_rationale": "Wire report with direct official quotes.",
        "summary": "A concise article summary.",
        "full_content_snippet": "Officials said the policy would be reviewed after public comment.",
        "body": "FULL_ARTICLE_BODY_SHOULD_BE_REMOVED",
        "raw_scraped_text": "RAW_SCRAPED_TEXT_SHOULD_BE_REMOVED",
        "empty_field": "",
    }
    data.update(overrides)
    return data


def test_compact_article_preserves_traceability_fields() -> None:
    article = _article()

    compact = compact_article(article)

    assert compact["source"] == "Reuters"
    assert compact["title"] == "Policy update draws response"
    assert compact["url"] == "https://example.com/policy-update"
    assert compact["published_date"] == "2026-07-01"
    assert compact["bias_category"] == "Center"
    assert compact["neutrality"] == "HIGH_NEUTRALITY"
    assert compact["summary"] == "A concise article summary."
    assert compact["full_content_snippet"].startswith("Officials said")
    assert "body" not in compact
    assert "raw_scraped_text" not in compact
    assert "empty_field" not in compact


def test_compact_article_preserves_wire_and_duplicate_metadata() -> None:
    compact = compact_article(_article())

    assert compact["outlet_group"] == "example.com"
    assert compact["wire_service"] == "Reuters"
    assert compact["duplicate_cluster"] == "Reuters: policy update draws response"
    assert compact["selection_rationale"] == "Wire report with direct official quotes."


def test_compact_article_truncates_long_summary_and_snippet() -> None:
    article = _article(
        summary="S" * 80,
        full_content_snippet="N" * 80,
    )

    compact = compact_article(article, max_summary_chars=20)

    assert compact["summary"] == f"{'S' * 17}..."
    assert compact["full_content_snippet"] == f"{'N' * 17}..."
    assert len(compact["summary"]) == 20
    assert len(compact["full_content_snippet"]) == 20


def test_compact_article_uses_snippet_fallback_when_full_snippet_missing() -> None:
    article = _article(full_content_snippet="", snippet="Fallback snippet text.")

    compact = compact_article(article)

    assert compact["full_content_snippet"] == "Fallback snippet text."


def test_compact_article_preserves_evidence_relevant_fields() -> None:
    article = _article(
        evidence=[
            {
                "source": "AP",
                "title": "Residents respond",
                "url": "https://example.com/residents",
                "published_date": "2026-07-02",
                "bias_category": "Center",
                "quote": "Q" * 40,
                "raw_body": "SHOULD_NOT_SURVIVE",
            }
        ],
        quote="Article-level quote should remain traceable.",
    )

    compact = compact_article(article, max_summary_chars=20)

    evidence = compact["evidence"][0]
    assert evidence["source"] == "AP"
    assert evidence["url"] == "https://example.com/residents"
    assert evidence["quote"] == f"{'Q' * 17}..."
    assert "raw_body" not in evidence
    assert compact["quote"] == "Article-level quo..."


def test_build_compact_articles_data_does_not_mutate_input() -> None:
    articles_data = {
        "topic": "Policy topic",
        "articles": [_article(summary="S" * 80)],
    }
    original = deepcopy(articles_data)

    compact = build_compact_articles_data(articles_data, max_summary_chars=20)

    assert articles_data == original
    assert compact["articles"][0]["summary"] == f"{'S' * 17}..."
    assert articles_data["articles"][0]["summary"] == "S" * 80


def test_build_compact_articles_data_handles_missing_fields() -> None:
    compact = build_compact_articles_data({"articles": [{"url": "https://example.com"}]})

    assert compact["article_count_available"] == 1
    assert compact["article_count_included"] == 1
    assert compact["articles"] == [{"url": "https://example.com"}]


def test_build_compact_articles_data_respects_max_articles() -> None:
    articles_data = {
        "topic": "Policy topic",
        "query_used": "policy topic latest",
        "warnings": ["Source set is thin."],
        "articles": [
            _article(title="First", url="https://example.com/1"),
            _article(title="Second", url="https://example.com/2"),
            _article(title="Third", url="https://example.com/3"),
        ],
    }

    compact = build_compact_articles_data(articles_data, max_articles=2)

    assert compact["topic"] == "Policy topic"
    assert compact["query_used"] == "policy topic latest"
    assert compact["warnings"] == ["Source set is thin."]
    assert compact["article_count_available"] == 3
    assert compact["article_count_included"] == 2
    assert [article["title"] for article in compact["articles"]] == ["First", "Second"]


def test_article_context_stats_returns_useful_size_stats() -> None:
    articles_data = {
        "topic": "Policy topic",
        "articles": [
            _article(
                body="B" * 3000,
                raw_scraped_text="R" * 3000,
                full_content_snippet="N" * 1000,
            )
        ],
    }

    stats = article_context_stats(articles_data)

    assert stats["article_count"] == 1
    assert stats["compact_article_count"] == 1
    assert stats["original_json_chars"] > stats["compact_json_chars"]
    assert stats["reduction_chars"] > 0
    assert 0 < stats["reduction_ratio"] < 1
