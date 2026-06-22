from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from analysis.keyword_miner import extract_terms_from_frame, suggest_keywords
from analysis.metrics import compute_basic_metrics, compute_topic_daily_metrics, top_records, top_title_terms
from pipeline.common import domain_keywords, get_domain, load_analysis_config
from storage.paths import normalize_date, processed_dir, raw_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算当天小红书趋势基础指标。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_clean(date_str: str, domain_id: str) -> pd.DataFrame:
    path = processed_dir(domain_id) / f"{date_str}_clean_notes.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"找不到清洗结果：{path}")
    return pd.read_excel(path)


def load_raw(date_str: str, domain_id: str) -> pd.DataFrame:
    path = raw_dir(date_str, domain_id) / "all_raw.xlsx"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_excel(path)
    if "domain_id" in df.columns:
        df = df[df["domain_id"].fillna("").astype(str) == domain_id].copy()
    return df


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        config = load_analysis_config().get("analysis", {})
        domain = get_domain(args.domain)
        raw_df = load_raw(date_str, args.domain)
        clean_df = load_clean(date_str, args.domain)
        high_like_threshold = int(config.get("high_like_threshold") or 1000)
        recent_publish_days = int(config.get("recent_publish_days") or 7)

        metrics = compute_basic_metrics(
            raw_df,
            clean_df,
            date_str=date_str,
            high_like_threshold=high_like_threshold,
            recent_publish_days=recent_publish_days,
        )
        metrics["domain_id"] = args.domain
        metrics["domain_name"] = domain.get("name", "")
        metrics["top_keywords"] = (
            clean_df.get("keyword", pd.Series(dtype=str)).fillna("").astype(str).value_counts().head(20).to_dict()
        )
        metrics["top_authors"] = (
            clean_df.get("author", pd.Series(dtype=str)).fillna("").astype(str).replace("", pd.NA).dropna().value_counts().head(20).to_dict()
        )
        metrics["top_title_terms"] = top_title_terms(clean_df, 30)
        metrics["mined_terms"] = extract_terms_from_frame(clean_df, 50)
        metrics["top_notes"] = top_records(clean_df, "like_count_num", int(config.get("top_cases") or 10))
        topic_metrics = compute_topic_daily_metrics(
            clean_df,
            date_str=date_str,
            domain_id=args.domain,
            high_like_threshold=high_like_threshold,
            recent_publish_days=recent_publish_days,
            topn=int(config.get("top_topics") or 10),
        )
        metrics["top_topics"] = topic_metrics.head(int(config.get("top_topics") or 10)).fillna("").to_dict(orient="records")

        metrics_path = processed_dir(args.domain) / f"{date_str}_metrics.json"
        top_notes_path = processed_dir(args.domain) / f"{date_str}_top_notes.xlsx"
        candidate_keywords_path = processed_dir(args.domain) / f"{date_str}_candidate_keywords.csv"
        topic_metrics_path = processed_dir(args.domain) / f"{date_str}_topic_daily_metrics.xlsx"
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        top_df = clean_df.sort_values("like_count_num", ascending=False, na_position="last").head(int(config.get("top_cases") or 10))
        top_df.to_excel(top_notes_path, index=False)
        topic_metrics.to_excel(topic_metrics_path, index=False)
        suggest_keywords(domain_keywords(domain), metrics["mined_terms"], 20).to_csv(
            candidate_keywords_path, index=False, encoding="utf-8-sig"
        )
    except Exception as exc:
        print(f"指标计算失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存指标 JSON：{metrics_path}")
    print(f"已保存高赞笔记：{top_notes_path}")
    print(f"已保存主题指标：{topic_metrics_path}")
    print(f"已保存候选关键词：{candidate_keywords_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
