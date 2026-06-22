from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analysis.keyword_miner import compute_three_day_trends
from analysis.llm_analyzer import analyze_with_llm, save_llm_input
from pipeline.common import get_domain
from storage.paths import normalize_date, processed_dir, report_dir


def md_table(rows: list[dict], columns: list[str], headers: list[str]) -> str:
    if not rows:
        return "暂无数据\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        values = [str(row.get(col, "") or "").replace("\n", " ") for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def clean_inline_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(clean_inline_text(item) for item in value if clean_inline_text(item))
    if isinstance(value, dict):
        return "；".join(
            f"{key}：{clean_inline_text(item)}"
            for key, item in value.items()
            if clean_inline_text(item)
        )
    return str(value).replace("\n", " ").strip()


def normalize_llm_items(items) -> list:
    if not items:
        return []
    if isinstance(items, str):
        return [items]
    if isinstance(items, dict):
        # Some models return {"1": "...", "2": "..."} instead of an array.
        if all(not isinstance(value, (dict, list)) for value in items.values()):
            return list(items.values())
        return [items]
    if isinstance(items, list):
        return items
    return [items]


def md_list(items) -> list[str]:
    items = normalize_llm_items(items)
    if not items:
        return ["暂无数据"]
    lines = []
    for item in items:
        if isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("topic")
                or item.get("keyword")
                or item.get("summary")
                or item.get("insight")
                or item.get("conclusion")
                or item.get("case")
                or item.get("name")
            )
            evidence = (
                item.get("evidence")
                or item.get("reason")
                or item.get("analysis")
                or item.get("suggestion")
                or item.get("content")
                or item.get("description")
                or item.get("detail")
                or item.get("recommendation")
                or item.get("data")
            )
            if not title:
                values = [clean_inline_text(value) for value in item.values() if clean_inline_text(value)]
                if len(values) == 1:
                    lines.append(f"- {values[0]}")
                    continue
                title = "结论"
                evidence = "；".join(values)
            title_text = clean_inline_text(title)
            evidence_text = clean_inline_text(evidence)
            lines.append(f"- {title_text}" + (f"：{evidence_text}" if evidence_text and evidence_text != title_text else ""))
        else:
            text = clean_inline_text(item)
            if text:
                lines.append(f"- {text}")
    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于指标和样本生成 Markdown 日报。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_history(domain_id: str) -> pd.DataFrame:
    path = processed_dir(domain_id) / "history_clean_notes.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        domain = get_domain(args.domain)
        metrics_path = processed_dir(args.domain) / f"{date_str}_metrics.json"
        top_notes_path = processed_dir(args.domain) / f"{date_str}_top_notes.xlsx"
        metrics = load_json(metrics_path)
        top_notes_df = pd.read_excel(top_notes_path) if top_notes_path.exists() else pd.DataFrame()
        top_notes = top_notes_df.fillna("").head(10).to_dict(orient="records")
        history_df = load_history(args.domain)
        trends = compute_three_day_trends(history_df, date_str, 20)
        llm_result = analyze_with_llm(metrics, top_notes, metrics.get("top_title_terms", []), trends)

        report_path = report_dir(date_str, args.domain) / f"{date_str}_小红书趋势日报.md"
        llm_input_path = processed_dir(args.domain) / f"{date_str}_llm_input.json"
        save_llm_input(
            llm_input_path,
            {
                "metrics": metrics,
                "top_notes": top_notes,
                "terms": metrics.get("top_title_terms", []),
                "trends": trends,
            },
        )

        lines = [
            f"# 小红书趋势日报：{domain.get('name', args.domain)}",
            "",
            f"日期：{date_str}",
            "",
            "## 今日结论",
            "",
            f"- 今日原始样本 {metrics.get('raw_count', 0)} 条，清洗去重后 {metrics.get('clean_count', 0)} 条，去重率 {metrics.get('dedupe_rate', 0):.2%}。",
            f"- 有标准发布时间的样本 {metrics.get('publish_date_present_count', 0)} 条，占比 {metrics.get('publish_date_present_rate', 0):.2%}。",
            f"- 近 {metrics.get('recent_publish_days', 7)} 天发布样本 {metrics.get('recent_publish_count', 0)} 条，占比 {metrics.get('recent_publish_ratio', 0):.2%}。",
            f"- 平均点赞 {metrics.get('avg_likes', 0)}，中位数点赞 {metrics.get('median_likes', 0)}，P90 点赞 {metrics.get('p90_likes', 0)}。",
            "",
            "## 数据概览",
            "",
            md_table(
                [
                    {"name": "原始样本数", "value": metrics.get("raw_count", 0)},
                    {"name": "去重后样本数", "value": metrics.get("clean_count", 0)},
                    {"name": "高赞笔记数", "value": metrics.get("high_like_count", 0)},
                    {"name": "高赞率", "value": f"{metrics.get('high_like_rate', 0):.2%}"},
                ],
                ["name", "value"],
                ["指标", "数值"],
            ),
            "## 高赞笔记 Top 10",
            "",
            md_table(
                top_notes,
                ["title", "author", "keyword", "publish_date", "like_count_num", "link"],
                ["标题", "作者", "关键词", "发布日期", "点赞", "链接"],
            ),
            "## 热门关键词",
            "",
            md_table(
                [{"keyword": k, "count": v} for k, v in metrics.get("top_keywords", {}).items()],
                ["keyword", "count"],
                ["关键词", "样本数"],
            ),
            "## 热门主题",
            "",
            md_table(
                metrics.get("top_topics", [])[:10],
                ["topic_name", "note_count", "avg_likes", "p90_likes", "high_like_rate", "representative_titles"],
                ["主题", "样本数", "平均点赞", "P90点赞", "高赞率", "代表标题"],
            ),
            "## 高频标题词",
            "",
            md_table(metrics.get("top_title_terms", [])[:20], ["term", "count"], ["词", "次数"]),
            "## 近 3 天上升词",
            "",
            md_table(
                trends[:20],
                ["term", "current_3d_count", "previous_3d_count", "growth_rate", "representative_titles"],
                ["词", "近3天", "前3天", "增速", "代表标题"],
            ),
            "## 值得关注的案例",
            "",
        ]
        for item in top_notes[:5]:
            lines.append(f"- {item.get('title', '')}：点赞 {item.get('like_count_num', '')}，作者 {item.get('author', '')}，链接 {item.get('link', '')}")
        lines.extend(
            [
                "",
                "## 明日关键词建议",
                "",
                f"候选关键词见 `{date_str}_candidate_keywords.csv`。建议先人工筛选，再加入 `config/domains.yaml`。",
                "",
                "## AI 解释",
                "",
            ]
        )
        if not llm_result.get("enabled"):
            lines.append(f"未启用大模型分析。{llm_result.get('error', '')}".strip())
        else:
            lines.extend(["### 关键结论", ""])
            lines.extend(md_list(llm_result.get("summary", [])))
            lines.extend(["", "### 主题洞察", ""])
            lines.extend(md_list(llm_result.get("topic_insights", [])))
            lines.extend(["", "### 案例分析", ""])
            lines.extend(md_list(llm_result.get("case_analysis", [])))
            lines.extend(["", "### 可复用模式", ""])
            lines.extend(md_list(llm_result.get("pattern_library", [])))
            lines.extend(["", "### 关键词建议", ""])
            lines.extend(md_list(llm_result.get("keyword_suggestions", [])))
            lines.extend(["", "### 内容建议", ""])
            lines.extend(md_list(llm_result.get("content_suggestions", [])))
            lines.extend(["", "### 风险提示", ""])
            lines.extend(md_list(llm_result.get("risk_notes", [])))
            lines.extend(["", "### 下一步动作", ""])
            lines.extend(md_list(llm_result.get("next_actions", [])))
        report_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        print(f"报告生成失败：{exc}", file=sys.stderr)
        return 1

    print(f"已生成日报：{report_path}")
    print(f"已保存 LLM 输入快照：{llm_input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
