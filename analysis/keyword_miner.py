from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from analysis.metrics import tokenize_chinese_text


def extract_terms_from_frame(df: pd.DataFrame, topn: int = 50) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for _, row in df.iterrows():
        text = " ".join(
            str(row.get(col, "") or "")
            for col in ["title", "cover_ocr_text", "image_summary"]
        )
        counter.update(tokenize_chinese_text(text))
    return [{"term": term, "count": count} for term, count in counter.most_common(topn)]


def compute_three_day_trends(history_df: pd.DataFrame, end_date: str, topn: int = 30) -> list[dict[str, Any]]:
    if history_df.empty or "crawl_date" not in history_df.columns:
        return []

    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    current_start = end - timedelta(days=2)
    prev_start = end - timedelta(days=5)
    dates = pd.to_datetime(history_df["crawl_date"], errors="coerce").dt.date
    current = history_df[(dates >= current_start) & (dates <= end)]
    previous = history_df[(dates >= prev_start) & (dates < current_start)]

    current_terms = Counter()
    previous_terms = Counter()
    for df, counter in [(current, current_terms), (previous, previous_terms)]:
        for _, row in df.iterrows():
            text = f"{row.get('title', '')} {row.get('cover_ocr_text', '')} {row.get('image_summary', '')}"
            counter.update(set(tokenize_chinese_text(str(text))))

    rows: list[dict[str, Any]] = []
    for term, count in current_terms.items():
        prev = previous_terms.get(term, 0)
        growth = round((count - prev) / prev, 4) if prev else None
        examples = current[
            current.apply(
                lambda row: term
                in f"{row.get('title', '')} {row.get('cover_ocr_text', '')} {row.get('image_summary', '')}",
                axis=1,
            )
        ].head(3)
        rows.append(
            {
                "term": term,
                "current_3d_count": int(count),
                "previous_3d_count": int(prev),
                "growth_rate": growth,
                "representative_titles": " | ".join(examples.get("title", pd.Series(dtype=str)).fillna("").astype(str)),
            }
        )

    rows.sort(key=lambda item: (item["growth_rate"] is None, item["growth_rate"] or 999, item["current_3d_count"]), reverse=True)
    return rows[:topn]


def suggest_keywords(existing_keywords: list[str], term_rows: list[dict[str, Any]], topn: int = 20) -> pd.DataFrame:
    existing = set(existing_keywords)
    rows = []
    for row in term_rows:
        term = str(row.get("term", "")).strip()
        if not term or term in existing:
            continue
        rows.append(
            {
                "keyword": term,
                "dimension": "data_mined_term",
                "reason": f"标题和可见文本中出现 {row.get('count', row.get('current_3d_count', 0))} 次",
                "priority": "medium",
                "source": "rule_keyword_miner",
                "first_seen_date": datetime.now().strftime("%Y-%m-%d"),
            }
        )
    return pd.DataFrame(rows[:topn])
