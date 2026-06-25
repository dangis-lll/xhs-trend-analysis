from __future__ import annotations

from typing import Any

import pandas as pd


def _present_rate(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    present = df[column].fillna("").astype(str).str.strip().ne("")
    return round(float(present.mean()), 4)


def _numeric_present_rate(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    present = pd.to_numeric(df[column], errors="coerce").notna()
    return round(float(present.mean()), 4)


def evaluate_quality(raw_df: pd.DataFrame, clean_df: pd.DataFrame, *, date_str: str, domain_id: str) -> dict[str, Any]:
    raw_count = len(raw_df)
    clean_count = len(clean_df)
    publish_rate = _present_rate(clean_df, "publish_date")
    like_rate = _numeric_present_rate(clean_df, "like_count_num")
    collect_rate = _numeric_present_rate(clean_df, "collect_count_num")
    comment_rate = _numeric_present_rate(clean_df, "comment_count_num")
    link_rate = _present_rate(clean_df, "link")
    title_rate = _present_rate(clean_df, "title")
    duplicate_rate = round(float(max(raw_count - clean_count, 0)) / raw_count, 4) if raw_count else 0.0

    blockers: list[str] = []
    warnings: list[str] = []
    disabled_conclusions: list[str] = []

    if clean_count < 3:
        level = "invalid"
        blockers.append("clean_count_lt_3")
    elif clean_count < 10:
        level = "low"
        warnings.append("clean_count_lt_10")
    else:
        level = "high"

    if publish_rate < 0.5:
        disabled_conclusions.append("strong_rising_or_cooling")
        warnings.append("publish_date_present_rate_low")
        if level == "high":
            level = "medium"

    interaction_rates = [like_rate, collect_rate, comment_rate]
    if sum(rate >= 0.5 for rate in interaction_rates) < 2:
        disabled_conclusions.append("interaction_ranking")
        warnings.append("interaction_fields_missing")
        if level == "high":
            level = "medium"

    if title_rate < 0.8:
        warnings.append("title_present_rate_low")
        if level == "high":
            level = "medium"

    if link_rate < 0.5:
        warnings.append("link_present_rate_low")

    if duplicate_rate > 0.8 and raw_count >= 10:
        warnings.append("duplicate_rate_high")
        if level == "high":
            level = "medium"

    if level == "invalid":
        memory_update_allowed = False
        report_allowed = False
    elif level == "low":
        memory_update_allowed = False
        report_allowed = True
    else:
        memory_update_allowed = True
        report_allowed = True

    return {
        "date": date_str,
        "domain_id": domain_id,
        "quality_level": level,
        "report_allowed": report_allowed,
        "memory_update_allowed": memory_update_allowed,
        "raw_count": int(raw_count),
        "clean_count": int(clean_count),
        "duplicate_rate": duplicate_rate,
        "field_present_rates": {
            "title": title_rate,
            "link": link_rate,
            "publish_date": publish_rate,
            "like_count_num": like_rate,
            "collect_count_num": collect_rate,
            "comment_count_num": comment_rate,
        },
        "disabled_conclusions": sorted(set(disabled_conclusions)),
        "warnings": sorted(set(warnings)),
        "blockers": blockers,
    }
