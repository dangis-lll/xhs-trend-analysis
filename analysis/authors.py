from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


DEFAULT_OR_AMBIGUOUS_AUTHOR_NAMES = {
    "momo",
    "小红书用户",
    "用户已注销",
    "已注销",
}


def clean_author_text(value: Any) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_author_key(author_id: Any, author_name: Any) -> str:
    clean_id = clean_author_text(author_id)
    if clean_id:
        return f"xhs_user:{clean_id}"
    return ""


def author_display_name(author_name: Any, author_key: str) -> str:
    clean_name = clean_author_text(author_name)
    if clean_name:
        return clean_name
    if author_key.startswith("xhs_user:"):
        return f"未知作者({author_key.removeprefix('xhs_user:')[-6:]})"
    return ""


def build_top_author_records(df: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    if df.empty or "author_id" not in df.columns:
        return []

    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        author_key = build_author_key(row.get("author_id"), row.get("author"))
        if not author_key:
            continue
        name = clean_author_text(row.get("author"))
        rows.append(
            {
                "author_key": author_key,
                "name": author_display_name(name, author_key),
                "author": author_display_name(name, author_key),
                "author_id": clean_author_text(row.get("author_id")),
            }
        )

    counter = Counter(row["author_key"] for row in rows)
    first_seen = {row["author_key"]: row for row in rows}
    records = []
    for author_key, count in counter.most_common(limit):
        item = first_seen[author_key]
        records.append(
            {
                "author_key": author_key,
                "name": item["name"],
                "author": item["author"],
                "author_id": item["author_id"],
                "count": int(count),
                "identity_basis": "author_id",
                "identity_confidence": "high",
                "note": "作者聚合基于 author_id；昵称可能重名，默认昵称如 momo 不单独聚合。",
            }
        )
    return records
