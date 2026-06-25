from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from analysis.authors import build_top_author_records
from analysis.entity_miner import mine_demand_signals, mine_entity_candidates
from analysis.metrics import numeric_series, safe_ratio, tokenize_chinese_text
from analysis.rule_loader import load_content_pattern_rules, load_entity_rules


CONTENT_PATTERN_RULES = load_content_pattern_rules()


def detect_content_pattern(title: str, rules: dict[str, list[str]] | None = None) -> str:
    clean = str(title or "")
    active_rules = rules or CONTENT_PATTERN_RULES
    for pattern, keywords in active_rules.items():
        if any(keyword in clean for keyword in keywords):
            return pattern
    return "其他"


def add_content_patterns(df: pd.DataFrame, rules: dict[str, list[str]] | None = None) -> pd.DataFrame:
    out = df.copy()
    active_rules = rules or CONTENT_PATTERN_RULES
    detected = (
        out.get("title", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .apply(lambda title: detect_content_pattern(title, active_rules))
    )
    if "content_pattern" in out.columns:
        existing = out["content_pattern"].fillna("").astype(str).str.strip()
        out["content_pattern"] = existing.where(existing.ne(""), detected)
    else:
        out["content_pattern"] = detected
    return out


def _top_counter(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [{"name": name, "count": int(count)} for name, count in counter.most_common(limit) if name]


def signal_score(*, note_share: float, avg_likes: float, note_count: int) -> float:
    count_score = min(note_count / 10, 1.0) * 0.35
    share_score = min(note_share / 0.35, 1.0) * 0.35
    like_score = min(avg_likes / 1000, 1.0) * 0.30
    return round(count_score + share_score + like_score, 4)


def signal_strength(score: float) -> str:
    if score >= 0.7:
        return "strong"
    if score >= 0.4:
        return "medium"
    if score > 0:
        return "weak"
    return "none"


def signal_confidence(*, note_count: int, note_share: float) -> str:
    if note_count >= 10 and note_share >= 0.25:
        return "high"
    if note_count >= 3 and note_share >= 0.1:
        return "medium"
    return "low"


def compute_search_page_signals(
    clean_df: pd.DataFrame,
    *,
    date_str: str,
    domain_id: str,
    content_pattern_rules: dict[str, list[str]] | None = None,
    entity_rules: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    active_rules = content_pattern_rules or CONTENT_PATTERN_RULES
    active_entity_rules = entity_rules or load_entity_rules()
    work = add_content_patterns(clean_df, active_rules)
    note_count = len(work)
    like_series = numeric_series(work, "like_count_num").fillna(0)
    collect_series = numeric_series(work, "collect_count_num").fillna(0)
    comment_series = numeric_series(work, "comment_count_num").fillna(0)

    pattern_rows = []
    if note_count:
        for pattern, group in work.groupby("content_pattern", dropna=False):
            group_likes = numeric_series(group, "like_count_num").fillna(0)
            note_share = safe_ratio(len(group), note_count)
            avg_likes = round(float(group_likes.mean()), 2) if len(group_likes) else 0
            score = signal_score(note_share=note_share, avg_likes=avg_likes, note_count=len(group))
            pattern_rows.append(
                {
                    "content_pattern": str(pattern or "其他"),
                    "note_count": int(len(group)),
                    "note_share": note_share,
                    "avg_likes": avg_likes,
                    "signal_score": score,
                    "signal_strength": signal_strength(score),
                    "confidence": signal_confidence(note_count=len(group), note_share=note_share),
                    "top_titles": group.sort_values("like_count_num", ascending=False, na_position="last")
                    .get("title", pd.Series(dtype=str))
                    .fillna("")
                    .astype(str)
                    .head(3)
                    .tolist(),
                }
            )
    pattern_rows.sort(key=lambda row: (row["note_count"], row["avg_likes"]), reverse=True)

    topic_rows = []
    if note_count and "topic_name" in work.columns:
        for topic, group in work.groupby("topic_name", dropna=False):
            topic_likes = numeric_series(group, "like_count_num").fillna(0)
            note_share = safe_ratio(len(group), note_count)
            avg_likes = round(float(topic_likes.mean()), 2) if len(topic_likes) else 0
            score = signal_score(note_share=note_share, avg_likes=avg_likes, note_count=len(group))
            topic_rows.append(
                {
                    "topic": str(topic or "其他"),
                    "note_count": int(len(group)),
                    "note_share": note_share,
                    "avg_likes": avg_likes,
                    "signal_score": score,
                    "signal_strength": signal_strength(score),
                    "confidence": signal_confidence(note_count=len(group), note_share=note_share),
                    "top_titles": group.sort_values("like_count_num", ascending=False, na_position="last")
                    .get("title", pd.Series(dtype=str))
                    .fillna("")
                    .astype(str)
                    .head(3)
                    .tolist(),
                }
            )
    topic_rows.sort(key=lambda row: (row["note_count"], row["avg_likes"]), reverse=True)

    title_counter: Counter[str] = Counter()
    for title in work.get("title", pd.Series(dtype=str)).fillna("").astype(str):
        title_counter.update(tokenize_chinese_text(title))

    keyword_counter = Counter(
        work.get("keyword", pd.Series(dtype=str)).fillna("").astype(str).str.strip().replace("", pd.NA).dropna().tolist()
    )

    return {
        "date": date_str,
        "domain_id": domain_id,
        "sample_scope": "xhs_search_page",
        "rule_meta": {
            "content_pattern_rule_count": len(active_rules),
            "content_pattern_names": list(active_rules.keys()),
            "entity_rule_count": sum(len(items) for items in active_entity_rules.values()),
            "entity_types": list(active_entity_rules.keys()),
        },
        "note_count": int(note_count),
        "content_patterns": pattern_rows[:20],
        "topics": topic_rows[:20],
        "entity_candidates": mine_entity_candidates(work, entity_rules=active_entity_rules),
        "demand_signals": mine_demand_signals(work),
        "top_title_terms": _top_counter(title_counter),
        "top_authors": build_top_author_records(work),
        "top_keywords": _top_counter(keyword_counter),
        "interaction_overview": {
            "total_likes": int(like_series.sum()),
            "total_collects": int(collect_series.sum()),
            "total_comments": int(comment_series.sum()),
            "collect_like_ratio": safe_ratio(int(collect_series.sum()), int(like_series.sum())),
            "comment_like_ratio": safe_ratio(int(comment_series.sum()), int(like_series.sum())),
        },
    }
