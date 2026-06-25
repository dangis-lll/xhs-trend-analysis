from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.evidence import add_note_global_ids, normalize_value


ALLOWED_SET_FIELDS = {
    "topic_name",
    "topic_cluster_id",
    "content_pattern",
    "manual_note",
    "exclude_from_analysis",
}


def load_corrections(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("enabled", True):
            records.append(record)
    return records


def correction_matches(row: pd.Series, correction: dict[str, Any]) -> bool:
    match = correction.get("match", {}) or {}
    if not match:
        return False

    for key in ["note_global_id", "note_id", "link", "title", "author"]:
        expected = normalize_value(match.get(key))
        if expected and normalize_value(row.get(key)) != expected:
            return False

    title_contains = normalize_value(match.get("title_contains"))
    if title_contains and title_contains not in normalize_value(row.get("title")):
        return False

    keyword = normalize_value(match.get("keyword"))
    if keyword and keyword not in normalize_value(row.get("keyword")):
        return False

    return True


def apply_manual_corrections(df: pd.DataFrame, corrections: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if df.empty or not corrections:
        return df.copy(), []

    out = add_note_global_ids(df)
    applied: list[dict[str, Any]] = []
    if "manual_correction_ids" not in out.columns:
        out["manual_correction_ids"] = ""

    for index, row in out.iterrows():
        applied_ids: list[str] = []
        for correction in corrections:
            if not correction_matches(row, correction):
                continue
            correction_id = normalize_value(correction.get("id")) or f"correction_{len(applied) + 1}"
            set_values = correction.get("set", {}) or {}
            changed_fields = []
            for field, value in set_values.items():
                if field not in ALLOWED_SET_FIELDS:
                    continue
                if field not in out.columns:
                    out[field] = ""
                out.at[index, field] = value
                changed_fields.append(field)
            applied_ids.append(correction_id)
            applied.append(
                {
                    "correction_id": correction_id,
                    "row_index": int(index),
                    "note_global_id": normalize_value(out.at[index, "note_global_id"]),
                    "note_id": normalize_value(out.at[index, "note_id"]),
                    "title": normalize_value(out.at[index, "title"]),
                    "changed_fields": changed_fields,
                }
            )
        if applied_ids:
            existing = normalize_value(out.at[index, "manual_correction_ids"])
            merged = [item for item in existing.split("|") if item] + applied_ids
            out.at[index, "manual_correction_ids"] = "|".join(dict.fromkeys(merged))

    if "exclude_from_analysis" in out.columns:
        mask = out["exclude_from_analysis"].fillna(False).astype(str).str.lower().isin({"1", "true", "yes", "y", "是"})
        out = out[~mask].copy()

    return out.reset_index(drop=True), applied
