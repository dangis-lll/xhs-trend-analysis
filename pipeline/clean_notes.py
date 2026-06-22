from __future__ import annotations

import argparse
import sys

import pandas as pd

from analysis.dedupe import hard_dedupe
from analysis.image_analyzer import add_image_analysis_placeholders
from analysis.metrics import parse_count
from analysis.topic_cluster import assign_rule_topics, semantic_dedupe_placeholder
from storage.paths import ensure_dirs, normalize_date, processed_dir, raw_dir


def load_raw(date_str: str, project_id: str) -> pd.DataFrame:
    path = raw_dir(date_str, project_id) / "all_raw.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"找不到当天原始合并文件：{path}")
    return pd.read_excel(path)


def clean_dataframe(raw_df: pd.DataFrame, domain_id: str | None = None) -> pd.DataFrame:
    df = raw_df.copy()
    if domain_id and "domain_id" in df.columns:
        df = df[df["domain_id"].fillna("").astype(str) == domain_id].copy()
    if df.empty:
        return df

    df["like_count_num"] = df.get("like_count", pd.Series(dtype=object)).apply(parse_count)
    for col in ["title", "author", "link", "note_id", "keyword", "publish_date", "visible_text"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    df = hard_dedupe(df)
    df["canonical_id"] = df["hard_duplicate_key"]
    df["quality_score"] = 100
    df.loc[df["title"].eq(""), "quality_score"] -= 30
    df.loc[df["link"].eq(""), "quality_score"] -= 30
    df.loc[df["publish_date"].eq(""), "quality_score"] -= 10
    df.loc[df["like_count_num"].isna(), "quality_score"] -= 10
    df = add_image_analysis_placeholders(df)
    df = assign_rule_topics(df)
    df = semantic_dedupe_placeholder(df)
    return df.reset_index(drop=True)


def save_clean(df: pd.DataFrame, date_str: str, domain_id: str) -> tuple[str, str]:
    ensure_dirs(date_str, domain_id)
    xlsx_path = processed_dir(domain_id) / f"{date_str}_clean_notes.xlsx"
    csv_path = processed_dir(domain_id) / f"{date_str}_clean_notes.csv"
    df.to_excel(xlsx_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return str(xlsx_path), str(csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清洗当天原始采集数据，标准化点赞数并做硬降重。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        raw_df = load_raw(date_str, args.domain)
        clean_df = clean_dataframe(raw_df, args.domain)
        xlsx_path, csv_path = save_clean(clean_df, date_str, args.domain)
    except Exception as exc:
        print(f"清洗失败：{exc}", file=sys.stderr)
        return 1
    print(f"已保存清洗 Excel：{xlsx_path}")
    print(f"已保存清洗 CSV：{csv_path}")
    print(f"完成：去重后 {len(clean_df)} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
