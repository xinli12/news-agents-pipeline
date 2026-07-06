import json
from pathlib import Path

from agents.app_utils.run_store import (
    build_run_snapshot,
    clear_saved_runs,
    get_run_store_dir,
    list_saved_runs,
    load_latest_run_snapshot,
    restore_snapshot_as_display_state,
    sanitize_for_json,
    save_run_snapshot,
)


def _state(run_id: str, status: str = "completed") -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "topic": f"Topic {run_id}",
        "current_step": "Done",
        "progress_logs": [{"step": "search", "message": "Search complete"}],
        "results": {
            "public_report": {"lead_paragraph": "Summary"},
            "api_key": "must-not-save",
        },
        "step_statuses": {"search": "completed", "public_report": "completed"},
        "model_name": "test-model",
        "run_metrics": {
            "token_usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            }
        },
        "control": {"paused": False, "stopped": False},
        "GEMINI_API_KEY": "must-not-save",
    }


def test_save_and_load_latest_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLENS_RUN_STORE_DIR", str(tmp_path))

    first_path = save_run_snapshot(_state("run-a"))
    second_path = save_run_snapshot(_state("run-b"))

    latest = load_latest_run_snapshot()
    assert first_path
    assert second_path
    assert latest is not None
    assert latest["run_id"] == "run-b"
    assert latest["topic"] == "Topic run-b"
    assert Path(second_path).exists()


def test_list_saved_runs_and_prune_to_latest_five(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLENS_RUN_STORE_DIR", str(tmp_path))

    for idx in range(7):
        assert save_run_snapshot(_state(f"run-{idx}"))

    saved = list_saved_runs(limit=10)
    assert len(saved) == 5
    assert [item["run_id"] for item in saved] == [
        "run-6",
        "run-5",
        "run-4",
        "run-3",
        "run-2",
    ]
    assert len(list(tmp_path.glob("*.json"))) == 5


def test_clear_saved_runs_removes_snapshot_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLENS_RUN_STORE_DIR", str(tmp_path))
    assert save_run_snapshot(_state("run-a"))
    (tmp_path / "leftover.tmp").write_text("temp", encoding="utf-8")

    clear_saved_runs()

    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_corrupted_json_is_ignored_safely(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLENS_RUN_STORE_DIR", str(tmp_path))
    assert save_run_snapshot(_state("good"))
    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")

    saved = list_saved_runs(limit=10)

    assert len(saved) == 1
    assert saved[0]["run_id"] == "good"


def test_sanitization_removes_forbidden_keys_and_keeps_safe_token_counts() -> None:
    sanitized = sanitize_for_json(
        {
            "api_key": "secret",
            "auth": "secret",
            "access_token": "secret",
            "env": {"GEMINI_API_KEY": "secret"},
            "nested": {"password": "secret", "value": "safe"},
            "token_usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            },
        }
    )

    assert "api_key" not in sanitized
    assert "auth" not in sanitized
    assert "access_token" not in sanitized
    assert "env" not in sanitized
    assert "password" not in sanitized["nested"]
    assert sanitized["nested"]["value"] == "safe"
    assert sanitized["token_usage"]["input_tokens"] == 1
    assert sanitized["token_usage"]["output_tokens"] == 2
    assert sanitized["token_usage"]["total_tokens"] == 3


def test_non_json_values_are_converted_safely() -> None:
    sanitized = sanitize_for_json({"items": {3, 1}, "path": Path("demo")})
    json.dumps(sanitized)

    assert sorted(sanitized["items"]) == [1, 3]
    assert sanitized["path"] == "demo"


def test_running_paused_and_stopping_snapshots_restore_as_interrupted() -> None:
    for status in ("running", "paused", "stopping"):
        snapshot = build_run_snapshot(
            {
                **_state(f"run-{status}", status=status),
                "step_statuses": {"search": "running", "expert": "queued"},
            }
        )

        restored = restore_snapshot_as_display_state(snapshot)

        assert restored["status"] == "stopped"
        assert restored["control"] == {"paused": False, "stopped": True}
        assert restored["restored_snapshot"] is True
        assert restored["snapshot_interrupted"] is True
        assert restored["step_statuses"]["search"] == "stopped"
        assert restored["step_statuses"]["expert"] == "stopped"


def test_terminal_snapshots_restore_display_only_without_interruption() -> None:
    for status in ("completed", "stopped", "failed"):
        snapshot = build_run_snapshot(_state(f"run-{status}", status=status))

        restored = restore_snapshot_as_display_state(snapshot)

        assert restored["status"] == status
        assert restored["control"] == {"paused": False, "stopped": True}
        assert restored["restored_snapshot"] is True
        assert restored["snapshot_interrupted"] is False
        assert restored["results"]["public_report"]["lead_paragraph"] == "Summary"


def test_get_run_store_dir_uses_environment_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLENS_RUN_STORE_DIR", str(tmp_path))

    assert get_run_store_dir() == tmp_path
