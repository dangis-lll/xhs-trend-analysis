from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from analysis.run_guard import load_run_state, should_skip_run
from pipeline.common import load_domains_config
from storage.paths import normalize_date


DEFAULT_STEPS = [
    "run_daily",
    "clean_notes",
    "apply_manual_corrections",
    "compute_metrics",
    "compute_search_page_signals",
    "evaluate_rules",
    "suggest_rule_candidates",
    "generate_evidence",
    "evaluate_data_quality",
    "merge_history_clean",
    "generate_market_report",
    "update_memory",
    "update_rollups",
    "update_knowledge_base",
]


def parse_time(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def is_due(domain: dict[str, Any], *, now: datetime) -> tuple[bool, str]:
    schedule = domain.get("schedule", {}) or {}
    enabled = bool(schedule.get("schedule_enabled") or domain.get("schedule_enabled"))
    if not enabled:
        return False, "schedule_disabled"
    preferred = str(schedule.get("preferred_time") or domain.get("preferred_time") or "09:00")
    try:
        hour, minute = parse_time(preferred)
    except (ValueError, TypeError):
        return False, "invalid_preferred_time"
    if (now.hour, now.minute) < (hour, minute):
        return False, "before_preferred_time"
    return True, "due"


def build_step_command(step: str, *, domain_id: str, date_value: str, py: str) -> list[str]:
    base = [py, "-m", f"pipeline.{step}", "--domain", domain_id, "--date", date_value]
    if step == "run_daily":
        base.extend(["--scheduled", "--once-per-day"])
    if step == "merge_history_clean":
        base.extend(["--days", "30"])
    return base


def run_domain_pipeline(
    *,
    domain_id: str,
    date_value: str,
    steps: list[str],
    dry_run: bool = False,
) -> int:
    py = sys.executable
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    for step in steps:
        command = build_step_command(step, domain_id=domain_id, date_value=date_value, py=py)
        print(f"[{domain_id}] {step}: {' '.join(command)}")
        if dry_run:
            continue
        completed = subprocess.run(command, env=env, text=True)
        if completed.returncode != 0:
            print(f"[{domain_id}] 步骤失败：{step}，退出码 {completed.returncode}", file=sys.stderr)
            return completed.returncode
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 domains.yaml 中的调度配置运行可选自动 pipeline。")
    parser.add_argument("--date", default="today", help="运行日期，默认 today")
    parser.add_argument("--config", type=Path, default=None, help="domains.yaml 路径")
    parser.add_argument("--domain", default="", help="只检查指定 domain")
    parser.add_argument("--dry-run", action="store_true", help="只输出将要执行的步骤")
    parser.add_argument("--steps", default=",".join(DEFAULT_STEPS), help="逗号分隔的 pipeline 步骤")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_domains_config(args.config)
    date_str = normalize_date(args.date)
    steps = [item.strip() for item in args.steps.split(",") if item.strip()]
    now = datetime.now()
    ran = 0
    for domain in config.get("domains", []):
        domain_id = str(domain.get("id") or "").strip()
        if not domain_id:
            continue
        if args.domain and args.domain != domain_id:
            continue
        due, due_reason = is_due(domain, now=now)
        if not due:
            print(f"[{domain_id}] 跳过：{due_reason}")
            continue
        skip, guard_reason = should_skip_run(load_run_state(domain_id), date_str=date_str, once_per_day=True)
        if skip:
            print(f"[{domain_id}] 跳过：{guard_reason}")
            continue
        code = run_domain_pipeline(domain_id=domain_id, date_value=date_str, steps=steps, dry_run=args.dry_run)
        ran += 1
        if code != 0:
            return code
    print(f"调度检查完成，触发 domain 数：{ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
