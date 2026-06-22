from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import sys

import pandas as pd

from storage.paths import normalize_date, processed_dir


def date_range(end_date: str, days: int) -> list[str]:
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    return [(end - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(days - 1, -1, -1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="合并最近 N 天清洗后的数据，保留每日快照。")
    parser.add_argument("--date", default="today", help="结束日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--days", type=int, default=30, help="合并最近多少天，默认 30")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    frames = []
    try:
        for day in date_range(date_str, args.days):
            path = processed_dir(args.domain) / f"{day}_clean_notes.xlsx"
            if path.exists():
                frames.append(pd.read_excel(path))
        history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        out_domain = processed_dir(args.domain) / "history_clean_notes.csv"
        history.to_csv(out_domain, index=False, encoding="utf-8-sig")
    except Exception as exc:
        print(f"历史合并失败：{exc}", file=sys.stderr)
        return 1
    print(f"已保存领域历史数据：{out_domain}")
    print(f"完成：共合并 {len(history)} 条快照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
