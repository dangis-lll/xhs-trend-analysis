from __future__ import annotations

from typing import Any


def _priority(count: int) -> str:
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _candidate_id(kind: str, term: str) -> str:
    safe = "".join(ch for ch in term.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return f"{kind}_{safe or 'candidate'}"


def build_rule_candidates(rule_effectiveness: dict[str, Any], *, min_count: int = 2) -> dict[str, Any]:
    pattern_terms = rule_effectiveness.get("content_pattern", {}).get("candidate_terms_from_other", []) or []
    topic_terms = rule_effectiveness.get("topic", {}).get("candidate_terms_from_other", []) or []

    content_pattern_candidates = []
    for item in pattern_terms:
        term = str(item.get("term", "")).strip()
        count = int(item.get("count") or 0)
        if not term or count < min_count:
            continue
        content_pattern_candidates.append(
            {
                "candidate_id": _candidate_id("pattern", term),
                "kind": "content_pattern",
                "suggested_name": term,
                "keywords": [term],
                "source": "uncovered_content_pattern_titles",
                "support_count": count,
                "priority": _priority(count),
                "status": "needs_review",
            }
        )

    topic_candidates = []
    for item in topic_terms:
        term = str(item.get("term", "")).strip()
        count = int(item.get("count") or 0)
        if not term or count < min_count:
            continue
        topic_candidates.append(
            {
                "candidate_id": _candidate_id("topic", term),
                "kind": "topic",
                "suggested_name": term,
                "keywords": [term],
                "source": "uncovered_topic_titles",
                "support_count": count,
                "priority": _priority(count),
                "status": "needs_review",
            }
        )

    return {
        "date": rule_effectiveness.get("date", ""),
        "domain_id": rule_effectiveness.get("domain_id", ""),
        "min_count": min_count,
        "content_pattern_candidates": content_pattern_candidates,
        "topic_candidates": topic_candidates,
        "summary": {
            "content_pattern_candidate_count": len(content_pattern_candidates),
            "topic_candidate_count": len(topic_candidates),
            "source_recommendations": rule_effectiveness.get("recommendations", []),
        },
    }


def render_rule_candidates(candidates: dict[str, Any]) -> str:
    lines = [
        f"# 规则候选：{candidates.get('domain_id', '')}",
        "",
        f"日期：{candidates.get('date', '')}",
        f"最小支持次数：{candidates.get('min_count', 0)}",
        "",
        "## Content Pattern 候选",
        "",
    ]
    for item in candidates.get("content_pattern_candidates", []):
        lines.append(
            f"- `{item.get('candidate_id')}` {item.get('suggested_name')}："
            f"支持 {item.get('support_count')} 次，优先级 {item.get('priority')}"
        )
    if not candidates.get("content_pattern_candidates"):
        lines.append("- 暂无候选。")

    lines.extend(["", "## Topic 候选", ""])
    for item in candidates.get("topic_candidates", []):
        lines.append(
            f"- `{item.get('candidate_id')}` {item.get('suggested_name')}："
            f"支持 {item.get('support_count')} 次，优先级 {item.get('priority')}"
        )
    if not candidates.get("topic_candidates"):
        lines.append("- 暂无候选。")

    lines.extend(
        [
            "",
            "## 使用方式",
            "",
            "- 人工确认后，把 topic 候选写入 `projects/<domain>/memory/taxonomy.yaml`。",
            "- 人工确认后，把 content_pattern 候选写入 `memory_global/pattern_rules/content_patterns.yaml` 或领域规则文件。",
            "- 不建议自动合并候选，避免把噪声词写成长期规则。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
