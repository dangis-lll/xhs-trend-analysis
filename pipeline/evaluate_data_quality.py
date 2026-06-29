from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from analysis.data_quality import evaluate_quality
from pipeline.clean_artifacts import load_clean_dataframe
from storage.paths import normalize_date, processed_dir, raw_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估当天搜索页样本的数据质量，并输出降级策略。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_raw(date_str: str, domain_id: str) -> pd.DataFrame:
    path = raw_dir(date_str, domain_id) / "all_raw.xlsx"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_excel(path)
    if "domain_id" in df.columns:
        df = df[df["domain_id"].fillna("").astype(str) == domain_id].copy()
    return df


def load_clean(date_str: str, domain_id: str) -> pd.DataFrame:
    return load_clean_dataframe(date_str, domain_id)


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        raw_df = load_raw(date_str, args.domain)
        clean_df = load_clean(date_str, args.domain)
        quality = evaluate_quality(raw_df, clean_df, date_str=date_str, domain_id=args.domain)
        out_path = processed_dir(args.domain) / f"{date_str}_data_quality.json"
        out_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"数据质量评估失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存数据质量报告：{out_path}")
    print(f"质量等级：{quality['quality_level']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
