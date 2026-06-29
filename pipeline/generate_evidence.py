from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from analysis.evidence import (
    add_note_global_ids,
    generate_evidence_map_records,
    generate_evidence_records_from_observations,
    generate_evidence_records,
    update_note_index,
    upsert_jsonl_by_key,
    write_jsonl,
)
from pipeline.clean_artifacts import load_clean_dataframe
from storage.paths import ensure_dirs, evidence_dir, normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从清洗后的搜索页样本生成 evidence_id 证据索引。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_clean(date_str: str, domain_id: str) -> pd.DataFrame:
    return load_clean_dataframe(date_str, domain_id)


def load_observations(date_str: str, domain_id: str) -> list[dict]:
    path = processed_dir(domain_id) / f"{date_str}_clean_observations.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        ensure_dirs(date_str, args.domain)
        observations = load_observations(date_str, args.domain)
        if observations:
            clean_df = load_clean(date_str, args.domain)
            records = generate_evidence_records_from_observations(
                observations,
                date_str=date_str,
                domain_id=args.domain,
                clean_df=clean_df,
            )
        else:
            clean_df = load_clean(date_str, args.domain)
            clean_with_ids = add_note_global_ids(clean_df)
            records = generate_evidence_records(clean_with_ids, date_str=date_str, domain_id=args.domain)
        evidence_path = evidence_dir(args.domain) / f"{date_str}_evidence.jsonl"
        evidence_map_path = evidence_dir(args.domain) / "evidence_map.jsonl"
        note_index_path = evidence_dir(args.domain) / "note_index.csv"
        write_jsonl(evidence_path, records)
        upsert_jsonl_by_key(evidence_map_path, generate_evidence_map_records(records), key="evidence_id")
        update_note_index(note_index_path, records)
    except Exception as exc:
        print(f"证据生成失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存证据索引：{evidence_path}")
    print(f"已保存证据映射：{evidence_map_path}")
    print(f"已更新笔记索引：{note_index_path}")
    print(f"完成：生成 {len(records)} 条 evidence。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
