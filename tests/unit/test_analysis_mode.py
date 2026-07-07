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
    search_profile_for_mode,
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


def _full_articles_data(article_count: int = 12) -> dict:
    return {
        "topic": "Policy topic",
        "search_status": "Good",
        "verification_summary": "Multiple sources found.",
        "source_balance": {"Center": article_count},
        "articles": [
            {
                "source": f"Source {idx}",
                "title": f"Policy update {idx}",
                "url": f"https://example.com/policy-{idx}",
                "published_date": "2026-07-01",
                "bias_category": "Center",
                "neutrality": "HIGH_NEUTRALITY",
                "summary": "S" * 900,
                "full_content_snippet": "N" * 900,
                "body": f"FULL_ARTICLE_BODY_SHOULD_STAY_STORED_{idx}",
            }
            for idx in range(article_count)
        ],
    }


async def _run_mocked_pipeline(
    *,
    analysis_mode: str,
    recruitment_result: dict,
) -> tuple[dict, dict, dict, dict, dict]:
    coordinator = NewsAnalysisCoordinator()
    articles_data = _full_articles_data()
    run_metrics = create_run_metrics("gemini-3.1-flash-lite")
    control_state = {
        "control": {"paused": False, "stopped": False},
        "run_metrics": run_metrics,
    }
    captured: dict = {
        "prompts": {},
        "verifier_articles": [],
    }

    async def fake_run_agent(
        self,
        agent,
        prompt_text,
        ctx,
        out_result,
        max_retries=3,
        run_metrics=None,
    ):
        if agent.name == "input_check_agent":
            out_result.append(
                {
                    "action": "accept",
                    "is_news_related": True,
                    "explanation": "Accepted.",
                    "notification_message": None,
                    "converted_query": None,
                }
            )
        else:
            out_result.append({})
        if False:
            yield Event(author=agent.name)

    async def fake_run_agent_with_audit(
        self,
        agent,
        prompt_generator,
        criteria,
        ctx,
        call_callback,
        step_name,
        editor_logs,
        out_result,
        max_revision_cycles=2,
        control_state=None,
        model_name=None,
        deterministic_check=None,
        audit_context_generator=None,
    ):
        captured["prompts"][step_name] = prompt_generator("", [])
        if step_name == "search":
            output = articles_data
        elif step_name == "recruiter":
            output = dict(recruitment_result)
        elif step_name == "fact_bias":
            output = {
                "consensus_facts": [],
                "timeline_events": [],
                "timeline": [],
            }
        elif step_name == "public_report":
            output = {
                "title": "Policy briefing",
                "lead_paragraph": "Briefing lead.",
                "key_takeaways": [],
                "narrative_summary": "",
                "future_outlook": "",
            }
        else:
            output = {}

        if deterministic_check:
            deterministic_check(output)
        out_result.append((output, True))
        if False:
            yield Event(author=agent.name)

    def fake_verify(articles_arg, **kwargs):
        captured["verifier_articles"].append(articles_arg)
        return {
            "passed": True,
            "issue_count": 0,
            "issues": [],
            "summary": "ok",
        }

    with (
        patch.object(NewsAnalysisCoordinator, "_run_agent", new=fake_run_agent),
        patch.object(
            NewsAnalysisCoordinator,
            "_run_agent_with_audit",
            new=fake_run_agent_with_audit,
        ),
        patch("agents.coordinator.verify_analysis_evidence", side_effect=fake_verify),
    ):
        results = await coordinator.analyze(
            "Policy topic",
            control_state=control_state,
            results_dict={},
            analysis_mode=analysis_mode,
        )

    return results, captured, control_state, run_metrics, articles_data


def test_normalize_analysis_mode_defaults_to_balanced() -> None:
    assert normalize_analysis_mode(None) == "balanced"
    assert normalize_analysis_mode("") == "balanced"
    assert normalize_analysis_mode("default") == "balanced"
    assert normalize_analysis_mode("unknown") == "balanced"
    assert normalize_analysis_mode("FAST") == "fast"
    assert normalize_analysis_mode("full depth") == "balanced"


def test_analysis_mode_configs_preserve_balanced_defaults() -> None:
    balanced = get_analysis_mode_config("balanced")

    assert balanced["mode"] == "balanced"
    assert balanced["compact_downstream_context"] is False
    assert balanced["downstream_article_limit"] is None
    assert balanced["search_profile"] == "balanced"
    assert balanced["fast_optional_module_policy"] is False
    assert audit_revision_cycles_for("balanced", "default") == 2
    assert audit_revision_cycles_for("balanced", "recruiter") == 1


def test_deep_mode_uses_a_larger_pool_and_extra_audit_cycles() -> None:
    deep = get_analysis_mode_config("deep")

    assert deep["mode"] == "deep"
    # Deep should never fall back to the compact/limited context Fast mode
    # uses -- it's meant to see strictly more than Balanced, not less.
    assert deep["compact_downstream_context"] is False
    assert deep["downstream_article_limit"] is None
    assert deep["search_profile"] == "deep"
    assert deep["search_prompt_article_target"] == "18-24"
    assert deep["fast_optional_module_policy"] is False
    assert audit_revision_cycles_for("deep", "default") == 3
    assert audit_revision_cycles_for("deep", "recruiter") == 2


def test_fast_mode_uses_compact_context_and_lighter_audit_cycles() -> None:
    config = get_analysis_mode_config("fast")

    assert config["mode"] == "fast"
    assert should_use_compact_context("fast") is True
    assert max_articles_for_downstream("fast") == 10
    assert max_articles_for_qa("fast") is None
    assert search_profile_for_mode("fast") == "fast"
    assert config["search_prompt_article_target"] == "8-10"
    assert config["fast_optional_module_policy"] is True
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


def test_fast_coordinator_uses_compact_context_and_keeps_full_verifier_input() -> None:
    recruitment = {
        "recruit_dispute": False,
        "recruit_perspective": False,
        "recruit_expert": True,
        "recruit_future_outlook": True,
        "recruitment_justification": "Low complexity but optional modules suggested.",
        "complexity_level": "low",
        "recruited_agents": [
            "Expert Agent",
            "Future Outlook Agent",
        ],
        "skipped_agents": [],
    }

    results, captured, control_state, run_metrics, articles_data = asyncio.run(
        _run_mocked_pipeline(analysis_mode="fast", recruitment_result=recruitment)
    )

    recruiter_prompt = captured["prompts"]["recruiter"]
    fact_prompt = captured["prompts"]["fact_bias"]
    assert "article_count_included" in recruiter_prompt
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED" not in recruiter_prompt
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED" not in fact_prompt

    assert results["articles"] is articles_data
    assert (
        results["articles"]["articles"][0]["body"]
        == "FULL_ARTICLE_BODY_SHOULD_STAY_STORED_0"
    )
    assert captured["verifier_articles"]
    assert all(article_payload is articles_data for article_payload in captured["verifier_articles"])

    adjustments = results["fast_mode_adjustments"]
    assert adjustments["enabled"] is True
    assert adjustments["source_search_profile"] == "fast"
    assert adjustments["compact_context_used"] is True
    assert adjustments["full_article_count"] == 12
    assert adjustments["compact_article_count"] == 10
    assert adjustments["approximate_context_reduction"] > 0
    assert adjustments["audit_revision_cycles_used"] == {
        "default": 1,
        "recruiter": 0,
    }
    assert adjustments["optional_modules_skipped_by_fast_mode"] == [
        "Expert Agent",
        "Future Outlook Agent",
    ]
    assert control_state["step_statuses"]["expert"] == "skipped"
    assert control_state["step_statuses"]["outlook"] == "skipped"
    assert run_metrics["fast_mode_adjustments"] == adjustments


def test_balanced_coordinator_uses_full_context_and_no_fast_skips() -> None:
    recruitment = {
        "recruit_dispute": False,
        "recruit_perspective": False,
        "recruit_expert": True,
        "recruit_future_outlook": True,
        "recruitment_justification": "Low complexity but optional modules suggested.",
        "complexity_level": "low",
        "recruited_agents": [
            "Expert Agent",
            "Future Outlook Agent",
        ],
        "skipped_agents": [],
    }

    results, captured, control_state, run_metrics, articles_data = asyncio.run(
        _run_mocked_pipeline(analysis_mode="balanced", recruitment_result=recruitment)
    )

    recruiter_prompt = captured["prompts"]["recruiter"]
    fact_prompt = captured["prompts"]["fact_bias"]
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED_0" in recruiter_prompt
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED_0" in fact_prompt
    assert "article_count_included" not in recruiter_prompt

    adjustments = results["fast_mode_adjustments"]
    assert adjustments["enabled"] is False
    assert adjustments["source_search_profile"] == "balanced"
    assert adjustments["compact_context_used"] is False
    assert adjustments["audit_revision_cycles_used"] == {
        "default": 2,
        "recruiter": 1,
    }
    assert adjustments["optional_modules_skipped_by_fast_mode"] == []
    assert control_state["step_statuses"]["expert"] == "completed"
    assert control_state["step_statuses"]["outlook"] == "completed"
    assert results["articles"] is articles_data
    assert run_metrics["fast_mode_adjustments"] == adjustments


def test_deep_coordinator_uses_full_context_extra_audits_and_no_fast_skips() -> None:
    recruitment = {
        "recruit_dispute": False,
        "recruit_perspective": False,
        "recruit_expert": True,
        "recruit_future_outlook": True,
        "recruitment_justification": "Low complexity but optional modules suggested.",
        "complexity_level": "low",
        "recruited_agents": [
            "Expert Agent",
            "Future Outlook Agent",
        ],
        "skipped_agents": [],
    }

    results, captured, control_state, run_metrics, articles_data = asyncio.run(
        _run_mocked_pipeline(analysis_mode="deep", recruitment_result=recruitment)
    )

    recruiter_prompt = captured["prompts"]["recruiter"]
    fact_prompt = captured["prompts"]["fact_bias"]
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED_0" in recruiter_prompt
    assert "FULL_ARTICLE_BODY_SHOULD_STAY_STORED_0" in fact_prompt
    assert "article_count_included" not in recruiter_prompt

    adjustments = results["fast_mode_adjustments"]
    assert adjustments["enabled"] is False
    assert adjustments["source_search_profile"] == "deep"
    assert adjustments["compact_context_used"] is False
    assert adjustments["audit_revision_cycles_used"] == {
        "default": 3,
        "recruiter": 2,
    }
    assert adjustments["optional_modules_skipped_by_fast_mode"] == []
    assert control_state["step_statuses"]["expert"] == "completed"
    assert control_state["step_statuses"]["outlook"] == "completed"
    assert results["articles"] is articles_data
    assert run_metrics["fast_mode_adjustments"] == adjustments
