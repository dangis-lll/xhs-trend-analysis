from __future__ import annotations

import pandas as pd

from analysis.keyword_miner import extract_terms_from_frame


def assign_rule_topics(df: pd.DataFrame, topn_terms: int = 30) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["topic_cluster_id"] = pd.Series(dtype=str)
        out["topic_name"] = pd.Series(dtype=str)
        return out

    terms = [row["term"] for row in extract_terms_from_frame(out, topn_terms)]
    topic_names = []
    topic_ids = []
    for _, row in out.iterrows():
        text = f"{row.get('title', '')} {row.get('cover_ocr_text', '')} {row.get('image_summary', '')}"
        matched = next((term for term in terms if term and term in text), "其他")
        topic_names.append(matched)
        topic_ids.append(f"rule_{matched}")
    out["topic_cluster_id"] = topic_ids
    out["topic_name"] = topic_names
    return out


def semantic_dedupe_placeholder(df: pd.DataFrame, threshold: float = 0.88) -> pd.DataFrame:
    out = df.copy()
    out["semantic_duplicate_group_id"] = ""
    out["semantic_similarity_threshold"] = threshold
    return out
