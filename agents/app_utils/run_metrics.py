"""Best-effort runtime metrics for the Streamlit diagnostics panel."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

STEP_KEYS = [
    "review",
    "search",
    "recruiter",
    "fact_bias",
    "dispute",
    "bias_agent",
    "expert",
    "outlook",
    "public_report",
    "public_editor",
]

STEP_LABELS = {
    "review": "Input Check",
    "search": "Source Search",
    "recruiter": "Orchestrator",
    "fact_bias": "Fact Extraction",
    "dispute": "Dispute Map",
    "bias_agent": "Perspectives",
    "expert": "Expert Panel",
    "outlook": "Future Outlook",
    "public_report": "Briefing Writer",
    "public_editor": "Dashboard Editor",
}

TOKEN_CHAR_RATIO = 4
MODEL_PRICING_PER_MILLION: dict[str, dict[str, float]] = {}


def current_timestamp() -> float:
    return time.time()


def iso_timestamp(timestamp: float | int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), UTC).isoformat()


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "not available"
    try:
        total_seconds = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "not available"
    if total_seconds < 60:
        return f"{total_seconds:.1f}s"
    minutes, remaining = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {remaining:04.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {remaining:04.1f}s"


def create_run_metrics(
    model_name: str | None,
    start_timestamp: float | int | None = None,
) -> dict[str, Any]:
    started_at = float(start_timestamp or current_timestamp())
    return {
        "run_start_time": iso_timestamp(started_at),
        "run_start_timestamp": started_at,
        "run_end_time": None,
        "run_end_timestamp": None,
        "total_runtime_seconds": None,
        "total_runtime_display": "not available",
        "model_name": model_name or "",
        "final_status": "running",
        "steps": {},
        "agent_calls": {"total": 0, "by_agent": {}},
        "audits": {
            "attempt_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
        },
        "step_counts": {
            "completed": 0,
            "skipped": 0,
            "failed": 0,
            "stopped": 0,
            "running": 0,
            "queued": 0,
        },
        "warning_count": 0,
        "token_usage": {
            "usage_type": "not_available",
            "model_name": model_name or "",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "by_agent": {},
            "actual_usage_seen": False,
            "estimated_usage_seen": False,
        },
        "cost_estimate": estimate_cost(
            model_name=model_name,
            input_tokens=None,
            output_tokens=None,
            usage_type="not_available",
        ),
    }


def ensure_run_metrics(
    control_state: dict[str, Any] | None,
    results_dict: dict[str, Any] | None,
    model_name: str | None,
) -> dict[str, Any]:
    if control_state is not None:
        metrics = control_state.get("run_metrics")
        if not isinstance(metrics, dict):
            metrics = create_run_metrics(model_name)
            control_state["run_metrics"] = metrics
        if results_dict is not None:
            results_dict["run_metrics"] = metrics
        return metrics

    if results_dict is not None:
        metrics = results_dict.get("run_metrics")
        if not isinstance(metrics, dict):
            metrics = create_run_metrics(model_name)
            results_dict["run_metrics"] = metrics
        return metrics

    return create_run_metrics(model_name)


def estimate_tokens_from_text(value: Any) -> int:
    if value is None:
        return 0
    text = str(value)
    if not text:
        return 0
    return max(1, math.ceil(len(text) / TOKEN_CHAR_RATIO))


def estimate_tokens_from_value(value: Any) -> int:
    if value is None:
        return 0
    try:
        text = json.dumps(value, ensure_ascii=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return estimate_tokens_from_text(text)


def estimate_cost(
    model_name: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    usage_type: str,
) -> dict[str, Any]:
    model_key = str(model_name or "")
    pricing = MODEL_PRICING_PER_MILLION.get(model_key)
    total_tokens = None
    if input_tokens is not None or output_tokens is not None:
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

    if not pricing:
        return {
            "usage_type": "not_available",
            "model_name": model_key,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_input_cost": None,
            "estimated_output_cost": None,
            "estimated_total_cost": None,
            "currency": "USD",
            "caveat": (
                "Cost unavailable: model pricing is not maintained in this app. "
                "Provider billing may differ."
            ),
        }

    input_cost = ((input_tokens or 0) / 1_000_000) * pricing["input"]
    output_cost = ((output_tokens or 0) / 1_000_000) * pricing["output"]
    return {
        "usage_type": usage_type,
        "model_name": model_key,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_input_cost": round(input_cost, 6),
        "estimated_output_cost": round(output_cost, 6),
        "estimated_total_cost": round(input_cost + output_cost, 6),
        "currency": "USD",
        "caveat": "Estimated only. Provider billing may differ.",
    }


def record_progress_event(
    metrics: dict[str, Any],
    step: str,
    message: str | None = None,
    timestamp: float | int | None = None,
) -> None:
    timestamp_value = float(timestamp or current_timestamp())
    step_key, event_type = normalize_progress_step(step)
    if not step_key:
        return

    steps = metrics.setdefault("steps", {})
    step_record = steps.setdefault(
        step_key,
        {
            "label": STEP_LABELS.get(step_key, step_key.replace("_", " ").title()),
            "start_time": None,
            "start_timestamp": None,
            "end_time": None,
            "end_timestamp": None,
            "latest_time": None,
            "latest_timestamp": None,
            "duration_seconds": None,
            "duration_display": "not available",
            "status": "running",
            "last_message": "",
        },
    )
    if step_record.get("start_timestamp") is None:
        step_record["start_timestamp"] = timestamp_value
        step_record["start_time"] = iso_timestamp(timestamp_value)

    step_record["latest_timestamp"] = timestamp_value
    step_record["latest_time"] = iso_timestamp(timestamp_value)
    if message:
        step_record["last_message"] = message

    if event_type == "completed":
        step_record["end_timestamp"] = timestamp_value
        step_record["end_time"] = iso_timestamp(timestamp_value)
        step_record["status"] = "completed"

    _refresh_step_duration(step_record)


def normalize_progress_step(step: str | None) -> tuple[str | None, str]:
    raw_step = str(step or "")
    if raw_step in STEP_KEYS:
        return raw_step, "started"

    for suffix in ("_complete", "_approved"):
        if raw_step.endswith(suffix):
            candidate = raw_step[: -len(suffix)]
            return _canonical_step(candidate), "completed"

    for suffix in ("_rejected", "_audit"):
        if raw_step.endswith(suffix):
            candidate = raw_step[: -len(suffix)]
            return _canonical_step(candidate), "updated"

    return _canonical_step(raw_step), "updated"


def _canonical_step(step: str) -> str | None:
    if step in STEP_KEYS:
        return step
    if step == "editor":
        return "public_editor"
    return None


def _refresh_step_duration(step_record: dict[str, Any]) -> None:
    start = step_record.get("start_timestamp")
    end = step_record.get("end_timestamp") or step_record.get("latest_timestamp")
    if start is None or end is None:
        return
    duration = max(0.0, float(end) - float(start))
    step_record["duration_seconds"] = round(duration, 3)
    step_record["duration_display"] = format_duration(duration)


def record_step_statuses(
    metrics: dict[str, Any],
    step_statuses: Mapping[str, str] | None,
) -> None:
    counts = {
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "stopped": 0,
        "running": 0,
        "queued": 0,
    }
    for step_key in STEP_KEYS:
        status = str((step_statuses or {}).get(step_key, "queued"))
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
        if status in {"completed", "skipped", "failed", "stopped"}:
            step_record = metrics.setdefault("steps", {}).setdefault(
                step_key,
                {
                    "label": STEP_LABELS.get(step_key, step_key),
                    "start_time": None,
                    "start_timestamp": None,
                    "end_time": None,
                    "end_timestamp": None,
                    "latest_time": None,
                    "latest_timestamp": None,
                    "duration_seconds": None,
                    "duration_display": "not available",
                    "status": status,
                    "last_message": "",
                },
            )
            step_record["status"] = status
            _refresh_step_duration(step_record)
    metrics["step_counts"] = counts


def record_agent_call(metrics: dict[str, Any], agent_name: str | None) -> None:
    agent_label = str(agent_name or "unknown_agent")
    agent_calls = metrics.setdefault("agent_calls", {"total": 0, "by_agent": {}})
    agent_calls["total"] = int(agent_calls.get("total") or 0) + 1
    by_agent = agent_calls.setdefault("by_agent", {})
    by_agent[agent_label] = int(by_agent.get(agent_label) or 0) + 1


def record_step_call_once(metrics: dict[str, Any], step: str | None) -> None:
    step_key, event_type = normalize_progress_step(step)
    if not step_key or event_type != "started":
        return

    agent_calls = metrics.setdefault("agent_calls", {"total": 0, "by_agent": {}})
    counted_steps = agent_calls.setdefault("counted_steps", [])
    if step_key in counted_steps:
        return

    counted_steps.append(step_key)
    record_agent_call(metrics, STEP_LABELS.get(step_key, step_key))


def record_agent_token_usage(
    metrics: dict[str, Any],
    agent_name: str | None,
    prompt_text: str | None = None,
    output_value: Any = None,
    actual_usage: Mapping[str, int] | None = None,
) -> None:
    actual = dict(actual_usage or {})
    has_actual = any(int(actual.get(key) or 0) for key in ("input", "output", "total"))
    if has_actual:
        input_tokens = int(actual.get("input") or 0)
        output_tokens = int(actual.get("output") or 0)
        total_tokens = int(actual.get("total") or input_tokens + output_tokens)
        usage_type = "actual"
    else:
        input_tokens = estimate_tokens_from_text(prompt_text)
        output_tokens = estimate_tokens_from_value(output_value)
        total_tokens = input_tokens + output_tokens
        usage_type = "estimated"

    _merge_token_usage(
        metrics=metrics,
        agent_name=str(agent_name or "unknown_agent"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        usage_type=usage_type,
    )


def record_result_token_estimate(
    metrics: dict[str, Any],
    results: Mapping[str, Any] | None,
    label: str = "workflow_result",
) -> None:
    if not results:
        return
    result_snapshot = {
        key: value
        for key, value in results.items()
        if key not in {"run_metrics"}
    }
    record_agent_token_usage(
        metrics,
        label,
        prompt_text=None,
        output_value=result_snapshot,
    )


def extract_event_token_usage(event: Any) -> dict[str, int]:
    usage = getattr(event, "usage_metadata", None)
    if usage is None and isinstance(event, Mapping):
        usage = event.get("usage_metadata")
    return extract_usage_metadata_counts(usage)


def extract_usage_metadata_counts(usage_metadata: Any) -> dict[str, int]:
    if usage_metadata is None:
        return {}
    input_tokens = _read_count(
        usage_metadata,
        (
            "input_tokens",
            "input_token_count",
            "inputTokenCount",
            "prompt_tokens",
            "prompt_token_count",
            "promptTokenCount",
        ),
    )
    output_tokens = _read_count(
        usage_metadata,
        (
            "output_tokens",
            "output_token_count",
            "outputTokenCount",
            "completion_tokens",
            "candidates_token_count",
            "candidatesTokenCount",
        ),
    )
    total_tokens = _read_count(
        usage_metadata,
        (
            "total_tokens",
            "total_token_count",
            "totalTokenCount",
        ),
    )
    counts = {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
    }
    return {key: value for key, value in counts.items() if value is not None}


def merge_usage_counts(
    current: dict[str, int],
    additional: Mapping[str, int] | None,
) -> dict[str, int]:
    for key in ("input", "output", "total"):
        value = int((additional or {}).get(key) or 0)
        if value:
            current[key] = int(current.get(key) or 0) + value
    return current


def sync_audit_metrics(
    metrics: dict[str, Any],
    editor_logs: list[dict[str, Any]] | None,
    audit_warnings: list[dict[str, Any]] | None = None,
) -> None:
    logs = editor_logs or []
    metrics["audits"] = {
        "attempt_count": len(logs),
        "approved_count": sum(1 for log in logs if log.get("approved") is True),
        "rejected_count": sum(1 for log in logs if log.get("approved") is False),
    }
    metrics["warning_count"] = len(audit_warnings or [])


def finalize_run_metrics(
    metrics: dict[str, Any],
    final_status: str,
    step_statuses: Mapping[str, str] | None = None,
    editor_logs: list[dict[str, Any]] | None = None,
    audit_warnings: list[dict[str, Any]] | None = None,
    end_timestamp: float | int | None = None,
) -> dict[str, Any]:
    ended_at = float(end_timestamp or current_timestamp())
    started_at = metrics.get("run_start_timestamp")
    metrics["run_end_timestamp"] = ended_at
    metrics["run_end_time"] = iso_timestamp(ended_at)
    if started_at is not None:
        runtime = max(0.0, ended_at - float(started_at))
        metrics["total_runtime_seconds"] = round(runtime, 3)
        metrics["total_runtime_display"] = format_duration(runtime)
    metrics["final_status"] = final_status
    record_step_statuses(metrics, step_statuses)
    sync_audit_metrics(metrics, editor_logs, audit_warnings)
    _refresh_token_usage(metrics)
    return metrics


def build_metrics_summary(metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    data = metrics or {}
    token_usage = data.get("token_usage") or {}
    return {
        "total_runtime": data.get("total_runtime_display") or "not available",
        "final_status": data.get("final_status") or "unknown",
        "model_name": data.get("model_name") or "",
        "agent_calls": (data.get("agent_calls") or {}).get("total", 0),
        "audit_attempts": (data.get("audits") or {}).get("attempt_count", 0),
        "warning_count": data.get("warning_count", 0),
        "token_usage_type": token_usage.get("usage_type", "not_available"),
        "total_tokens": token_usage.get("total_tokens"),
    }


def _merge_token_usage(
    metrics: dict[str, Any],
    agent_name: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    usage_type: str,
) -> None:
    token_usage = metrics.setdefault("token_usage", {})
    token_usage.setdefault("by_agent", {})
    agent_usage = token_usage["by_agent"].setdefault(
        agent_name,
        {
            "usage_type": usage_type,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    )
    agent_usage["input_tokens"] += input_tokens
    agent_usage["output_tokens"] += output_tokens
    agent_usage["total_tokens"] += total_tokens
    if agent_usage.get("usage_type") != usage_type:
        agent_usage["usage_type"] = "estimated"

    token_usage["actual_usage_seen"] = bool(token_usage.get("actual_usage_seen")) or (
        usage_type == "actual"
    )
    token_usage["estimated_usage_seen"] = bool(
        token_usage.get("estimated_usage_seen")
    ) or (usage_type == "estimated")
    _refresh_token_usage(metrics)


def _refresh_token_usage(metrics: dict[str, Any]) -> None:
    token_usage = metrics.setdefault("token_usage", {})
    by_agent = token_usage.setdefault("by_agent", {})
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in by_agent.values())
    output_tokens = sum(
        int(item.get("output_tokens") or 0) for item in by_agent.values()
    )
    total_tokens = sum(int(item.get("total_tokens") or 0) for item in by_agent.values())

    if total_tokens:
        token_usage["input_tokens"] = input_tokens
        token_usage["output_tokens"] = output_tokens
        token_usage["total_tokens"] = total_tokens
        token_usage["usage_type"] = (
            "actual"
            if token_usage.get("actual_usage_seen")
            and not token_usage.get("estimated_usage_seen")
            else "estimated"
        )
    else:
        token_usage["input_tokens"] = None
        token_usage["output_tokens"] = None
        token_usage["total_tokens"] = None
        token_usage["usage_type"] = "not_available"

    token_usage["model_name"] = metrics.get("model_name", "")
    metrics["cost_estimate"] = estimate_cost(
        model_name=metrics.get("model_name"),
        input_tokens=token_usage.get("input_tokens"),
        output_tokens=token_usage.get("output_tokens"),
        usage_type=token_usage.get("usage_type", "not_available"),
    )


def _read_count(source: Any, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = None
        if isinstance(source, Mapping):
            value = source.get(key)
        else:
            value = getattr(source, key, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
