from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def week_key(date_str: str) -> str:
    year, week, _ = parse_date(date_str).isocalendar()
    return f"{year}-W{week:02d}"


def month_key(date_str: str) -> str:
    value = parse_date(date_str)
    return f"{value.year}-{value.month:02d}"


def weekly_date_range(end_date: str) -> tuple[str, str]:
    end = parse_date(end_date)
    start = end - timedelta(days=end.weekday())
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def monthly_date_range(end_date: str) -> tuple[str, str]:
    end = parse_date(end_date)
    start = end.replace(day=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def filter_summaries(summaries: list[dict[str, Any]], *, start_date: str, end_date: str) -> list[dict[str, Any]]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    return [
        item
        for item in summaries
        if item.get("date") and start <= parse_date(str(item["date"])) <= end
    ]


def _counter_from_items(summaries: list[dict[str, Any]], list_key: str, name_key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for summary in summaries:
        for item in summary.get(list_key, []) or []:
            name = item.get(name_key) or item.get("name")
            if name:
                counter[str(name)] += int(item.get("note_count") or item.get("count") or 1)
    return counter


def _quality_counts(summaries: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for summary in summaries:
        level = summary.get("data_quality", {}).get("quality_level", "unknown")
        counter[str(level)] += 1
    return dict(counter)


def _avg_metric(summaries: list[dict[str, Any]], metric: str) -> float:
    values = []
    for summary in summaries:
        value = summary.get("metrics_summary", {}).get(metric)
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return round(sum(values) / len(values), 4) if values else 0.0


def build_rollup(
    summaries: list[dict[str, Any]],
    *,
    domain_id: str,
    period_type: str,
    period_key: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    topic_counter = _counter_from_items(summaries, "top_topics", "topic")
    pattern_counter = _counter_from_items(summaries, "top_content_patterns", "content_pattern")
    author_counter = _counter_from_items(summaries, "top_authors", "name")
    clean_counts = [
        int(summary.get("metrics_summary", {}).get("clean_count") or 0)
        for summary in summaries
    ]
    evidence_ids = []
    for summary in summaries:
        for item in summary.get("evidence_cases", []) or []:
            evidence_id = item.get("evidence_id") or item.get("based_on_evidence_id")
            if evidence_id:
                evidence_ids.append(str(evidence_id))

    return {
        "domain_id": domain_id,
        "period_type": period_type,
        "period_key": period_key,
        "start_date": start_date,
        "end_date": end_date,
        "days_observed": len(summaries),
        "total_clean_count": sum(clean_counts),
        "avg_clean_count": round(sum(clean_counts) / len(clean_counts), 2) if clean_counts else 0,
        "quality_counts": _quality_counts(summaries),
        "avg_recent_publish_ratio": _avg_metric(summaries, "recent_publish_ratio"),
        "avg_high_like_rate": _avg_metric(summaries, "high_like_rate"),
        "avg_collect_like_ratio": _avg_metric(summaries, "collect_like_ratio"),
        "avg_comment_like_ratio": _avg_metric(summaries, "comment_like_ratio"),
        "top_topics": [{"topic": name, "score": count} for name, count in topic_counter.most_common(12)],
        "top_content_patterns": [
            {"content_pattern": name, "score": count} for name, count in pattern_counter.most_common(12)
        ],
        "top_authors": [{"name": name, "score": count} for name, count in author_counter.most_common(12)],
        "representative_evidence_ids": list(dict.fromkeys(evidence_ids))[:20],
    }


def render_rollup_summary(rollup: dict[str, Any]) -> str:
    lines = [
        f"# {rollup.get('period_type', '')} rollup: {rollup.get('period_key', '')}",
        "",
        f"- domain_id: `{rollup.get('domain_id', '')}`",
        f"- date_range: `{rollup.get('start_date', '')}` 至 `{rollup.get('end_date', '')}`",
        f"- observed_days: `{rollup.get('days_observed', 0)}`",
        f"- total_clean_count: `{rollup.get('total_clean_count', 0)}`",
        f"- avg_clean_count: `{rollup.get('avg_clean_count', 0)}`",
        f"- quality_counts: `{rollup.get('quality_counts', {})}`",
        "",
        "## 主题汇总",
        "",
    ]
    for item in rollup.get("top_topics", [])[:10]:
        lines.append(f"- {item.get('topic', '')}: score {item.get('score', 0)}")
    if not rollup.get("top_topics"):
        lines.append("- 暂无主题汇总。")

    lines.extend(["", "## 内容打法汇总", ""])
    for item in rollup.get("top_content_patterns", [])[:10]:
        lines.append(f"- {item.get('content_pattern', '')}: score {item.get('score', 0)}")
    if not rollup.get("top_content_patterns"):
        lines.append("- 暂无内容打法汇总。")

    lines.extend(["", "## 高频作者汇总", ""])
    for item in rollup.get("top_authors", [])[:10]:
        lines.append(f"- {item.get('name', '')}: score {item.get('score', 0)}")
    if not rollup.get("top_authors"):
        lines.append("- 暂无作者汇总。")

    lines.extend(["", "## 代表证据索引", ""])
    for evidence_id in rollup.get("representative_evidence_ids", [])[:12]:
        lines.append(f"- `{evidence_id}`")
    if not rollup.get("representative_evidence_ids"):
        lines.append("- 暂无 evidence_id。")
    return "\n".join(lines).rstrip() + "\n"
