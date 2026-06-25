from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from analysis.rule_effectiveness import evaluate_rule_effectiveness
from storage.paths import normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估 topic/content_pattern 规则覆盖率和候选补充词。")
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
        result = evaluate_rule_effectiveness(clean_df, date_str=date_str, domain_id=args.domain)
        out_path = processed_dir(args.domain) / f"{date_str}_rule_effectiveness.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"规则效果评估失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存规则效果评估：{out_path}")
    print(
        "覆盖率："
        f"content_pattern={result.get('content_pattern', {}).get('covered_rate', 0):.2%}，"
        f"topic={result.get('topic', {}).get('covered_rate', 0):.2%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
