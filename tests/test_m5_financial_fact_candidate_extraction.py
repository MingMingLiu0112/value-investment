import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "runtime/m5-600519-disclosure-queue-20260924/source/600519/announcements/2026-08-15/1225475868.pdf"


def test_half_year_pdf_extracts_statement_navigation_without_promoting_facts(tmp_path):
    output = tmp_path / "candidates.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/extract_m5_financial_fact_candidates.py"),
            "--pdf", str(PDF), "--symbol", "600519",
            "--announcement-id", "1225475868",
            "--published-at", "2026-08-15T00:00:00+08:00",
            "--output", str(output),
        ],
        check=True, capture_output=True, text=True,
    )
    assert '"action": "no_order"' in completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verification_status"] == "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION"
    assert {
        item["field"] for item in payload["numeric_facts"]
    } == {
        "cash_and_cash_equivalents",
        "operating_revenue",
        "operating_cost",
        "net_profit",
        "cash_received_from_sales",
    }
    assert all(
        item["verification_status"] == "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION"
        and item["page_text_sha256"]
        and item["source_line"]
        for item in payload["numeric_facts"]
    )
    assert {heading for page in payload["matched_statement_pages"] for heading in page["headings"]} == {
        "合并资产负债表", "合并利润表", "合并现金流量表"
    }
