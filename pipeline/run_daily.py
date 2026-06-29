from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.run_guard import load_run_state, record_run_failure, record_run_start, record_run_success, should_skip_run
from collector.search_page_collector import PERSISTED_NOTE_COLUMNS, collect_keyword, enrich_items, note_item_to_row
from collector.search_page_collector import RiskControlDetected
from pipeline.common import get_domain
from storage.paths import browser_profile_dir, ensure_dirs, get_project_root, normalize_date, raw_dir


def safe_filename(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", text).strip()
    return cleaned[:60] or "keyword"


def pick_keywords(domain: dict[str, Any], limit: int | None = None) -> list[str]:
    keywords = [str(k).strip() for k in domain.get("seed_keywords", []) if str(k).strip()]
    collection = domain.get("collection", {}) or {}
    keyword_limit = limit or int(collection.get("keywords_per_day") or len(keywords))
    return keywords[:keyword_limit]


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=PERSISTED_NOTE_COLUMNS)


def save_keyword_raw(rows: list[dict[str, Any]], output_base: Path) -> None:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    df = rows_to_frame(rows)
    xlsx_path = output_base.with_suffix(".xlsx")
    json_path = output_base.with_suffix(".json")
    df.to_excel(xlsx_path, index=False)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存关键词原始数据：{xlsx_path}")
    print(f"已保存关键词 JSON：{json_path}")


async def sleep_between_keywords(min_seconds: float, max_seconds: float, *, before_keyword: str = "") -> None:
    lower = max(0.0, float(min_seconds))
    upper = max(lower, float(max_seconds))
    if upper <= 0:
        return
    seconds = random.uniform(lower, upper)
    suffix = f"（下一个关键词：{before_keyword}）" if before_keyword else ""
    print(f"保守采集暂停 {seconds:.1f} 秒{suffix}。")
    await asyncio.sleep(seconds)


async def run_daily(args: argparse.Namespace) -> int:
    domain = get_domain(args.domain, args.config)
    project_id = args.domain
    collection = domain.get("collection", {}) or {}
    date_str = normalize_date(args.date)
    ensure_dirs(date_str, project_id)
    run_type = "scheduled" if args.scheduled else "manual"
    failure_threshold = args.failure_threshold or int(collection.get("circuit_breaker_failure_threshold") or 2)
    skip, reason = should_skip_run(
        load_run_state(project_id),
        date_str=date_str,
        force=args.force,
        once_per_day=args.once_per_day,
    )
    if skip:
        print(f"跳过采集：{reason}。如需强制运行，请添加 --force。")
        return 0
    record_run_start(project_id, date_str=date_str, run_type=run_type)

    keywords = pick_keywords(domain, args.keywords_per_day)
    if not keywords:
        print("配置中没有可采集的关键词。", file=sys.stderr)
        record_run_failure(
            project_id,
            date_str=date_str,
            error="配置中没有可采集的关键词",
            run_type=run_type,
            failure_threshold=failure_threshold,
        )
        return 2

    notes_per_keyword = args.notes_per_keyword or int(collection.get("notes_per_keyword") or 50)
    max_daily_notes = args.max_daily_notes or int(collection.get("max_daily_notes") or 0)
    login_timeout = args.login_timeout or int(collection.get("login_timeout") or 180)
    slow_mo = args.slow_mo if args.slow_mo is not None else int(collection.get("slow_mo") or 0)
    headless = args.headless or bool(collection.get("headless") or False)
    keyword_delay_min = float(collection.get("keyword_delay_min_seconds") or 0)
    keyword_delay_max = float(collection.get("keyword_delay_max_seconds") or keyword_delay_min)
    scroll_wait_min_ms = int(collection.get("scroll_wait_min_ms") or 2500)
    scroll_wait_max_ms = int(collection.get("scroll_wait_max_ms") or 7000)
    scroll_px_min = int(collection.get("scroll_px_min") or 700)
    scroll_px_max = int(collection.get("scroll_px_max") or 1800)
    risk_control_keywords = [
        str(item).strip()
        for item in collection.get("risk_control_keywords", [])
        if str(item).strip()
    ] or None
    profile_dir = (
        (get_project_root() / collection["profile_dir"]).resolve()
        if collection.get("profile_dir")
        else browser_profile_dir(project_id).resolve()
    )

    all_rows: list[dict[str, Any]] = []
    print(f"开始采集领域：{domain.get('name', args.domain)}（{args.domain}）")
    print(f"采集日期：{date_str}；关键词数：{len(keywords)}；每词目标：{notes_per_keyword}")

    consecutive_keyword_failures = 0
    for index, keyword in enumerate(keywords, start=1):
        if index > 1:
            await sleep_between_keywords(keyword_delay_min, keyword_delay_max, before_keyword=keyword)
        remaining = max_daily_notes - len(all_rows) if max_daily_notes else notes_per_keyword
        if max_daily_notes and remaining <= 0:
            print(f"已达到 max_daily_notes={max_daily_notes}，停止继续采集。")
            break
        count = min(notes_per_keyword, remaining) if max_daily_notes else notes_per_keyword
        crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{index}/{len(keywords)}] 搜索关键词：{keyword}，目标 {count} 条")

        try:
            items = await collect_keyword(
                keyword=keyword,
                count=count,
                profile_dir=profile_dir,
                headless=headless,
                login_timeout=login_timeout,
                slow_mo=slow_mo,
                scroll_wait_min_ms=scroll_wait_min_ms,
                scroll_wait_max_ms=scroll_wait_max_ms,
                scroll_px_min=scroll_px_min,
                scroll_px_max=scroll_px_max,
                risk_control_keywords=risk_control_keywords,
            )
            consecutive_keyword_failures = 0
        except RiskControlDetected as exc:
            print(f"疑似触发小红书风控，停止当天采集：{exc}", file=sys.stderr)
            record_run_failure(
                project_id,
                date_str=date_str,
                error=f"疑似触发小红书风控，已停止当天采集：{exc}",
                run_type=run_type,
                failure_threshold=1,
            )
            return 1
        except Exception as exc:
            consecutive_keyword_failures += 1
            print(f"关键词采集失败：{keyword}；错误：{exc}", file=sys.stderr)
            if consecutive_keyword_failures >= failure_threshold:
                record_run_failure(
                    project_id,
                    date_str=date_str,
                    error=f"连续 {consecutive_keyword_failures} 个关键词采集失败；最后错误：{exc}",
                    run_type=run_type,
                    failure_threshold=failure_threshold,
                )
                print("连续失败达到阈值，触发本日熔断。", file=sys.stderr)
                return 1
            continue
        file_stem = f"{date_str}_{args.domain}_{index:02d}_{safe_filename(keyword)}"
        source_file = str((raw_dir(date_str, project_id) / f"{file_stem}.xlsx").resolve())
        enrich_items(
            items,
            crawl_date=date_str,
            crawl_time=crawl_time,
            domain_id=args.domain,
            domain_name=str(domain.get("name") or ""),
            source_file=source_file,
        )
        rows = [note_item_to_row(item) for item in items]
        save_keyword_raw(rows, raw_dir(date_str, project_id) / file_stem)
        all_rows.extend(rows)

    all_df = rows_to_frame(all_rows)
    all_xlsx = raw_dir(date_str, project_id) / "all_raw.xlsx"
    all_json = raw_dir(date_str, project_id) / "all_raw.json"
    all_df.to_excel(all_xlsx, index=False)
    all_json.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已合并当天原始 Excel：{all_xlsx}")
    print(f"已合并当天原始 JSON：{all_json}")
    print(f"完成：共采集 {len(all_rows)} 条。")
    if not all_rows:
        record_run_failure(
            project_id,
            date_str=date_str,
            error="本次采集没有得到任何搜索页样本",
            run_type=run_type,
            failure_threshold=failure_threshold,
        )
        return 1
    record_run_success(project_id, date_str=date_str, row_count=len(all_rows), run_type=run_type)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按领域配置批量采集小红书搜索结果页原始数据。")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--date", default="today", help="采集日期，默认 today")
    parser.add_argument("--config", type=Path, default=None, help="domains.yaml 路径")
    parser.add_argument("--keywords-per-day", type=int, default=None, help="覆盖配置中的 keywords_per_day")
    parser.add_argument("--notes-per-keyword", type=int, default=None, help="覆盖配置中的 notes_per_keyword")
    parser.add_argument("--max-daily-notes", type=int, default=None, help="覆盖配置中的 max_daily_notes")
    parser.add_argument("--login-timeout", type=int, default=None, help="覆盖配置中的 login_timeout")
    parser.add_argument("--slow-mo", type=int, default=None, help="覆盖配置中的 slow_mo")
    parser.add_argument("--headless", action="store_true", help="覆盖配置，使用无头模式")
    parser.add_argument("--once-per-day", action="store_true", help="同一领域同一天已有成功采集时跳过")
    parser.add_argument("--force", action="store_true", help="忽略一天一次限制和本日熔断，强制采集")
    parser.add_argument("--scheduled", action="store_true", help="标记为自动调度运行")
    parser.add_argument("--failure-threshold", type=int, default=None, help="连续关键词失败达到该数量后触发本日熔断")
    return parser.parse_args()


def main() -> int:
    try:
        return asyncio.run(run_daily(parse_args()))
    except KeyboardInterrupt:
        print("用户中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
