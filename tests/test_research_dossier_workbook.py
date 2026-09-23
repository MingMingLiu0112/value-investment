from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from value_investment_agent.m1_research_dossier_candidate import (
    build_candidate_collection,
    write_candidate,
)
from value_investment_agent.m1_sample_preregistration import (
    load_m1_sample_preregistration,
)
from value_investment_agent.research_dossier_workbook import (
    GAP_SHEET,
    OVERVIEW_SHEET,
    build_dossier_workbook,
    write_dossier_workbook,
)


GENERATED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
REF = {"id": "source", "path": "source.pdf", "sha256": "a" * 64}


def _record(symbol: str, name: str) -> dict:
    return {
        "case": {
            "symbol": symbol,
            "name": name,
            "as_of": "2025-12-31",
            "run_id": "legacy",
            "generated_at": "2026-09-21T00:00:00+08:00",
            "research_version": "legacy-v1",
            "industry": "fixture",
            "investment_path": "fixture",
            "thesis": "legacy thesis",
            "return_driver": "legacy driver",
            "mispricing_hypothesis": "not proven",
            "financial_summary": {"period_end": "2025-12-31"},
            "positives": [
                {"kind": "fact", "text": "positive", "evidence_refs": ["source"]}
            ],
            "counter_evidence": [
                {"kind": "fact", "text": "counter", "evidence_refs": ["source"]}
            ],
            "thesis_breakers": [
                {
                    "kind": "hypothesis",
                    "text": "breaker",
                    "evidence_refs": ["source"],
                }
            ],
            "next_events": [
                {"kind": "fact", "text": "next", "evidence_refs": ["source"]}
            ],
            "evidence_status": "verified",
            "valuation_status": "not_ready",
            "research_status": "financial_scope_approved",
            "blockers": ["legacy blocker"],
            "evidence_refs": [REF],
            "quote_date": None,
            "financial_period": "2025-12-31",
            "missing_date_reasons": {"quote_date": "not used"},
        },
        "gate": {},
    }


def _collection():
    return build_candidate_collection(
        load_m1_sample_preregistration(),
        {
            "version": "excel-mvp-research-cases-v1",
            "generated_at": "2026-09-22T00:00:00+08:00",
            "records": [
                _record("600519", "Moutai"),
                _record("000333", "Midea"),
                _record("601088", "Shenhua"),
            ],
            "formal_trade_instructions": False,
        },
        generated_at=GENERATED_AT,
    )


def _all_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_workbook_contains_all_twenty_dossiers_and_keeps_no_order_contract():
    workbook = build_dossier_workbook(_collection())

    assert OVERVIEW_SHEET in workbook.sheetnames
    assert GAP_SHEET in workbook.sheetnames
    assert all(symbol in workbook.sheetnames for symbol in (
        "600519",
        "000333",
        "601088",
        "600887",
        "600036",
    ))
    assert len([name for name in workbook.sheetnames if name.isdigit()]) == 20
    text = _all_text(workbook)
    assert "action=no_order" in text
    assert "买入" not in text
    assert "卖出" not in text
    assert "目标仓位" not in text


def test_workbook_makes_blockers_and_unknown_business_dimensions_visible():
    workbook = build_dossier_workbook(_collection())
    gap_text = "\n".join(
        str(cell.value)
        for row in workbook[GAP_SHEET].iter_rows()
        for cell in row
        if cell.value is not None
    )
    moutai_text = "\n".join(
        str(cell.value)
        for row in workbook["600519"].iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert "legacy blocker" in gap_text
    assert "legacy blocker" in moutai_text
    assert "unknown" in moutai_text.lower()
    assert "Business Quality" in moutai_text


def test_workbook_writer_creates_hash_pinned_runtime_candidate(tmp_path):
    collection = _collection()
    write_candidate(collection, root=tmp_path)
    result = write_dossier_workbook(collection, root=tmp_path)

    target = tmp_path / result["workbook_path"]
    assert target.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    manifest = json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["workbook_sha256"] == result["workbook_sha256"]
