"""Direct financing-summary tests; synthetic rows are explicitly TEST_ONLY."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.domain.discovery.financial_source_comparison_v1 import summarize_official_financing
from value_investment_agent.infrastructure.screening import official_funding_details_v1 as adapter

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
PERIOD = "2025-12-31"


def row(field="short_term_borrowings", value="10.25"):
    return dict(symbol="600887", field_name=field, value=value, prior_value="999.00",
        period_label=PERIOD, prior_period_label="2024-12-31",
        unit="CNY", currency="CNY", statement_scope="consolidated",
        page=189, excerpt="TEST_ONLY explicit current and prior printed amounts",
        column_status="ORDERED_TWO_COLUMNS", financial_fact_admitted=False,
        complete_debt_verified=False, action="no_order",
        source_binding=dict(symbol="600887", period=PERIOD,
            path="TEST_ONLY/original.pdf", sha256="a"*64,
            source_url="https://static.cninfo.com.cn/finalpage/2026-04-30/123.PDF",
            available_at="2026-10-30T12:00:00+00:00"))


def summarize(rows, **kwargs):
    return summarize_official_financing(rows, symbol="600887", period=PERIOD,
                                       evaluated_at=kwargs.get("evaluated_at", NOW))


def test_real_adapter_shaped_disjoint_rows_exact_sum_without_admission():
    rows = [row("short_term_borrowings", "45630626027.83"),
            row("short_term_bonds", "9043394520.53"),
            row("long_term_borrowings_noncurrent", "472479632.72"),
            row("long_term_borrowings_current", "4263076679.33"),
            row("lease_liabilities_noncurrent", "288520048.50"),
            row("lease_liabilities_current", "151630797.19"),
            row("financial_member_deposits", "908486765.87")]
    before = deepcopy(rows)
    result = summarize(rows)
    assert result["known_total"] == "60758214471.97"
    assert len(result["components"]) == 7 and result["status"] == "PARTIAL"
    assert result["errors"] == []
    assert result["action"] == "no_order"
    assert result["complete_debt_verified"] is result["formal_admission"] is False
    assert rows == before
    assert all(r["page"] == 189 and r["sha256"] == "a"*64 for r in result["components"])


@pytest.mark.parametrize("second", ["10.25", "20.00", None])
def test_duplicate_bucket_rejects_even_equal_or_unknown(second):
    result = summarize([row(), row(value=second)])
    assert result["status"] == "REJECTED" and result["known_total"] is None
    assert "DUPLICATE_FINANCING_BUCKET:short_term_borrowings" in result["errors"]


@pytest.mark.parametrize("member_value", ["10.25", None])
def test_deposit_aggregate_member_overlap_not_summed(member_value):
    result = summarize([row("financial_deposits_and_interbank", "30.00"),
                        row("financial_member_deposits", member_value)])
    assert result["status"] == "REJECTED" and result["known_total"] is None
    assert "DEPOSIT_AGGREGATE_AND_MEMBER_COMPONENT_MAY_OVERLAP" in result["errors"]


@pytest.mark.parametrize("where,key,value", [
    ("row", "symbol", "600519"), ("source", "symbol", "600519"),
    ("row", "period_label", "2024-12-31"), ("source", "period", "2024-12-31"),
    ("row", "unit", "CNY_10000"), ("row", "currency", "USD"),
    ("source", "available_at", "2027-01-01T00:00:00+00:00"),
    ("source", "available_at", "2026-10-30T12:00:00"),
    ("source", "available_at", "invalid"),
    ("row", "page", 0), ("row", "page", True), ("row", "excerpt", ""),
    ("source", "sha256", "broken"),
    ("source", "source_url", "http://static.cninfo.com.cn/finalpage/2026-04-30/123.PDF"),
    ("source", "source_url", "https://test-user@static.cninfo.com.cn/finalpage/2026-04-30/123.PDF"),
    ("row", "statement_scope", None),
])
def test_invalid_binding_period_identity_units_time(where, key, value):
    damaged = row()
    target = damaged if where == "row" else damaged["source_binding"]
    target[key] = value
    result = summarize([damaged, row("short_term_bonds", "2.00")])
    assert result["status"] == "REJECTED" and result["known_total"] is None
    assert "FINANCING_SOURCE_SCOPE_OR_TIME_INVALID:short_term_borrowings" in result["errors"]


def test_naive_cutoff_rejected_and_equal_source_clock_allowed():
    with pytest.raises(ValueError, match="AWARE_FINANCING_CUTOFF_REQUIRED"):
        summarize([row()], evaluated_at=NOW.replace(tzinfo=None))
    result = summarize([row()], evaluated_at=datetime.fromisoformat(row()["source_binding"]["available_at"]))
    assert result["known_total"] == "10.25"


def test_null_preserves_unknown_does_not_use_prior_or_single_printed_amount():
    unknown = row("bonds_payable_current", None)
    unknown.update(single_printed_amount="3600851765.96", column_status="UNKNOWN_SINGLE_COLUMN")
    result = summarize([row(), unknown])
    assert result["known_total"] == "10.25" and result["status"] == "PARTIAL"
    assert [x["field"] for x in result["unknown_components"]] == ["bonds_payable_current"]
    assert len(result["components"]) == 1
    only_unknown = summarize([unknown])
    assert only_unknown["known_total"] is None and only_unknown["status"] == "NOT_AVAILABLE"
    assert summarize([])["known_total"] is None
    zero = summarize([row(value="0.00")])
    assert Decimal(zero["known_total"]) == 0 and len(zero["components"]) == 1


@pytest.mark.parametrize("value", ["-0.01", "NaN", "Infinity", "-Infinity", True, "", "bad"])
def test_negative_or_invalid_amount_blocks_total(value):
    result = summarize([row(value=value), row("short_term_bonds", "1.00")])
    assert result["status"] == "REJECTED" and result["known_total"] is None
    assert "INVALID_FINANCING_AMOUNT:short_term_borrowings" in result["errors"]


def test_unclassified_other_payables_not_whole_bucket_financing():
    result = summarize([row(), row("other_payables", "999999999.00")])
    assert result["known_total"] == "10.25"
    assert len(result["components"]) == 1


def test_parent_scope_cannot_be_summed_as_consolidated():
    damaged = row()
    damaged["statement_scope"] = "parent"
    result = summarize([damaged])
    assert result["status"] == "REJECTED" and result["known_total"] is None


@pytest.mark.parametrize("index,symbol,digest,total", [
    ("0", "600519", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288", "18272094956.12"),
    ("1", "600887", "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac", "60758214471.97"),
    ("2", "000544", "55bac5078b18dfe1c7ff5bf79c90bf985e2635a7432c1aed2de579a63fe55002", None),
])
def test_real_public_original_replay(tmp_path, index, symbol, digest, total):
    configured = os.environ.get("OFFICIAL_FUNDING_REAL_ROOT")
    if not configured:
        if os.environ.get("OFFICIAL_FUNDING_REAL_REQUIRED") == "1":
            pytest.fail("Explicit official original root required")
        pytest.skip("Set OFFICIAL_FUNDING_REAL_ROOT for read-only public-original replay")
    root = Path(configured)
    receipt_path = root / ("runtime/public-evidence/20261030-a-first/"+index+"/acquisition/receipt.json")
    receipt_bytes = receipt_path.read_bytes()
    source = json.loads(receipt_bytes)["source"]
    assert source["symbol"] == symbol and source["period"] == PERIOD and source["sha256"] == digest
    original = root / source["path"]
    raw = original.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    copy = tmp_path / "original.pdf"
    copy.write_bytes(raw)
    source = dict(source, path="original.pdf")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(schema_version=adapter.VERSION, sources=[source])), encoding="utf-8")
    binding = dict(path="manifest.json", sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    if total is None:
        # This original has no admitted native currency context: no zero/success fallback.
        with pytest.raises(ValueError, match="NO_VERIFIABLE_FUNDING_ROWS"):
            adapter.load(tmp_path, binding, NOW)
    else:
        result = adapter.load(tmp_path, binding, NOW)
        summary = summarize_official_financing(result["observations"], symbol=symbol,
                                              period=PERIOD, evaluated_at=NOW)
        assert summary["known_total"] == total and summary["status"] == "PARTIAL"
        assert summary["errors"] == []
        assert summary["complete_debt_verified"] is summary["formal_admission"] is False
        if symbol == "600887":
            assert {r["field"] for r in summary["unknown_components"]} == {
                "bonds_payable_current", "long_term_payables_current"}
        (tmp_path / "replay-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert original.read_bytes() == raw and receipt_path.read_bytes() == receipt_bytes
