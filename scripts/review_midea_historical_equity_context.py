"""Print bounded excerpts from the generated Midea historical context probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT = ROOT / "runtime" / "midea-historical-equity-context.json"
TIMELINE = ROOT / "runtime" / "company-research" / "midea-annual-share-timeline-20260912T054403745196Z" / "evidence.json"
KEYS = (
    "归属于母公司股东权益合计",
    "归属于母公司股东的净利润",
    "基本每股收益",
    "每 10 股派息数",
    "现金分红总额",
    "现金分红金额",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--source", type=Path, default=DEFAULT_CONTEXT)
    args = parser.parse_args()
    rows = json.loads(args.source.read_text(encoding="utf-8-sig"))
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    year_by_file = {
        Path(item["source"]["source_path"].replace("\\", "/")).name: item["report_year"]
        for item in timeline["rows"]
    }
    for row in rows:
        year = year_by_file[row["file"]]
        if args.years and year not in args.years:
            continue
        print(f"\n### {row['file']} ({year})")
        for page, text in row.get("contexts", {}).items():
            for key in KEYS:
                start = 0
                while (index := text.find(key, start)) >= 0:
                    snippet = text[max(0, index - 120):index + 420]
                    print(f"\nPAGE {page} KEY {key}\n{snippet}")
                    start = index + len(key)


if __name__ == "__main__":
    main()
