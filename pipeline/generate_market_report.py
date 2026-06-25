from __future__ import annotations

import argparse
import json
import sys

from analysis.llm_analyzer import analyze_market_context_with_llm
from analysis.llm_context_builder import build_llm_input, save_llm_input
from analysis.market_report import deterministic_market_analysis, render_market_report
from analysis.report_validator import validate_market_analysis
from pipeline.common import get_domain
from storage.paths import market_report_dir, normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于结构化输入生成搜索页市场局势报告。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    try:
        domain = get_domain(args.domain)
        llm_input = build_llm_input(domain_id=args.domain, date_str=date_str, domain=domain)
        llm_input_path = save_llm_input(llm_input, domain_id=args.domain, date_str=date_str)

        analysis = analyze_market_context_with_llm(llm_input)
        if not analysis.get("enabled"):
            fallback = deterministic_market_analysis(llm_input)
            if analysis.get("error"):
                fallback["llm_error"] = analysis["error"]
            analysis = fallback
        analysis, validation = validate_market_analysis(analysis, llm_input)

        analysis_path = processed_dir(args.domain) / f"{date_str}_market_analysis.json"
        validation_path = processed_dir(args.domain) / f"{date_str}_market_analysis_validation.json"
        analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")

        report = render_market_report(llm_input, analysis)
        out_dir = market_report_dir(args.domain)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"{date_str}_小红书市场局势报告.md"
        report_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        print(f"市场局势报告生成失败：{exc}", file=sys.stderr)
        return 1

    print(f"已保存 LLM 输入包：{llm_input_path}")
    print(f"已保存市场分析 JSON：{analysis_path}")
    print(f"已保存报告校验结果：{validation_path}")
    print(f"已生成市场局势报告：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
