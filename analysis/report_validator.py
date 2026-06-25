from __future__ import annotations

import re
from typing import Any


REPORT_ARRAY_FIELDS = [
    "situation_summary",
    "topic_findings",
    "pattern_findings",
    "author_findings",
    "evidence_cases",
    "uncertainties",
    "low_priority_suggestions",
]

FORBIDDEN_CLAIMS = [
    "销量",
    "成交",
    "销售额",
    "GMV",
    "真实投放",
    "投放预算",
    "全市场",
    "市场规模",
    "评论区都在",
    "详情页显示",
]


def collect_allowed_evidence_ids(llm_input: dict[str, Any]) -> set[str]:
    allowed = set()
    for item in llm_input.get("representative_evidence", []) or []:
        evidence_id = item.get("evidence_id")
        if evidence_id:
            allowed.add(str(evidence_id))
    return allowed


def _iter_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        texts: list[str] = []
        for item in value.values():
            texts.extend(_iter_texts(item))
        return texts
    if isinstance(value, list):
        texts = []
        for item in value:
            texts.extend(_iter_texts(item))
        return texts
    return []


def _normalize_array(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"text": str(item)} for item in value]
    return [{"text": str(value)}]


def _filter_evidence_ids(item: dict[str, Any], allowed: set[str], issues: list[dict[str, Any]], field: str) -> None:
    if "evidence_ids" in item:
        raw_ids = item.get("evidence_ids")
        ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        valid = [str(eid) for eid in ids if eid and str(eid) in allowed]
        invalid = [str(eid) for eid in ids if eid and str(eid) not in allowed]
        if invalid:
            issues.append({"type": "invalid_evidence_id", "field": field, "evidence_ids": invalid})
        item["evidence_ids"] = valid

    for key in ["evidence_id", "based_on_evidence_id"]:
        if key not in item:
            continue
        evidence_id = str(item.get(key) or "")
        if evidence_id and evidence_id not in allowed:
            issues.append({"type": "invalid_evidence_id", "field": field, "evidence_ids": [evidence_id]})
            item[key] = ""


def _check_forbidden_claims(analysis: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    for text in _iter_texts(analysis):
        for claim in FORBIDDEN_CLAIMS:
            if claim in text:
                issues.append({"type": "forbidden_claim", "claim": claim, "text_excerpt": text[:120]})


def _check_lengths(analysis: dict[str, Any], issues: list[dict[str, Any]], max_text_length: int) -> None:
    for field in REPORT_ARRAY_FIELDS:
        for index, item in enumerate(_normalize_array(analysis.get(field))):
            for key, value in item.items():
                if isinstance(value, str) and len(value) > max_text_length:
                    issues.append({"type": "text_too_long", "field": field, "index": index, "key": key, "length": len(value)})
                    item[key] = value[:max_text_length].rstrip() + "..."


def validate_market_analysis(
    analysis: dict[str, Any],
    llm_input: dict[str, Any],
    *,
    max_text_length: int = 500,
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = collect_allowed_evidence_ids(llm_input)
    cleaned = dict(analysis)
    issues: list[dict[str, Any]] = []

    for field in REPORT_ARRAY_FIELDS:
        cleaned[field] = _normalize_array(cleaned.get(field))
        for item in cleaned[field]:
            _filter_evidence_ids(item, allowed, issues, field)

    _check_forbidden_claims(cleaned, issues)
    _check_lengths(cleaned, issues, max_text_length)

    if issues:
        cleaned.setdefault("uncertainties", [])
        cleaned["uncertainties"].append(
            {
                "uncertainty": "报告输出经过程序校验后被降级",
                "impact": "部分无效 evidence_id、过长文本或禁用表达已被记录，相关结论需人工复核。",
            }
        )

    validation = {
        "valid": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "allowed_evidence_count": len(allowed),
    }
    cleaned["validation"] = validation
    return cleaned, validation


def evidence_ids_in_text(text: str) -> list[str]:
    return re.findall(r"ev_[0-9]{8}_[A-Za-z0-9_-]+_[A-Za-z]+_[A-Fa-f0-9]+", text)
