#!/usr/bin/env python3
"""Verify an archived 2014 Q3 parent-equity fact packet for 600519.

The packet is deliberately supplementary to the pre-registered annual-input
window.  It identifies the latest issuer interim filing available before the
first decision date, but does not amend the registered window or create a
historical valuation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader
import pypdfium2 as pdfium

from value_investment_agent.historical_asof import publication_date_upper_bound


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "evidence-archive/cninfo/600519/2014-q3/600519-1200354286.pdf"
PDF_SHA256 = "1a4a97f3a0922416ab6285530772a64b9badddbd44f98d919812f8fccf2355cb"
INDEX = ROOT / "runtime/historical-filing-index/20260909T061926130764Z/600519-1-00c13403e0767a0f495d47aac579ab9e2ab305c5f48ead5f6d31bbad16bbf7c1.json"
INDEX_SHA256 = "00c13403e0767a0f495d47aac579ab9e2ab305c5f48ead5f6d31bbad16bbf7c1"
WINDOW = ROOT / "runtime/strategy-validation/moutai-historical-window-registration-20260918T121703Z/evidence.json"
ANNOUNCEMENT_ID = "1200354286"
FIRST_DECISION_AT = "2015-01-05T15:00:00+08:00"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def build() -> dict:
    if digest(PDF) != PDF_SHA256 or digest(INDEX) != INDEX_SHA256:
        raise ValueError("Archived Q3 filing or CNINFO index changed")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    announcements = [
        row for row in index["response"]["announcements"]
        if str(row["announcementId"]) == ANNOUNCEMENT_ID and row["secCode"] == "600519"
    ]
    if len(announcements) != 1:
        raise ValueError("Q3 announcement identity is missing or ambiguous")
    announcement = announcements[0]
    published = datetime.fromtimestamp(
        announcement["announcementTime"] / 1000, timezone(timedelta(hours=8))
    ).date().isoformat()
    source_url = "https://static.cninfo.com.cn/" + announcement["adjunctUrl"]
    if (announcement["announcementTitle"] != "2014\u5e74\u7b2c\u4e09\u5b63\u5ea6\u62a5\u544a"
            or published != "2014-10-30" or published not in source_url):
        raise ValueError("Q3 title, publication date, or original URL mismatch")
    available_at = publication_date_upper_bound(published).isoformat()
    if available_at > FIRST_DECISION_AT:
        raise ValueError("Q3 filing was not available before the historical decision window")
    reviewed = {
        3: (
                "\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u8d44\u4ea748,740,550,040.56",
                "\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da610,693,329,220.86",
        ),
        4: ("\u57fa\u672c\u6bcf\u80a1\u6536\u76ca\uff08\u5143/\u80a1\uff099.36",),
        12: (
            "\u5b9e\u6536\u8d44\u672c\uff08\u6216\u80a1\u672c\uff091,141,998,000.00",
            "\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u6240\u6709\u8005\u6743\u76ca\u5408\u8ba148,740,550,040.56",
        ),
        # This filing's profit-row label is not identically extracted by the
        # two PDF engines. The four-column numeric row is unique in both and
        # is retained with its statement-page role rather than inventing a
        # normalized label.
        16: ("10,693,329,220.86",),
    }
    evidence = []
    reader = PdfReader(PDF)
    with pdfium.PdfDocument(PDF) as document:
        for page_number, literals in reviewed.items():
            page = document[page_number - 1]
            textpage = page.get_textpage()
            try:
                decoded = (compact(reader.pages[page_number - 1].extract_text()), compact(textpage.get_text_range()))
            finally:
                textpage.close()
                page.close()
            for literal in literals:
                needle = compact(literal)
                expected_count = 2 if page_number == 16 else 1
                if any(text.count(needle) != expected_count for text in decoded):
                    raise ValueError(f"Q3 page {page_number} does not contain the expected numeric/text evidence: {literal}")
                evidence.append({"page": page_number, "literal": literal, "decoders": ["pypdf", "pdfium"]})
    registration = json.loads(WINDOW.read_text(encoding="utf-8"))
    if registration["window"]["start"] != "2015-01-05" or registration["window"]["annual_source_id"] != "cninfo:63720184":
        raise ValueError("Registered window changed; review interim-input relationship")
    return {
        "packet_version": "moutai-2014-q3-parent-equity-fact-v1",
        "symbol": "600519",
        "status": "supplementary_interim_fact_verified_not_registered_for_historical_valuation",
        "report_period": "2014-09-30",
        "source_id": "cninfo:" + ANNOUNCEMENT_ID,
        "source_url": source_url,
        "source_path": relative(PDF),
        "raw_file_hash": PDF_SHA256,
        "published_date": published,
        "available_at": available_at,
        "available_before_first_registered_decision": True,
        "facts": {
            "parent_equity_cny": "48740550040.56",
            "parent_profit_ytd_cny": "10693329220.86",
            "issued_shares_cny_par_value": "1141998000.00",
            "reported_basic_eps_ytd_cny_per_share": "9.36",
        },
        "evidence": evidence,
        "relationship_to_registered_window": {
            "registered_annual_source_id": registration["window"]["annual_source_id"],
            "replaces_registered_annual_source": False,
            "may_be_considered_only_after_a_versioned_window_and_model-contract_amendment": True,
            "reason": "The annual source was pre-registered. This later interim fact improves freshness but cannot be silently substituted after seeing prices or outcomes.",
        },
        "remaining_gaps": [
            "A historical residual-income assumption policy and cost-of-equity basis have not been frozen at the decision time.",
            "The Q3 parent-equity figure needs a registered clean-surplus/capital-action treatment before it can be used as opening book equity.",
            "Execution costs, next-open rules, liquidity and same-period benchmark acceptance remain incomplete.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "inputs": {
            relative(PDF): digest(PDF),
            relative(INDEX): digest(INDEX),
            relative(WINDOW): digest(WINDOW),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-2014-q3-parent-equity-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script": relative(Path(__file__)),
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "source_id": result["source_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
