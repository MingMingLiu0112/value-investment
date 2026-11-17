"""Contract checks for the numbered-report D2 fact projection (TEST_ONLY)."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.research import direct_owner_cash_agent_facts_v2 as facts
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
            "period_end": "2025-12-31", "symbol": "000568", "scope": SCOPE,
            "currency": "CNY", "source_binding": {"path": "runtime/original.pdf"},
            "income": {"revenue": row("100", 3), "cost": row("50", 4),
                       "parent_net_profit_cny": row("20", 5)},
            "cash_flow": {"customer_cash_cny": row("95", 6),
                          "supplier_cash_cny": row("45", 7),
                          "cfo_cny": row("30", 8)},
            "ordinary_shares_evidence": (
                {"period_end": "2025-12-31", "unit": "shares",
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
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_numbered_projection_rejects_unproven_shares(tmp_path, monkeypatch):
    binding = _spec(tmp_path)
    monkeypatch.setattr(facts, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: _evidence(shares=False))
    with pytest.raises(ValueError, match="DATED_SHARES_REQUIRED"):
        facts.read_parent_cash_agent_facts_v2(root=tmp_path, spec_binding=binding, now=NOW)
