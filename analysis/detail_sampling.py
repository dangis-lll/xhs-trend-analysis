from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def select_detail_sample_targets(clean_df: pd.DataFrame, *, limit: int = 5) -> list[dict[str, Any]]:
    if clean_df.empty or limit <= 0:
        return []
    work = clean_df.copy()
    for column in ["like_count_num", "rank"]:
        if column not in work.columns:
            work[column] = 0
    work["like_count_num"] = pd.to_numeric(work["like_count_num"], errors="coerce").fillna(0)
    work["rank"] = pd.to_numeric(work["rank"], errors="coerce").fillna(999999)
    work = work.sort_values(["like_count_num", "rank"], ascending=[False, True])

    targets = []
    seen: set[str] = set()
    for _, row in work.iterrows():
        note_id = _text(row.get("note_id"))
        link = _text(row.get("link"))
        key = note_id or link or _text(row.get("title"))
        if not key or key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "note_id": note_id,
                "link": link,
                "title": _text(row.get("title")),
                "author": _text(row.get("author")),
                "keyword": _text(row.get("keyword")),
                "topic_name": _text(row.get("topic_name")),
                "content_pattern": _text(row.get("content_pattern")),
                "like_count_num": int(float(row.get("like_count_num") or 0)),
                "rank": int(float(row.get("rank") or 0)),
                "status": "target_only",
                "detail_source": "not_collected",
            }
        )
        if len(targets) >= limit:
            break
    return targets


def build_manual_detail_template(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "note_id": target.get("note_id", ""),
            "link": target.get("link", ""),
            "title": target.get("title", ""),
            "manual_detail_summary": "",
            "manual_comment_summary": "",
            "manual_tags": [],
            "source": "manual",
        }
        for target in targets
    ]


def load_manual_detail_supplements(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        records = []
        for line in text.splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def merge_manual_detail_supplements(
    targets: list[dict[str, Any]],
    supplements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in supplements:
        key = _supplement_key(item)
        if key:
            index[key] = item

    merged = []
    for target in targets:
        supplement = index.get(_supplement_key(target), {})
        row = dict(target)
        if supplement:
            row.update(
                {
                    "manual_detail_summary": _text(supplement.get("manual_detail_summary")),
                    "manual_comment_summary": _text(supplement.get("manual_comment_summary")),
                    "manual_tags": supplement.get("manual_tags", []),
                    "detail_source": _text(supplement.get("source") or "manual"),
                    "status": "manual_supplemented",
                }
            )
        merged.append(row)
    return merged


def _supplement_key(item: dict[str, Any]) -> str:
    return _text(item.get("note_id")) or _text(item.get("link")) or _text(item.get("title"))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

