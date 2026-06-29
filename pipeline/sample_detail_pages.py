from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analysis.detail_sampling import (
    build_manual_detail_template,
    load_manual_detail_supplements,
    merge_manual_detail_supplements,
    select_detail_sample_targets,
)
from pipeline.clean_artifacts import resolve_clean_path
from storage.paths import details_dir, ensure_dirs, normalize_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成少量详情页抽样目标；默认不实际进入详情页。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--enable", action="store_true", help="启用详情页抽样目标生成")
    parser.add_argument("--limit", type=int, default=5, help="抽样目标上限")
    parser.add_argument("--manual-supplements", default="", help="人工详情补录 JSON/JSONL 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        ensure_dirs(date_str, args.domain)
        detail_dir = details_dir(date_str, args.domain)
        status_path = detail_dir / "detail_sampling_status.json"
        if not args.enable:
            status = {
                "date": date_str,
                "domain_id": args.domain,
                "enabled": False,
                "status": "skipped",
                "reason": "detail_sampling_disabled",
                "core_pipeline_blocking": False,
            }
            status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"详情页抽样未启用，已记录状态：{status_path}")
            return 0

        clean_path = resolve_clean_path(date_str, args.domain)
        clean_df = pd.read_excel(clean_path)
        targets = select_detail_sample_targets(clean_df, limit=args.limit)
        supplements = load_manual_detail_supplements(Path(args.manual_supplements)) if args.manual_supplements else []
        merged = merge_manual_detail_supplements(targets, supplements)

        targets_path = detail_dir / "detail_sample_targets.json"
        template_path = detail_dir / "manual_detail_template.json"
        merged_path = detail_dir / "detail_supplements_merged.json"
        targets_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
        template_path.write_text(json.dumps(build_manual_detail_template(targets), ensure_ascii=False, indent=2), encoding="utf-8")
        merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(merged).to_csv(detail_dir / "detail_supplements_merged.csv", index=False, encoding="utf-8-sig")

        status = {
            "date": date_str,
            "domain_id": args.domain,
            "enabled": True,
            "status": "target_list_ready",
            "target_count": len(targets),
            "manual_supplement_count": len(supplements),
            "network_collection": False,
            "core_pipeline_blocking": False,
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"详情页抽样失败：{exc}", file=sys.stderr)
        return 1
    print(f"已生成详情页抽样目标：{targets_path}")
    print(f"已生成人工详情补录模板：{template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
