"""Contract checks for the numbered-report D2 fact projection (TEST_ONLY)."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import direct_owner_cash_agent_facts_v2 as facts
from value_investment_agent.application.research.direct_owner_cash_staged_v3 import staged_parent_cash_request_v3
from value_investment_agent.domain.valuation.parent_direct_operating_cash import SCOPE


NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def _spec(tmp_path):
    spec = {
        "schema_version": "direct-owner-cash-research-spec-v1",
        "action": "no_order", "scope": SCOPE, "currency": "CNY",
        "model_applicable": True, "model_applicability_evidence": ["TEST_ONLY"],
        "symbol": "000568", "issuer_name": "TEST_ONLY",
        "computed_at": NOW.isoformat(), "valuation_date": "2025-12-31",
        "source_adapter_version": "NUMBERED_CNINFO_V2",
        "operating_sources": [], "owner_sources": [{"TEST_ONLY": True}],
        "fact_anchors": {
            "revenue": {"period_end": "2025-12-31", "section": "operating",
                        "field": "revenue", "column": "current"},
            "profit": {"period_end": "2025-12-31", "section": "income",
                       "field": "parent_net_profit_cny", "column": "current"},
        },
        "opening": {}, "scenarios": {"TEST_ONLY": "must not enter facts"},
    }
    target = tmp_path / "runtime" / "spec.json"
    target.parent.mkdir()
    raw = json.dumps(spec, ensure_ascii=False).encode()
    target.write_bytes(raw)
    return {"path": "runtime/spec.json", "sha256": hashlib.sha256(raw).hexdigest()}


def _evidence(shares=True):
    def row(value, page):
        return {"current": value, "comparative": value,
                "source_refs": {"path": "runtime/original.pdf",
                                "sha256": "a" * 64, "physical_page": page,
                                "excerpt": "TEST_ONLY"}}
    return {
        "statements": [{
            "period_start": "2025-01-01", "period_end": "2025-12-31",
            "symbol": "000568", "scope": SCOPE,
            "currency": "CNY", "source_binding": {"path": "runtime/original.pdf"},
            "income": {"revenue": row("100", 3), "cost": row("50", 4),
                       "parent_net_profit_cny": row("20", 5)},
            "cash_flow": {"customer_cash_cny": row("95", 6),
                          "supplier_cash_cny": row("45", 7),
                          "cfo_cny": row("30", 8),
                          "borrowings_received_cny": row("25", 13),
                          "debt_repayments_paid_cny": row("15", 14)},
            "balance_sheet": {
                "liabilities_cny": row("100", 10),
                "current_noncurrent_liabilities_cny": row("40", 11),
                "long_term_borrowings_cny": row("20", 12),
            },
            "ordinary_shares_evidence": (
                {"period_end": "2025-12-31", "unit": "shares",
                 "classification": "DERIVED_FACT",
                 "derivation": "TEST_ONLY_RECONCILIATION",
                 "scope": "TOTAL_ISSUED_ORDINARY_SHARES", "count": "10",
                 "source_refs": [row("10", 9)["source_refs"]]} if shares else None),
        }],
        "status": "SOURCE_BOUND_PARENT_BRIDGE_FACTS_NOT_OWNER_CASH",
        "working_capital_cash_component": None,
        "constraints": None, "unresolved": ["TEST_ONLY"],
        "fund_commitment_evidence": None,
    }


def test_numbered_projection_keeps_row_evidence_and_excludes_forecasts(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: _evidence())
    result = facts.read_parent_cash_agent_facts_v2(
        root=tmp_path, spec_binding=binding, now=NOW)
    assert result["facts"]["revenue"]["source_refs"]["physical_page"] == 3
    assert result["facts"]["profit"]["source_refs"]["physical_page"] == 5
    assert result["forecast_scenarios_present"] is False
    assert result["ordinary_shares"]["classification"] == "DERIVED_FACT"
    financing = result["historical_financing_range"]
    assert result["historical_financing_observations"] == [financing]
    assert financing["selected_liability_rows_sum_cny"] == "60"
    assert financing["on_balance_liabilities_ceiling"]["value_cny"] == "100"
    assert financing["components"]["short_term_borrowings_cny"]["classification"] == "UNKNOWN"
    assert financing["components"]["bonds_payable_cny"]["value_cny"] is None
    assert financing["complete_financing_scope_verified"] is False
    assert financing["future_refinancing_verified"] is False
    cash = financing["financing_cash_flows"]
    assert cash["period_start"] == "2025-01-01"
    assert cash["components"]["debt_repayments_paid_cny"]["source_refs"]["physical_page"] == 14
    assert cash["net_borrowing_cash_cny"] == "10"
    assert cash["classification"] == "HISTORICAL_CASH_FLOW_NOT_DEBT_BALANCE_CHANGE"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_numbered_projection_rejects_unproven_shares(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: _evidence(shares=False))
    with pytest.raises(ValueError, match="DATED_SHARES_REQUIRED"):
        facts.read_parent_cash_agent_facts_v2(root=tmp_path, spec_binding=binding, now=NOW)


def test_financing_components_cannot_exceed_parent_liabilities(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    evidence = _evidence()
    evidence["statements"][0]["balance_sheet"]["liabilities_cny"]["current"] = "50"
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: evidence)
    with pytest.raises(ValueError, match="FINANCING_RANGE_INVALID"):
        facts.read_parent_cash_agent_facts_v2(root=tmp_path, spec_binding=binding, now=NOW)


def test_missing_financing_rows_are_unknown_not_zero_debt(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    evidence = _evidence()
    evidence["statements"][0]["balance_sheet"] = {}
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: evidence)
    result = facts.read_parent_cash_agent_facts_v2(
        root=tmp_path, spec_binding=binding, now=NOW)
    financing = result["historical_financing_range"]
    assert financing["selected_liability_rows_sum_cny"] is None
    assert financing["reported_component_count"] == 0
    assert financing["on_balance_liabilities_ceiling"] is None


def test_missing_repayment_does_not_infer_zero_or_net_borrowing(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    evidence = _evidence()
    del evidence["statements"][0]["cash_flow"]["debt_repayments_paid_cny"]
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: evidence)
    cash = facts.read_parent_cash_agent_facts_v2(
        root=tmp_path, spec_binding=binding, now=NOW
    )["historical_financing_range"]["financing_cash_flows"]
    assert cash["components"]["debt_repayments_paid_cny"] == {
        "classification": "UNKNOWN", "value_cny": None,
    }
    assert cash["net_borrowing_cash_cny"] is None


def test_real_parent_financing_cash_reaches_d2_request():
    root = Path(os.environ.get("VALUE_REAL_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
    relative = "runtime/direct-owner-cash-000568-20261117/source-only-v3-h1.json"
    if not (root / relative).exists():
        pytest.skip("Retained official source spec unavailable")
    binding = {"path": relative,
               "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()}
    now = datetime.now(timezone.utc)
    context = facts.read_parent_cash_agent_facts_v2(
        root=root, spec_binding=binding, now=now)
    history = {row["period_end"]: row for row in context["historical_financing_observations"]}
    fy = history["2025-12-31"]["financing_cash_flows"]
    h1 = history["2026-06-30"]["financing_cash_flows"]
    assert fy["components"]["borrowings_received_cny"]["classification"] == "UNKNOWN"
    assert fy["components"]["debt_repayments_paid_cny"]["value_cny"] == "3220200000.00"
    assert h1["net_borrowing_cash_cny"] == "-551200000.00"
    request = staged_parent_cash_request_v3(
        root=root, spec_binding=binding, scenario="bear", stage="operating",
        generated_at=now, verified_context=context)
    received = json.loads(request.user)["source_context"]["historical_financing_observations"]
    assert received == context["historical_financing_observations"]
    from decimal import Decimal

    cash_history = json.loads(request.user)["source_context"]["parent_operating_cash_observations"]
    assert cash_history == context["parent_operating_cash_observations"]
    assert {row["period_end"] for row in cash_history} == {"2025-12-31", "2026-06-30"}
    for row in cash_history:
        changes = row["cash_change_explanation"]
        assert changes["classification"] == "DERIVED_HISTORICAL_CASH_CHANGE_NOT_WORKING_CAPITAL"
        assert Decimal(changes["cfo_change_cny"]) == sum(Decimal(changes[key]) for key in (
            "customer_receipt_change_cny", "lower_supplier_payments_contribution_cny",
            "other_operating_cash_change_cny"))
        assert row["source_refs"]["cfo"]
    assert context["working_capital_cash_component"] is None
