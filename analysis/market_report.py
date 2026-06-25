from __future__ import annotations

from typing import Any


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "0.00%"


def _num(value: Any) -> str:
    if value is None:
        return "0"
    return str(value)


def _bullet(text: str) -> str:
    return f"- {text}"


def _evidence_line(item: dict[str, Any]) -> str:
    metrics = []
    for label, key in [("赞", "like_count_num"), ("藏", "collect_count_num"), ("评", "comment_count_num")]:
        if item.get(key) is not None:
            metrics.append(f"{label}{item.get(key)}")
    metric_text = "，".join(metrics)
    evidence_id = item.get("evidence_id", "")
    title = item.get("title", "")
    topic = item.get("topic_name", "")
    return f"{title}（{topic}，{metric_text}，evidence_id: `{evidence_id}`）"


def deterministic_market_analysis(llm_input: dict[str, Any]) -> dict[str, Any]:
    quality = llm_input.get("data_quality", {})
    metrics = llm_input.get("metrics_summary", {})
    signals = llm_input.get("signals", {})
    evidence = llm_input.get("representative_evidence", [])

    top_topics = signals.get("topics", [])[:5]
    top_patterns = signals.get("content_patterns", [])[:5]
    top_authors = signals.get("top_authors", [])[:5]
    top_entities = signals.get("entity_candidates", [])[:5]
    top_demands = signals.get("demand_signals", [])[:5]

    situation = [
        {
            "summary": (
                f"当前搜索页样本共 {metrics.get('clean_count', 0)} 条，数据质量为 "
                f"{quality.get('quality_level', 'unknown')}。近期发布占比 {_percent(metrics.get('recent_publish_ratio'))}，"
                f"高赞率 {_percent(metrics.get('high_like_rate'))}。"
            ),
            "evidence_ids": [item.get("evidence_id") for item in evidence[:3] if item.get("evidence_id")],
        }
    ]
    topic_findings = [
        {
            "topic": item.get("topic", ""),
            "finding": (
                f"样本数 {item.get('note_count', 0)}，样本占比 {_percent(item.get('note_share'))}，"
                f"平均点赞 {_num(item.get('avg_likes'))}，信号强度 {item.get('signal_strength', 'unknown')}。"
            ),
            "confidence": item.get("confidence", "low"),
            "evidence_ids": [],
        }
        for item in top_topics
    ]
    pattern_findings = [
        {
            "content_pattern": item.get("content_pattern", ""),
            "finding": (
                f"样本数 {item.get('note_count', 0)}，样本占比 {_percent(item.get('note_share'))}，"
                f"平均点赞 {_num(item.get('avg_likes'))}，信号强度 {item.get('signal_strength', 'unknown')}。"
            ),
            "confidence": item.get("confidence", "low"),
            "evidence_ids": [],
        }
        for item in top_patterns
    ]
    author_findings = [
        {"author": item.get("name", ""), "finding": f"搜索页样本中出现 {item.get('count', 0)} 次。", "evidence_ids": []}
        for item in top_authors
    ]
    entity_findings = [
        {
            "entity": item.get("entity", ""),
            "entity_type": item.get("entity_type", ""),
            "finding": (
                f"标题/关键词中出现 {item.get('sample_count', 0)} 次，类型候选为 {item.get('entity_type', '')}，"
                f"信号强度 {item.get('signal_strength', 'unknown')}。"
            ),
            "confidence": item.get("confidence", "low"),
            "evidence_ids": [],
        }
        for item in top_entities
    ]
    demand_findings = [
        {
            "demand_type": item.get("demand_type", ""),
            "finding": (
                f"相关样本 {item.get('sample_count', 0)} 条，样本占比 {_percent(item.get('note_share'))}，"
                f"信号强度 {item.get('signal_strength', 'unknown')}。"
            ),
            "confidence": item.get("confidence", "low"),
            "evidence_ids": [],
        }
        for item in top_demands
    ]
    evidence_cases = [
        {
            "title": item.get("title", ""),
            "why_it_matters": "代表当前样本中的高互动或高可见案例。",
            "evidence_id": item.get("evidence_id", ""),
        }
        for item in evidence[:8]
    ]
    uncertainties = [
        {"uncertainty": warning, "impact": "该问题会降低趋势判断强度。"}
        for warning in quality.get("warnings", [])
    ]
    if quality.get("quality_level") in {"low", "invalid"}:
        uncertainties.append(
            {
                "uncertainty": "样本量不足或质量较低",
                "impact": "本报告只能描述搜索页可见局势，不更新强趋势判断。",
            }
        )

    return {
        "enabled": False,
        "situation_summary": situation,
        "topic_findings": topic_findings,
        "pattern_findings": pattern_findings,
        "author_findings": author_findings,
        "entity_findings": entity_findings,
        "demand_findings": demand_findings,
        "evidence_cases": evidence_cases,
        "uncertainties": uncertainties,
        "low_priority_suggestions": [],
    }


def render_market_report(llm_input: dict[str, Any], analysis: dict[str, Any]) -> str:
    meta = llm_input.get("meta", {})
    quality = llm_input.get("data_quality", {})
    metrics = llm_input.get("metrics_summary", {})
    evidence = llm_input.get("representative_evidence", [])
    lines = [
        f"# 小红书搜索页市场局势报告：{meta.get('domain_name', meta.get('domain_id', ''))}",
        "",
        f"日期：{meta.get('date', '')}",
        "",
        "## 数据边界",
        "",
        "- 数据来源：小红书搜索结果页样本。",
        "- 本报告只描述当前搜索页样本中可见的局势，不推断全市场规模、销量、成交或真实投放。",
        f"- 数据质量：{quality.get('quality_level', 'unknown')}；清洗后样本数 {metrics.get('clean_count', 0)}。",
        "",
        "## 当前局势",
        "",
    ]
    for item in analysis.get("situation_summary", []) or []:
        lines.append(_bullet(str(item.get("summary") or item.get("finding") or "")))

    lines.extend(["", "## 主题信号", ""])
    topic_items = analysis.get("topic_findings", []) or []
    if topic_items:
        for item in topic_items:
            topic = item.get("topic") or item.get("name") or "未命名主题"
            lines.append(_bullet(f"{topic}：{item.get('finding') or item.get('analysis') or ''}"))
    else:
        lines.append("暂无足够主题信号。")

    lines.extend(["", "## 内容打法信号", ""])
    pattern_items = analysis.get("pattern_findings", []) or analysis.get("content_patterns", []) or []
    if pattern_items:
        for item in pattern_items:
            pattern = item.get("content_pattern") or item.get("pattern") or "未命名打法"
            lines.append(_bullet(f"{pattern}：{item.get('finding') or item.get('signal_value') or item.get('analysis') or ''}"))
    else:
        lines.append("暂无足够内容打法信号。")

    lines.extend(["", "## 作者与样本集中度", ""])
    author_items = analysis.get("author_findings", []) or []
    if author_items:
        for item in author_items:
            author = item.get("author") or item.get("name") or "未知作者"
            lines.append(_bullet(f"{author}：{item.get('finding') or item.get('analysis') or ''}"))
    else:
        lines.append("暂无明显作者集中信号。")

    lines.extend(["", "## 实体/IP/产品候选", ""])
    entity_items = analysis.get("entity_findings", []) or []
    if entity_items:
        for item in entity_items:
            entity = item.get("entity") or "未命名实体"
            entity_type = item.get("entity_type") or "unknown"
            lines.append(_bullet(f"{entity}（{entity_type}）：{item.get('finding') or item.get('analysis') or ''}"))
    else:
        lines.append("暂无明显实体/IP/产品候选。")

    lines.extend(["", "## 需求信号", ""])
    demand_items = analysis.get("demand_findings", []) or []
    if demand_items:
        for item in demand_items:
            demand = item.get("demand_type") or "unknown"
            lines.append(_bullet(f"{demand}：{item.get('finding') or item.get('analysis') or ''}"))
    else:
        lines.append("暂无明显需求信号。")

    lines.extend(["", "## 代表证据", ""])
    if evidence:
        for item in evidence[:10]:
            lines.append(_bullet(_evidence_line(item)))
    else:
        lines.append("暂无 evidence 记录。")

    lines.extend(["", "## 不确定性", ""])
    uncertainties = analysis.get("uncertainties", []) or analysis.get("anomaly_risks", []) or []
    if uncertainties:
        for item in uncertainties:
            lines.append(_bullet(f"{item.get('uncertainty') or item.get('risk') or ''}：{item.get('impact') or ''}"))
    else:
        lines.append("- 暂无额外不确定性。")

    suggestions = analysis.get("low_priority_suggestions", []) or analysis.get("low_priority_content_ideas", []) or []
    if suggestions:
        lines.extend(["", "## 低优先级建议", ""])
        for item in suggestions[:3]:
            lines.append(_bullet(str(item.get("suggestion") or item.get("idea") or item)))

    return "\n".join(lines).rstrip() + "\n"
