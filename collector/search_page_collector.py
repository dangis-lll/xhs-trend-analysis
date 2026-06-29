from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import pandas as pd
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


XHS_HOME = "https://www.xiaohongshu.com"
DEFAULT_PROFILE_DIR = Path("browser_profile").resolve()
DEFAULT_RISK_CONTROL_KEYWORDS = [
    "验证码",
    "安全验证",
    "访问频繁",
    "操作频繁",
    "请稍后再试",
    "当前环境异常",
    "账号异常",
    "网络环境异常",
    "滑块验证",
    "人机验证",
]
PERSISTED_NOTE_COLUMNS = [
    "crawl_date",
    "crawl_time",
    "domain_id",
    "domain_name",
    "keyword",
    "rank",
    "title",
    "author",
    "publish_date",
    "link",
    "note_id",
    "xsec_token",
    "model_type",
    "note_type",
    "author_id",
    "author_avatar",
    "cover_url",
    "cover_width",
    "cover_height",
    "cover_file_id",
    "like_count",
    "collect_count",
    "comment_count",
    "share_count",
    "interaction_count",
    "is_video",
    "video_duration",
    "data_attrs",
    "visible_text",
    "extract_method",
    "quality_flags",
    "source_file",
]


@dataclass
class NoteItem:
    keyword: str
    crawl_date: str = ""
    crawl_time: str = ""
    domain_id: str = ""
    domain_name: str = ""
    rank: int = 0
    title: str = ""
    author: str = ""
    publish_time: str = ""
    publish_date: str = ""
    link: str = ""
    note_id: str = ""
    xsec_token: str = ""
    model_type: str = ""
    note_type: str = ""
    author_id: str = ""
    author_avatar: str = ""
    cover_url: str = ""
    cover_width: int = 0
    cover_height: int = 0
    cover_file_id: str = ""
    like_count: str = ""
    collect_count: str = ""
    comment_count: str = ""
    share_count: str = ""
    interaction_count: str = ""
    is_video: bool = False
    video_duration: int = 0
    data_attrs: str = ""
    visible_text: str = ""
    extract_method: str = "search_page_card"
    quality_flags: str = ""
    source_file: str = ""


class RiskControlDetected(RuntimeError):
    """Raised when the page looks blocked by login, captcha, or anti-abuse checks."""


def detect_risk_control(text: str, keywords: list[str] | None = None) -> str:
    haystack = normalize_space(text)
    for keyword in keywords or DEFAULT_RISK_CONTROL_KEYWORDS:
        if keyword and keyword in haystack:
            return keyword
    return ""


async def wait_random_timeout(page: Any, min_ms: int, max_ms: int) -> None:
    lower = max(0, int(min_ms))
    upper = max(lower, int(max_ms))
    await page.wait_for_timeout(random.randint(lower, upper))


def note_item_to_row(item: NoteItem) -> dict[str, Any]:
    row = asdict(item)
    row.pop("publish_time", None)
    return row


def build_search_url(keyword: str) -> str:
    return (
        f"{XHS_HOME}/search_result?keyword={quote(keyword)}"
        "&source=web_search_result_notes"
    )


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def note_id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|discovery/item)/([^/?#]+)", url)
    return match.group(1) if match else ""


def pick_publish_time(text: str) -> str:
    patterns = [
        r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?",
        r"\d{1,2}[-/.月]\d{1,2}日?",
        r"\d+\s*(?:秒|分钟|小时|天|周|个月|年)前",
        r"(?:刚刚|昨天|前天)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def normalize_publish_date(raw_time: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    text = normalize_space(raw_time)
    if not text:
        return ""

    full_date = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if full_date:
        year, month, day = map(int, full_date.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    month_day = re.search(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})日?", text)
    if month_day:
        month, day = map(int, month_day.groups())
        year = now.year
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            return ""
        if candidate.date() > now.date():
            candidate = datetime(year - 1, month, day)
        return candidate.strftime("%Y-%m-%d")

    if "刚刚" in text:
        return now.strftime("%Y-%m-%d")
    if "昨天" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    if "前天" in text:
        return (now - timedelta(days=2)).strftime("%Y-%m-%d")

    relative = re.search(r"(\d+)\s*(秒|分钟|小时|天|周|个月|年)前", text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if unit in {"秒", "分钟", "小时"}:
            delta = timedelta(days=0)
        elif unit == "天":
            delta = timedelta(days=amount)
        elif unit == "周":
            delta = timedelta(days=amount * 7)
        elif unit == "个月":
            delta = timedelta(days=amount * 30)
        else:
            delta = timedelta(days=amount * 365)
        return (now - delta).strftime("%Y-%m-%d")

    return ""


def pick_metric(text: str, names: list[str]) -> str:
    for name in names:
        patterns = [
            rf"{name}\s*[:：]?\s*([0-9.]+万?)",
            rf"([0-9.]+万?)\s*{name}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return ""


def note_dedupe_key(item: NoteItem) -> str:
    return item.note_id or item.link or f"{item.title}|{item.author}|{item.visible_text[:80]}"


def merge_note_item(base: NoteItem, incoming: NoteItem) -> NoteItem:
    """Fill missing fields on a stable search item with data from another extractor."""
    for field_name in NoteItem.__dataclass_fields__:
        if field_name in {"rank", "data_attrs", "extract_method", "quality_flags"}:
            continue
        current = getattr(base, field_name)
        candidate = getattr(incoming, field_name)
        if current in {"", 0, False, None} and candidate not in {"", 0, False, None}:
            setattr(base, field_name, candidate)

    if not base.publish_time and incoming.visible_text:
        base.publish_time = pick_publish_time(incoming.visible_text)
        base.publish_date = normalize_publish_date(base.publish_time)
    elif base.publish_time and not base.publish_date:
        base.publish_date = normalize_publish_date(base.publish_time)

    if incoming.rank and (not base.rank or incoming.rank < base.rank):
        base.rank = incoming.rank

    methods = [part for part in [base.extract_method, incoming.extract_method] if part]
    if methods:
        base.extract_method = "+".join(dict.fromkeys(methods))

    attrs = [part for part in [base.data_attrs, incoming.data_attrs] if part]
    if attrs:
        base.data_attrs = "\n".join(dict.fromkeys(attrs))

    if incoming.visible_text and incoming.visible_text not in base.visible_text:
        base.visible_text = normalize_space(" ".join([base.visible_text, incoming.visible_text]))

    return base


def dedupe_notes(items: list[NoteItem]) -> list[NoteItem]:
    by_key: dict[str, NoteItem] = {}
    order: list[str] = []
    for item in items:
        key = note_dedupe_key(item)
        if not key:
            continue
        if key in by_key:
            merge_note_item(by_key[key], item)
            continue
        by_key[key] = item
        order.append(key)
    return [by_key[key] for key in order]


def first_image_url(cover: dict[str, Any]) -> str:
    for key in ["url", "urlDefault", "urlPre"]:
        value = normalize_space(cover.get(key))
        if value:
            return value
    for info in cover.get("infoList") or []:
        if isinstance(info, dict):
            value = normalize_space(info.get("url"))
            if value:
                return value
    return ""


def note_link(note_id: str, xsec_token: str = "") -> str:
    if not note_id:
        return ""
    link = f"{XHS_HOME}/explore/{note_id}"
    if xsec_token:
        link = f"{link}?xsec_token={quote(xsec_token)}&xsec_source=pc_search"
    return link


async def extract_notes_from_initial_state(page: Any, keyword: str) -> list[NoteItem]:
    raw_items = await page.evaluate(
        """
        () => {
          const feeds =
            window.__INITIAL_STATE__?.search?.feeds?.value ??
            window.__INITIAL_STATE__?.search?.feeds?._value ??
            [];
          return Array.isArray(feeds) ? feeds : [];
        }
        """
    )

    items: list[NoteItem] = []
    for index, raw in enumerate(raw_items or []):
        if not isinstance(raw, dict):
            continue
        card = raw.get("noteCard") or {}
        user = card.get("user") or {}
        interact = card.get("interactInfo") or {}
        cover = card.get("cover") or {}
        video = card.get("video") or {}
        capa = video.get("capa") or {} if isinstance(video, dict) else {}

        note_id = normalize_space(raw.get("id"))
        xsec_token = normalize_space(raw.get("xsecToken"))
        title = normalize_space(card.get("displayTitle"))
        author = normalize_space(user.get("nickname") or user.get("nickName"))
        like_count = normalize_space(interact.get("likedCount"))
        collect_count = normalize_space(interact.get("collectedCount"))
        comment_count = normalize_space(interact.get("commentCount"))
        share_count = normalize_space(interact.get("sharedCount"))
        visible_parts = [
            title,
            author,
            f"点赞 {like_count}" if like_count else "",
            f"收藏 {collect_count}" if collect_count else "",
            f"评论 {comment_count}" if comment_count else "",
            f"分享 {share_count}" if share_count else "",
        ]

        items.append(
            NoteItem(
                keyword=keyword,
                rank=int(raw.get("index") if raw.get("index") is not None else index) + 1,
                title=title,
                author=author,
                link=note_link(note_id, xsec_token),
                note_id=note_id,
                xsec_token=xsec_token,
                model_type=normalize_space(raw.get("modelType")),
                note_type=normalize_space(card.get("type")),
                author_id=normalize_space(user.get("userId")),
                author_avatar=normalize_space(user.get("avatar")),
                cover_url=first_image_url(cover),
                cover_width=int(cover.get("width") or 0),
                cover_height=int(cover.get("height") or 0),
                cover_file_id=normalize_space(cover.get("fileId")),
                like_count=like_count,
                collect_count=collect_count,
                comment_count=comment_count,
                share_count=share_count,
                interaction_count=like_count or collect_count or comment_count or share_count,
                is_video=bool(video),
                video_duration=int(capa.get("duration") or 0),
                data_attrs=json.dumps(
                    {
                        "source": "window.__INITIAL_STATE__.search.feeds",
                        "raw_index": raw.get("index"),
                    },
                    ensure_ascii=False,
                ),
                visible_text=normalize_space(" ".join(part for part in visible_parts if part)),
                extract_method="search_initial_state",
            )
        )
    return dedupe_notes(items)


def enrich_items(
    items: list[NoteItem],
    *,
    crawl_date: str = "",
    crawl_time: str = "",
    domain_id: str = "",
    domain_name: str = "",
    source_file: str = "",
) -> list[NoteItem]:
    for item in items:
        item.crawl_date = crawl_date
        item.crawl_time = crawl_time
        item.domain_id = domain_id
        item.domain_name = domain_name
        item.source_file = source_file
        flags: list[str] = []
        if not item.title:
            flags.append("missing_title")
        if not item.link:
            flags.append("missing_link")
        if not item.publish_date:
            flags.append("missing_publish_date")
        if not item.like_count:
            flags.append("missing_like_count")
        item.quality_flags = ",".join(flags)
    return items


async def extract_notes_from_page(page: Any, keyword: str) -> list[NoteItem]:
    initial_state_items = await extract_notes_from_initial_state(page, keyword)
    raw_items = await page.evaluate(
        """
        () => {
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
          const abs = (href) => {
            try { return new URL(href, location.origin).href; } catch { return href || ''; }
          };
          const cardSelectors = [
            'section.note-item',
            '.note-item',
            '[class*="note-item"]',
            '[data-note-id]',
            '[data-id]'
          ];
          const titleSelectors = [
            '.title',
            '[class*="title"]',
            'a[href*="/explore/"] span',
            'a[href*="/discovery/item/"] span'
          ];
          const authorSelectors = [
            '.author .name',
            '.author-wrapper .name',
            '[class*="author"] [class*="name"]',
            '[class*="user"] [class*="name"]',
            '[class*="nickname"]'
          ];
          const timeSelectors = [
            '.time',
            '.date',
            '[class*="time"]',
            '[class*="date"]'
          ];
          const likeSelectors = [
            '.like-wrapper',
            '.like',
            '[class*="like"]',
            '[class*="count"]'
          ];
          const collectSelectors = [
            '[class*="collect"]',
            '[class*="favorite"]',
            '[class*="star"]'
          ];
          const commentSelectors = [
            '[class*="comment"]'
          ];

          const imageUrl = (img) => {
            if (!img) return '';
            const src = img.currentSrc || img.src || img.getAttribute('src') || '';
            const dataSrc = img.getAttribute('data-src') || img.getAttribute('data-original') || '';
            const srcset = img.getAttribute('srcset') || '';
            if (src) return abs(src);
            if (dataSrc) return abs(dataSrc);
            if (srcset) return abs(srcset.split(',')[0].trim().split(' ')[0]);
            return '';
          };
          const getFirstText = (card, selectors, maxLen = 60) => {
            for (const selector of selectors) {
              const node = card.querySelector(selector);
              const text = norm(node && node.innerText);
              if (text && text.length <= maxLen) return text;
              const label = norm(node && (node.getAttribute('aria-label') || node.getAttribute('title')));
              if (label && label.length <= maxLen) return label;
            }
            return '';
          };
          const dataAttrs = (card) => {
            const out = {};
            for (const el of [card, ...Array.from(card.querySelectorAll('*')).slice(0, 40)]) {
              for (const attr of Array.from(el.attributes || [])) {
                if (attr.name.startsWith('data-') && attr.value && attr.value.length <= 300) {
                  out[attr.name] = attr.value;
                }
              }
            }
            return out;
          };

          const anchors = Array.from(document.querySelectorAll(
            'a[href*="/explore/"], a[href*="/discovery/item/"]'
          ));

          const cards = [];
          for (const anchor of anchors) {
            let card = null;
            for (const selector of cardSelectors) {
              card = anchor.closest(selector);
              if (card) break;
            }
            if (!card) {
              let node = anchor.parentElement;
              for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {
                const txt = norm(node.innerText);
                if (txt.length >= 5 && txt.length <= 600) {
                  card = node;
                  break;
                }
              }
            }
            if (card && !cards.includes(card)) cards.push(card);
          }

          return cards.map((card, index) => {
            const linkNode = card.querySelector(
              'a[href*="/explore/"], a[href*="/discovery/item/"]'
            );
            let title = '';
            for (const selector of titleSelectors) {
              const node = card.querySelector(selector);
              const text = norm(node && node.innerText);
              if (text && text.length <= 120) {
                title = text;
                break;
              }
            }
            if (!title && linkNode) title = norm(linkNode.innerText).split(' ')[0] || '';

            let author = '';
            for (const selector of authorSelectors) {
              const node = card.querySelector(selector);
              const text = norm(node && node.innerText);
              if (text && text !== title && text.length <= 60) {
                author = text;
                break;
              }
            }

            const publish_time = getFirstText(card, timeSelectors, 40);
            const cover_url = imageUrl(card.querySelector('img'));
            const like_count = getFirstText(card, likeSelectors, 40);
            const collect_count = getFirstText(card, collectSelectors, 40);
            const comment_count = getFirstText(card, commentSelectors, 40);

            return {
              rank: index + 1,
              title,
              author,
              publish_time,
              link: abs(linkNode && linkNode.getAttribute('href')),
              cover_url,
              like_count,
              collect_count,
              comment_count,
              data_attrs: dataAttrs(card),
              visible_text: norm(card.innerText)
            };
          }).filter((item) => item.link || item.title || item.visible_text);
        }
        """
    )

    items: list[NoteItem] = []
    for raw in raw_items:
        link = normalize_space(raw.get("link"))
        visible_text = normalize_space(raw.get("visible_text"))
        publish_time = normalize_space(raw.get("publish_time")) or pick_publish_time(visible_text)
        publish_date = normalize_publish_date(publish_time)
        like_count = normalize_space(raw.get("like_count")) or pick_metric(visible_text, ["点赞", "赞"])
        collect_count = normalize_space(raw.get("collect_count")) or pick_metric(visible_text, ["收藏"])
        comment_count = normalize_space(raw.get("comment_count")) or pick_metric(visible_text, ["评论"])
        interaction_count = like_count or pick_metric(visible_text, ["互动", "赞过"])
        items.append(
            NoteItem(
                keyword=keyword,
                rank=int(raw.get("rank") or 0),
                title=normalize_space(raw.get("title")),
                author=normalize_space(raw.get("author")),
                publish_time=publish_time,
                publish_date=publish_date,
                link=urljoin(XHS_HOME, link) if link else "",
                note_id=note_id_from_url(link),
                cover_url=normalize_space(raw.get("cover_url")),
                like_count=like_count,
                collect_count=collect_count,
                comment_count=comment_count,
                interaction_count=interaction_count,
                data_attrs=json.dumps(raw.get("data_attrs") or {}, ensure_ascii=False),
                visible_text=visible_text,
                extract_method="search_dom_card",
            )
        )
    return dedupe_notes([*initial_state_items, *items])


async def maybe_accept_manual_login(page: Any, login_timeout: int) -> None:
    print("如果页面要求登录或验证码，请在打开的 Chrome 里手动完成。")
    print(f"程序会等待最多 {login_timeout} 秒，然后继续抓取搜索结果。")
    end = time.time() + login_timeout
    while time.time() < end:
        try:
            url = page.url
            text = await page.locator("body").inner_text(timeout=1000)
            if "登录" not in text[:1000] and "验证码" not in text[:1000]:
                return
            print("仍在等待登录/验证完成...")
        except Exception:
            pass
        await asyncio.sleep(5)


async def assert_not_risk_controlled(page: Any, *, keywords: list[str] | None = None) -> None:
    try:
        text = await page.locator("body").inner_text(timeout=1000)
    except Exception:
        return
    matched = detect_risk_control(text[:3000], keywords)
    if matched:
        raise RiskControlDetected(f"页面出现疑似风控/验证提示：{matched}")


async def collect_keyword(
    keyword: str,
    count: int,
    profile_dir: Path,
    headless: bool,
    login_timeout: int,
    slow_mo: int,
    scroll_wait_min_ms: int = 2500,
    scroll_wait_max_ms: int = 7000,
    scroll_px_min: int = 700,
    scroll_px_max: int = 1800,
    risk_control_keywords: list[str] | None = None,
) -> list[NoteItem]:
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=headless,
                chromium_sandbox=True,
                slow_mo=slow_mo,
                viewport={"width": 1440, "height": 1000},
                locale="zh-CN",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            )
        except Exception:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=headless,
                chromium_sandbox=True,
                slow_mo=slow_mo,
                viewport={"width": 1440, "height": 1000},
                locale="zh-CN",
                args=["--disable-blink-features=AutomationControlled"],
            )

        try:
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(15_000)

            await page.goto(build_search_url(keyword), wait_until="domcontentloaded")
            await maybe_accept_manual_login(page, login_timeout)
            await assert_not_risk_controlled(page, keywords=risk_control_keywords)

            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightTimeoutError:
                pass
            await assert_not_risk_controlled(page, keywords=risk_control_keywords)

            items: list[NoteItem] = []
            last_size = 0
            stale_rounds = 0
            max_rounds = max(12, min(80, count * 3))

            for round_index in range(max_rounds):
                await assert_not_risk_controlled(page, keywords=risk_control_keywords)
                batch = await extract_notes_from_page(page, keyword)
                items = dedupe_notes([*items, *batch])
                print(f"第 {round_index + 1} 轮：已提取 {len(items)}/{count} 条")

                if len(items) >= count:
                    break

                if len(items) == last_size:
                    stale_rounds += 1
                else:
                    stale_rounds = 0
                last_size = len(items)

                if stale_rounds >= 6:
                    print("连续多轮没有新增结果，提前结束。")
                    break

                await page.mouse.wheel(0, random.randint(max(1, scroll_px_min), max(scroll_px_min, scroll_px_max)))
                await wait_random_timeout(page, scroll_wait_min_ms, scroll_wait_max_ms)

            return items[:count]
        finally:
            await context.close()


def save_outputs(items: list[NoteItem], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [note_item_to_row(item) for item in items]
    df = pd.DataFrame(
        rows,
        columns=PERSISTED_NOTE_COLUMNS,
    )
    df.to_excel(output, index=False)
    json_path = output.with_suffix(".json")
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存 Excel：{output}")
    print(f"已保存 JSON 备份：{json_path}")
