from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from datetime import datetime

import pandas as pd

from analysis.dedupe import build_hard_duplicate_key, hard_dedupe
from analysis.data_quality import evaluate_quality
from analysis.detail_sampling import (
    build_manual_detail_template,
    merge_manual_detail_supplements,
    select_detail_sample_targets,
)
from analysis.evidence import (
    build_evidence_id,
    build_note_global_id,
    generate_evidence_map_records,
    generate_evidence_records,
    upsert_jsonl_by_key,
)
from analysis.entity_miner import mine_demand_signals, mine_entity_candidates
from analysis.llm_context_builder import build_llm_input
from analysis.manual_corrections import apply_manual_corrections
from analysis.market_report import deterministic_market_analysis, render_market_report
from analysis.memory import (
    build_conflict_records,
    build_daily_summary,
    decide_current_state_update,
    days_since_last_valid_observation,
    memory_update_allowed,
    render_current_state,
)
from analysis.metrics import compute_basic_metrics, parse_count, recent_publish_mask, tokenize_chinese_text
from analysis.rule_loader import load_content_pattern_rules
from analysis.rollup import build_rollup, month_key, render_rollup_summary, week_key
from analysis.rule_candidates import build_rule_candidates, render_rule_candidates
from analysis.rule_effectiveness import evaluate_rule_effectiveness
from analysis.report_validator import validate_market_analysis
from analysis.run_guard import (
    already_completed_today,
    circuit_breaker_active,
    record_run_failure,
    record_run_success,
    should_skip_run,
)
from analysis.search_page_signals import add_content_patterns, compute_search_page_signals
from analysis.topic_cluster import assign_rule_topics
from analysis.trend_store import (
    append_events_jsonl,
    build_content_pattern_index_rows,
    build_demand_rows,
    build_entity_comparison_rows,
    build_entity_rows,
    build_keyword_daily_rows,
    build_pattern_daily_rows,
    build_title_template_rows,
    build_topic_index_rows,
    build_topic_daily_rows,
    build_trend_events,
    upsert_csv,
    upsert_index_csv,
)
from analysis.wiki_memory import update_wiki_files
from pipeline.update_rollups import build_and_write_period
from collector.search_page_collector import extract_notes_from_initial_state, normalize_publish_date
from pipeline.clean_notes import clean_dataframe
from pipeline.generate_report import md_list
from pipeline.install_windows_task import build_schtasks_command, build_task_run_command
from pipeline.merge_history_clean import date_range
from pipeline.run_scheduled import is_due


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


class EvidenceTests(unittest.TestCase):
    def test_note_global_id_prefers_note_id(self) -> None:
        row = {"note_id": "abc", "link": "https://example.com/1", "title": "标题", "author": "作者"}
        same = {"note_id": "abc", "link": "https://example.com/2", "title": "另一个标题", "author": "作者"}
        self.assertEqual(build_note_global_id(row), build_note_global_id(same))

    def test_evidence_id_is_same_for_same_day_and_note(self) -> None:
        note_global_id = "ng_note_x"
        first = build_evidence_id(date_str="2026-06-22", domain_id="camping", source="search", note_global_id=note_global_id)
        second = build_evidence_id(date_str="2026-06-22", domain_id="camping", source="search", note_global_id=note_global_id)
        next_day = build_evidence_id(date_str="2026-06-23", domain_id="camping", source="search", note_global_id=note_global_id)
        self.assertEqual(first, second)
        self.assertNotEqual(first, next_day)

    def test_generate_evidence_dedupes_same_note_in_one_day(self) -> None:
        df = pd.DataFrame(
            [
                {"note_id": "a", "title": "露营清单", "author": "作者", "keyword": "露营", "like_count_num": 10},
                {"note_id": "a", "title": "露营清单", "author": "作者", "keyword": "装备", "like_count_num": 10},
            ]
        )
        records = generate_evidence_records(df, date_str="2026-06-22", domain_id="camping")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["note_id"], "a")
        self.assertEqual(records[0]["like_count_num"], 10)

    def test_evidence_map_upserts_by_evidence_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence_map.jsonl"
            first = {"evidence_id": "ev_1", "title": "旧标题"}
            second = {"evidence_id": "ev_1", "title": "新标题"}
            extra = {"evidence_id": "ev_2", "title": "另一条"}
            upsert_jsonl_by_key(path, [first], key="evidence_id")
            upsert_jsonl_by_key(path, [second, extra], key="evidence_id")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("新标题", lines[0])

    def test_generate_evidence_map_records_are_compact(self) -> None:
        records = [
            {
                "evidence_id": "ev_1",
                "note_global_id": "ng_1",
                "date": "2026-06-22",
                "domain_id": "camping",
                "source": "search",
                "title": "露营清单",
                "like_count_num": 100,
            }
        ]
        mapped = generate_evidence_map_records(records)
        self.assertEqual(mapped[0]["evidence_id"], "ev_1")
        self.assertNotIn("like_count_num", mapped[0])


class SearchSignalTests(unittest.TestCase):
    def test_content_pattern_does_not_overwrite_topic(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "新手露营装备清单", "topic_name": "露营装备", "like_count_num": 100},
                {"title": "露营灯避坑实测", "topic_name": "露营灯", "like_count_num": 200},
            ]
        )
        with_patterns = add_content_patterns(df)
        self.assertEqual(with_patterns["topic_name"].tolist(), ["露营装备", "露营灯"])
        self.assertEqual(with_patterns["content_pattern"].tolist(), ["清单", "测评"])
        signals = compute_search_page_signals(with_patterns, date_str="2026-06-22", domain_id="camping")
        self.assertEqual({item["topic"] for item in signals["topics"]}, {"露营装备", "露营灯"})
        self.assertIn("content_pattern", signals["content_patterns"][0])
        self.assertIn("signal_strength", signals["topics"][0])
        self.assertIn("confidence", signals["content_patterns"][0])

    def test_content_pattern_rules_can_load_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.yaml"
            path.write_text("content_patterns:\n  种草:\n    keywords:\n      - 种草\n", encoding="utf-8")
            rules = load_content_pattern_rules(path)
        df = pd.DataFrame([{"title": "小众博主种草合集"}])
        out = add_content_patterns(df, rules)
        self.assertEqual(out.loc[0, "content_pattern"], "种草")

    def test_existing_content_pattern_is_preserved(self) -> None:
        df = pd.DataFrame([{"title": "露营灯实测", "content_pattern": "人工打法"}])
        out = add_content_patterns(df)
        self.assertEqual(out.loc[0, "content_pattern"], "人工打法")

    def test_entity_and_demand_signals_are_included(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "某IP周边亚克力立牌怎么找工厂打样", "keyword": "IP周边", "like_count_num": 100},
                {"title": "动漫徽章避坑清单", "keyword": "谷圈周边", "like_count_num": 50},
            ]
        )
        signals = compute_search_page_signals(df, date_str="2026-06-22", domain_id="ip")
        self.assertTrue(signals["entity_candidates"])
        self.assertTrue(signals["demand_signals"])
        self.assertIn("entity_candidates", signals)
        self.assertIn("demand_signals", signals)


class EntityMinerTests(unittest.TestCase):
    def test_mine_entity_candidates_uses_rules(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "IP周边亚克力立牌", "keyword": "周边", "like_count_num": 100},
                {"title": "亚克力挂件工厂打样", "keyword": "工厂", "like_count_num": 200},
            ]
        )
        entities = mine_entity_candidates(df, entity_rules={"product": ["亚克力"], "supplier": ["工厂"]})
        names = {item["entity"] for item in entities}
        self.assertIn("亚克力", names)
        self.assertIn("工厂", names)

    def test_mine_demand_signals_detects_questions_and_factory_need(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "周边怎么找工厂打样", "like_count_num": 100},
                {"title": "吧唧多少钱起订", "like_count_num": 50},
            ]
        )
        demands = mine_demand_signals(df)
        demand_types = {item["demand_type"] for item in demands}
        self.assertIn("how_to", demand_types)
        self.assertIn("price_or_factory", demand_types)


class DetailSamplingTests(unittest.TestCase):
    def test_select_detail_targets_prefers_high_like_and_dedupes(self) -> None:
        df = pd.DataFrame(
            [
                {"note_id": "a", "title": "低赞", "like_count_num": 1, "rank": 1, "link": "l1"},
                {"note_id": "b", "title": "高赞", "like_count_num": 100, "rank": 2, "link": "l2"},
                {"note_id": "b", "title": "高赞重复", "like_count_num": 100, "rank": 3, "link": "l2"},
            ]
        )
        targets = select_detail_sample_targets(df, limit=2)
        self.assertEqual([item["note_id"] for item in targets], ["b", "a"])
        self.assertEqual(targets[0]["detail_source"], "not_collected")

    def test_manual_detail_template_and_merge(self) -> None:
        targets = [{"note_id": "a", "link": "l1", "title": "样本A"}]
        template = build_manual_detail_template(targets)
        self.assertEqual(template[0]["manual_detail_summary"], "")
        merged = merge_manual_detail_supplements(
            targets,
            [{"note_id": "a", "manual_detail_summary": "正文摘要", "manual_comment_summary": "评论摘要"}],
        )
        self.assertEqual(merged[0]["status"], "manual_supplemented")
        self.assertEqual(merged[0]["manual_detail_summary"], "正文摘要")


class TopicRuleTests(unittest.TestCase):
    def test_topic_rules_override_term_fallback(self) -> None:
        df = pd.DataFrame([{"title": "小众博主种草合作怎么做", "like_count": "10"}])
        out = assign_rule_topics(df, topic_rules={"博主推广": ["博主", "种草"]})
        self.assertEqual(out.loc[0, "topic_name"], "博主推广")
        self.assertEqual(out.loc[0, "topic_source"], "taxonomy_rule")

    def test_topic_fallback_still_assigns_topic(self) -> None:
        df = pd.DataFrame([{"title": "露营装备清单", "like_count": "10"}])
        out = assign_rule_topics(df, topic_rules={})
        self.assertIn("topic_name", out.columns)
        self.assertIn(out.loc[0, "topic_source"], {"title_term", "fallback"})


class RuleEffectivenessTests(unittest.TestCase):
    def test_rule_effectiveness_reports_coverage_and_candidates(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "AI写作教程", "content_pattern": "教程", "topic_name": "AI 写作", "topic_source": "taxonomy_rule"},
                {"title": "未知玩法合集", "content_pattern": "其他", "topic_name": "其他", "topic_source": "fallback"},
            ]
        )
        result = evaluate_rule_effectiveness(df, date_str="2026-06-22", domain_id="ai")
        self.assertEqual(result["content_pattern"]["covered_rate"], 0.5)
        self.assertEqual(result["topic"]["taxonomy_rule_rate"], 0.5)
        self.assertIn("content_pattern_rules_need_expansion", result["recommendations"])
        self.assertTrue(result["topic"]["candidate_terms_from_other"])


class RuleCandidateTests(unittest.TestCase):
    def test_rule_candidates_are_review_only(self) -> None:
        effectiveness = {
            "date": "2026-06-22",
            "domain_id": "ai",
            "content_pattern": {"candidate_terms_from_other": [{"term": "复盘", "count": 3}]},
            "topic": {"candidate_terms_from_other": [{"term": "AI简历", "count": 2}]},
            "recommendations": ["topic_taxonomy_need_expansion"],
        }
        candidates = build_rule_candidates(effectiveness, min_count=2)
        self.assertEqual(candidates["summary"]["content_pattern_candidate_count"], 1)
        self.assertEqual(candidates["summary"]["topic_candidate_count"], 1)
        self.assertEqual(candidates["topic_candidates"][0]["status"], "needs_review")
        text = render_rule_candidates(candidates)
        self.assertIn("不建议自动合并候选", text)


class DataQualityTests(unittest.TestCase):
    def test_invalid_when_clean_count_too_low(self) -> None:
        raw = pd.DataFrame([{"title": "a"}, {"title": "b"}])
        clean = pd.DataFrame([{"title": "a", "publish_date": "", "like_count_num": None}])
        quality = evaluate_quality(raw, clean, date_str="2026-06-22", domain_id="camping")
        self.assertEqual(quality["quality_level"], "invalid")
        self.assertFalse(quality["report_allowed"])
        self.assertFalse(quality["memory_update_allowed"])

    def test_low_quality_blocks_memory_update(self) -> None:
        raw = pd.DataFrame([{"title": str(i)} for i in range(8)])
        clean = pd.DataFrame(
            [{"title": str(i), "publish_date": "2026-06-22", "like_count_num": i, "collect_count_num": i} for i in range(8)]
        )
        quality = evaluate_quality(raw, clean, date_str="2026-06-22", domain_id="camping")
        self.assertEqual(quality["quality_level"], "low")
        self.assertTrue(quality["report_allowed"])
        self.assertFalse(quality["memory_update_allowed"])


class ManualCorrectionTests(unittest.TestCase):
    def test_manual_correction_updates_topic_and_pattern(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "note_id": "a",
                    "title": "小众博主种草合集",
                    "author": "作者A",
                    "topic_name": "其他",
                    "topic_cluster_id": "rule_其他",
                }
            ]
        )
        corrections = [
            {
                "id": "fix_1",
                "match": {"note_id": "a"},
                "set": {
                    "topic_name": "小众博主推广",
                    "topic_cluster_id": "manual_小众博主推广",
                    "content_pattern": "种草",
                },
            }
        ]
        out, applied = apply_manual_corrections(df, corrections)
        self.assertEqual(out.loc[0, "topic_name"], "小众博主推广")
        self.assertEqual(out.loc[0, "content_pattern"], "种草")
        self.assertEqual(applied[0]["correction_id"], "fix_1")

    def test_manual_correction_can_exclude_note(self) -> None:
        df = pd.DataFrame([{"note_id": "a", "title": "无关样本"}, {"note_id": "b", "title": "保留样本"}])
        corrections = [{"id": "drop_a", "match": {"note_id": "a"}, "set": {"exclude_from_analysis": True}}]
        out, applied = apply_manual_corrections(df, corrections)
        self.assertEqual(out["note_id"].tolist(), ["b"])
        self.assertEqual(applied[0]["changed_fields"], ["exclude_from_analysis"])


class MarketReportTests(unittest.TestCase):
    def test_deterministic_market_report_includes_scope_and_evidence_id(self) -> None:
        payload = {
            "meta": {"domain_id": "camping", "domain_name": "露营", "date": "2026-06-22"},
            "data_quality": {"quality_level": "high", "warnings": []},
            "metrics_summary": {"clean_count": 12, "recent_publish_ratio": 0.5, "high_like_rate": 0.25},
            "signals": {
                "topics": [{"topic": "露营装备", "note_count": 4, "note_share": 0.33, "avg_likes": 100}],
                "content_patterns": [{"content_pattern": "清单", "note_count": 3, "note_share": 0.25, "avg_likes": 120}],
                "top_authors": [{"name": "作者A", "count": 2}],
            },
            "representative_evidence": [
                {
                    "evidence_id": "ev_20260622_camping_search_abc",
                    "title": "新手露营装备清单",
                    "topic_name": "露营装备",
                    "like_count_num": 100,
                    "collect_count_num": 20,
                    "comment_count_num": 5,
                }
            ],
        }
        analysis = deterministic_market_analysis(payload)
        report = render_market_report(payload, analysis)
        self.assertIn("不推断全市场规模", report)
        self.assertIn("ev_20260622_camping_search_abc", report)

    def test_llm_input_builder_returns_compressed_keys_when_files_missing(self) -> None:
        payload = build_llm_input(domain_id="__missing_test_domain__", date_str="2026-06-22", domain={"name": "测试"})
        self.assertIn("metrics_summary", payload)
        self.assertIn("signals", payload)
        self.assertIn("representative_evidence", payload)
        self.assertNotIn("raw_notes", payload)
        self.assertNotIn("clean_notes", payload)

    def test_market_analysis_validation_filters_bad_evidence_ids(self) -> None:
        llm_input = {
            "representative_evidence": [
                {"evidence_id": "ev_20260622_camping_search_abc123", "title": "样本A"}
            ]
        }
        analysis = {
            "situation_summary": [
                {
                    "summary": "当前搜索页样本显示主题集中，不代表全市场。",
                    "evidence_ids": ["ev_20260622_camping_search_abc123", "ev_fake"],
                }
            ],
            "evidence_cases": [{"title": "伪造证据", "evidence_id": "ev_fake"}],
        }
        cleaned, validation = validate_market_analysis(analysis, llm_input)
        self.assertFalse(validation["valid"])
        self.assertEqual(cleaned["situation_summary"][0]["evidence_ids"], ["ev_20260622_camping_search_abc123"])
        self.assertEqual(cleaned["evidence_cases"][0]["evidence_id"], "")
        self.assertTrue(any(issue["type"] == "forbidden_claim" for issue in validation["issues"]))


class MemoryTests(unittest.TestCase):
    def test_low_quality_memory_update_is_blocked(self) -> None:
        self.assertFalse(memory_update_allowed({"quality_level": "low", "memory_update_allowed": False}))
        self.assertFalse(memory_update_allowed({"quality_level": "invalid", "memory_update_allowed": False}))

    def test_daily_summary_and_current_state_keep_evidence(self) -> None:
        metrics = {"clean_count": 12, "raw_count": 15, "high_like_rate": 0.2}
        signals = {
            "topics": [{"topic": "露营装备", "note_count": 5, "note_share": 0.4, "avg_likes": 120}],
            "content_patterns": [{"content_pattern": "清单", "note_count": 4, "note_share": 0.3, "avg_likes": 110}],
            "top_authors": [{"name": "作者A", "count": 2}],
        }
        quality = {"quality_level": "high", "memory_update_allowed": True}
        market_analysis = {
            "situation_summary": [{"summary": "搜索页样本中露营装备较集中。"}],
            "evidence_cases": [
                {
                    "title": "新手露营装备清单",
                    "why_it_matters": "代表高互动清单型样本。",
                    "evidence_id": "ev_20260622_camping_search_abc",
                }
            ],
        }
        summary = build_daily_summary(
            domain_id="camping",
            date_str="2026-06-22",
            metrics=metrics,
            signals=signals,
            data_quality=quality,
            market_analysis=market_analysis,
        )
        state = render_current_state(domain={"id": "camping", "name": "露营"}, daily_summary=summary)
        self.assertTrue(summary["data_quality"]["memory_update_allowed"])
        self.assertIn("露营装备", state)
        self.assertIn("ev_20260622_camping_search_abc", state)

    def test_conflict_queue_records_low_quality_observation(self) -> None:
        summary = {
            "date": "2026-06-22",
            "domain_id": "camping",
            "data_quality": {"quality_level": "low"},
            "top_topics": [{"topic": "露营装备"}],
        }
        records = build_conflict_records(
            domain_id="camping",
            date_str="2026-06-22",
            daily_summary=summary,
            previous_text="",
            updated_current_state=False,
        )
        self.assertEqual(records[0]["type"], "quality_blocked_memory_update")

    def test_cooling_topic_requires_three_valid_absent_days_before_update(self) -> None:
        previous_text = "# 测试 current_state\n\n## 主要主题\n\n- 露营装备: 样本数 8，占比 0.4，平均点赞 100\n"
        quality = {"quality_level": "high", "memory_update_allowed": True}
        current = {
            "date": "2026-06-24",
            "data_quality": {"quality_level": "high", "memory_update_allowed": True},
            "top_topics": [{"topic": "露营灯"}],
        }
        one_day_decision = decide_current_state_update(
            data_quality=quality,
            daily_summary=current,
            previous_text=previous_text,
            recent_summaries=[],
        )
        self.assertFalse(one_day_decision["allowed"])
        self.assertEqual(one_day_decision["pending_disappeared_topics"], ["露营装备"])

        recent = [
            {
                "date": "2026-06-22",
                "data_quality": {"quality_level": "high", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营灯"}],
            },
            {
                "date": "2026-06-23",
                "data_quality": {"quality_level": "medium", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营桌"}],
            },
        ]
        third_day_decision = decide_current_state_update(
            data_quality=quality,
            daily_summary=current,
            previous_text=previous_text,
            recent_summaries=recent,
        )
        self.assertTrue(third_day_decision["allowed"])
        self.assertEqual(third_day_decision["confirmed_disappeared_topics"], ["露营装备"])

    def test_first_three_valid_observation_days_need_verification(self) -> None:
        quality = {"quality_level": "high", "memory_update_allowed": True}
        current = {
            "date": "2026-06-24",
            "data_quality": {"quality_level": "high", "memory_update_allowed": True},
            "top_topics": [{"topic": "露营装备"}],
        }
        first_day = decide_current_state_update(
            data_quality=quality,
            daily_summary=current,
            previous_text="",
            recent_summaries=[],
        )
        self.assertTrue(first_day["allowed"])
        self.assertEqual(first_day["verification_status"], "needs_verification")

        recent = [
            {
                "date": "2026-06-22",
                "data_quality": {"quality_level": "high", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营装备"}],
            },
            {
                "date": "2026-06-23",
                "data_quality": {"quality_level": "medium", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营装备"}],
            },
        ]
        third_day = decide_current_state_update(
            data_quality=quality,
            daily_summary=current,
            previous_text="",
            recent_summaries=recent,
        )
        self.assertEqual(third_day["verification_status"], "observed")
        self.assertEqual(third_day["valid_observation_days"], 3)

    def test_reactivated_after_thirty_days_without_valid_observation(self) -> None:
        recent = [
            {
                "date": "2026-05-01",
                "data_quality": {"quality_level": "high", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营装备"}],
            }
        ]
        self.assertEqual(days_since_last_valid_observation("2026-06-24", recent), 54)
        decision = decide_current_state_update(
            data_quality={"quality_level": "high", "memory_update_allowed": True},
            daily_summary={
                "date": "2026-06-24",
                "data_quality": {"quality_level": "high", "memory_update_allowed": True},
                "top_topics": [{"topic": "露营装备"}],
            },
            previous_text="",
            recent_summaries=recent,
        )
        self.assertEqual(decision["verification_status"], "reactivated")
        self.assertEqual(decision["inactive_days"], 54)

    def test_wiki_files_are_generated_from_daily_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wiki_dir = Path(tmp) / "wiki"
            summary = {
                "date": "2026-06-24",
                "domain_id": "camping",
                "verification_status": "observed",
                "valid_observation_days": 3,
                "data_quality": {"quality_level": "high"},
                "metrics_summary": {"clean_count": 12},
                "top_topics": [{"topic": "露营装备", "note_count": 5, "note_share": 0.4, "signal_strength": "medium"}],
                "top_content_patterns": [{"content_pattern": "清单", "note_count": 4, "note_share": 0.3}],
                "evidence_cases": [{"evidence_id": "ev_1", "title": "露营清单", "why_it_matters": "代表样本"}],
            }
            paths = update_wiki_files(
                wiki_dir=wiki_dir,
                domain={"id": "camping", "name": "露营"},
                daily_summary=summary,
                current_state_text="# current",
            )
            self.assertTrue(paths["index"].exists())
            self.assertTrue(paths["schema"].exists())
            self.assertTrue(paths["domain_overview"].exists())
            self.assertTrue(paths["log"].exists())
            overview = paths["domain_overview"].read_text(encoding="utf-8")
            self.assertIn("露营装备", overview)
            self.assertIn("ev_1", overview)


class RollupTests(unittest.TestCase):
    def test_week_and_month_keys(self) -> None:
        self.assertEqual(week_key("2026-06-24"), "2026-W26")
        self.assertEqual(month_key("2026-06-24"), "2026-06")

    def test_build_rollup_summarizes_daily_memory(self) -> None:
        summaries = [
            {
                "date": "2026-06-22",
                "domain_id": "camping",
                "data_quality": {"quality_level": "high"},
                "metrics_summary": {"clean_count": 10, "high_like_rate": 0.2},
                "top_topics": [{"topic": "露营装备", "note_count": 4}],
                "top_content_patterns": [{"content_pattern": "清单", "note_count": 3}],
                "top_authors": [{"name": "作者A", "count": 2}],
                "evidence_cases": [{"evidence_id": "ev_1"}],
            },
            {
                "date": "2026-06-23",
                "domain_id": "camping",
                "data_quality": {"quality_level": "medium"},
                "metrics_summary": {"clean_count": 20, "high_like_rate": 0.1},
                "top_topics": [{"topic": "露营装备", "note_count": 5}, {"topic": "露营灯", "note_count": 2}],
                "top_content_patterns": [{"content_pattern": "测评", "note_count": 4}],
                "top_authors": [{"name": "作者B", "count": 1}],
                "evidence_cases": [{"evidence_id": "ev_2"}],
            },
        ]
        rollup = build_rollup(
            summaries,
            domain_id="camping",
            period_type="weekly",
            period_key="2026-W26",
            start_date="2026-06-22",
            end_date="2026-06-28",
        )
        self.assertEqual(rollup["days_observed"], 2)
        self.assertEqual(rollup["total_clean_count"], 30)
        self.assertEqual(rollup["top_topics"][0]["topic"], "露营装备")
        text = render_rollup_summary(rollup)
        self.assertIn("weekly rollup", text)
        self.assertIn("ev_1", text)

    def test_rollup_skips_when_valid_days_below_threshold(self) -> None:
        summaries = [{"date": "2026-06-24", "domain_id": "camping", "metrics_summary": {"clean_count": 10}}]
        result = build_and_write_period(
            summaries=summaries,
            domain_id="camping",
            date_str="2026-06-24",
            period_type="weekly",
            min_days=3,
        )
        self.assertIsInstance(result, str)
        self.assertIn("低于阈值", result)


class TrendStoreTests(unittest.TestCase):
    def test_daily_rows_keep_topic_and_pattern_separate(self) -> None:
        summary = {
            "date": "2026-06-24",
            "domain_id": "ip",
            "data_quality": {"quality_level": "high"},
            "top_topics": [{"topic": "亚克力周边", "note_count": 4, "note_share": 0.4, "avg_likes": 100}],
            "top_content_patterns": [{"content_pattern": "测评", "note_count": 3, "note_share": 0.3, "avg_likes": 80}],
        }
        topic_rows = build_topic_daily_rows(summary)
        pattern_rows = build_pattern_daily_rows(summary)
        self.assertEqual(topic_rows[0]["topic"], "亚克力周边")
        self.assertNotIn("content_pattern", topic_rows[0])
        self.assertEqual(pattern_rows[0]["content_pattern"], "测评")
        self.assertNotIn("topic", pattern_rows[0])

    def test_entity_and_demand_rows_are_built_from_signals(self) -> None:
        signals = {
            "entity_candidates": [
                {"entity": "亚克力", "entity_type": "product", "sample_count": 2, "note_share": 0.2}
            ],
            "demand_signals": [{"demand_type": "price_or_factory", "sample_count": 3, "note_share": 0.3}],
        }
        entity_rows = build_entity_rows(signals, date_str="2026-06-24", domain_id="ip")
        demand_rows = build_demand_rows(signals, date_str="2026-06-24", domain_id="ip")
        self.assertEqual(entity_rows[0]["entity"], "亚克力")
        self.assertEqual(demand_rows[0]["demand_type"], "price_or_factory")

    def test_keyword_and_title_template_rows_are_built_from_signals(self) -> None:
        signals = {
            "top_keywords": [{"name": "IP周边", "count": 4}],
            "top_title_terms": [{"name": "工厂打样", "count": 3}],
        }
        keyword_rows = build_keyword_daily_rows(signals, date_str="2026-06-24", domain_id="ip")
        title_rows = build_title_template_rows(signals, date_str="2026-06-24", domain_id="ip")
        self.assertEqual(keyword_rows[0]["keyword"], "IP周边")
        self.assertEqual(title_rows[0]["template_candidate"], "工厂打样")
        self.assertEqual(title_rows[0]["status"], "needs_review")

    def test_content_pattern_index_and_entity_comparison_rows(self) -> None:
        summary = {
            "date": "2026-06-24",
            "domain_id": "ip",
            "top_content_patterns": [{"content_pattern": "避坑", "note_count": 4, "signal_score": 0.5}],
        }
        pattern_index = build_content_pattern_index_rows(summary)
        self.assertEqual(pattern_index[0]["content_pattern"], "避坑")
        comparison = build_entity_comparison_rows(
            [
                {"date": "2026-06-24", "domain_id": "ip", "entity_type": "product", "entity": "亚克力", "sample_count": 5},
                {"date": "2026-06-24", "domain_id": "ip", "entity_type": "product", "entity": "徽章", "sample_count": 2},
            ]
        )
        self.assertEqual(comparison[0]["entity"], "亚克力")
        self.assertEqual(comparison[0]["rank_in_type"], 1)

    def test_trend_events_include_pending_cooling(self) -> None:
        summary = {
            "date": "2026-06-24",
            "domain_id": "camping",
            "verification_status": "needs_verification",
            "top_topics": [{"topic": "露营灯", "note_count": 3}],
            "top_content_patterns": [{"content_pattern": "清单", "note_count": 2}],
            "top_authors": [{"name": "作者A", "count": 2}],
        }
        events = build_trend_events(summary, update_decision={"pending_disappeared_topics": ["露营装备"]})
        event_types = {event["event_type"] for event in events}
        self.assertIn("topic_observed", event_types)
        self.assertIn("pattern_observed", event_types)
        self.assertIn("author_observed", event_types)
        self.assertIn("topic_cooling_pending", event_types)

    def test_upsert_csv_replaces_same_key_and_events_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "topic_daily.csv"
            upsert_csv(
                csv_path,
                [{"date": "2026-06-24", "domain_id": "camping", "topic": "露营灯", "note_count": 1}],
                key_fields=["date", "domain_id", "topic"],
            )
            upsert_csv(
                csv_path,
                [{"date": "2026-06-24", "domain_id": "camping", "topic": "露营灯", "note_count": 3}],
                key_fields=["date", "domain_id", "topic"],
            )
            df = pd.read_csv(csv_path)
            self.assertEqual(len(df), 1)
            self.assertEqual(int(df.loc[0, "note_count"]), 3)

            events_path = Path(tmp) / "trend_events.jsonl"
            event = {
                "event_id": "2026-06-24_camping_topic_observed_露营灯",
                "date": "2026-06-24",
                "domain_id": "camping",
                "event_type": "topic_observed",
            }
            append_events_jsonl(events_path, [event])
            append_events_jsonl(events_path, [event])
            self.assertEqual(len(events_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_upsert_index_preserves_first_seen_and_updates_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.csv"
            first = {"domain_id": "camping", "topic": "露营灯", "first_seen": "2026-06-22", "last_seen": "2026-06-22", "latest_note_count": 2}
            second = {"domain_id": "camping", "topic": "露营灯", "first_seen": "2026-06-24", "last_seen": "2026-06-24", "latest_note_count": 5}
            upsert_index_csv(path, [first], key_fields=["domain_id", "topic"])
            upsert_index_csv(path, [second], key_fields=["domain_id", "topic"])
            df = pd.read_csv(path)
            self.assertEqual(len(df), 1)
            self.assertEqual(str(df.loc[0, "first_seen"]), "2026-06-22")
            self.assertEqual(str(df.loc[0, "last_seen"]), "2026-06-24")
            self.assertEqual(int(df.loc[0, "latest_note_count"]), 5)

    def test_topic_index_rows_use_daily_summary(self) -> None:
        rows = build_topic_index_rows(
            {
                "date": "2026-06-24",
                "domain_id": "camping",
                "top_topics": [{"topic": "露营灯", "note_count": 3, "signal_score": 0.4}],
            }
        )
        self.assertEqual(rows[0]["topic"], "露营灯")
        self.assertEqual(rows[0]["first_seen"], "2026-06-24")


class RunGuardTests(unittest.TestCase):
    def test_should_skip_when_once_per_day_completed(self) -> None:
        state = {"last_success_date": "2026-06-24"}
        skip, reason = should_skip_run(state, date_str="2026-06-24", once_per_day=True)
        self.assertTrue(skip)
        self.assertEqual(reason, "already_completed_today")
        forced_skip, forced_reason = should_skip_run(state, date_str="2026-06-24", once_per_day=True, force=True)
        self.assertFalse(forced_skip)
        self.assertEqual(forced_reason, "force")

    def test_circuit_breaker_blocks_same_day(self) -> None:
        state = {"circuit_breaker_until": "2026-06-24"}
        self.assertTrue(circuit_breaker_active(state, date_str="2026-06-24"))
        skip, reason = should_skip_run(state, date_str="2026-06-24")
        self.assertTrue(skip)
        self.assertEqual(reason, "circuit_breaker_active")

    def test_record_failure_triggers_breaker_and_success_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import analysis.run_guard as run_guard

            old_memory_dir = run_guard.memory_dir
            run_guard.memory_dir = lambda domain_id="manual": Path(tmp) / domain_id / "memory"
            try:
                failed = record_run_failure(
                    "camping",
                    date_str="2026-06-24",
                    error="blocked",
                    failure_threshold=1,
                )
                self.assertEqual(failed["circuit_breaker_until"], "2026-06-24")
                succeeded = record_run_success("camping", date_str="2026-06-24", row_count=12)
                self.assertEqual(succeeded["consecutive_failures"], 0)
                self.assertEqual(succeeded["circuit_breaker_until"], "")
                self.assertTrue(already_completed_today(succeeded, date_str="2026-06-24"))
            finally:
                run_guard.memory_dir = old_memory_dir


class SchedulerTests(unittest.TestCase):
    def test_domain_schedule_due_after_preferred_time(self) -> None:
        now = datetime(2026, 6, 24, 10, 0, 0)
        due, reason = is_due({"schedule": {"schedule_enabled": True, "preferred_time": "09:30"}}, now=now)
        self.assertTrue(due)
        self.assertEqual(reason, "due")
        early, early_reason = is_due({"schedule": {"schedule_enabled": True, "preferred_time": "10:30"}}, now=now)
        self.assertFalse(early)
        self.assertEqual(early_reason, "before_preferred_time")

    def test_windows_task_command_builder(self) -> None:
        run_command = build_task_run_command(
            python_exe=r"C:\Python\python.exe",
            project_root=Path(r"C:\Users\dangis\Desktop\xhs-trend-analysis"),
            domain_id="camping",
            date_value="today",
        )
        self.assertIn("pipeline.run_scheduled", run_command)
        self.assertIn("--domain camping", run_command)
        command = build_schtasks_command(
            task_name="XHSTrendAnalysis",
            time_value="09:30",
            task_run_command=run_command,
            force=True,
        )
        self.assertEqual(command[0], "schtasks")
        self.assertIn("/F", command)


class MergeHistoryCleanTests(unittest.TestCase):
    def test_date_range_is_ascending_and_inclusive(self) -> None:
        self.assertEqual(date_range("2026-06-24", 3), ["2026-06-22", "2026-06-23", "2026-06-24"])


if __name__ == "__main__":
    unittest.main()
