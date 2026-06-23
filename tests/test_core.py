from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

import pandas as pd

from analysis.dedupe import build_hard_duplicate_key, hard_dedupe
from analysis.metrics import compute_basic_metrics, parse_count, recent_publish_mask, tokenize_chinese_text
from collector.search_page_collector import extract_notes_from_initial_state, normalize_publish_date
from pipeline.clean_notes import clean_dataframe
from pipeline.generate_report import md_list


class FakeInitialStatePage:
    async def evaluate(self, _script: str):
        return [
            {
                "id": "abc123",
                "xsecToken": "tok",
                "modelType": "note",
                "index": 0,
                "noteCard": {
                    "type": "normal",
                    "displayTitle": "新手露营装备清单",
                    "user": {
                        "userId": "u1",
                        "nickname": "露营研究员",
                        "avatar": "https://example.com/avatar.jpg",
                    },
                    "interactInfo": {
                        "likedCount": "1.2万",
                        "collectedCount": "8000",
                        "commentCount": "321",
                        "sharedCount": "88",
                    },
                    "cover": {
                        "width": 1080,
                        "height": 1440,
                        "urlDefault": "https://example.com/cover.jpg",
                        "fileId": "cover-id",
                    },
                    "video": None,
                },
            }
        ]


class MetricsTests(unittest.TestCase):
    def test_parse_count(self) -> None:
        self.assertEqual(parse_count("1.2万"), 12000)
        self.assertEqual(parse_count("赞 268"), 268)
        self.assertEqual(parse_count("1,234"), 1234)
        self.assertIsNone(parse_count(""))

    def test_tokenize_filters_noise(self) -> None:
        tokens = tokenize_chinese_text("新手露营 5324 04 09 nan 有哪些好用建议")
        self.assertIn("新手露营", tokens)
        self.assertIn("有哪些好用建议", tokens)
        self.assertNotIn("5324", tokens)
        self.assertNotIn("nan", tokens)

    def test_basic_metrics_include_trend_ratios(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "like_count_num": 100,
                    "collect_count_num": 50,
                    "comment_count_num": 10,
                    "share_count_num": 5,
                    "publish_date": "2026-06-22",
                    "is_video": True,
                },
                {
                    "like_count_num": 300,
                    "collect_count_num": 150,
                    "comment_count_num": 30,
                    "share_count_num": 15,
                    "publish_date": "2026-06-20",
                    "is_video": False,
                },
            ]
        )
        metrics = compute_basic_metrics(
            df,
            df,
            date_str="2026-06-22",
            high_like_threshold=200,
            recent_publish_days=7,
        )
        self.assertEqual(metrics["total_likes"], 400)
        self.assertEqual(metrics["collect_like_ratio"], 0.5)
        self.assertEqual(metrics["comment_like_ratio"], 0.1)
        self.assertEqual(metrics["share_like_ratio"], 0.05)
        self.assertEqual(metrics["video_rate"], 0.5)

    def test_recent_publish_mask_handles_missing_dates(self) -> None:
        df = pd.DataFrame({"publish_date": ["2026-06-22", "", None, "not-a-date"]})
        mask = recent_publish_mask(df, "2026-06-22", 7)
        self.assertEqual(mask.tolist(), [True, False, False, False])


class CollectorTests(unittest.TestCase):
    def test_extract_notes_from_initial_state(self) -> None:
        items = asyncio.run(extract_notes_from_initial_state(FakeInitialStatePage(), "露营装备"))
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.note_id, "abc123")
        self.assertEqual(item.xsec_token, "tok")
        self.assertEqual(item.title, "新手露营装备清单")
        self.assertEqual(item.author_id, "u1")
        self.assertEqual(item.like_count, "1.2万")
        self.assertEqual(item.collect_count, "8000")
        self.assertEqual(item.comment_count, "321")
        self.assertEqual(item.share_count, "88")
        self.assertEqual(item.cover_width, 1080)
        self.assertFalse(item.is_video)


class DedupeTests(unittest.TestCase):
    def test_build_hard_duplicate_key_priority(self) -> None:
        key = build_hard_duplicate_key({"note_id": "abc", "link": "https://x/1", "title": "t"})
        self.assertEqual(key, "note:abc")

    def test_hard_dedupe_keeps_highest_like(self) -> None:
        df = pd.DataFrame(
            [
                {"note_id": "a", "title": "低赞", "like_count_num": 1, "rank": 2},
                {"note_id": "a", "title": "高赞", "like_count_num": 100, "rank": 1},
            ]
        )
        out = hard_dedupe(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["title"], "高赞")

    def test_clean_dataframe_normalizes_video_bool_strings(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "note_id": "a",
                    "title": "图文",
                    "like_count": "10",
                    "rank": 1,
                    "is_video": "False",
                },
                {
                    "note_id": "b",
                    "title": "视频",
                    "like_count": "20",
                    "rank": 2,
                    "is_video": "True",
                },
            ]
        )
        out = clean_dataframe(df)
        self.assertEqual(out["is_video"].tolist(), [False, True])


class TimeParseTests(unittest.TestCase):
    def test_normalize_publish_date(self) -> None:
        now = datetime(2026, 6, 22, 10, 0, 0)
        self.assertEqual(normalize_publish_date("2025-12-03", now), "2025-12-03")
        self.assertEqual(normalize_publish_date("6月18日", now), "2026-06-18")
        self.assertEqual(normalize_publish_date("3天前", now), "2026-06-19")
        self.assertEqual(normalize_publish_date("昨天", now), "2026-06-21")


class ReportRenderTests(unittest.TestCase):
    def test_md_list_does_not_split_string_into_characters(self) -> None:
        lines = md_list("本期露营装备领域互动两极分化。")
        self.assertEqual(lines, ["- 本期露营装备领域互动两极分化。"])

    def test_md_list_supports_varied_llm_dict_keys(self) -> None:
        lines = md_list([{"conclusion": "清单类内容需求强", "description": "高频词包含露营清单"}])
        self.assertEqual(lines, ["- 清单类内容需求强：高频词包含露营清单"])


if __name__ == "__main__":
    unittest.main()
