from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from analysis.memory import (
    append_jsonl,
    build_conflict_records,
    build_daily_summary,
    build_judgment_record,
    decide_current_state_update,
    render_current_state,
)
from analysis.trend_store import (
    append_events_jsonl,
    build_author_daily_rows,
    build_author_index_rows,
    build_brand_or_ip_rows,
    build_content_pattern_index_rows,
    build_demand_rows,
    build_entity_comparison_rows,
    build_entity_rows,
    build_keyword_daily_rows,
    build_pattern_daily_rows,
    build_keyword_index_rows,
    build_title_template_rows,
    build_topic_daily_rows,
    build_topic_index_rows,
    build_trend_events,
    upsert_csv,
    upsert_index_csv,
)
from analysis.wiki_memory import update_wiki_files
from pipeline.common import get_domain
from storage.paths import (
    ensure_dirs,
    judgments_dir,
    memory_daily_dir,
    memory_dir,
    memory_entities_dir,
    memory_patterns_dir,
    memory_trends_dir,
    memory_wiki_dir,
    normalize_date,
    processed_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据当天结构化结果更新分层记忆。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"找不到文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_recent_daily_summaries(domain_id: str, before_date: str, limit: int = 14) -> list[dict[str, Any]]:
    daily_dir = memory_daily_dir(domain_id)
    if not daily_dir.exists():
        return []
    summaries = []
    for path in sorted(daily_dir.glob("*_summary.json")):
        date_part = path.name.replace("_summary.json", "")
        if date_part >= before_date:
            continue
        try:
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return summaries[-limit:]


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        ensure_dirs(date_str, args.domain)
        domain = get_domain(args.domain)
        processed = processed_dir(args.domain)
        metrics = load_json(processed / f"{date_str}_metrics.json", {})
        signals = load_json(processed / f"{date_str}_search_signals.json", {})
        data_quality = load_json(processed / f"{date_str}_data_quality.json", {})
        market_analysis = load_json(processed / f"{date_str}_market_analysis.json", {})

        daily_summary = build_daily_summary(
            domain_id=args.domain,
            date_str=date_str,
            metrics=metrics,
            signals=signals,
            data_quality=data_quality,
            market_analysis=market_analysis,
        )
        daily_path = memory_daily_dir(args.domain) / f"{date_str}_summary.json"
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily_path.write_text(json.dumps(daily_summary, ensure_ascii=False, indent=2), encoding="utf-8")

        current_state_path = memory_dir(args.domain) / "current_state.md"
        previous_text = current_state_path.read_text(encoding="utf-8") if current_state_path.exists() else ""
        recent_summaries = load_recent_daily_summaries(args.domain, before_date=date_str)
        update_decision = decide_current_state_update(
            data_quality=data_quality,
            daily_summary=daily_summary,
            previous_text=previous_text,
            recent_summaries=recent_summaries,
        )
        daily_summary["verification_status"] = update_decision.get("verification_status", "unknown")
        daily_summary["valid_observation_days"] = update_decision.get("valid_observation_days", 0)
        daily_path.write_text(json.dumps(daily_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        should_update = bool(update_decision.get("allowed"))
        if should_update:
            current_state_path.parent.mkdir(parents=True, exist_ok=True)
            current_state_path.write_text(
                render_current_state(domain=domain, daily_summary=daily_summary, previous_text=previous_text),
                encoding="utf-8",
            )
        current_state_text = current_state_path.read_text(encoding="utf-8") if current_state_path.exists() else ""

        judgment = build_judgment_record(
            domain_id=args.domain,
            date_str=date_str,
            daily_summary=daily_summary,
            updated_current_state=should_update,
            update_decision=update_decision,
        )
        append_jsonl(judgments_dir(args.domain) / "judgments.jsonl", judgment)
        conflict_records = build_conflict_records(
            domain_id=args.domain,
            date_str=date_str,
            daily_summary=daily_summary,
            previous_text=previous_text,
            updated_current_state=should_update,
            update_decision=update_decision,
        )
        for record in conflict_records:
            append_jsonl(judgments_dir(args.domain) / "conflict_resolution_queue.jsonl", record)

        trends_dir = memory_trends_dir(args.domain)
        upsert_csv(
            trends_dir / "topic_daily.csv",
            build_topic_daily_rows(daily_summary),
            key_fields=["date", "domain_id", "topic"],
        )
        upsert_csv(
            trends_dir / "author_daily.csv",
            build_author_daily_rows(daily_summary),
            key_fields=["date", "domain_id", "author"],
        )
        upsert_csv(
            trends_dir / "keyword_daily.csv",
            build_keyword_daily_rows(signals, date_str=date_str, domain_id=args.domain),
            key_fields=["date", "domain_id", "keyword"],
        )
        upsert_csv(
            trends_dir / "pattern_daily.csv",
            build_pattern_daily_rows(daily_summary),
            key_fields=["date", "domain_id", "content_pattern"],
        )
        entities_dir = memory_entities_dir(args.domain)
        entity_rows = build_entity_rows(signals, date_str=date_str, domain_id=args.domain)
        upsert_csv(
            entities_dir / "product_candidates.csv",
            entity_rows,
            key_fields=["date", "domain_id", "entity_type", "entity"],
        )
        upsert_index_csv(
            entities_dir / "topics.csv",
            build_topic_index_rows(daily_summary),
            key_fields=["domain_id", "topic"],
        )
        upsert_index_csv(
            entities_dir / "authors.csv",
            build_author_index_rows(daily_summary),
            key_fields=["domain_id", "author"],
        )
        upsert_index_csv(
            entities_dir / "keywords.csv",
            build_keyword_index_rows(signals, date_str=date_str, domain_id=args.domain),
            key_fields=["domain_id", "keyword"],
        )
        upsert_index_csv(
            entities_dir / "brands_or_ips.csv",
            build_brand_or_ip_rows(entity_rows),
            key_fields=["domain_id", "entity_type", "entity"],
        )
        upsert_csv(
            entities_dir / "entity_comparison.csv",
            build_entity_comparison_rows(entity_rows),
            key_fields=["date", "domain_id", "entity_type", "entity"],
        )
        patterns_dir = memory_patterns_dir(args.domain)
        upsert_index_csv(
            patterns_dir / "content_patterns.csv",
            build_content_pattern_index_rows(daily_summary),
            key_fields=["domain_id", "content_pattern"],
        )
        upsert_csv(
            patterns_dir / "title_templates.csv",
            build_title_template_rows(signals, date_str=date_str, domain_id=args.domain),
            key_fields=["date", "domain_id", "template_candidate"],
        )
        upsert_csv(
            patterns_dir / "demand_signals.csv",
            build_demand_rows(signals, date_str=date_str, domain_id=args.domain),
            key_fields=["date", "domain_id", "demand_type"],
        )
        trend_events = build_trend_events(daily_summary, update_decision=update_decision)
        append_events_jsonl(trends_dir / "trend_events.jsonl", trend_events)

        wiki_paths = update_wiki_files(
            wiki_dir=memory_wiki_dir(args.domain),
            domain=domain,
            daily_summary=daily_summary,
            current_state_text=current_state_text,
            event="memory_update" if should_update else "memory_observation_only",
            details=f"reason={update_decision.get('reason', 'unknown')}; updated_current_state={should_update}",
        )
    except Exception as exc:
        print(f"记忆更新失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存每日记忆摘要：{daily_path}")
    if should_update:
        print(f"已更新 current_state：{current_state_path}")
    else:
        print(f"本日仅作为观察记录：{update_decision.get('reason', 'unknown')}")
    print(f"已记录判断日志：{judgments_dir(args.domain) / 'judgments.jsonl'}")
    if conflict_records:
        print(f"已写入待观察冲突：{len(conflict_records)} 条")
    print(f"已更新长期趋势表：{memory_trends_dir(args.domain)}")
    print(f"已刷新 wiki 索引：{wiki_paths['index']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
