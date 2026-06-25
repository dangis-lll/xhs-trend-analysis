from __future__ import annotations

from datetime import datetime
from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def normalize_date(value: str | None) -> str:
    if not value or value == "today":
        return get_today_str()
    return value


def data_dir() -> Path:
    return get_project_root() / "data"


def projects_dir() -> Path:
    return get_project_root() / "projects"


def project_dir(project_id: str) -> Path:
    return projects_dir() / project_id


def raw_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "raw" / normalize_date(date)


def processed_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "processed"


def report_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "reports" / "daily"


def market_report_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "reports" / "market"


def memory_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "memory"


def evidence_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "evidence"


def memory_daily_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "daily"


def memory_rollups_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "rollups"


def judgments_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "judgments"


def memory_wiki_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "wiki"


def memory_trends_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "trends"


def memory_entities_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "entities"


def memory_patterns_dir(project_id: str = "manual") -> Path:
    return memory_dir(project_id) / "patterns"


def images_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "images" / normalize_date(date)


def snapshots_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "snapshots" / normalize_date(date)


def details_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "details" / normalize_date(date)


def knowledge_base_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "knowledge-base"


def browser_profile_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "browser_profile"


def ensure_dirs(date: str | None = None, project_id: str = "manual") -> None:
    for path in [
        raw_dir(date, project_id),
        processed_dir(project_id),
        report_dir(date, project_id),
        market_report_dir(project_id),
        evidence_dir(project_id),
        memory_daily_dir(project_id),
        memory_rollups_dir(project_id),
        judgments_dir(project_id),
        memory_wiki_dir(project_id),
        memory_trends_dir(project_id),
        memory_entities_dir(project_id),
        memory_patterns_dir(project_id),
        images_dir(date, project_id),
        snapshots_dir(date, project_id),
        details_dir(date, project_id),
        knowledge_base_dir(project_id),
    ]:
        path.mkdir(parents=True, exist_ok=True)
