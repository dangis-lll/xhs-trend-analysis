from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import sys
from pathlib import Path

import pandas as pd

from pipeline.clean_artifacts import resolve_clean_path
from storage.paths import normalize_date, processed_dir


def date_range(end_date: str, days: int) -> list[str]:
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    return [(end - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(days - 1, -1, -1)]


def read_clean_snapshot(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_excel(path)
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    return None


def merge_history_clean(domain_id: str, date_str: str, days: int = 30) -> tuple[pd.DataFrame, Path]:
    frames = []
    for day in date_range(date_str, days):
        try:
            path = resolve_clean_path(day, domain_id)
        except FileNotFoundError:
            continue
        snapshot = read_clean_snapshot(path)
        if snapshot is not None:
            snapshot = snapshot.copy()
            if "snapshot_date" not in snapshot.columns:
                snapshot["snapshot_date"] = day
            frames.append(snapshot)

    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out_path = processed_dir(domain_id) / "history_clean_notes.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(out_path, index=False, encoding="utf-8-sig")
    return history, out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="合并最近 N 天清洗后的搜索页样本，生成 history_clean_notes.csv。")
    parser.add_argument("--date", default="today", help="结束日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--days", type=int, default=30, help="合并最近多少天，默认 30")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        history, out_path = merge_history_clean(args.domain, date_str, args.days)
    except Exception as exc:
        print(f"历史 clean 合并失败：{exc}", file=sys.stderr)
        return 1
    print(f"已保存领域历史 clean 数据：{out_path}")
    print(f"完成：共合并 {len(history)} 条快照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
