import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.adk.agents import Agent

from agents.app_utils.run_metrics import create_run_metrics
from agents.coordinator import InvocationContext, NewsAnalysisCoordinator


def _usage_event(
    *,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
    marker: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=input_tokens,
            candidates_token_count=output_tokens,
            total_token_count=total_tokens or input_tokens + output_tokens,
        ),
        actions=None,
        marker=marker,
    )


async def _test_context(
    coordinator: NewsAnalysisCoordinator,
    session_id: str,
) -> InvocationContext:
    session = await coordinator.session_service.create_session(
        app_name="news_app",
        user_id="user",
        session_id=session_id,
    )
    return InvocationContext(
        invocation_id=session_id,
        session_service=coordinator.session_service,
        session=session,
    )


def _agent(name: str, output_key: str = "dummy_output") -> Agent:
    return Agent(
        name=name,
        model="gemini-3.1-flash-lite",
        instruction="Return a structured result.",
        output_key=output_key,
    )


def test_run_agent_merges_multiple_streamed_usage_events_and_records_success() -> None:
    coordinator = NewsAnalysisCoordinator()
    metrics = create_run_metrics("gemini-3.1-flash-lite")
    agent = _agent("streamed_usage_agent")

    async def fake_run_async(self, ctx):
        ctx.session.state["dummy_output"] = {"summary": "RESULT_SHOULD_NOT_BE_STORED"}
        yield _usage_event(input_tokens=3, output_tokens=2, marker="RAW_EVENT_ONE")
        yield _usage_event(input_tokens=5, output_tokens=7, marker="RAW_EVENT_TWO")

    async def run_test() -> list:
        ctx = await _test_context(coordinator, "sess_streamed_usage")
        out_result = []
        async for _ in coordinator._run_agent(
            agent,
            "PROMPT_SHOULD_NOT_BE_STORED",
            ctx,
            out_result,
            run_metrics=metrics,
        ):
            pass
        return out_result

    with patch.object(Agent, "run_async", new=fake_run_async):
        out_result = asyncio.run(run_test())

    assert out_result == [{"summary": "RESULT_SHOULD_NOT_BE_STORED"}]
    usage = metrics["token_usage"]
    agent_usage = usage["by_agent"]["streamed_usage_agent"]
    assert usage["usage_type"] == "actual"
    assert agent_usage == {
        "usage_type": "actual",
        "input_tokens": 8,
        "output_tokens": 9,
        "total_tokens": 17,
    }
    timing = metrics["agent_timings"]["by_agent"]["streamed_usage_agent"]
    assert timing["call_count"] == 1
    assert timing["last_status"] == "completed"
    assert timing["duration_seconds"] >= 0

    metrics_text = str(metrics)
    assert "PROMPT_SHOULD_NOT_BE_STORED" not in metrics_text
    assert "RESULT_SHOULD_NOT_BE_STORED" not in metrics_text
    assert "RAW_EVENT_ONE" not in metrics_text
    assert "RAW_EVENT_TWO" not in metrics_text


def test_run_agent_records_failure_timing_without_leaking_payloads() -> None:
    coordinator = NewsAnalysisCoordinator()
    metrics = create_run_metrics("gemini-3.1-flash-lite")
    agent = _agent("failing_metrics_agent")

    async def fake_run_async(self, ctx):
        raise ValueError("FULL_RESPONSE_SHOULD_NOT_BE_STORED")
        yield

    async def run_test() -> None:
        ctx = await _test_context(coordinator, "sess_failure_metrics")
        out_result = []
        async for _ in coordinator._run_agent(
            agent,
            "PROMPT_SHOULD_NOT_BE_STORED",
            ctx,
            out_result,
            max_retries=1,
            run_metrics=metrics,
        ):
            pass

    with patch.object(Agent, "run_async", new=fake_run_async):
        with pytest.raises(ValueError, match="FULL_RESPONSE_SHOULD_NOT_BE_STORED"):
            asyncio.run(run_test())

    usage = metrics["token_usage"]
    assert usage["usage_type"] == "estimated"
    assert usage["input_tokens"] > 0
    timing = metrics["agent_timings"]["by_agent"]["failing_metrics_agent"]
    assert timing["call_count"] == 1
    assert timing["last_status"] == "failed"
    assert timing["duration_seconds"] >= 0

    metrics_text = str(metrics)
    assert "PROMPT_SHOULD_NOT_BE_STORED" not in metrics_text
    assert "FULL_RESPONSE_SHOULD_NOT_BE_STORED" not in metrics_text


def test_run_agent_retry_aggregates_timing_and_token_usage_for_same_agent() -> None:
    coordinator = NewsAnalysisCoordinator()
    metrics = create_run_metrics("gemini-3.1-flash-lite")
    agent = _agent("retry_metrics_agent")
    calls = {"count": 0}

    async def fake_run_async(self, ctx):
        calls["count"] += 1
        if calls["count"] == 1:
            yield _usage_event(input_tokens=2, output_tokens=1, marker="RAW_RETRY_EVENT")
            raise ValueError("malformed structured output")
        ctx.session.state["dummy_output"] = {"ok": True}
        yield _usage_event(input_tokens=4, output_tokens=3)

    async def run_test() -> list:
        ctx = await _test_context(coordinator, "sess_retry_metrics")
        out_result = []
        async for _ in coordinator._run_agent(
            agent,
            "Initial prompt.",
            ctx,
            out_result,
            max_retries=2,
            run_metrics=metrics,
        ):
            pass
        return out_result

    with patch.object(Agent, "run_async", new=fake_run_async):
        out_result = asyncio.run(run_test())

    assert calls["count"] == 2
    assert out_result == [{"ok": True}]
    agent_usage = metrics["token_usage"]["by_agent"]["retry_metrics_agent"]
    assert agent_usage["usage_type"] == "actual"
    assert agent_usage["input_tokens"] == 6
    assert agent_usage["output_tokens"] == 4
    assert agent_usage["total_tokens"] == 10
    timing = metrics["agent_timings"]["by_agent"]["retry_metrics_agent"]
    assert timing["call_count"] == 2
    assert timing["last_status"] == "completed"
    assert timing["duration_seconds"] >= 0
    assert "RAW_RETRY_EVENT" not in str(metrics)


def test_run_agent_metrics_keep_parallel_agent_names_separate() -> None:
    coordinator = NewsAnalysisCoordinator()
    metrics = create_run_metrics("gemini-3.1-flash-lite")
    first_agent = _agent("parallel_first_agent", output_key="first_output")
    second_agent = _agent("parallel_second_agent", output_key="second_output")

    async def fake_run_async(self, ctx):
        if self.name == "parallel_first_agent":
            ctx.session.state["first_output"] = {"first": True}
            yield _usage_event(input_tokens=7, output_tokens=1)
        else:
            ctx.session.state["second_output"] = {"second": True}
            yield _usage_event(input_tokens=11, output_tokens=2)

    async def run_agent_once(agent: Agent, session_id: str) -> list:
        ctx = await _test_context(coordinator, session_id)
        out_result = []
        async for _ in coordinator._run_agent(
            agent,
            f"Prompt for {agent.name}",
            ctx,
            out_result,
            run_metrics=metrics,
        ):
            pass
        return out_result

    async def run_test() -> tuple[list, list]:
        return await asyncio.gather(
            run_agent_once(first_agent, "sess_parallel_first"),
            run_agent_once(second_agent, "sess_parallel_second"),
        )

    with patch.object(Agent, "run_async", new=fake_run_async):
        first_result, second_result = asyncio.run(run_test())

    assert first_result == [{"first": True}]
    assert second_result == [{"second": True}]
    usage_by_agent = metrics["token_usage"]["by_agent"]
    assert usage_by_agent["parallel_first_agent"]["input_tokens"] == 7
    assert usage_by_agent["parallel_first_agent"]["output_tokens"] == 1
    assert usage_by_agent["parallel_second_agent"]["input_tokens"] == 11
    assert usage_by_agent["parallel_second_agent"]["output_tokens"] == 2
    timings = metrics["agent_timings"]["by_agent"]
    assert timings["parallel_first_agent"]["call_count"] == 1
    assert timings["parallel_second_agent"]["call_count"] == 1


def test_run_agent_with_audit_records_target_and_audit_metrics_from_control_state() -> None:
    coordinator = NewsAnalysisCoordinator()
    metrics = create_run_metrics("gemini-3.1-flash-lite")
    target_agent = _agent("audit_target_agent", output_key="target_output")
    control_state = {"run_metrics": metrics}

    async def fake_run_async(self, ctx):
        if self.name == "audit_target_agent":
            ctx.session.state["target_output"] = {"value": "draft"}
            yield _usage_event(input_tokens=13, output_tokens=5)
        else:
            ctx.session.state["audit_result"] = {
                "is_approved": True,
                "audit_feedback": [],
                "recommended_fixes": [],
            }
            yield _usage_event(input_tokens=17, output_tokens=3)

    async def noop_callback(*args, **kwargs) -> None:
        return None

    async def run_test() -> tuple[list, list]:
        ctx = await _test_context(coordinator, "sess_audit_metrics")
        editor_logs: list = []
        out_result: list = []
        async for _ in coordinator._run_agent_with_audit(
            target_agent,
            lambda feedback, suggestions: "Produce audited output.",
            "Audit criteria.",
            ctx,
            noop_callback,
            "audit_test_step",
            editor_logs,
            out_result,
            max_revision_cycles=1,
            control_state=control_state,
        ):
            pass
        return editor_logs, out_result

    with patch.object(Agent, "run_async", new=fake_run_async):
        editor_logs, out_result = asyncio.run(run_test())

    assert out_result == [({"value": "draft"}, True)]
    assert [log["approved"] for log in editor_logs] == [True]
    usage_by_agent = metrics["token_usage"]["by_agent"]
    assert usage_by_agent["audit_target_agent"]["total_tokens"] == 18
    assert usage_by_agent["audit_target_agent_audit"]["total_tokens"] == 20
    assert metrics["agent_timings"]["by_agent"]["audit_target_agent"]["call_count"] == 1
    assert (
        metrics["agent_timings"]["by_agent"]["audit_target_agent_audit"]["call_count"]
        == 1
    )
