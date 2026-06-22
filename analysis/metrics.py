from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import pandas as pd


STOPWORDS = {
    "一个",
    "这个",
    "真的",
    "可以",
    "不是",
    "没有",
    "什么",
    "怎么",
    "小红书",
    "nan",
    "none",
    "分享",
    "推荐",
    "攻略",
    "笔记",
}


def parse_count(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(万|w|W|千|k|K)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or ""
    if unit in {"万", "w", "W"}:
        number *= 10_000
    elif unit in {"千", "k", "K"}:
        number *= 1_000
    return int(number)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def tokenize_chinese_text(text: str, min_len: int = 2) -> list[str]:
    text = normalize_text(text)
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text)
    clean_tokens = []
    for token in tokens:
        if len(token) < min_len or token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        if re.fullmatch(r"\d+[年月日]?", token):
            continue
        if re.fullmatch(r"\d+(?:赞|点赞|收藏|评论)", token):
            continue
        clean_tokens.append(token)
    return clean_tokens


def top_title_terms(df: pd.DataFrame, topn: int = 30) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for title in df.get("title", pd.Series(dtype=str)).fillna(""):
        counter.update(tokenize_chinese_text(str(title)))
    return [{"term": term, "count": count} for term, count in counter.most_common(topn)]


def recent_publish_mask(df: pd.DataFrame, date_str: str, days: int = 7) -> pd.Series:
    if "publish_date" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    end = datetime.strptime(date_str, "%Y-%m-%d").date()
    start = end - timedelta(days=days - 1)
    dates = pd.to_datetime(df["publish_date"], errors="coerce").dt.date
    return dates.apply(lambda value: bool(value and start <= value <= end))


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def compute_basic_metrics(
    raw_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    *,
    date_str: str,
    high_like_threshold: int,
    recent_publish_days: int,
) -> dict[str, Any]:
    raw_count = len(raw_df)
    clean_count = len(clean_df)
    like_series = pd.to_numeric(clean_df.get("like_count_num", pd.Series(dtype=float)), errors="coerce")
    valid_likes = like_series.dropna()
    recent_mask = recent_publish_mask(clean_df, date_str, recent_publish_days)
    publish_present = clean_df.get("publish_date", pd.Series(dtype=str)).fillna("").astype(str).ne("")
    high_like_mask = like_series.fillna(0) >= high_like_threshold

    return {
        "date": date_str,
        "raw_count": int(raw_count),
        "clean_count": int(clean_count),
        "duplicate_count": int(max(raw_count - clean_count, 0)),
        "dedupe_rate": safe_ratio(max(raw_count - clean_count, 0), raw_count),
        "publish_date_present_count": int(publish_present.sum()),
        "publish_date_present_rate": safe_ratio(int(publish_present.sum()), clean_count),
        "recent_publish_days": recent_publish_days,
        "recent_publish_count": int(recent_mask.sum()),
        "recent_publish_ratio": safe_ratio(int(recent_mask.sum()), clean_count),
        "avg_likes": round(float(valid_likes.mean()), 2) if not valid_likes.empty else 0,
        "median_likes": round(float(valid_likes.median()), 2) if not valid_likes.empty else 0,
        "p90_likes": round(float(valid_likes.quantile(0.9)), 2) if not valid_likes.empty else 0,
        "high_like_threshold": high_like_threshold,
        "high_like_count": int(high_like_mask.sum()),
        "high_like_rate": safe_ratio(int(high_like_mask.sum()), clean_count),
    }


def top_records(df: pd.DataFrame, by: str, topn: int = 10) -> list[dict[str, Any]]:
    if by not in df.columns or df.empty:
        return []
    cols = [
        col
        for col in ["title", "author", "keyword", "publish_date", "like_count_num", "link", "note_id"]
        if col in df.columns
    ]
    ranked = df.sort_values(by=by, ascending=False, na_position="last").head(topn)
    return ranked[cols].fillna("").to_dict(orient="records")


def compute_topic_daily_metrics(
    df: pd.DataFrame,
    *,
    date_str: str,
    domain_id: str,
    high_like_threshold: int,
    recent_publish_days: int,
    topn: int = 20,
) -> pd.DataFrame:
    columns = [
        "date",
        "domain_id",
        "topic_cluster_id",
        "topic_name",
        "note_count",
        "new_note_count",
        "total_likes",
        "avg_likes",
        "median_likes",
        "p90_likes",
        "high_like_count",
        "high_like_rate",
        "recent_publish_ratio",
        "topic_score",
        "growth_rate_3d",
        "representative_titles",
        "representative_note_ids",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    work = df.copy()
    if "topic_name" not in work.columns:
        work["topic_name"] = "其他"
    if "topic_cluster_id" not in work.columns:
        work["topic_cluster_id"] = "rule_其他"
    work["like_count_num"] = pd.to_numeric(work.get("like_count_num", 0), errors="coerce").fillna(0)
    recent_mask = recent_publish_mask(work, date_str, recent_publish_days)
    work["_recent_publish"] = recent_mask
    work["_high_like"] = work["like_count_num"] >= high_like_threshold

    rows = []
    for (cluster_id, topic_name), group in work.groupby(["topic_cluster_id", "topic_name"], dropna=False):
        likes = group["like_count_num"].dropna()
        representative = group.sort_values("like_count_num", ascending=False).head(3)
        note_count = len(group)
        high_like_count = int(group["_high_like"].sum())
        recent_ratio = safe_ratio(int(group["_recent_publish"].sum()), note_count)
        p90 = round(float(likes.quantile(0.9)), 2) if not likes.empty else 0
        topic_score = round(note_count * 1.0 + high_like_count * 3.0 + p90 / 1000.0 + recent_ratio * 2.0, 4)
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "topic_cluster_id": str(cluster_id or ""),
                "topic_name": str(topic_name or "其他"),
                "note_count": int(note_count),
                "new_note_count": int(group["_recent_publish"].sum()),
                "total_likes": int(likes.sum()) if not likes.empty else 0,
                "avg_likes": round(float(likes.mean()), 2) if not likes.empty else 0,
                "median_likes": round(float(likes.median()), 2) if not likes.empty else 0,
                "p90_likes": p90,
                "high_like_count": high_like_count,
                "high_like_rate": safe_ratio(high_like_count, note_count),
                "recent_publish_ratio": recent_ratio,
                "topic_score": topic_score,
                "growth_rate_3d": "",
                "representative_titles": " | ".join(representative.get("title", pd.Series(dtype=str)).fillna("").astype(str)),
                "representative_note_ids": " | ".join(representative.get("note_id", pd.Series(dtype=str)).fillna("").astype(str)),
            }
        )

    return pd.DataFrame(rows, columns=columns).sort_values(
        ["topic_score", "note_count"], ascending=[False, False]
    ).head(topn)
