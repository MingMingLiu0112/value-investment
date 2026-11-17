"""TEST_ONLY numbered-source compiler integration with the existing cash domain."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_compilation_v2 as compiler
from test_direct_owner_cash_compilation_v1 import sample


NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def _numbered_spec(monkeypatch):
    spec = sample(monkeypatch)
    spec["source_adapter_version"] = "NUMBERED_CNINFO_V2"
    spec["operating_sources"] = []
    spec["ordinary_shares"]["classification"] = "DERIVED_FACT"
    statement = {
        "period_start": "2025-01-01", "period_end": "2025-12-31",
        "period_basis": "FY", "symbol": spec["symbol"],
        "scope": compiler.SCOPE, "currency": "CNY",
        "balance_sheet": {}, "income": {}, "cash_flow": {},
        "ordinary_shares_evidence": {
            "classification": "DERIVED_FACT", "period_end": "2025-12-31",
            "unit": "shares", "scope": "TOTAL_ISSUED_ORDINARY_SHARES",
            "count": "100", "source_refs": [{"path": "runtime/TEST_ONLY.pdf",
                                              "sha256": "a" * 64}]},
    }
    row_ref = {"path": "runtime/TEST_ONLY.pdf", "sha256": "a" * 64,
               "physical_page": 1, "excerpt": "TEST_ONLY"}
    for name, ref in spec["fact_anchors"].items():
        value = ("1000" if name == "book_equity_cny" else
                 "20" if name == "closing_cash_and_equivalents_cny" else
                 "80" if name == "profit" else "100")
        statement[ref["section"]][ref["field"]] = {
            "current": value, "comparative": value,
            "source_refs": row_ref,
        }
    statement["income"].update(
        revenue={"current": "200", "source_refs": row_ref},
        cost={"current": "100", "source_refs": row_ref})
    statement["cash_flow"].update(
        customer_cash_cny={"current": "200", "source_refs": row_ref},
        supplier_cash_cny={"current": "100", "source_refs": row_ref},
        cfo_cny={"current": "100", "source_refs": row_ref})
    monkeypatch.setattr(compiler, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: {"statements": [statement],
                                           "constraints": None})
    return spec, statement


def test_numbered_report_compiles_existing_cash_model(monkeypatch, tmp_path):
    spec, _statement = _numbered_spec(monkeypatch)
    result = compiler.compile_source_bound_owner_cash_v2(
        root=tmp_path, spec=spec, now=NOW)
    assert result["ordinary_shares"] == "100"
    assert result["scenarios"]["base"]["years"][0]["policy"]["operating_cash"] == "100"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_numbered_report_rejects_share_and_cash_source_gaps(monkeypatch, tmp_path):
    spec, statement = _numbered_spec(monkeypatch)
    wrong = deepcopy(spec)
    wrong["ordinary_shares"]["classification"] = "FACT"
    with pytest.raises(ValueError, match="DATED_SHARE_FACT_REQUIRED"):
        compiler.compile_source_bound_owner_cash_v2(root=tmp_path, spec=wrong, now=NOW)
    del statement["cash_flow"]["customer_cash_cny"]
    with pytest.raises(ValueError, match="NUMBERED_OPERATING_FACT_MISSING"):
        compiler.compile_source_bound_owner_cash_v2(root=tmp_path, spec=spec, now=NOW)
