from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Note:
    note_global_id: str
    domain_id: str
    note_id: str = ""
    link: str = ""
    title: str = ""
    author: str = ""
    author_id: str = ""
    first_seen_date: str = ""
    last_seen_date: str = ""


@dataclass(frozen=True)
class Observation:
    observation_id: str
    run_id: str
    date: str
    domain_id: str
    keyword: str
    rank: int | None
    note_global_id: str
    note_id: str = ""
    link: str = ""
    title: str = ""
    author: str = ""
    author_id: str = ""
    like_count: int | None = None
    collect_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    publish_date: str = ""
    crawl_time: str = ""
    source: str = "search_page"
    source_file: str = ""
    model_type: str = ""
    note_type: str = ""
    is_video: bool = False


@dataclass(frozen=True)
class Annotation:
    annotation_id: str
    date: str
    domain_id: str
    note_global_id: str
    annotation_type: str
    value: str
    source: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)


def normalize_observation(payload: dict[str, Any]) -> dict[str, Any]:
    note_global_id = _text(payload.get("note_global_id"))
    record = Observation(
        observation_id=_text(payload.get("observation_id")),
        run_id=_text(payload.get("run_id")),
        date=_text(payload.get("date")),
        domain_id=_text(payload.get("domain_id")),
        keyword=_text(payload.get("keyword")),
        rank=_int_or_none(payload.get("rank")),
        note_global_id=note_global_id,
        note_id=_text(payload.get("note_id")),
        link=_text(payload.get("link")),
        title=_text(payload.get("title")),
        author=_text(payload.get("author")),
        author_id=_text(payload.get("author_id")),
        like_count=_int_or_none(payload.get("like_count")),
        collect_count=_int_or_none(payload.get("collect_count")),
        comment_count=_int_or_none(payload.get("comment_count")),
        share_count=_int_or_none(payload.get("share_count")),
        publish_date=_text(payload.get("publish_date")),
        crawl_time=_text(payload.get("crawl_time")),
        source=_text(payload.get("source")) or "search_page",
        source_file=_text(payload.get("source_file")),
        model_type=_text(payload.get("model_type")),
        note_type=_text(payload.get("note_type")),
        is_video=_bool(payload.get("is_video")),
    )
    out = asdict(record)
    if not out["observation_id"]:
        out["observation_id"] = observation_id(out)
    if not out["run_id"]:
        out["run_id"] = f"{out['date']}_{out['domain_id']}"
    validate_observation(out)
    return out


def note_from_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        raise ValueError("note_from_observations requires at least one observation")
    items = [normalize_observation(item) for item in observations]
    first = items[0]
    dates = sorted({item["date"] for item in items if item["date"]})
    note = Note(
        note_global_id=first["note_global_id"],
        domain_id=first["domain_id"],
        note_id=first["note_id"],
        link=first["link"],
        title=first["title"],
        author=first["author"],
        author_id=first["author_id"],
        first_seen_date=dates[0] if dates else "",
        last_seen_date=dates[-1] if dates else "",
    )
    out = asdict(note)
    validate_note(out)
    return out


def annotation_id(*, date: str, domain_id: str, note_global_id: str, annotation_type: str, value: str, source: str) -> str:
    seed = "\u0001".join([date, domain_id, note_global_id, annotation_type, value, source])
    return f"ann_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def observation_id(payload: dict[str, Any]) -> str:
    seed = "|".join(
        _text(payload.get(key))
        for key in ("date", "domain_id", "keyword", "rank", "note_global_id", "crawl_time")
    )
    return f"obs_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def validate_note(payload: dict[str, Any]) -> None:
    _require(payload, "note_global_id")
    _require(payload, "domain_id")


def validate_observation(payload: dict[str, Any]) -> None:
    for key in ("observation_id", "date", "domain_id", "keyword", "note_global_id", "source"):
        _require(payload, key)


def validate_annotation(payload: dict[str, Any]) -> None:
    for key in ("annotation_id", "date", "domain_id", "note_global_id", "annotation_type", "value", "source"):
        _require(payload, key)


def _require(payload: dict[str, Any], key: str) -> None:
    if not _text(payload.get(key)):
        raise ValueError(f"missing_required_field:{key}")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "视频"}
