from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from analysis.rollup import (
    build_rollup,
    filter_summaries,
    month_key,
    monthly_date_range,
    render_rollup_summary,
    week_key,
    weekly_date_range,
)
from storage.paths import ensure_dirs, memory_daily_dir, memory_rollups_dir, normalize_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 daily summary 更新周/月 rollup。")
    parser.add_argument("--date", default="today", help="结束日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--period", choices=["week", "month", "both"], default="both", help="更新周期")
    parser.add_argument("--min-week-days", type=int, default=3, help="周 rollup 最少有效天数，默认 3")
    parser.add_argument("--min-month-days", type=int, default=15, help="月 rollup 最少有效天数，默认 15")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_daily_summaries(domain_id: str) -> list[dict[str, Any]]:
    daily_dir = memory_daily_dir(domain_id)
    if not daily_dir.exists():
        return []
    summaries = []
    for path in sorted(daily_dir.glob("*_summary.json")):
        try:
            summaries.append(load_json(path))
        except json.JSONDecodeError:
            continue
    return summaries


def write_rollup(rollup: dict[str, Any], domain_id: str) -> tuple[Path, Path]:
    out_dir = memory_rollups_dir(domain_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{rollup['period_type']}_{rollup['period_key']}"
    metrics_path = out_dir / f"{base}_metrics.json"
    summary_path = out_dir / f"{base}_summary.md"
    metrics_path.write_text(json.dumps(rollup, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(render_rollup_summary(rollup), encoding="utf-8")
    return metrics_path, summary_path


def build_and_write_period(
    *,
    summaries: list[dict[str, Any]],
    domain_id: str,
    date_str: str,
    period_type: str,
    min_days: int,
) -> tuple[Path, Path] | str:
    if period_type == "weekly":
        start_date, end_date = weekly_date_range(date_str)
        period_key = week_key(date_str)
    elif period_type == "monthly":
        start_date, end_date = monthly_date_range(date_str)
        period_key = month_key(date_str)
    else:
        raise ValueError(f"未知 period_type: {period_type}")

    period_summaries = filter_summaries(summaries, start_date=start_date, end_date=end_date)
    if len(period_summaries) < min_days:
        return f"{period_type} rollup 跳过：有效天数 {len(period_summaries)}，低于阈值 {min_days}。"
    rollup = build_rollup(
        period_summaries,
        domain_id=domain_id,
        period_type=period_type,
        period_key=period_key,
        start_date=start_date,
        end_date=end_date,
    )
    return write_rollup(rollup, domain_id)


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        ensure_dirs(date_str, args.domain)
        summaries = load_daily_summaries(args.domain)
        periods = ["weekly", "monthly"] if args.period == "both" else [f"{args.period}ly"]
        written = []
        for period in periods:
            min_days = args.min_week_days if period == "weekly" else args.min_month_days
            result = build_and_write_period(
                summaries=summaries,
                domain_id=args.domain,
                date_str=date_str,
                period_type=period,
                min_days=min_days,
            )
            if result:
                if isinstance(result, str):
                    print(result)
                else:
                    written.append(result)
    except Exception as exc:
        print(f"rollup 更新失败：{exc}", file=sys.stderr)
        return 1

    if not written:
        print("没有可用于 rollup 的 daily summary。")
    for metrics_path, summary_path in written:
        print(f"已保存 rollup metrics：{metrics_path}")
        print(f"已保存 rollup summary：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
