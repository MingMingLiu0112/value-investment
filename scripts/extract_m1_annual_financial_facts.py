"""Extract candidate annual-report facts for the M1 valuation evidence layer.

This script only reads the retained CNINFO PDF originals.  Its output is a
search/parse audit: every candidate remains ``verified=False`` until a later
domain-level review binds it to an exact page, period, source URL and hash.
It never writes Excel, PostgreSQL, or a trading action.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import re

from value_investment_agent.pdf_text import extract_pages


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "company-research" / "m1-valuation-filings-20260923"

SYMBOLS = {
    "600887": "伊利股份",
    "600741": "华域汽车",
    "000651": "格力电器",
}


def normalize(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text)


def candidates_for(
    pages: list[str],
    needles: tuple[str, ...],
    *,
    context_chars: int = 500,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for zero_index, page_text in enumerate(pages):
        compact = normalize(page_text)
        found = [needle for needle in needles if normalize(needle) in compact]
        if not found:
            continue
        snippet = compact
        if len(snippet) > context_chars:
            starts = [compact.find(normalize(needle)) for needle in found]
            starts = [value for value in starts if value >= 0]
            low = max(0, min(starts) - context_chars // 2)
            snippet = compact[low : low + context_chars]
        result.append({
            "pdf_page_index": zero_index,
            "printed_page_candidate": None,
            "needles": found,
            "context": snippet,
        })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or (
        args.root / "runtime" / "company-research"
        / "m1-annual-financial-fact-candidates-20260923.json"
    )

    reports: dict[str, dict[str, object]] = {}
    for symbol, issuer in SYMBOLS.items():
        directory = REPORT_DIR / symbol
        annual = next(directory.glob("*annual*.pdf"))
        pages = extract_pages(annual)
        reports[symbol] = {
            "issuer": issuer,
            "path": str(annual),
            "page_count": len(pages),
            "searches": {
                "consolidated": candidates_for(
                    pages,
                    (
                        "归属于母公司所有者的净利润",
                        "归属于母公司股东的净利润",
                        "归属于上市公司股东的净利润",
                    ),
                ),
                "equity": candidates_for(
                    pages,
                    (
                        "归属于母公司所有者权益",
                        "归属于母公司股东权益",
                        "归属于上市公司股东的净资产",
                    ),
                ),
                "shares": candidates_for(
                    pages,
                    (
                        "期末总股本",
                        "普通股",
                        "已发行股份",
                        "总股本",
                    ),
                ),
                "cash_flow": candidates_for(
                    pages,
                    (
                        "经营活动产生的现金流量净额",
                        "购建固定资产、无形资产和其他长期资产支付的现金",
                    ),
                ),
            },
        }

    payload = {
        "purpose": "M1 candidate facts: raw PDF search audit only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": "no_order",
        "verified": False,
        "reports": reports,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
