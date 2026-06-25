from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _top_titles(item: dict[str, Any]) -> str:
    titles = item.get("top_titles", [])
    if not isinstance(titles, list):
        return ""
    return " | ".join(_clean_text(title) for title in titles[:3] if _clean_text(title))


def build_topic_daily_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    date_str = _clean_text(daily_summary.get("date"))
    domain_id = _clean_text(daily_summary.get("domain_id"))
    quality = daily_summary.get("data_quality", {}) or {}
    rows = []
    for item in daily_summary.get("top_topics", []) or []:
        topic = _clean_text(item.get("topic") or item.get("name"))
        if not topic:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "topic": topic,
                "note_count": _int(item.get("note_count")),
                "note_share": _float(item.get("note_share")),
                "avg_likes": _float(item.get("avg_likes")),
                "signal_score": _float(item.get("signal_score")),
                "signal_strength": _clean_text(item.get("signal_strength")),
                "confidence": _clean_text(item.get("confidence")),
                "data_quality": _clean_text(quality.get("quality_level", "unknown")),
                "top_titles": _top_titles(item),
            }
        )
    return rows


def build_pattern_daily_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    date_str = _clean_text(daily_summary.get("date"))
    domain_id = _clean_text(daily_summary.get("domain_id"))
    quality = daily_summary.get("data_quality", {}) or {}
    rows = []
    for item in daily_summary.get("top_content_patterns", []) or []:
        pattern = _clean_text(item.get("content_pattern") or item.get("pattern"))
        if not pattern:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "content_pattern": pattern,
                "note_count": _int(item.get("note_count")),
                "note_share": _float(item.get("note_share")),
                "avg_likes": _float(item.get("avg_likes")),
                "signal_score": _float(item.get("signal_score")),
                "signal_strength": _clean_text(item.get("signal_strength")),
                "confidence": _clean_text(item.get("confidence")),
                "data_quality": _clean_text(quality.get("quality_level", "unknown")),
                "top_titles": _top_titles(item),
            }
        )
    return rows


def build_author_daily_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    date_str = _clean_text(daily_summary.get("date"))
    domain_id = _clean_text(daily_summary.get("domain_id"))
    quality = daily_summary.get("data_quality", {}) or {}
    rows = []
    for item in daily_summary.get("top_authors", []) or []:
        author = _clean_text(item.get("name") or item.get("author"))
        author_key = _clean_text(item.get("author_key"))
        if not author_key:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "author_key": author_key,
                "author": author,
                "author_id": _clean_text(item.get("author_id")),
                "sample_count": _int(item.get("count") or item.get("sample_count")),
                "identity_basis": _clean_text(item.get("identity_basis")),
                "identity_confidence": _clean_text(item.get("identity_confidence")),
                "data_quality": _clean_text(quality.get("quality_level", "unknown")),
            }
        )
    return rows


def build_keyword_daily_rows(signals: dict[str, Any], *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in signals.get("top_keywords", []) or []:
        keyword = _clean_text(item.get("name") or item.get("keyword"))
        if not keyword:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "keyword": keyword,
                "sample_count": _int(item.get("count")),
            }
        )
    return rows


def build_entity_rows(signals: dict[str, Any], *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in signals.get("entity_candidates", []) or []:
        entity = _clean_text(item.get("entity"))
        entity_type = _clean_text(item.get("entity_type"))
        if not entity:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "entity": entity,
                "entity_type": entity_type,
                "sample_count": _int(item.get("sample_count")),
                "note_share": _float(item.get("note_share")),
                "avg_likes": _float(item.get("avg_likes")),
                "signal_score": _float(item.get("signal_score")),
                "signal_strength": _clean_text(item.get("signal_strength")),
                "confidence": _clean_text(item.get("confidence")),
                "source": _clean_text(item.get("source")),
                "top_titles": _top_titles(item),
            }
        )
    return rows


def build_demand_rows(signals: dict[str, Any], *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in signals.get("demand_signals", []) or []:
        demand_type = _clean_text(item.get("demand_type"))
        if not demand_type:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "demand_type": demand_type,
                "sample_count": _int(item.get("sample_count")),
                "note_share": _float(item.get("note_share")),
                "avg_likes": _float(item.get("avg_likes")),
                "signal_score": _float(item.get("signal_score")),
                "signal_strength": _clean_text(item.get("signal_strength")),
                "confidence": _clean_text(item.get("confidence")),
                "top_titles": _top_titles(item),
            }
        )
    return rows


def build_topic_index_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _index_row(
            date_str=_clean_text(daily_summary.get("date")),
            domain_id=_clean_text(daily_summary.get("domain_id")),
            name=_clean_text(item.get("topic") or item.get("name")),
            name_field="topic",
            item=item,
        )
        for item in daily_summary.get("top_topics", []) or []
        if _clean_text(item.get("topic") or item.get("name"))
    ]


def build_content_pattern_index_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _index_row(
            date_str=_clean_text(daily_summary.get("date")),
            domain_id=_clean_text(daily_summary.get("domain_id")),
            name=_clean_text(item.get("content_pattern") or item.get("pattern")),
            name_field="content_pattern",
            item=item,
        )
        for item in daily_summary.get("top_content_patterns", []) or []
        if _clean_text(item.get("content_pattern") or item.get("pattern"))
    ]


def build_author_index_rows(daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    date_str = _clean_text(daily_summary.get("date"))
    domain_id = _clean_text(daily_summary.get("domain_id"))
    rows = []
    for item in daily_summary.get("top_authors", []) or []:
        author = _clean_text(item.get("name") or item.get("author"))
        author_key = _clean_text(item.get("author_key"))
        if not author_key:
            continue
        rows.append(
            {
                "domain_id": domain_id,
                "author_key": author_key,
                "author": author,
                "author_id": _clean_text(item.get("author_id")),
                "first_seen": date_str,
                "last_seen": date_str,
                "latest_sample_count": _int(item.get("count") or item.get("sample_count")),
                "identity_basis": _clean_text(item.get("identity_basis")),
                "identity_confidence": _clean_text(item.get("identity_confidence")),
            }
        )
    return rows


def build_keyword_index_rows(signals: dict[str, Any], *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in signals.get("top_keywords", []) or []:
        keyword = _clean_text(item.get("name") or item.get("keyword"))
        if not keyword:
            continue
        rows.append(
            {
                "domain_id": domain_id,
                "keyword": keyword,
                "first_seen": date_str,
                "last_seen": date_str,
                "latest_count": _int(item.get("count")),
            }
        )
    return rows


def build_brand_or_ip_rows(entity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in entity_rows:
        entity_type = _clean_text(row.get("entity_type"))
        if entity_type not in {"brand", "ip"}:
            continue
        rows.append(
            {
                "domain_id": _clean_text(row.get("domain_id")),
                "entity": _clean_text(row.get("entity")),
                "entity_type": entity_type,
                "first_seen": _clean_text(row.get("date")),
                "last_seen": _clean_text(row.get("date")),
                "latest_sample_count": _int(row.get("sample_count")),
                "latest_signal_score": _float(row.get("signal_score")),
                "confidence": _clean_text(row.get("confidence")),
                "source": _clean_text(row.get("source")),
            }
        )
    return [row for row in rows if row["entity"]]


def build_title_template_rows(signals: dict[str, Any], *, date_str: str, domain_id: str) -> list[dict[str, Any]]:
    rows = []
    for item in signals.get("top_title_terms", []) or []:
        term = _clean_text(item.get("name"))
        if not term:
            continue
        rows.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "template_candidate": term,
                "sample_count": _int(item.get("count")),
                "source": "top_title_terms",
                "status": "needs_review",
            }
        )
    return rows


def build_entity_comparison_rows(entity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in entity_rows:
        by_type.setdefault(_clean_text(row.get("entity_type")), []).append(row)
    for entity_type, items in by_type.items():
        ranked = sorted(items, key=lambda item: (_int(item.get("sample_count")), _float(item.get("avg_likes"))), reverse=True)
        for index, row in enumerate(ranked[:10], start=1):
            rows.append(
                {
                    "date": _clean_text(row.get("date")),
                    "domain_id": _clean_text(row.get("domain_id")),
                    "entity_type": entity_type,
                    "entity": _clean_text(row.get("entity")),
                    "rank_in_type": index,
                    "sample_count": _int(row.get("sample_count")),
                    "avg_likes": _float(row.get("avg_likes")),
                    "signal_score": _float(row.get("signal_score")),
                    "confidence": _clean_text(row.get("confidence")),
                }
            )
    return [row for row in rows if row["entity"]]


def upsert_index_csv(path: Path, rows: list[dict[str, Any]], *, key_fields: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows)
    if not path.exists():
        new_df.to_csv(path, index=False, encoding="utf-8-sig")
        return

    old_df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in new_df.columns:
        if column not in old_df.columns:
            old_df[column] = ""
    for column in old_df.columns:
        if column not in new_df.columns:
            new_df[column] = ""
    old_df = old_df[new_df.columns.tolist()]

    old_by_key = {_row_key(row, key_fields): dict(row) for row in old_df.to_dict(orient="records")}
    for row in new_df.to_dict(orient="records"):
        key = _row_key(row, key_fields)
        old = old_by_key.get(key, {})
        if old:
            row["first_seen"] = min(_clean_text(old.get("first_seen")), _clean_text(row.get("first_seen"))) or _clean_text(
                old.get("first_seen") or row.get("first_seen")
            )
        old_by_key[key] = row
    out = pd.DataFrame(old_by_key.values())
    sort_fields = [field for field in [*key_fields, "last_seen"] if field in out.columns]
    if sort_fields:
        out = out.sort_values(sort_fields).reset_index(drop=True)
    out.to_csv(path, index=False, encoding="utf-8-sig")


def _index_row(
    *,
    date_str: str,
    domain_id: str,
    name: str,
    name_field: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "domain_id": domain_id,
        name_field: name,
        "first_seen": date_str,
        "last_seen": date_str,
        "latest_note_count": _int(item.get("note_count")),
        "latest_note_share": _float(item.get("note_share")),
        "latest_avg_likes": _float(item.get("avg_likes")),
        "latest_signal_score": _float(item.get("signal_score")),
        "signal_strength": _clean_text(item.get("signal_strength")),
        "confidence": _clean_text(item.get("confidence")),
    }


def _row_key(row: dict[str, Any], key_fields: list[str]) -> str:
    return "\u0001".join(_clean_text(row.get(field)) for field in key_fields)


def build_trend_events(
    daily_summary: dict[str, Any],
    *,
    update_decision: dict[str, Any] | None = None,
    max_per_type: int = 5,
) -> list[dict[str, Any]]:
    date_str = _clean_text(daily_summary.get("date"))
    domain_id = _clean_text(daily_summary.get("domain_id"))
    decision = update_decision or {}
    verification_status = _clean_text(daily_summary.get("verification_status") or decision.get("verification_status"))
    events: list[dict[str, Any]] = []

    for item in (daily_summary.get("top_topics", []) or [])[:max_per_type]:
        topic = _clean_text(item.get("topic") or item.get("name"))
        if topic:
            events.append(_event(date_str, domain_id, "topic_observed", topic, "topic", item, verification_status))

    for item in (daily_summary.get("top_content_patterns", []) or [])[:max_per_type]:
        pattern = _clean_text(item.get("content_pattern") or item.get("pattern"))
        if pattern:
            events.append(_event(date_str, domain_id, "pattern_observed", pattern, "content_pattern", item, verification_status))

    for item in (daily_summary.get("top_authors", []) or [])[:max_per_type]:
        author = _clean_text(item.get("name") or item.get("author"))
        author_key = _clean_text(item.get("author_key"))
        if author_key:
            events.append(
                {
                    "event_id": _event_id(date_str, domain_id, "author_observed", author_key),
                    "date": date_str,
                    "domain_id": domain_id,
                    "event_type": "author_observed",
                    "subject_type": "author",
                    "subject": author,
                    "subject_key": author_key,
                    "sample_count": _int(item.get("count") or item.get("sample_count")),
                    "verification_status": verification_status,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )

    for topic in decision.get("pending_disappeared_topics", []) or []:
        subject = _clean_text(topic)
        if subject:
            events.append(
                {
                    "event_id": _event_id(date_str, domain_id, "topic_cooling_pending", subject),
                    "date": date_str,
                    "domain_id": domain_id,
                    "event_type": "topic_cooling_pending",
                    "subject_type": "topic",
                    "subject": subject,
                    "verification_status": verification_status,
                    "resolution_status": "pending",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )

    for topic in decision.get("confirmed_disappeared_topics", []) or []:
        subject = _clean_text(topic)
        if subject:
            events.append(
                {
                    "event_id": _event_id(date_str, domain_id, "topic_cooling_confirmed", subject),
                    "date": date_str,
                    "domain_id": domain_id,
                    "event_type": "topic_cooling_confirmed",
                    "subject_type": "topic",
                    "subject": subject,
                    "verification_status": verification_status,
                    "resolution_status": "resolved",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
    return events


def _event(
    date_str: str,
    domain_id: str,
    event_type: str,
    subject: str,
    subject_type: str,
    item: dict[str, Any],
    verification_status: str,
) -> dict[str, Any]:
    return {
        "event_id": _event_id(date_str, domain_id, event_type, subject),
        "date": date_str,
        "domain_id": domain_id,
        "event_type": event_type,
        "subject_type": subject_type,
        "subject": subject,
        "note_count": _int(item.get("note_count")),
        "note_share": _float(item.get("note_share")),
        "avg_likes": _float(item.get("avg_likes")),
        "signal_score": _float(item.get("signal_score")),
        "signal_strength": _clean_text(item.get("signal_strength")),
        "confidence": _clean_text(item.get("confidence")),
        "verification_status": verification_status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def _event_id(date_str: str, domain_id: str, event_type: str, subject: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in subject.lower()).strip("_")[:40] or "item"
    return f"{date_str}_{domain_id}_{event_type}_{normalized}"


def upsert_csv(path: Path, rows: list[dict[str, Any]], *, key_fields: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows)
    if path.exists():
        old_df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for column in new_df.columns:
            if column not in old_df.columns:
                old_df[column] = ""
        for column in old_df.columns:
            if column not in new_df.columns:
                new_df[column] = ""
        old_df = old_df[new_df.columns.tolist()]
        old_keys = old_df[key_fields].astype(str).agg("\u0001".join, axis=1)
        new_keys = set(new_df[key_fields].astype(str).agg("\u0001".join, axis=1).tolist())
        old_df = old_df.loc[~old_keys.isin(new_keys)]
        out = pd.concat([old_df, new_df], ignore_index=True)
    else:
        out = new_df
    sort_fields = [field for field in ["date", *key_fields] if field in out.columns]
    if sort_fields:
        out = out.sort_values(sort_fields).reset_index(drop=True)
    out.to_csv(path, index=False, encoding="utf-8-sig")


def append_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_id = _clean_text(record.get("event_id"))
            if event_id:
                existing_ids.add(event_id)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            if event["event_id"] in existing_ids:
                continue
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            existing_ids.add(event["event_id"])
