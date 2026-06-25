from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from storage.paths import get_project_root


DEFAULT_CONTENT_PATTERN_RULES: dict[str, list[str]] = {
    "测评": ["测评", "实测", "体验", "试用", "好用吗"],
    "避坑": ["避坑", "踩雷", "别买", "不建议", "后悔"],
    "清单": ["清单", "合集", "盘点", "必备", "推荐"],
    "教程": ["教程", "攻略", "怎么", "如何", "步骤"],
    "对比": ["对比", "区别", "横评", "哪个更", "vs", "VS"],
    "平替": ["平替", "替代", "低配", "同款", "相似"],
    "开箱": ["开箱", "到手", "拆箱", "入手"],
}

DEFAULT_TOPIC_RULES: dict[str, list[str]] = {}
DEFAULT_ENTITY_RULES: dict[str, list[str]] = {
    "ip": ["IP", "ip", "联名", "动漫", "角色", "谷圈"],
    "product": ["周边", "徽章", "立牌", "吧唧", "亚克力", "贴纸", "挂件", "娃娃", "手办", "卡套"],
    "brand": ["品牌", "官方", "旗舰店", "工厂", "厂家", "代工"],
}


def default_pattern_rules_path() -> Path:
    return get_project_root() / "memory_global" / "pattern_rules" / "content_patterns.yaml"


def default_taxonomy_path() -> Path:
    return get_project_root() / "memory_global" / "taxonomy.yaml"


def default_entity_rules_path() -> Path:
    return get_project_root() / "memory_global" / "pattern_rules" / "entity_patterns.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def normalize_rules(raw: Any, root_key: str | None = None) -> dict[str, list[str]]:
    if not raw:
        return {}
    if root_key and isinstance(raw, dict) and root_key in raw:
        raw = raw.get(root_key)
    if not isinstance(raw, dict):
        return {}

    rules: dict[str, list[str]] = {}
    for pattern, value in raw.items():
        keywords: list[str] = []
        if isinstance(value, dict):
            value = value.get("keywords", [])
        if isinstance(value, str):
            keywords = [value]
        elif isinstance(value, list):
            keywords = [str(item).strip() for item in value if str(item).strip()]
        if keywords:
            rules[str(pattern).strip()] = keywords
    return rules


def load_content_pattern_rules(path: Path | None = None) -> dict[str, list[str]]:
    loaded = normalize_rules(load_yaml(path or default_pattern_rules_path()), "content_patterns")
    rules = dict(loaded)
    for pattern, keywords in DEFAULT_CONTENT_PATTERN_RULES.items():
        rules.setdefault(pattern, keywords)
    return rules


def load_topic_rules(*, global_path: Path | None = None, domain_path: Path | None = None) -> dict[str, list[str]]:
    rules = dict(DEFAULT_TOPIC_RULES)
    global_rules = normalize_rules(load_yaml(global_path or default_taxonomy_path()), "topics")
    rules.update(global_rules)
    if domain_path:
        rules.update(normalize_rules(load_yaml(domain_path), "topics"))
    return rules


def load_entity_rules(path: Path | None = None) -> dict[str, list[str]]:
    loaded = normalize_rules(load_yaml(path or default_entity_rules_path()), "entity_patterns")
    rules = dict(loaded)
    for entity_type, keywords in DEFAULT_ENTITY_RULES.items():
        rules.setdefault(entity_type, keywords)
    return rules
