from __future__ import annotations

from pathlib import Path

import pandas as pd

from storage.paths import processed_dir


DERIVED_CLEAN_VARIANTS = ("corrected", "image_enriched")


def clean_base_path(date_str: str, domain_id: str, *, suffix: str = "xlsx") -> Path:
    return processed_dir(domain_id) / f"{date_str}_clean_notes.{suffix}"


def clean_derived_path(date_str: str, domain_id: str, variant: str, *, suffix: str = "xlsx") -> Path:
    return processed_dir(domain_id) / f"{date_str}_clean_notes_{variant}.{suffix}"


def resolve_clean_path(date_str: str, domain_id: str, *, prefer_derived: bool = True) -> Path:
    if prefer_derived:
        candidates = [
            clean_derived_path(date_str, domain_id, variant)
            for variant in DERIVED_CLEAN_VARIANTS
            if clean_derived_path(date_str, domain_id, variant).exists()
        ]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    path = clean_base_path(date_str, domain_id)
    if not path.exists():
        raise FileNotFoundError(f"找不到清洗结果：{path}")
    return path


def load_clean_dataframe(date_str: str, domain_id: str, *, prefer_derived: bool = True) -> pd.DataFrame:
    return pd.read_excel(resolve_clean_path(date_str, domain_id, prefer_derived=prefer_derived))


def write_clean_variant(df: pd.DataFrame, date_str: str, domain_id: str, variant: str) -> tuple[Path, Path]:
    xlsx_path = clean_derived_path(date_str, domain_id, variant, suffix="xlsx")
    csv_path = clean_derived_path(date_str, domain_id, variant, suffix="csv")
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(xlsx_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return xlsx_path, csv_path


def remove_clean_variants(date_str: str, domain_id: str) -> None:
    for variant in DERIVED_CLEAN_VARIANTS:
        for suffix in ("xlsx", "csv"):
            path = clean_derived_path(date_str, domain_id, variant, suffix=suffix)
            if path.exists():
                path.unlink()
