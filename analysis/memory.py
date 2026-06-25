from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _top(items: Any, limit: int = 8) -> list[dict[str, Any]]:
    return items[:limit] if isinstance(items, list) else []


def _names(items: list[dict[str, Any]], key: str, limit: int = 8) -> list[str]:
    values = []
    for item in items[:limit]:
        value = item.get(key)
        if value:
            values.append(str(value))
    return values


def memory_update_allowed(data_quality: dict[str, Any]) -> bool:
    return bool(data_quality.get("memory_update_allowed")) and data_quality.get("quality_level") in {"high", "medium"}


def summary_is_valid_observation(summary: dict[str, Any]) -> bool:
    quality = summary.get("data_quality", {})
    return bool(quality.get("memory_update_allowed")) and quality.get("quality_level") in {"high", "medium"}


def topic_names_from_summary(summary: dict[str, Any], limit: int = 8) -> list[str]:
    return _names(summary.get("top_topics", []), "topic", limit)


def consecutive_absent_days(
    topic: str,
    *,
    current_summary: dict[str, Any],
    recent_summaries: list[dict[str, Any]],
) -> int:
    streak = 0
    for summary in [current_summary] + list(reversed(recent_summaries)):
        if not summary_is_valid_observation(summary):
            break
        if topic in topic_names_from_summary(summary):
            break
        streak += 1
    return streak


def days_since_last_valid_observation(date_str: str, recent_summaries: list[dict[str, Any]] | None = None) -> int | None:
    current = _parse_date(date_str)
    if current is None:
        return None
    valid_dates = [
        _parse_date(str(summary.get("date", "")))
        for summary in (recent_summaries or [])
        if summary_is_valid_observation(summary)
    ]
    valid_dates = [date for date in valid_dates if date is not None and date < current]
    if not valid_dates:
        return None
    return (current - max(valid_dates)).days


def decide_current_state_update(
    *,
    data_quality: dict[str, Any],
    daily_summary: dict[str, Any],
    previous_text: str,
    recent_summaries: list[dict[str, Any]] | None = None,
    cooling_confirm_days: int = 3,
) -> dict[str, Any]:
    if not memory_update_allowed(data_quality):
        return {
            "allowed": False,
            "reason": "quality_blocked_or_disabled",
            "resolution_status": "ignored_low_quality",
            "disappeared_topics": [],
            "pending_disappeared_topics": [],
            "confirmed_disappeared_topics": [],
            "appeared_topics": [],
            "cooling_absent_streaks": {},
        }

    current_topics = topic_names_from_summary(daily_summary, limit=8)
    previous_topics = _extract_topic_names(previous_text, limit=8)
    valid_observation_days = 1 + sum(1 for summary in (recent_summaries or []) if summary_is_valid_observation(summary))
    inactive_days = days_since_last_valid_observation(
        str(daily_summary.get("date", "")),
        recent_summaries or [],
    )
    verification_status = "needs_verification" if valid_observation_days < 3 else "observed"
    if inactive_days is not None and inactive_days >= 30:
        verification_status = "reactivated"
    appeared = [topic for topic in current_topics if topic not in previous_topics]
    disappeared = [topic for topic in previous_topics if topic not in current_topics]
    if not disappeared:
        return {
            "allowed": True,
            "reason": "quality_allowed_no_unconfirmed_disappearance",
            "resolution_status": "resolved",
            "verification_status": verification_status,
            "valid_observation_days": valid_observation_days,
            "inactive_days": inactive_days,
            "disappeared_topics": [],
            "pending_disappeared_topics": [],
            "confirmed_disappeared_topics": [],
            "appeared_topics": appeared,
            "cooling_absent_streaks": {},
        }

    summaries = recent_summaries or []
    streaks = {
        topic: consecutive_absent_days(topic, current_summary=daily_summary, recent_summaries=summaries)
        for topic in disappeared
    }
    pending = [topic for topic, streak in streaks.items() if streak < cooling_confirm_days]
    confirmed = [topic for topic, streak in streaks.items() if streak >= cooling_confirm_days]
    return {
        "allowed": not pending,
        "reason": "cooling_confirmed" if not pending else "cooling_needs_more_observation",
        "resolution_status": "resolved" if not pending else "pending",
        "verification_status": verification_status,
        "valid_observation_days": valid_observation_days,
        "inactive_days": inactive_days,
        "disappeared_topics": disappeared,
        "pending_disappeared_topics": pending,
        "confirmed_disappeared_topics": confirmed,
        "appeared_topics": appeared,
        "cooling_absent_streaks": streaks,
    }


def build_daily_summary(
    *,
    domain_id: str,
    date_str: str,
    metrics: dict[str, Any],
    signals: dict[str, Any],
    data_quality: dict[str, Any],
    market_analysis: dict[str, Any],
) -> dict[str, Any]:
    topics = _top(signals.get("topics"), 10)
    patterns = _top(signals.get("content_patterns"), 10)
    authors = _top(signals.get("top_authors"), 10)
    evidence_cases = _top(market_analysis.get("evidence_cases"), 10)

    return {
        "date": date_str,
        "domain_id": domain_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_quality": {
            "quality_level": data_quality.get("quality_level", "unknown"),
            "memory_update_allowed": memory_update_allowed(data_quality),
            "warnings": data_quality.get("warnings", []),
            "blockers": data_quality.get("blockers", []),
        },
        "metrics_summary": {
            "raw_count": metrics.get("raw_count", 0),
            "clean_count": metrics.get("clean_count", 0),
            "dedupe_rate": metrics.get("dedupe_rate", 0),
            "publish_date_present_rate": metrics.get("publish_date_present_rate", 0),
            "recent_publish_ratio": metrics.get("recent_publish_ratio", 0),
            "high_like_rate": metrics.get("high_like_rate", 0),
            "collect_like_ratio": metrics.get("collect_like_ratio", 0),
            "comment_like_ratio": metrics.get("comment_like_ratio", 0),
        },
        "top_topics": topics,
        "top_content_patterns": patterns,
        "top_authors": authors,
        "situation_summary": _top(market_analysis.get("situation_summary"), 5),
        "topic_findings": _top(market_analysis.get("topic_findings"), 10),
        "pattern_findings": _top(market_analysis.get("pattern_findings"), 10),
        "uncertainties": _top(market_analysis.get("uncertainties"), 10),
        "evidence_cases": evidence_cases,
    }


def render_current_state(*, domain: dict[str, Any], daily_summary: dict[str, Any], previous_text: str = "") -> str:
    domain_id = daily_summary.get("domain_id", domain.get("id", ""))
    date_str = daily_summary.get("date", "")
    quality = daily_summary.get("data_quality", {})
    verification_status = daily_summary.get("verification_status", "unknown")
    valid_observation_days = daily_summary.get("valid_observation_days", 0)
    metrics = daily_summary.get("metrics_summary", {})
    topics = daily_summary.get("top_topics", [])
    patterns = daily_summary.get("top_content_patterns", [])
    authors = daily_summary.get("top_authors", [])
    uncertainties = daily_summary.get("uncertainties", [])
    evidence_cases = daily_summary.get("evidence_cases", [])

    lines = [
        f"# {domain.get('name', domain_id)} current_state",
        "",
        f"- domain_id: `{domain_id}`",
        f"- last_updated: `{date_str}`",
        f"- data_quality: `{quality.get('quality_level', 'unknown')}`",
        f"- verification_status: `{verification_status}`",
        f"- valid_observation_days: `{valid_observation_days}`",
        f"- clean_count: `{metrics.get('clean_count', 0)}`",
        "",
        "## 当前搜索页局势",
        "",
    ]
    situation = daily_summary.get("situation_summary", [])
    if situation:
        for item in situation:
            lines.append(f"- {item.get('summary') or item.get('finding') or ''}")
    else:
        lines.append("- 暂无足够局势摘要。")

    lines.extend(["", "## 主要主题", ""])
    for item in topics[:8]:
        topic = item.get("topic") or item.get("name") or ""
        lines.append(
            f"- {topic}: 样本数 {item.get('note_count', 0)}，占比 {item.get('note_share', 0)}，平均点赞 {item.get('avg_likes', 0)}"
        )
    if not topics:
        lines.append("- 暂无主题信号。")

    lines.extend(["", "## 内容打法", ""])
    for item in patterns[:8]:
        pattern = item.get("content_pattern") or item.get("pattern") or ""
        lines.append(
            f"- {pattern}: 样本数 {item.get('note_count', 0)}，占比 {item.get('note_share', 0)}，平均点赞 {item.get('avg_likes', 0)}"
        )
    if not patterns:
        lines.append("- 暂无内容打法信号。")

    lines.extend(["", "## 高频作者", ""])
    for item in authors[:8]:
        lines.append(f"- {item.get('name', '')}: 出现 {item.get('count', 0)} 次")
    if not authors:
        lines.append("- 暂无明显作者集中信号。")

    lines.extend(["", "## 代表证据", ""])
    for item in evidence_cases[:8]:
        evidence_id = item.get("evidence_id") or item.get("based_on_evidence_id") or ""
        title = item.get("title") or item.get("case") or ""
        why = item.get("why_it_matters") or item.get("finding") or ""
        lines.append(f"- `{evidence_id}` {title}: {why}")
    if not evidence_cases:
        lines.append("- 暂无 evidence case。")

    lines.extend(["", "## 不确定性", ""])
    for item in uncertainties[:8]:
        lines.append(f"- {item.get('uncertainty') or item.get('risk') or ''}: {item.get('impact', '')}")
    if not uncertainties:
        lines.append("- 暂无额外不确定性。")

    if previous_text:
        lines.extend(["", "## 上一版索引", ""])
        old_topics = _extract_section_items(previous_text, "## 主要主题", limit=5)
        if old_topics:
            lines.extend(old_topics)
        else:
            lines.append("- 未读取到上一版主题索引。")

    return "\n".join(lines).rstrip() + "\n"


def build_judgment_record(
    *,
    domain_id: str,
    date_str: str,
    daily_summary: dict[str, Any],
    updated_current_state: bool,
    update_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = update_decision or {}
    return {
        "date": date_str,
        "domain_id": domain_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "event": "memory_update" if updated_current_state else "memory_observation_only",
        "quality_level": daily_summary.get("data_quality", {}).get("quality_level", "unknown"),
        "updated_current_state": updated_current_state,
        "resolution_status": decision.get("resolution_status", "resolved" if updated_current_state else "pending"),
        "verification_status": decision.get("verification_status", "unknown"),
        "valid_observation_days": decision.get("valid_observation_days", 0),
        "top_topics": _names(daily_summary.get("top_topics", []), "topic", 5),
        "top_content_patterns": _names(daily_summary.get("top_content_patterns", []), "content_pattern", 5),
        "reason": decision.get("reason") or ("quality_allowed" if updated_current_state else "quality_blocked_or_disabled"),
        "pending_disappeared_topics": decision.get("pending_disappeared_topics", []),
        "confirmed_disappeared_topics": decision.get("confirmed_disappeared_topics", []),
    }


def build_conflict_records(
    *,
    domain_id: str,
    date_str: str,
    daily_summary: dict[str, Any],
    previous_text: str,
    updated_current_state: bool,
    update_decision: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    quality = daily_summary.get("data_quality", {})
    current_topics = _names(daily_summary.get("top_topics", []), "topic", 5)
    previous_topics = _extract_topic_names(previous_text, limit=8)
    decision = update_decision or {}

    if not updated_current_state:
        records.append(
            {
                "date": date_str,
                "domain_id": domain_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "type": "quality_blocked_memory_update",
                "status": decision.get("resolution_status", "pending_observation"),
                "quality_level": quality.get("quality_level", "unknown"),
                "reason": decision.get("reason") or "低质量或无效数据不覆盖 current_state",
                "current_topics": current_topics,
                "pending_disappeared_topics": decision.get("pending_disappeared_topics", []),
            }
        )

    if previous_topics and current_topics:
        disappeared = [topic for topic in previous_topics if topic not in current_topics]
        appeared = [topic for topic in current_topics if topic not in previous_topics]
        if disappeared or appeared:
            records.append(
                {
                    "date": date_str,
                    "domain_id": domain_id,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "type": "topic_set_changed",
                    "status": decision.get("resolution_status", "pending_observation"),
                    "reason": decision.get("reason") or "current_state 中的主题集合与当天样本主题集合不同，需观察是否连续出现",
                    "appeared_topics": appeared,
                    "disappeared_topics": disappeared,
                    "pending_disappeared_topics": decision.get("pending_disappeared_topics", []),
                    "confirmed_disappeared_topics": decision.get("confirmed_disappeared_topics", []),
                    "cooling_absent_streaks": decision.get("cooling_absent_streaks", {}),
                }
            )

    return records


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _extract_section_items(text: str, heading: str, limit: int = 5) -> list[str]:
    lines = text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    items = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip().startswith("- "):
            items.append(line)
        if len(items) >= limit:
            break
    return items


def _extract_topic_names(text: str, limit: int = 8) -> list[str]:
    items = _extract_section_items(text, "## 主要主题", limit=limit)
    topics = []
    for item in items:
        clean = item.removeprefix("- ").strip()
        topic = clean.split(":", 1)[0].strip()
        if topic:
            topics.append(topic)
    return topics


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
