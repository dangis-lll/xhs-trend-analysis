from __future__ import annotations

import unittest
from datetime import datetime

import pandas as pd

from analysis.dedupe import build_hard_duplicate_key, hard_dedupe
from analysis.metrics import parse_count, tokenize_chinese_text
from collector.search_page_collector import normalize_publish_date
from pipeline.generate_report import md_list


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
