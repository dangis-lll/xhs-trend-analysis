from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analysis.rule_loader import load_content_pattern_rules, load_entity_rules
from analysis.search_page_signals import add_content_patterns, compute_search_page_signals
from storage.paths import normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算搜索页可见信号，包括 topic 和 content_pattern。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--pattern-rules", default="", help="内容打法规则 YAML 路径，默认 memory_global/pattern_rules/content_patterns.yaml")
    parser.add_argument("--entity-rules", default="", help="实体候选规则 YAML 路径，默认 memory_global/pattern_rules/entity_patterns.yaml")
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
        rules = load_content_pattern_rules(Path(args.pattern_rules)) if args.pattern_rules else load_content_pattern_rules()
        entity_rules = load_entity_rules(Path(args.entity_rules)) if args.entity_rules else load_entity_rules()
        clean_with_patterns = add_content_patterns(clean_df, rules)
        clean_with_patterns.to_excel(processed_dir(args.domain) / f"{date_str}_clean_notes.xlsx", index=False)
        clean_with_patterns.to_csv(processed_dir(args.domain) / f"{date_str}_clean_notes.csv", index=False, encoding="utf-8-sig")

        signals = compute_search_page_signals(
            clean_with_patterns,
            date_str=date_str,
            domain_id=args.domain,
            content_pattern_rules=rules,
            entity_rules=entity_rules,
        )
        out_path = processed_dir(args.domain) / f"{date_str}_search_signals.json"
        out_path.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"搜索页信号计算失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存搜索页信号：{out_path}")
    print(
        "完成：识别 "
        f"{len(signals['content_patterns'])} 类内容打法，"
        f"{len(signals['topics'])} 类主题，"
        f"{len(signals['entity_candidates'])} 个实体候选。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
