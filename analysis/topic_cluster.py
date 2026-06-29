from __future__ import annotations

import pandas as pd

from analysis.keyword_miner import extract_terms_from_frame
from analysis.rule_loader import load_topic_rules


def match_topic_by_rules(text: str, rules: dict[str, list[str]]) -> str:
    for topic, keywords in rules.items():
        if any(keyword and keyword in text for keyword in keywords):
            return topic
    return ""


def assign_rule_topics(
    df: pd.DataFrame,
    topn_terms: int = 30,
    topic_rules: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["topic_cluster_id"] = pd.Series(dtype=str)
        out["topic_name"] = pd.Series(dtype=str)
        out["topic_source"] = pd.Series(dtype=str)
        return out

    rules = topic_rules if topic_rules is not None else load_topic_rules()
    terms = [row["term"] for row in extract_terms_from_frame(out, topn_terms)]
    topic_names = []
    topic_ids = []
    topic_sources = []
    for _, row in out.iterrows():
        text = f"{row.get('title', '')} {row.get('cover_ocr_text', '')} {row.get('image_summary', '')}"
        matched = match_topic_by_rules(text, rules)
        source = "taxonomy_rule" if matched else "title_term"
        if not matched:
            matched = next((term for term in terms if term and term in text), "其他")
            if matched == "其他":
                source = "fallback"
        topic_names.append(matched)
        topic_ids.append(f"{source}_{matched}")
        topic_sources.append(source)
    out["topic_cluster_id"] = topic_ids
    out["topic_name"] = topic_names
    out["topic_source"] = topic_sources
    return out


def add_semantic_dedupe_placeholders(df: pd.DataFrame, threshold: float = 0.88) -> pd.DataFrame:
    out = df.copy()
    out["semantic_duplicate_group_id"] = ""
    out["semantic_similarity_threshold"] = threshold
    return out


def semantic_dedupe_placeholder(df: pd.DataFrame, threshold: float = 0.88) -> pd.DataFrame:
    return add_semantic_dedupe_placeholders(df, threshold)
