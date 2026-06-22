from __future__ import annotations

import argparse
import sys

import pandas as pd

from analysis.image_analyzer import add_image_analysis_placeholders, download_cover_images
from pipeline.common import load_analysis_config
from storage.paths import normalize_date, processed_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载封面图并预留 OCR/多模态分析字段。")
    parser.add_argument("--date", default="today", help="日期，默认 today")
    parser.add_argument("--domain", required=True, help="领域 id，例如 camping")
    parser.add_argument("--download", action="store_true", help="实际下载封面图；默认只添加占位字段")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = normalize_date(args.date)
    path = processed_dir(args.domain) / f"{date_str}_clean_notes.xlsx"
    try:
        if not path.exists():
            raise FileNotFoundError(f"找不到清洗结果：{path}")
        df = pd.read_excel(path)
        config = load_analysis_config().get("analysis", {})
        enable_ocr = bool(config.get("enable_ocr", False))
        out = download_cover_images(df, date_str, args.domain) if args.download else add_image_analysis_placeholders(df)
        if not enable_ocr:
            out["cover_ocr_text"] = out.get("cover_ocr_text", "")
        out.to_excel(path, index=False)
        out.to_csv(processed_dir(args.domain) / f"{date_str}_clean_notes.csv", index=False, encoding="utf-8-sig")
    except Exception as exc:
        print(f"图片分析失败：{exc}", file=sys.stderr)
        return 1
    print(f"已更新图片分析字段：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
