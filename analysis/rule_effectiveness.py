from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from analysis.metrics import tokenize_chinese_text


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _value_counts(df: pd.DataFrame, column: str, limit: int = 20) -> list[dict[str, Any]]:
    if column not in df.columns or df.empty:
        return []
    counts = df[column].fillna("").astype(str).replace("", "unknown").value_counts().head(limit)
    return [{"name": str(name), "count": int(count)} for name, count in counts.items()]


def _term_candidates(df: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for title in df.get("title", pd.Series(dtype=str)).fillna("").astype(str):
        counter.update(tokenize_chinese_text(title))
    return [{"term": term, "count": int(count)} for term, count in counter.most_common(limit)]


def evaluate_rule_effectiveness(clean_df: pd.DataFrame, *, date_str: str, domain_id: str) -> dict[str, Any]:
    total = len(clean_df)
    if total == 0:
        return {
            "date": date_str,
            "domain_id": domain_id,
            "note_count": 0,
            "content_pattern": {},
            "topic": {},
            "recommendations": ["no_data"],
        }

    pattern_series = clean_df.get("content_pattern", pd.Series(["其他"] * total)).fillna("").astype(str)
    topic_series = clean_df.get("topic_name", pd.Series(["其他"] * total)).fillna("").astype(str)
    topic_source_series = clean_df.get("topic_source", pd.Series(["unknown"] * total)).fillna("").astype(str)

    pattern_other_mask = pattern_series.eq("") | pattern_series.eq("其他")
    topic_other_mask = topic_series.eq("") | topic_series.eq("其他")
    taxonomy_mask = topic_source_series.eq("taxonomy_rule")
    manual_pattern_mask = clean_df.get("manual_correction_ids", pd.Series([""] * total)).fillna("").astype(str).ne("") & pattern_series.ne("其他")

    recommendations = []
    pattern_other_rate = _rate(int(pattern_other_mask.sum()), total)
    topic_other_rate = _rate(int(topic_other_mask.sum()), total)
    taxonomy_rate = _rate(int(taxonomy_mask.sum()), total)
    if pattern_other_rate > 0.4:
        recommendations.append("content_pattern_rules_need_expansion")
    if topic_other_rate > 0.4:
        recommendations.append("topic_taxonomy_need_expansion")
    if taxonomy_rate < 0.3:
        recommendations.append("topic_taxonomy_low_coverage")

    return {
        "date": date_str,
        "domain_id": domain_id,
        "note_count": int(total),
        "content_pattern": {
            "covered_count": int((~pattern_other_mask).sum()),
            "covered_rate": _rate(int((~pattern_other_mask).sum()), total),
            "other_count": int(pattern_other_mask.sum()),
            "other_rate": pattern_other_rate,
            "manual_override_count": int(manual_pattern_mask.sum()),
            "distribution": _value_counts(clean_df, "content_pattern"),
            "candidate_terms_from_other": _term_candidates(clean_df[pattern_other_mask], 20),
        },
        "topic": {
            "covered_count": int((~topic_other_mask).sum()),
            "covered_rate": _rate(int((~topic_other_mask).sum()), total),
            "other_count": int(topic_other_mask.sum()),
            "other_rate": topic_other_rate,
            "taxonomy_rule_count": int(taxonomy_mask.sum()),
            "taxonomy_rule_rate": taxonomy_rate,
            "source_distribution": _value_counts(clean_df, "topic_source"),
            "distribution": _value_counts(clean_df, "topic_name"),
            "candidate_terms_from_other": _term_candidates(clean_df[topic_other_mask], 20),
        },
        "recommendations": recommendations,
    }
