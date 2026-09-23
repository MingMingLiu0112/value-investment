"""Extract page-level balance-sheet and income candidates for M1 valuation.

This is an audit-only reader for retained CNINFO PDF originals. It writes page
text snippets to runtime and never assigns a verified domain value.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.pdf_text import extract_pages


REPORT_DIR = ROOT / "runtime" / "company-research" / "m1-valuation-filings-20260923"


def compact(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", value)


def dump_pages(pages: list[str], indexes: list[int], out_dir: Path) -> list[dict]:
    rows = []
    for raw_index in indexes:
        if raw_index < 0 or raw_index >= len(pages):
            rows.append({"pdf_page_index": raw_index, "error": "missing"})
            continue
        text = pages[raw_index]
        path = out_dir / f"page-{raw_index}.txt"
        path.write_text(text, encoding="utf-8")
        rows.append(
            {
                "pdf_page_index": raw_index,
                "path": str(path.relative_to(ROOT)),
                "text": text[:30000],
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--period", default="annual")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    directory = args.root / REPORT_DIR.relative_to(ROOT) / args.symbol
    annual = next(directory.glob(f"*{args.period}*.pdf"))
    indexes = [int(value) for value in args.pages.split(",")]
    out_dir = directory / f"{args.period}-page-dumps"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = dump_pages(extract_pages(annual), indexes, out_dir)
    payload = {
        "symbol": args.symbol,
        f"{args.period}_pdf": str(annual.relative_to(ROOT)),
        "purpose": "raw PDF page dump audit only",
        "pages": rows,
    }
    output = directory / f"{args.period}-valuation-page-dumps.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
