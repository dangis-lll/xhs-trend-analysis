from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from analysis.metrics import tokenize_chinese_text
from analysis.rule_loader import load_entity_rules


DEMAND_RULES: dict[str, list[str]] = {
    "how_to": ["怎么", "如何", "教程", "步骤", "攻略"],
    "recommendation": ["推荐", "求推荐", "有没有", "哪些", "清单"],
    "avoidance": ["避坑", "踩雷", "别买", "不建议", "后悔"],
    "comparison": ["对比", "区别", "哪个更", "vs", "VS"],
    "price_or_factory": ["多少钱", "预算", "平替", "工厂", "打样", "起订", "定制"],
}


def signal_score(*, note_share: float, avg_likes: float, note_count: int) -> float:
    count_score = min(note_count / 10, 1.0) * 0.35
    share_score = min(note_share / 0.35, 1.0) * 0.35
    like_score = min(avg_likes / 1000, 1.0) * 0.30
    return round(count_score + share_score + like_score, 4)


def signal_strength(score: float) -> str:
    if score >= 0.7:
        return "strong"
    if score >= 0.4:
        return "medium"
    if score > 0:
        return "weak"
    return "none"


def signal_confidence(*, note_count: int, note_share: float) -> str:
    if note_count >= 10 and note_share >= 0.25:
        return "high"
    if note_count >= 3 and note_share >= 0.1:
        return "medium"
    return "low"


def _text_from_row(row: pd.Series) -> str:
    values = [row.get("title", ""), row.get("keyword", ""), row.get("topic_name", "")]
    return " ".join(str(value or "") for value in values)


def mine_entity_candidates(
    clean_df: pd.DataFrame,
    *,
    entity_rules: dict[str, list[str]] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rules = entity_rules or load_entity_rules()
    bucket: dict[tuple[str, str], dict[str, Any]] = {}

    for _, row in clean_df.iterrows():
        text = _text_from_row(row)
        title = str(row.get("title", "") or "")
        likes = row.get("like_count_num") or 0
        for entity_type, keywords in rules.items():
            for keyword in keywords:
                clean_keyword = str(keyword).strip()
                if not clean_keyword or clean_keyword not in text:
                    continue
                key = (str(entity_type), clean_keyword)
                record = bucket.setdefault(
                    key,
                    {
                        "entity": clean_keyword,
                        "entity_type": str(entity_type),
                        "sample_count": 0,
                        "avg_likes": 0,
                        "top_titles": [],
                        "_likes": [],
                    },
                )
                record["sample_count"] += 1
                record["_likes"].append(float(likes or 0))
                if title and title not in record["top_titles"]:
                    record["top_titles"].append(title)

    rows = []
    total = max(len(clean_df), 1)
    for record in bucket.values():
        likes = record.pop("_likes")
        avg_likes = round(sum(likes) / len(likes), 2) if likes else 0
        note_share = round(record["sample_count"] / total, 4)
        score = signal_score(note_share=note_share, avg_likes=avg_likes, note_count=record["sample_count"])
        rows.append(
            {
                **record,
                "note_share": note_share,
                "avg_likes": avg_likes,
                "signal_score": score,
                "signal_strength": signal_strength(score),
                "confidence": signal_confidence(note_count=record["sample_count"], note_share=note_share),
                "top_titles": record["top_titles"][:3],
                "source": "rule_keyword_match",
            }
        )
    rows.sort(key=lambda item: (item["sample_count"], item["avg_likes"], item["entity"]), reverse=True)
    return rows[:limit]


def mine_demand_signals(clean_df: pd.DataFrame, *, limit: int = 12) -> list[dict[str, Any]]:
    matches: dict[str, list[pd.Series]] = defaultdict(list)
    for _, row in clean_df.iterrows():
        text = _text_from_row(row)
        for demand_type, keywords in DEMAND_RULES.items():
            if any(keyword in text for keyword in keywords):
                matches[demand_type].append(row)

    total = max(len(clean_df), 1)
    rows = []
    for demand_type, row_list in matches.items():
        titles = [str(row.get("title", "") or "") for row in row_list if str(row.get("title", "") or "")]
        likes = [float(row.get("like_count_num") or 0) for row in row_list]
        terms = Counter()
        for title in titles:
            terms.update(tokenize_chinese_text(title))
        avg_likes = round(sum(likes) / len(likes), 2) if likes else 0
        note_share = round(len(row_list) / total, 4)
        score = signal_score(note_share=note_share, avg_likes=avg_likes, note_count=len(row_list))
        rows.append(
            {
                "demand_type": demand_type,
                "sample_count": len(row_list),
                "note_share": note_share,
                "avg_likes": avg_likes,
                "signal_score": score,
                "signal_strength": signal_strength(score),
                "confidence": signal_confidence(note_count=len(row_list), note_share=note_share),
                "top_terms": [{"name": name, "count": count} for name, count in terms.most_common(8)],
                "top_titles": titles[:3],
            }
        )
    rows.sort(key=lambda item: (item["sample_count"], item["avg_likes"]), reverse=True)
    return rows[:limit]
