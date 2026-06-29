from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.data_contracts import normalize_observation


EVIDENCE_SOURCE = "search"


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def build_note_global_id(row: dict[str, Any] | pd.Series) -> str:
    data = row.to_dict() if isinstance(row, pd.Series) else row
    note_id = normalize_value(data.get("note_id"))
    if note_id:
        return f"ng_note_{stable_hash(note_id)}"

    link = normalize_value(data.get("link"))
    if link:
        return f"ng_link_{stable_hash(link)}"

    title = normalize_value(data.get("title"))
    author = normalize_value(data.get("author") or data.get("author_id"))
    return f"ng_title_author_{stable_hash(title + '|' + author)}"


def build_evidence_id(*, date_str: str, domain_id: str, source: str, note_global_id: str) -> str:
    seed = f"{date_str}|{domain_id}|{source}|{note_global_id}"
    return f"ev_{date_str.replace('-', '')}_{domain_id}_{source}_{stable_hash(seed, 10)}"


def _record_from_row(row: pd.Series, *, date_str: str, domain_id: str) -> dict[str, Any]:
    note_global_id = normalize_value(row.get("note_global_id")) or build_note_global_id(row)
    evidence_id = build_evidence_id(
        date_str=date_str,
        domain_id=domain_id,
        source=EVIDENCE_SOURCE,
        note_global_id=note_global_id,
    )
    keywords = sorted(
        {
            item.strip()
            for item in normalize_value(row.get("keyword")).split("|")
            if item.strip()
        }
    )
    return {
        "evidence_id": evidence_id,
        "note_global_id": note_global_id,
        "date": date_str,
        "domain_id": domain_id,
        "source": EVIDENCE_SOURCE,
        "keywords": keywords,
        "title": normalize_value(row.get("title")),
        "author": normalize_value(row.get("author")),
        "author_id": normalize_value(row.get("author_id")),
        "link": normalize_value(row.get("link")),
        "note_id": normalize_value(row.get("note_id")),
        "publish_date": normalize_value(row.get("publish_date")),
        "topic_name": normalize_value(row.get("topic_name")),
        "topic_cluster_id": normalize_value(row.get("topic_cluster_id")),
        "like_count_num": _int_or_none(row.get("like_count_num")),
        "collect_count_num": _int_or_none(row.get("collect_count_num")),
        "comment_count_num": _int_or_none(row.get("comment_count_num")),
        "share_count_num": _int_or_none(row.get("share_count_num")),
        "is_video": _bool_value(row.get("is_video")),
        "quality_score": _int_or_none(row.get("quality_score")),
    }


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    text = normalize_value(value).lower()
    return text in {"1", "true", "yes", "y", "是", "视频"}


def generate_evidence_map_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": record.get("evidence_id", ""),
            "note_global_id": record.get("note_global_id", ""),
            "date": record.get("date", ""),
            "domain_id": record.get("domain_id", ""),
            "source": record.get("source", ""),
            "topic_name": record.get("topic_name", ""),
            "title": record.get("title", ""),
            "note_id": record.get("note_id", ""),
            "link": record.get("link", ""),
        }
        for record in records
    ]


def add_note_global_ids(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["note_global_id"] = [build_note_global_id(row) for _, row in out.iterrows()]
    return out


def generate_evidence_records(df: pd.DataFrame, *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    if df.empty:
        return []
    work = add_note_global_ids(df)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in work.iterrows():
        note_global_id = normalize_value(row.get("note_global_id"))
        if note_global_id in seen:
            continue
        seen.add(note_global_id)
        records.append(_record_from_row(row, date_str=date_str, domain_id=domain_id))
    return records


def generate_evidence_records_from_observations(
    observations: list[dict[str, Any]],
    *,
    date_str: str,
    domain_id: str,
    clean_df: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    annotations = _annotations_by_note_global_id(clean_df)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        observation = normalize_observation(observation)
        if normalize_value(observation.get("domain_id")) and normalize_value(observation.get("domain_id")) != domain_id:
            continue
        note_global_id = normalize_value(observation.get("note_global_id")) or build_note_global_id(observation)
        grouped.setdefault(note_global_id, []).append(observation)

    records: list[dict[str, Any]] = []
    for note_global_id in sorted(grouped):
        items = grouped[note_global_id]
        first = items[0]
        annotation = annotations.get(note_global_id, {})
        ranks = [
            {
                "keyword": normalize_value(item.get("keyword")),
                "rank": _int_or_none(item.get("rank")),
                "observation_id": normalize_value(item.get("observation_id")),
            }
            for item in items
            if normalize_value(item.get("keyword"))
        ]
        valid_ranks = [item["rank"] for item in ranks if item["rank"] is not None]
        evidence_id = build_evidence_id(
            date_str=date_str,
            domain_id=domain_id,
            source=EVIDENCE_SOURCE,
            note_global_id=note_global_id,
        )
        records.append(
            {
                "evidence_id": evidence_id,
                "note_global_id": note_global_id,
                "date": date_str,
                "domain_id": domain_id,
                "source": EVIDENCE_SOURCE,
                "keywords": sorted({item["keyword"] for item in ranks if item["keyword"]}),
                "best_rank": min(valid_ranks) if valid_ranks else None,
                "all_ranks": ranks,
                "source_observation_ids": [
                    normalize_value(item.get("observation_id")) for item in items if normalize_value(item.get("observation_id"))
                ],
                "title": normalize_value(first.get("title")),
                "author": normalize_value(first.get("author")),
                "author_id": normalize_value(first.get("author_id")),
                "link": normalize_value(first.get("link")),
                "note_id": normalize_value(first.get("note_id")),
                "publish_date": normalize_value(first.get("publish_date")),
                "topic_name": normalize_value(annotation.get("topic_name")) or normalize_value(first.get("topic_name")),
                "topic_cluster_id": normalize_value(annotation.get("topic_cluster_id"))
                or normalize_value(first.get("topic_cluster_id")),
                "like_count_num": _max_int(items, "like_count", "like_count_num"),
                "collect_count_num": _max_int(items, "collect_count", "collect_count_num"),
                "comment_count_num": _max_int(items, "comment_count", "comment_count_num"),
                "share_count_num": _max_int(items, "share_count", "share_count_num"),
                "metrics_snapshot": {
                    "observation_count": len(items),
                    "best_rank": min(valid_ranks) if valid_ranks else None,
                    "like_count_num": _max_int(items, "like_count", "like_count_num"),
                    "collect_count_num": _max_int(items, "collect_count", "collect_count_num"),
                    "comment_count_num": _max_int(items, "comment_count", "comment_count_num"),
                },
                "content_patterns": _content_patterns_from_annotation(annotation),
                "primary_content_pattern": normalize_value(annotation.get("primary_content_pattern"))
                or normalize_value(annotation.get("content_pattern")),
                "quality_flags": [],
            }
        )
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def upsert_jsonl_by_key(path: Path, records: list[dict[str, Any]], *, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_key: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_key = normalize_value(record.get(key))
            if record_key:
                by_key[record_key] = record
    for record in records:
        record_key = normalize_value(record.get(key))
        if record_key:
            by_key[record_key] = record
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record_key in sorted(by_key):
            handle.write(json.dumps(by_key[record_key], ensure_ascii=False, sort_keys=True) + "\n")


def update_note_index(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["note_global_id", "first_seen_date", "last_seen_date", "title", "author", "note_id", "link"]
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)
    by_id = {str(row["note_global_id"]): row.to_dict() for _, row in existing.iterrows() if row.get("note_global_id")}

    for record in records:
        note_global_id = record["note_global_id"]
        current = by_id.get(note_global_id, {})
        first_seen = normalize_value(current.get("first_seen_date")) or record["date"]
        last_seen = max(normalize_value(current.get("last_seen_date")) or record["date"], record["date"])
        by_id[note_global_id] = {
            "note_global_id": note_global_id,
            "first_seen_date": first_seen,
            "last_seen_date": last_seen,
            "title": normalize_value(current.get("title")) or record["title"],
            "author": normalize_value(current.get("author")) or record["author"],
            "note_id": normalize_value(current.get("note_id")) or record["note_id"],
            "link": normalize_value(current.get("link")) or record["link"],
        }

    pd.DataFrame(by_id.values(), columns=columns).sort_values("last_seen_date").to_csv(
        path, index=False, encoding="utf-8-sig"
    )


def _max_int(items: list[dict[str, Any]], *keys: str) -> int | None:
    values = []
    for item in items:
        for key in keys:
            value = _int_or_none(item.get(key))
            if value is not None:
                values.append(value)
                break
    return max(values) if values else None


def _annotations_by_note_global_id(clean_df: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if clean_df is None or clean_df.empty:
        return {}
    work = add_note_global_ids(clean_df)
    annotations: dict[str, dict[str, Any]] = {}
    for _, row in work.iterrows():
        note_global_id = normalize_value(row.get("note_global_id"))
        if not note_global_id or note_global_id in annotations:
            continue
        annotations[note_global_id] = row.to_dict()
    return annotations


def _content_patterns_from_annotation(annotation: dict[str, Any]) -> list[str]:
    raw = annotation.get("content_patterns")
    if isinstance(raw, list):
        return [normalize_value(item) for item in raw if normalize_value(item)]
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                return [normalize_value(item) for item in parsed if normalize_value(item)]
        except json.JSONDecodeError:
            pass
    values = [
        normalize_value(annotation.get("primary_content_pattern")),
        normalize_value(annotation.get("content_pattern")),
    ]
    return list(dict.fromkeys(value for value in values if value))
