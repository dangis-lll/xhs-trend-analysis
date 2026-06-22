from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd


def normalize_title(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", "", text).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def normalize_link(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text.split("?")[0].rstrip("/")


def build_hard_duplicate_key(row: pd.Series | dict[str, Any]) -> str:
    get = row.get
    note_id = str(get("note_id", "") or "").strip()
    if note_id:
        return f"note:{note_id}"

    link = normalize_link(get("link", ""))
    if link:
        return f"link:{link}"

    author = str(get("author", "") or "").strip()
    title = normalize_title(get("title", ""))
    if author or title:
        return f"author_title:{author}:{title}"

    fallback = str(get("visible_text", "") or "")[:120]
    digest = hashlib.sha1(fallback.encode("utf-8", errors="ignore")).hexdigest()
    return f"text:{digest}"


def hard_dedupe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    out["hard_duplicate_key"] = out.apply(build_hard_duplicate_key, axis=1)
    if "like_count_num" not in out.columns:
        out["like_count_num"] = pd.NA
    out["_like_sort"] = pd.to_numeric(out["like_count_num"], errors="coerce").fillna(-1)
    out["_rank_sort"] = pd.to_numeric(out.get("rank", 999999), errors="coerce").fillna(999999)
    out = out.sort_values(
        by=["hard_duplicate_key", "_like_sort", "_rank_sort"],
        ascending=[True, False, True],
    )
    out["duplicate_group_id"] = out.groupby("hard_duplicate_key", sort=False).ngroup() + 1
    deduped = out.drop_duplicates(subset=["hard_duplicate_key"], keep="first").copy()
    deduped = deduped.drop(columns=["_like_sort", "_rank_sort"], errors="ignore")
    return deduped.reset_index(drop=True)
