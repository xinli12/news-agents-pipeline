import asyncio
from unittest.mock import patch

from google.adk.agents import Agent
from google.adk.events import Event

from agents.app_utils.analysis_mode import (
    article_context_stats_for_mode,
    audit_revision_cycles_for,
    build_articles_context_for_mode,
    get_analysis_mode_config,
    max_articles_for_downstream,
    max_articles_for_qa,
    normalize_analysis_mode,
    should_use_compact_context,
)
from agents.app_utils.run_metrics import create_run_metrics
from agents.coordinator import NewsAnalysisCoordinator


def _articles_data() -> dict:
    return {
        "topic": "Policy topic",
        "articles": [
            {
                "source": "Reuters",
                "title": "Policy update draws response",
                "url": "https://example.com/policy-update",
                "published_date": "2026-07-01",
                "bias_category": "Center",
                "neutrality": "HIGH_NEUTRALITY",
                "summary": "S" * 900,
                "full_content_snippet": "N" * 900,
                "body": "FULL_ARTICLE_BODY_SHOULD_NOT_BE_IN_COMPACT_CONTEXT",
            },
            {
                "source": "AP",
                "title": "Second policy story",
                "url": "https://example.com/second",
                "published_date": "2026-07-02",
                "bias_category": "Center",
                "neutrality": "MEDIUM_NEUTRALITY",
                "summary": "Second summary.",
                "full_content_snippet": "Second snippet.",
            },
        ],
    }


def test_normalize_analysis_mode_defaults_to_balanced() -> None:
    assert normalize_analysis_mode(None) == "balanced"
    assert normalize_analysis_mode("") == "balanced"
    assert normalize_analysis_mode("default") == "balanced"
    assert normalize_analysis_mode("unknown") == "balanced"
    assert normalize_analysis_mode("FAST") == "fast"
    assert normalize_analysis_mode("full depth") == "balanced"


def test_analysis_mode_configs_preserve_balanced_defaults() -> None:
    balanced = get_analysis_mode_config("balanced")
    deep = get_analysis_mode_config("deep")

    assert balanced["mode"] == "balanced"
    assert balanced["compact_downstream_context"] is False
    assert balanced["downstream_article_limit"] is None
    assert audit_revision_cycles_for("balanced", "default") == 2
    assert audit_revision_cycles_for("balanced", "recruiter") == 1

    assert deep["mode"] == "deep"
    assert deep["compact_downstream_context"] is False
    assert audit_revision_cycles_for("deep", "default") == 2
    assert audit_revision_cycles_for("deep", "recruiter") == 1


def test_fast_mode_uses_compact_context_and_lighter_audit_cycles() -> None:
    config = get_analysis_mode_config("fast")

    assert config["mode"] == "fast"
    assert should_use_compact_context("fast") is True
    assert max_articles_for_downstream("fast") == 10
    assert max_articles_for_qa("fast") is None
    assert audit_revision_cycles_for("fast", "default") == 1
    assert audit_revision_cycles_for("fast", "recruiter") == 0


def test_balanced_and_deep_use_original_articles_context() -> None:
    articles_data = _articles_data()

    assert build_articles_context_for_mode(articles_data, "balanced") is articles_data
    assert build_articles_context_for_mode(articles_data, "deep") is articles_data
    assert should_use_compact_context("balanced") is False
    assert should_use_compact_context("deep") is False


def test_fast_compact_context_does_not_mutate_full_articles_data() -> None:
    articles_data = _articles_data()

    compact = build_articles_context_for_mode(articles_data, "fast")

    assert compact is not articles_data
    assert compact["article_count_available"] == 2
    assert compact["article_count_included"] == 2
    assert "body" not in compact["articles"][0]
    assert len(compact["articles"][0]["summary"]) == 700
    assert (
        articles_data["articles"][0]["body"]
        == "FULL_ARTICLE_BODY_SHOULD_NOT_BE_IN_COMPACT_CONTEXT"
    )
    assert len(articles_data["articles"][0]["summary"]) == 900


def test_article_context_stats_for_mode_marks_fast_compaction() -> None:
    stats = article_context_stats_for_mode(_articles_data(), "fast")

    assert stats["mode"] == "fast"
    assert stats["compact_context_enabled"] is True
    assert stats["article_count"] == 2
    assert stats["compact_article_count"] == 2
    assert stats["reduction_chars"] > 0


def test_coordinator_stores_analysis_mode_in_results_control_state_and_metrics() -> None:
    coordinator = NewsAnalysisCoordinator()
    run_metrics = create_run_metrics("gemini-3.1-flash-lite")
    control_state = {
        "control": {"paused": False, "stopped": False},
        "run_metrics": run_metrics,
    }

    async def fake_run_async(self, ctx):
        ctx.session.state[self.output_key] = {
            "action": "reject_with_confirmation",
            "is_news_related": False,
            "explanation": "Not a news topic.",
            "notification_message": "Please enter a news topic.",
            "converted_query": None,
        }
        yield Event(author=self.name)

    async def run_test() -> dict:
        with patch.object(Agent, "run_async", new=fake_run_async):
            return await coordinator.analyze(
                "not news",
                control_state=control_state,
                results_dict={},
                analysis_mode="FAST",
            )

    results = asyncio.run(run_test())

    assert results["analysis_mode"] == "fast"
    assert results["analysis_mode_label"] == "Fast"
    assert control_state["analysis_mode"] == "fast"
    assert control_state["analysis_mode_label"] == "Fast"
    assert run_metrics["analysis_mode"] == "fast"
    assert run_metrics["analysis_mode_label"] == "Fast"
