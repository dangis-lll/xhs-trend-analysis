from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.paths import processed_dir


@dataclass(frozen=True)
class QualityGate:
    quality_level: str
    report_allowed: bool
    memory_update_allowed: bool
    reasons: tuple[str, ...]
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_level": self.quality_level,
            "report_allowed": self.report_allowed,
            "memory_update_allowed": self.memory_update_allowed,
            "reasons": list(self.reasons),
            "status": self.status,
        }


def load_quality_gate(domain_id: str, date_str: str) -> QualityGate:
    path = processed_dir(domain_id) / f"{date_str}_data_quality.json"
    if not path.exists():
        return QualityGate(
            quality_level="unknown",
            report_allowed=False,
            memory_update_allowed=False,
            reasons=(f"missing_quality_file:{path}",),
            status="missing",
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return QualityGate(
            quality_level="unknown",
            report_allowed=False,
            memory_update_allowed=False,
            reasons=(f"malformed_quality_file:{exc.msg}",),
            status="malformed",
        )

    if not isinstance(payload, dict):
        return QualityGate(
            quality_level="unknown",
            report_allowed=False,
            memory_update_allowed=False,
            reasons=("malformed_quality_payload:not_object",),
            status="malformed",
        )

    level = str(payload.get("quality_level") or "unknown").strip().lower()
    reasons = _quality_reasons(payload)
    report_allowed = bool(payload.get("report_allowed")) and level in {"low", "medium", "high"}
    memory_update_allowed = bool(payload.get("memory_update_allowed")) and level in {"medium", "high"}

    if not report_allowed:
        reasons.append("report_blocked_by_quality_gate")
    if not memory_update_allowed:
        reasons.append("memory_blocked_by_quality_gate")

    return QualityGate(
        quality_level=level,
        report_allowed=report_allowed,
        memory_update_allowed=memory_update_allowed,
        reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
    )


def write_skip_artifact(path: Path, *, domain_id: str, date_str: str, step: str, gate: QualityGate) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date_str,
        "domain_id": domain_id,
        "step": step,
        "status": "skipped",
        "quality_gate": gate.to_dict(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _quality_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("blockers", "warnings", "disabled_conclusions"):
        values = payload.get(key, [])
        if isinstance(values, list):
            reasons.extend(str(item) for item in values if str(item).strip())
    return reasons
