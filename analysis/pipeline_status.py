from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.paths import processed_dir


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def status_path(domain_id: str, date_str: str) -> Path:
    return processed_dir(domain_id) / f"{date_str}_pipeline_status.json"


def init_status(domain_id: str, date_str: str, steps: list[str]) -> dict[str, Any]:
    payload = {
        "domain_id": domain_id,
        "date": date_str,
        "started_at": now_iso(),
        "finished_at": "",
        "overall_status": "running",
        "steps": [
            {
                "name": step,
                "status": "pending",
                "started_at": "",
                "finished_at": "",
                "exit_code": None,
                "error": "",
            }
            for step in steps
        ],
    }
    write_status(domain_id, date_str, payload)
    return payload


def load_status(domain_id: str, date_str: str) -> dict[str, Any]:
    path = status_path(domain_id, date_str)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(domain_id: str, date_str: str, payload: dict[str, Any]) -> None:
    path = status_path(domain_id, date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_step(
    domain_id: str,
    date_str: str,
    step: str,
    *,
    status: str,
    exit_code: int | None = None,
    error: str = "",
) -> None:
    payload = load_status(domain_id, date_str)
    if not payload:
        payload = init_status(domain_id, date_str, [step])

    found = False
    for item in payload.get("steps", []):
        if item.get("name") != step:
            continue
        found = True
        item["status"] = status
        if status == "running" and not item.get("started_at"):
            item["started_at"] = now_iso()
        if status in {"success", "failed", "skipped"}:
            item["finished_at"] = now_iso()
        item["exit_code"] = exit_code
        item["error"] = error
        break

    if not found:
        payload.setdefault("steps", []).append(
            {
                "name": step,
                "status": status,
                "started_at": now_iso() if status == "running" else "",
                "finished_at": now_iso() if status in {"success", "failed", "skipped"} else "",
                "exit_code": exit_code,
                "error": error,
            }
        )

    if status == "failed":
        payload["overall_status"] = "failed"
        payload["finished_at"] = now_iso()
    elif all(item.get("status") == "success" for item in payload.get("steps", [])):
        payload["overall_status"] = "success"
        payload["finished_at"] = now_iso()

    write_status(domain_id, date_str, payload)
