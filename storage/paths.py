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


def images_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "images" / normalize_date(date)


def snapshots_dir(date: str | None = None, project_id: str = "manual") -> Path:
    return project_dir(project_id) / "snapshots" / normalize_date(date)


def knowledge_base_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "knowledge-base"


def browser_profile_dir(project_id: str = "manual") -> Path:
    return project_dir(project_id) / "browser_profile"


def ensure_dirs(date: str | None = None, project_id: str = "manual") -> None:
    for path in [
        raw_dir(date, project_id),
        processed_dir(project_id),
        report_dir(date, project_id),
        images_dir(date, project_id),
        snapshots_dir(date, project_id),
        knowledge_base_dir(project_id),
    ]:
        path.mkdir(parents=True, exist_ok=True)
