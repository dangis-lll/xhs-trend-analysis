from __future__ import annotations

import argparse
import sys

import pandas as pd

from analysis.dedupe import hard_dedupe
from analysis.image_analyzer import add_image_analysis_placeholders
from analysis.metrics import parse_count
from analysis.rule_loader import load_topic_rules
from analysis.topic_cluster import assign_rule_topics, semantic_dedupe_placeholder
from storage.paths import ensure_dirs, memory_dir, normalize_date, processed_dir, raw_dir


def parse_bool(value) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "是", "视频"}


def load_raw(date_str: str, project_id: str) -> pd.DataFrame:
    path = raw_dir(date_str, project_id) / "all_raw.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"找不到当天原始合并文件：{path}")
    return pd.read_excel(path)


def clean_dataframe(
    raw_df: pd.DataFrame,
    domain_id: str | None = None,
    topic_rules: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    df = raw_df.copy()
    if domain_id and "domain_id" in df.columns:
        df = df[df["domain_id"].fillna("").astype(str) == domain_id].copy()
    if df.empty:
        return df

    for source_col, num_col in [
        ("like_count", "like_count_num"),
        ("collect_count", "collect_count_num"),
        ("comment_count", "comment_count_num"),
        ("share_count", "share_count_num"),
    ]:
        df[num_col] = df.get(source_col, pd.Series(dtype=object)).apply(parse_count)

    for col in [
        "title",
        "author",
        "link",
        "note_id",
        "xsec_token",
        "model_type",
        "note_type",
        "author_id",
        "keyword",
        "publish_date",
        "visible_text",
        "extract_method",
    ]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    if "is_video" not in df.columns:
        df["is_video"] = False
    df["is_video"] = df["is_video"].fillna(False).apply(parse_bool)
    df = hard_dedupe(df)
    df["canonical_id"] = df["hard_duplicate_key"]
    df["quality_score"] = 100
    df.loc[df["title"].eq(""), "quality_score"] -= 30
    df.loc[df["link"].eq(""), "quality_score"] -= 30
    df.loc[df["publish_date"].eq(""), "quality_score"] -= 10
    df.loc[df["like_count_num"].isna(), "quality_score"] -= 10
    df = add_image_analysis_placeholders(df)
    df = assign_rule_topics(df, topic_rules=topic_rules)
    df = semantic_dedupe_placeholder(df)
    if "publish_time" in df.columns:
        df = df.drop(columns=["publish_time"])
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
        domain_taxonomy_path = memory_dir(args.domain) / "taxonomy.yaml"
        clean_df = clean_dataframe(raw_df, args.domain, load_topic_rules(domain_path=domain_taxonomy_path))
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
