from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from analysis.pipeline_status import init_status, load_status, update_step
from pipeline.step_registry import PipelineStep, build_step_command
from storage.atomic_io import atomic_write_json
from storage.paths import processed_dir


LineCallback = Callable[[str], None]
StepCallback = Callable[[str, str, int, int], None]


@dataclass
class PipelineRunner:
    domain_id: str
    date_value: str
    date_str: str
    plan: list[PipelineStep]
    py: str = sys.executable
    env: dict[str, str] = field(default_factory=lambda: os.environ.copy())
    scheduled: bool = False
    dry_run: bool = False
    line_callback: LineCallback | None = None
    step_callback: StepCallback | None = None
    run_id: str = ""

    def __post_init__(self) -> None:
        if not self.run_id:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.run_id = f"run_{self.date_str.replace('-', '')}_{self.domain_id}_{stamp}"
        self.env.setdefault("PYTHONIOENCODING", "utf-8")

    def run(self) -> int:
        init_status(self.domain_id, self.date_str, [step.name for step in self.plan])
        manifest: dict[str, object] = {
            "run_id": self.run_id,
            "domain_id": self.domain_id,
            "date": self.date_str,
            "scheduled": self.scheduled,
            "dry_run": self.dry_run,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": "",
            "steps": [],
        }
        total = len(self.plan)
        for index, step in enumerate(self.plan, start=1):
            command = build_step_command(
                step.name,
                domain_id=self.domain_id,
                date_value=self.date_value,
                py=self.py,
                scheduled=self.scheduled,
            )
            self._line(f"[{self.domain_id}] {step.name}: {' '.join(command)}")
            self._step(step.name, "running", index - 1, total)
            update_step(self.domain_id, self.date_str, step.name, status="running")
            if self.dry_run:
                update_step(self.domain_id, self.date_str, step.name, status="skipped", exit_code=0, error="dry_run")
                self._step(step.name, "skipped", index, total)
                manifest["steps"].append(_manifest_step(step, command, "skipped", 0, "dry_run"))
                continue
            completed = subprocess.run(command, env=self.env, text=True, capture_output=True)
            if completed.stdout:
                self._line(completed.stdout.rstrip())
            if completed.stderr:
                self._line(completed.stderr.rstrip())
            if completed.returncode != 0:
                update_step(
                    self.domain_id,
                    self.date_str,
                    step.name,
                    status="failed",
                    exit_code=completed.returncode,
                    error=completed.stderr.strip(),
                )
                self._step(step.name, "failed", index, total)
                manifest["steps"].append(_manifest_step(step, command, "failed", completed.returncode, completed.stderr.strip()))
                manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
                self._write_manifest(manifest)
                return completed.returncode
            final_status, final_error = self._step_status_after_subprocess(step.name)
            if final_status not in {"skipped", "success"}:
                final_status = "success"
            if final_status == "success":
                update_step(self.domain_id, self.date_str, step.name, status="success", exit_code=0)
                final_error = ""
            self._step(step.name, final_status, index, total)
            manifest["steps"].append(_manifest_step(step, command, final_status, 0, final_error))

        manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_manifest(manifest)
        return 0

    def _write_manifest(self, manifest: dict[str, object]) -> Path:
        path = processed_dir(self.domain_id) / f"{self.date_str}_artifact_manifest.json"
        atomic_write_json(path, manifest)
        return path

    def _line(self, text: str) -> None:
        if self.line_callback:
            self.line_callback(text)
        else:
            print(text)

    def _step(self, step: str, status: str, completed: int, total: int) -> None:
        if self.step_callback:
            self.step_callback(step, status, completed, total)

    def _step_status_after_subprocess(self, step_name: str) -> tuple[str, str]:
        payload = load_status(self.domain_id, self.date_str)
        for item in payload.get("steps", []):
            if item.get("name") == step_name:
                return str(item.get("status") or ""), str(item.get("error") or "")
        return "", ""


def _manifest_step(step: PipelineStep, command: list[str], status: str, exit_code: int, error: str) -> dict[str, object]:
    return {
        "name": step.name,
        "module": step.module,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "error": error,
        "requires": list(step.requires),
        "produces": list(step.produces),
    }
