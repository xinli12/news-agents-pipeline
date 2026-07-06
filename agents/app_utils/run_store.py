"""Local JSON snapshots for refresh-safe Streamlit run display."""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_RUN_LIMIT = 5
DEFAULT_STORE_DIR = ".newslens_runs"
INTERRUPTED_STATUSES = {"running", "paused", "stopping"}
TERMINAL_STATUSES = {"completed", "stopped", "failed"}
SAFE_TOKEN_KEYS = {
    "tokenusage",
    "inputtokens",
    "outputtokens",
    "totaltokens",
    "actualusageseen",
    "estimatedusageseen",
}
SENSITIVE_EXACT_KEYS = {
    "auth",
    "authentication",
    "authheader",
    "env",
    "environ",
    "environment",
    "envvars",
    "environmentvariables",
}
SENSITIVE_KEY_MARKERS = (
    "apikey",
    "secret",
    "password",
    "credential",
    "authorization",
    "bearer",
    "cookie",
    "environment",
    "envvar",
)


def get_run_store_dir() -> Path:
    configured = os.getenv("NEWSLENS_RUN_STORE_DIR")
    return Path(configured or DEFAULT_STORE_DIR)


def save_run_snapshot(shared_state: dict) -> str | None:
    try:
        store_dir = get_run_store_dir()
        store_dir.mkdir(parents=True, exist_ok=True)
        snapshot = build_run_snapshot(shared_state)
        path = store_dir / f"{snapshot['run_id']}.json"
        atomic_write_json(path, snapshot)
        prune_saved_runs(DEFAULT_RUN_LIMIT)
        return str(path)
    except Exception:
        return None


def load_latest_run_snapshot() -> dict | None:
    saved_runs = list_saved_runs(limit=1)
    return saved_runs[0] if saved_runs else None


def list_saved_runs(limit: int = DEFAULT_RUN_LIMIT) -> list[dict]:
    store_dir = get_run_store_dir()
    if not store_dir.exists():
        return []

    snapshots: list[dict[str, Any]] = []
    for path in store_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(snapshot, dict):
            snapshots.append(snapshot)

    snapshots.sort(key=_snapshot_sort_key, reverse=True)
    if limit <= 0:
        return snapshots
    return snapshots[:limit]


def clear_saved_runs() -> None:
    store_dir = get_run_store_dir()
    if not store_dir.exists():
        return
    for pattern in ("*.json", "*.tmp"):
        for path in store_dir.glob(pattern):
            try:
                path.unlink()
            except OSError:
                continue


def restore_snapshot_as_display_state(snapshot: dict) -> dict:
    status = str(snapshot.get("status") or "stopped")
    interrupted = status in INTERRUPTED_STATUSES
    restored_status = "stopped" if interrupted else status
    if restored_status not in TERMINAL_STATUSES:
        restored_status = "stopped"

    step_statuses = dict(snapshot.get("step_statuses") or {})
    if interrupted:
        step_statuses = {
            key: "stopped" if value in {"queued", "running", "paused"} else value
            for key, value in step_statuses.items()
        }

    run_metrics = dict(snapshot.get("run_metrics") or {})
    results = dict(snapshot.get("results") or {})
    if run_metrics and not results.get("run_metrics"):
        results["run_metrics"] = run_metrics

    current_step = snapshot.get("current_step") or ""
    if interrupted:
        current_step = "Restored saved snapshot. Backend execution is not running."

    return {
        "status": restored_status,
        "topic": snapshot.get("topic", ""),
        "current_step": current_step,
        "progress_logs": list(snapshot.get("progress_logs") or []),
        "results": results,
        "control": {"paused": False, "stopped": True},
        "step_statuses": step_statuses,
        "error": snapshot.get("error"),
        "model_name": snapshot.get("model_name", ""),
        "run_metrics": run_metrics,
        "run_id": snapshot.get("run_id"),
        "restored_snapshot": True,
        "snapshot_interrupted": interrupted,
        "snapshot_saved_at": snapshot.get("saved_at"),
    }


def sanitize_for_json(value: Any) -> Any:
    return _sanitize_value(value, seen=set(), depth=0)


def build_run_snapshot(shared_state: dict) -> dict:
    run_id = str(shared_state.get("run_id") or _new_run_id())
    saved_at = _iso_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "saved_at": saved_at,
        "topic": sanitize_for_json(shared_state.get("topic", "")),
        "status": sanitize_for_json(shared_state.get("status", "")),
        "current_step": sanitize_for_json(shared_state.get("current_step", "")),
        "progress_logs": sanitize_for_json(shared_state.get("progress_logs", [])),
        "results": sanitize_for_json(shared_state.get("results", {})),
        "step_statuses": sanitize_for_json(shared_state.get("step_statuses", {})),
        "model_name": sanitize_for_json(shared_state.get("model_name", "")),
        "run_metrics": sanitize_for_json(shared_state.get("run_metrics", {})),
        "control": sanitize_for_json(shared_state.get("control", {})),
        "error": sanitize_for_json(shared_state.get("error")),
    }


def prune_saved_runs(limit: int = DEFAULT_RUN_LIMIT) -> None:
    if limit < 0:
        return
    store_dir = get_run_store_dir()
    if not store_dir.exists():
        return

    records: list[tuple[float, Path]] = []
    for path in store_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        records.append((_snapshot_sort_key(snapshot), path))

    records.sort(key=lambda item: item[0], reverse=True)
    for _sort_key, path in records[limit:]:
        try:
            path.unlink()
        except OSError:
            continue


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _sanitize_value(value: Any, seen: set[int], depth: int) -> Any:
    if depth > 20:
        return str(value)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)

    value_id = id(value)
    if value_id in seen:
        return str(value)

    if isinstance(value, Mapping):
        seen.add(value_id)
        sanitized = {
            str(key): _sanitize_value(item, seen, depth + 1)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
        seen.discard(value_id)
        return sanitized

    if isinstance(value, list | tuple | set):
        seen.add(value_id)
        sanitized_list = [_sanitize_value(item, seen, depth + 1) for item in value]
        seen.discard(value_id)
        return sanitized_list

    return str(value)


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(char for char in key.lower() if char.isalnum())
    if normalized in SAFE_TOKEN_KEYS:
        return False
    if normalized in SENSITIVE_EXACT_KEYS:
        return True
    if "token" in normalized:
        return True
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _snapshot_sort_key(snapshot: Any) -> float:
    if not isinstance(snapshot, Mapping):
        return 0.0
    saved_at = snapshot.get("saved_at")
    if isinstance(saved_at, str):
        try:
            return datetime.fromisoformat(saved_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return 0.0


def _new_run_id() -> str:
    timestamp = datetime.fromtimestamp(time.time(), UTC).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _iso_now() -> str:
    return datetime.fromtimestamp(time.time(), UTC).isoformat()
