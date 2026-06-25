from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.paths import memory_dir


def run_state_path(domain_id: str) -> Path:
    return memory_dir(domain_id) / "run_state.json"


def load_run_state(domain_id: str) -> dict[str, Any]:
    path = run_state_path(domain_id)
    if not path.exists():
        return {"domain_id": domain_id, "runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"domain_id": domain_id, "runs": [], "state_error": "invalid_json"}
    if not isinstance(data, dict):
        return {"domain_id": domain_id, "runs": [], "state_error": "invalid_shape"}
    data.setdefault("domain_id", domain_id)
    data.setdefault("runs", [])
    return data


def save_run_state(domain_id: str, state: dict[str, Any]) -> Path:
    path = run_state_path(domain_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["domain_id"] = domain_id
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def circuit_breaker_active(state: dict[str, Any], *, date_str: str) -> bool:
    until = str(state.get("circuit_breaker_until") or "")
    return bool(until and until >= date_str)


def already_completed_today(state: dict[str, Any], *, date_str: str) -> bool:
    return str(state.get("last_success_date") or "") == date_str


def should_skip_run(
    state: dict[str, Any],
    *,
    date_str: str,
    force: bool = False,
    once_per_day: bool = False,
) -> tuple[bool, str]:
    if force:
        return False, "force"
    if circuit_breaker_active(state, date_str=date_str):
        return True, "circuit_breaker_active"
    if once_per_day and already_completed_today(state, date_str=date_str):
        return True, "already_completed_today"
    return False, "ready"


def record_run_start(domain_id: str, *, date_str: str, run_type: str = "manual") -> dict[str, Any]:
    state = load_run_state(domain_id)
    state["last_started_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_started_date"] = date_str
    state["last_run_type"] = run_type
    save_run_state(domain_id, state)
    return state


def record_run_success(domain_id: str, *, date_str: str, row_count: int = 0, run_type: str = "manual") -> dict[str, Any]:
    state = load_run_state(domain_id)
    record = {
        "date": date_str,
        "run_type": run_type,
        "status": "success",
        "row_count": int(row_count),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["last_success_date"] = date_str
    state["last_status"] = "success"
    state["last_error"] = ""
    state["consecutive_failures"] = 0
    state["circuit_breaker_until"] = ""
    _append_run_record(state, record)
    save_run_state(domain_id, state)
    return state


def record_run_failure(
    domain_id: str,
    *,
    date_str: str,
    error: str,
    run_type: str = "manual",
    failure_threshold: int = 2,
) -> dict[str, Any]:
    state = load_run_state(domain_id)
    failures = int(state.get("consecutive_failures") or 0) + 1
    record = {
        "date": date_str,
        "run_type": run_type,
        "status": "failed",
        "error": str(error)[:500],
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "consecutive_failures": failures,
    }
    state["last_status"] = "failed"
    state["last_error"] = str(error)[:500]
    state["consecutive_failures"] = failures
    if failures >= max(int(failure_threshold), 1):
        state["circuit_breaker_until"] = date_str
        record["circuit_breaker_triggered"] = True
    _append_run_record(state, record)
    save_run_state(domain_id, state)
    return state


def _append_run_record(state: dict[str, Any], record: dict[str, Any], limit: int = 50) -> None:
    runs = state.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    runs.append(record)
    state["runs"] = runs[-limit:]

