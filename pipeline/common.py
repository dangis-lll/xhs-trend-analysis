from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from storage.paths import get_project_root


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_domains_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or get_project_root() / "config" / "domains.yaml")


def load_analysis_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or get_project_root() / "config" / "analysis_config.yaml")


def get_domain(domain_id: str, config_path: Path | None = None) -> dict[str, Any]:
    config = load_domains_config(config_path)
    for domain in config.get("domains", []):
        if domain.get("id") == domain_id:
            return domain
    available = ", ".join(d.get("id", "") for d in config.get("domains", []))
    raise ValueError(f"找不到 domain={domain_id}。可用 domain：{available or '无'}")


def domain_keywords(domain: dict[str, Any]) -> list[str]:
    return [str(item).strip() for item in domain.get("seed_keywords", []) if str(item).strip()]
