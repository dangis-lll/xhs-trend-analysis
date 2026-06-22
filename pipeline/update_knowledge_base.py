from __future__ import annotations

import argparse
from datetime import datetime
import sys

import pandas as pd

from pipeline.common import get_domain
from storage.paths import knowledge_base_dir, normalize_date, processed_dir


def append_section(path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# {path.stem}\n"
    path.write_text(existing.rstrip() + "\n\n" + f"## {title}\n\n" + body.strip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把候选关键词和稳定主题追加到知识库。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    kb = knowledge_base_dir(args.domain)
    try:
        domain = get_domain(args.domain)
        candidate_path = processed_dir(args.domain) / f"{date_str}_candidate_keywords.csv"
        if candidate_path.exists():
            candidates = pd.read_csv(candidate_path).head(20)
        else:
            candidates = pd.DataFrame()
        body_lines = [f"领域：{domain.get('name', args.domain)}", f"更新日期：{date_str}", ""]
        if candidates.empty:
            body_lines.append("暂无候选关键词。")
        else:
            for _, row in candidates.iterrows():
                body_lines.append(f"- {row.get('keyword', '')}：{row.get('reason', '')}")
        append_section(kb / "keyword_pool.md", f"{date_str} {args.domain} 候选关键词", "\n".join(body_lines))
        append_section(
            kb / "domain_profile.md",
            f"{date_str} {args.domain} 运行记录",
            f"本次由规则流程自动更新。生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )
    except Exception as exc:
        print(f"知识库更新失败：{exc}", file=sys.stderr)
        return 1
    print(f"已更新知识库目录：{kb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
