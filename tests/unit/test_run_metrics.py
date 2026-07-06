from types import SimpleNamespace

from agents.app_utils.run_metrics import (
    build_metrics_summary,
    create_run_metrics,
    estimate_cost,
    estimate_tokens_from_text,
    extract_event_token_usage,
    finalize_run_metrics,
    format_duration,
    merge_usage_counts,
    record_agent_call,
    record_agent_token_usage,
    record_progress_event,
    record_result_token_estimate,
    record_step_call_once,
)


def test_format_duration_seconds_minutes_and_hours() -> None:
    assert format_duration(None) == "not available"
    assert format_duration(4.25) == "4.2s"
    assert format_duration(65.2) == "1m 05.2s"
    assert format_duration(3661.5) == "1h 1m 01.5s"


def test_step_timing_aggregation_records_duration() -> None:
    metrics = create_run_metrics("test-model", start_timestamp=100.0)

    record_progress_event(metrics, "search", "Search started", timestamp=110.0)
    record_progress_event(metrics, "search_complete", "Search complete", timestamp=125.5)
    finalize_run_metrics(
        metrics,
        final_status="completed",
        step_statuses={"search": "completed"},
        end_timestamp=130.0,
    )

    search = metrics["steps"]["search"]
    assert search["status"] == "completed"
    assert search["duration_seconds"] == 15.5
    assert search["duration_display"] == "15.5s"
    assert metrics["total_runtime_seconds"] == 30.0
    assert metrics["step_counts"]["completed"] == 1


def test_token_estimate_helper_uses_character_approximation() -> None:
    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text("abcd") == 1
    assert estimate_tokens_from_text("abcde") == 2


def test_actual_usage_metadata_is_extracted_from_adk_event_shape() -> None:
    event = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=7,
            total_token_count=17,
        )
    )

    assert extract_event_token_usage(event) == {
        "input": 10,
        "output": 7,
        "total": 17,
    }


def test_agent_usage_falls_back_to_estimated_tokens() -> None:
    metrics = create_run_metrics("test-model", start_timestamp=100.0)

    record_agent_call(metrics, "search_agent")
    record_agent_token_usage(
        metrics,
        "search_agent",
        prompt_text="x" * 8,
        output_value={"answer": "y" * 8},
    )

    usage = metrics["token_usage"]
    assert metrics["agent_calls"]["total"] == 1
    assert metrics["agent_calls"]["by_agent"]["search_agent"] == 1
    assert usage["usage_type"] == "estimated"
    assert usage["input_tokens"] == 2
    assert usage["output_tokens"] > 0
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]


def test_step_call_counting_deduplicates_progress_starts() -> None:
    metrics = create_run_metrics("test-model", start_timestamp=100.0)

    record_step_call_once(metrics, "search")
    record_step_call_once(metrics, "search")
    record_step_call_once(metrics, "search_complete")
    record_step_call_once(metrics, "fact_bias")

    assert metrics["agent_calls"]["total"] == 2
    assert metrics["agent_calls"]["by_agent"]["Source Search"] == 1
    assert metrics["agent_calls"]["by_agent"]["Fact Extraction"] == 1


def test_result_token_estimate_does_not_store_result_payload() -> None:
    metrics = create_run_metrics("test-model", start_timestamp=100.0)

    record_result_token_estimate(
        metrics,
        {
            "public_report": {"lead_paragraph": "A short generated summary."},
            "run_metrics": {"should": "be ignored"},
        },
    )

    usage = metrics["token_usage"]
    assert usage["usage_type"] == "estimated"
    assert usage["output_tokens"] > 0
    assert "public_report" not in str(usage["by_agent"]["workflow_result"])


def test_cost_estimate_unknown_model_returns_not_available() -> None:
    cost = estimate_cost(
        model_name="unknown-model",
        input_tokens=100,
        output_tokens=50,
        usage_type="estimated",
    )

    assert cost["usage_type"] == "not_available"
    assert cost["estimated_total_cost"] is None
    assert cost["total_tokens"] == 150
    assert "Cost unavailable" in cost["caveat"]


def test_metrics_summary_handles_empty_and_partial_inputs() -> None:
    empty_summary = build_metrics_summary({})
    assert empty_summary["total_runtime"] == "not available"
    assert empty_summary["final_status"] == "unknown"
    assert empty_summary["agent_calls"] == 0
    assert empty_summary["token_usage_type"] == "not_available"

    partial = create_run_metrics("test-model", start_timestamp=100.0)
    merge_usage_counts({"input": 1}, {"output": 2, "total": 3})
    finalize_run_metrics(partial, "stopped", end_timestamp=103.0)
    summary = build_metrics_summary(partial)
    assert summary["total_runtime"] == "3.0s"
    assert summary["final_status"] == "stopped"
    assert summary["model_name"] == "test-model"
