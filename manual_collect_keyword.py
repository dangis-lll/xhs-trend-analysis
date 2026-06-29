from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from collector.search_page_collector import (
    collect_keyword,
    enrich_items,
    save_outputs,
)
from storage.paths import ensure_dirs, normalize_date, raw_dir
from storage.paths import browser_profile_dir


def safe_filename(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", text).strip()
    return cleaned[:60] or "keyword"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="手动打开 Chrome 搜索单个小红书关键词，并导出搜索结果页卡片信息。"
    )
    parser.add_argument("keyword", help="要搜索的小红书关键词")
    parser.add_argument("-n", "--count", type=int, default=20, help="要抓取的笔记数量，默认 20")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Excel 输出路径；默认 projects/<project>/raw/YYYY-MM-DD/<关键词>/xhs_<关键词>_<时间戳>.xlsx",
    )
    parser.add_argument(
        "--project",
        default="manual",
        help="保存到哪个项目目录，默认 manual；例如 camping",
    )
    parser.add_argument(
        "--date",
        default="today",
        help="归档日期，默认 today",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="Chrome 登录态目录，默认 projects/<project>/browser_profile",
    )
    parser.add_argument("--headless", action="store_true", help="无头模式运行，不建议首次登录时使用")
    parser.add_argument("--login-timeout", type=int, default=180, help="等待手动登录/验证码的秒数")
    parser.add_argument("--slow-mo", type=int, default=0, help="Playwright 操作延迟毫秒，调试时可设为 100")
    parser.add_argument("--scroll-wait-min-ms", type=int, default=2500, help="每次滚动后的最短等待毫秒数")
    parser.add_argument("--scroll-wait-max-ms", type=int, default=7000, help="每次滚动后的最长等待毫秒数")
    parser.add_argument("--scroll-px-min", type=int, default=700, help="每次滚动的最小像素")
    parser.add_argument("--scroll-px-max", type=int, default=1800, help="每次滚动的最大像素")
    return parser.parse_args()


def resolve_output(args: argparse.Namespace) -> Path:
    if args.output is not None:
        return args.output.resolve()

    date_str = normalize_date(args.date)
    keyword_dir = raw_dir(date_str, args.project) / safe_filename(args.keyword)
    ts = time.strftime("%Y%m%d_%H%M%S")
    return (keyword_dir / f"xhs_{safe_filename(args.keyword)}_{ts}.xlsx").resolve()


async def main_async() -> int:
    args = parse_args()
    if args.count <= 0:
        print("count 必须大于 0", file=sys.stderr)
        return 2

    output = resolve_output(args)
    crawl_date = normalize_date(args.date)
    ensure_dirs(crawl_date, args.project)

    profile_dir = args.profile_dir.resolve() if args.profile_dir else browser_profile_dir(args.project).resolve()
    items = await collect_keyword(
        keyword=args.keyword,
        count=args.count,
        profile_dir=profile_dir,
        headless=args.headless,
        login_timeout=args.login_timeout,
        slow_mo=args.slow_mo,
        scroll_wait_min_ms=args.scroll_wait_min_ms,
        scroll_wait_max_ms=args.scroll_wait_max_ms,
        scroll_px_min=args.scroll_px_min,
        scroll_px_max=args.scroll_px_max,
    )
    enrich_items(
        items,
        crawl_date=crawl_date,
        crawl_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_file=str(output),
    )
    save_outputs(items, output)
    print(f"完成：共导出 {len(items)} 条。")
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("用户中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
