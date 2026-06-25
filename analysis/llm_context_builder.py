from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storage.paths import evidence_dir, memory_dir, processed_dir


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
        if limit and len(records) >= limit:
            break
    return records


def current_state_excerpt(domain_id: str, max_chars: int = 3000) -> str:
    path = memory_dir(domain_id) / "current_state.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    return text[:max_chars]


def _top_items(items: Any, limit: int = 10) -> list[Any]:
    if isinstance(items, list):
        return items[:limit]
    if isinstance(items, dict):
        return [{"name": key, "value": value} for key, value in list(items.items())[:limit]]
    return []


def _representative_evidence(records: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    ranked = sorted(
        records,
        key=lambda item: (
            item.get("like_count_num") or 0,
            item.get("collect_count_num") or 0,
            item.get("comment_count_num") or 0,
        ),
        reverse=True,
    )
    keep_fields = [
        "evidence_id",
        "note_global_id",
        "keywords",
        "title",
        "author",
        "publish_date",
        "topic_name",
        "like_count_num",
        "collect_count_num",
        "comment_count_num",
        "share_count_num",
        "link",
    ]
    return [{field: item.get(field) for field in keep_fields} for item in ranked[:limit]]


def build_llm_input(*, domain_id: str, date_str: str, domain: dict[str, Any] | None = None) -> dict[str, Any]:
    processed = processed_dir(domain_id)
    metrics = load_json(processed / f"{date_str}_metrics.json", {})
    signals = load_json(processed / f"{date_str}_search_signals.json", {})
    quality = load_json(processed / f"{date_str}_data_quality.json", {})
    evidence_records = load_jsonl(evidence_dir(domain_id) / f"{date_str}_evidence.jsonl")

    payload = {
        "meta": {
            "domain_id": domain_id,
            "domain_name": (domain or {}).get("name", domain_id),
            "date": date_str,
            "input_type": "compressed_structured_market_context",
            "source_scope": "xhs_search_page_only",
        },
        "data_boundary": {
            "allowed_claims": [
                "当前搜索页样本中可见的主题、作者、标题打法、互动分布和近期发布信号",
                "基于样本的强弱信号、异常和待验证方向",
            ],
            "forbidden_claims": [
                "不得推断全市场规模、销量、成交、真实投放、评论区观点或详情页正文",
                "不得把单条爆款直接写成长期趋势",
            ],
        },
        "data_quality": quality,
        "current_state_excerpt": current_state_excerpt(domain_id),
        "metrics_summary": {
            "raw_count": metrics.get("raw_count", 0),
            "clean_count": metrics.get("clean_count", 0),
            "dedupe_rate": metrics.get("dedupe_rate", 0),
            "publish_date_present_rate": metrics.get("publish_date_present_rate", 0),
            "recent_publish_ratio": metrics.get("recent_publish_ratio", 0),
            "avg_likes": metrics.get("avg_likes", 0),
            "median_likes": metrics.get("median_likes", 0),
            "p90_likes": metrics.get("p90_likes", 0),
            "collect_like_ratio": metrics.get("collect_like_ratio", 0),
            "comment_like_ratio": metrics.get("comment_like_ratio", 0),
            "video_rate": metrics.get("video_rate", 0),
            "high_like_rate": metrics.get("high_like_rate", 0),
        },
        "signals": {
            "topics": _top_items(signals.get("topics"), 12),
            "content_patterns": _top_items(signals.get("content_patterns"), 12),
            "top_title_terms": _top_items(signals.get("top_title_terms"), 20),
            "top_authors": _top_items(signals.get("top_authors"), 12),
            "top_keywords": _top_items(signals.get("top_keywords"), 12),
            "entity_candidates": _top_items(signals.get("entity_candidates"), 12),
            "demand_signals": _top_items(signals.get("demand_signals"), 12),
            "interaction_overview": signals.get("interaction_overview", {}),
        },
        "representative_evidence": _representative_evidence(evidence_records, 20),
        "requirements": {
            "analysis_focus": "现有局势分析为主，建议为低优先级",
            "important_claims_need_evidence_id": True,
            "write_uncertainties_when_quality_low": True,
            "output_language": "zh-CN",
        },
    }
    return payload


def save_llm_input(payload: dict[str, Any], *, domain_id: str, date_str: str) -> Path:
    path = processed_dir(domain_id) / f"{date_str}_llm_input.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
