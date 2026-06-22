from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from storage.paths import images_dir


def safe_image_name(row: pd.Series) -> str:
    note_id = str(row.get("note_id", "") or "").strip()
    if note_id:
        return f"{note_id}.jpg"
    link = str(row.get("link", "") or "").strip().replace("/", "_").replace(":", "_")
    return f"{link[:80] or 'image'}.jpg"


def download_cover_images(df: pd.DataFrame, date: str, project_id: str = "manual", timeout: int = 20) -> pd.DataFrame:
    out = df.copy()
    image_root = images_dir(date, project_id)
    image_root.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    flags: list[str] = []
    for _, row in out.iterrows():
        url = str(row.get("cover_url", "") or "").strip()
        current_flags = str(row.get("quality_flags", "") or "")
        if not url or not urlparse(url).scheme:
            paths.append("")
            flags.append(",".join(filter(None, [current_flags, "missing_cover_url"])))
            continue
        path = image_root / safe_image_name(row)
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            path.write_bytes(response.content)
            paths.append(str(path))
            flags.append(current_flags)
        except Exception:
            paths.append("")
            flags.append(",".join(filter(None, [current_flags, "cover_download_failed"])))
    out["cover_image_path"] = paths
    out["quality_flags"] = flags
    return out


def extract_ocr_text(image_path: Path) -> str:
    return ""


def add_image_analysis_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cover_ocr_text" not in out.columns:
        out["cover_ocr_text"] = ""
    if "image_summary" not in out.columns:
        out["image_summary"] = ""
    return out
