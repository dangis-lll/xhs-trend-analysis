from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from analysis.manual_corrections import apply_manual_corrections, load_corrections
from storage.paths import memory_dir, normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="应用人工纠错规则，修正 clean_notes 中的结构化字段。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_clean(date_str: str, domain_id: str) -> pd.DataFrame:
    path = processed_dir(domain_id) / f"{date_str}_clean_notes.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"找不到清洗结果：{path}")
    return pd.read_excel(path)


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        clean_df = load_clean(date_str, args.domain)
        corrections_path = memory_dir(args.domain) / "manual_corrections.jsonl"
        corrections = load_corrections(corrections_path)
        corrected_df, applied = apply_manual_corrections(clean_df, corrections)

        xlsx_path = processed_dir(args.domain) / f"{date_str}_clean_notes.xlsx"
        csv_path = processed_dir(args.domain) / f"{date_str}_clean_notes.csv"
        applied_path = processed_dir(args.domain) / f"{date_str}_manual_corrections_applied.json"
        corrected_df.to_excel(xlsx_path, index=False)
        corrected_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        applied_path.write_text(json.dumps(applied, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"人工纠错应用失败：{exc}", file=sys.stderr)
        return 1

    print(f"已读取人工纠错文件：{corrections_path}")
    print(f"已应用纠错记录：{len(applied)} 条")
    print(f"已保存纠错日志：{applied_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
