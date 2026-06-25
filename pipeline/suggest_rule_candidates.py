from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from analysis.rule_candidates import build_rule_candidates, render_rule_candidates
from storage.paths import normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据规则效果评估生成可审阅的规则候选。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--min-count", type=int, default=2, help="候选词最小出现次数，默认 2")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        source_path = processed_dir(args.domain) / f"{date_str}_rule_effectiveness.json"
        effectiveness = load_json(source_path)
        candidates = build_rule_candidates(effectiveness, min_count=args.min_count)
        json_path = processed_dir(args.domain) / f"{date_str}_rule_candidates.json"
        md_path = processed_dir(args.domain) / f"{date_str}_rule_candidates.md"
        json_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_rule_candidates(candidates), encoding="utf-8")
    except Exception as exc:
        print(f"规则候选生成失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存规则候选 JSON：{json_path}")
    print(f"已保存规则候选摘要：{md_path}")
    print(
        "候选数量："
        f"content_pattern={candidates['summary']['content_pattern_candidate_count']}，"
        f"topic={candidates['summary']['topic_candidate_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
