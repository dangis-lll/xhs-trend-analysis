from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _fmt_date() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _line_item(name: str, path: str, description: str) -> str:
    return f"- [[{path}|{name}]]：{description}"


def render_wiki_schema() -> str:
    return "\n".join(
        [
            "# Wiki Schema",
            "",
            "这个目录是领域记忆的可浏览层，不是事实源。",
            "",
            "## 约束",
            "",
            "- 事实源以 processed、daily summary、rollup、evidence 为准。",
            "- wiki 页面只做压缩索引和可读摘要。",
            "- 重要判断应能回到 evidence_id 或 daily summary。",
            "- 不把搜索页样本写成全市场销量、成交、投放事实。",
            "",
            "## 页面",
            "",
            "- `index.md`：入口索引。",
            "- `log.md`：按时间追加的维护记录。",
            "- `domain_overview.md`：领域当前概览。",
            "- `schema.md`：本文件。",
            "",
        ]
    )


def render_domain_overview(*, domain: dict[str, Any], daily_summary: dict[str, Any], current_state_text: str = "") -> str:
    domain_id = daily_summary.get("domain_id", domain.get("id", ""))
    metrics = daily_summary.get("metrics_summary", {})
    quality = daily_summary.get("data_quality", {})
    lines = [
        f"# {domain.get('name', domain_id)} Domain Overview",
        "",
        f"- domain_id: `{domain_id}`",
        f"- last_observed: `{daily_summary.get('date', '')}`",
        f"- quality_level: `{quality.get('quality_level', 'unknown')}`",
        f"- verification_status: `{daily_summary.get('verification_status', 'unknown')}`",
        f"- valid_observation_days: `{daily_summary.get('valid_observation_days', 0)}`",
        f"- clean_count: `{metrics.get('clean_count', 0)}`",
        "",
        "## Top Topics",
        "",
    ]
    topics = daily_summary.get("top_topics", []) or []
    for item in topics[:10]:
        lines.append(
            f"- {item.get('topic', '')}: 样本数 {item.get('note_count', 0)}，"
            f"占比 {item.get('note_share', 0)}，信号 {item.get('signal_strength', 'unknown')}"
        )
    if not topics:
        lines.append("- 暂无主题信号。")

    lines.extend(["", "## Content Patterns", ""])
    patterns = daily_summary.get("top_content_patterns", []) or []
    for item in patterns[:10]:
        lines.append(
            f"- {item.get('content_pattern', '')}: 样本数 {item.get('note_count', 0)}，"
            f"占比 {item.get('note_share', 0)}，信号 {item.get('signal_strength', 'unknown')}"
        )
    if not patterns:
        lines.append("- 暂无内容打法信号。")

    lines.extend(["", "## Evidence Cases", ""])
    evidence_cases = daily_summary.get("evidence_cases", []) or []
    for item in evidence_cases[:8]:
        evidence_id = item.get("evidence_id") or item.get("based_on_evidence_id") or ""
        lines.append(f"- `{evidence_id}` {item.get('title', '')}: {item.get('why_it_matters', '')}")
    if not evidence_cases:
        lines.append("- 暂无 evidence case。")

    if current_state_text:
        lines.extend(["", "## Current State Excerpt", "", current_state_text[:1800].strip()])

    return "\n".join(lines).rstrip() + "\n"


def render_index(*, domain: dict[str, Any], daily_summary: dict[str, Any], wiki_dir: Path) -> str:
    domain_id = daily_summary.get("domain_id", domain.get("id", ""))
    date_str = daily_summary.get("date", "")
    pages = [
        _line_item("Domain Overview", "domain_overview.md", "领域当前压缩概览。"),
        _line_item("Schema", "schema.md", "wiki 维护规则和边界。"),
        _line_item("Log", "log.md", "按时间追加的维护记录。"),
        _line_item("Current State", "../current_state.md", "程序压缩后的长期状态。"),
        _line_item("最新日摘要", f"../daily/{date_str}_summary.json", "最近一次结构化日摘要，不是面向用户的日报。"),
    ]
    rollup_pages = sorted(wiki_dir.parent.glob("rollups/*_summary.md"))[-6:]
    for path in reversed(rollup_pages):
        pages.append(_line_item(path.stem, f"../rollups/{path.name}", "周/月 rollup 可读摘要。"))

    return "\n".join(
        [
            f"# {domain.get('name', domain_id)} Wiki Index",
            "",
            f"- domain_id: `{domain_id}`",
            f"- last_updated: `{_fmt_date()}`",
            f"- last_observed: `{date_str}`",
            "",
            "## Pages",
            "",
            *pages,
            "",
        ]
    )


def append_wiki_log(path: Path, *, date_str: str, event: str, details: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"## [{_fmt_date()}] {event} | {date_str}"
    entry = f"{prefix}\n\n{details.strip()}\n\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip() + "\n\n" + entry, encoding="utf-8")
    else:
        path.write_text("# Wiki Log\n\n" + entry, encoding="utf-8")


def update_wiki_files(
    *,
    wiki_dir: Path,
    domain: dict[str, Any],
    daily_summary: dict[str, Any],
    current_state_text: str = "",
    event: str = "memory_update",
    details: str = "",
) -> dict[str, Path]:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    schema_path = wiki_dir / "schema.md"
    overview_path = wiki_dir / "domain_overview.md"
    index_path = wiki_dir / "index.md"
    log_path = wiki_dir / "log.md"

    schema_path.write_text(render_wiki_schema(), encoding="utf-8")
    overview_path.write_text(
        render_domain_overview(domain=domain, daily_summary=daily_summary, current_state_text=current_state_text),
        encoding="utf-8",
    )
    index_path.write_text(render_index(domain=domain, daily_summary=daily_summary, wiki_dir=wiki_dir), encoding="utf-8")
    append_wiki_log(
        log_path,
        date_str=str(daily_summary.get("date", "")),
        event=event,
        details=details or "根据 daily summary/current_state 刷新 wiki 索引。",
    )
    return {
        "schema": schema_path,
        "domain_overview": overview_path,
        "index": index_path,
        "log": log_path,
    }
