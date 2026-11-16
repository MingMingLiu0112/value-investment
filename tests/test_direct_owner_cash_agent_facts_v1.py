"""TEST_ONLY D2 parent fact projection; no model call or investment admission."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.research import direct_owner_cash_agent_facts_v1 as target

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def _bound(tmp_path, spec):
    path = tmp_path / "runtime" / "source-spec.json"
    path.parent.mkdir(exist_ok=True)
    raw = json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return {"path": "runtime/source-spec.json", "sha256": sha256(raw).hexdigest()}


def _source(monkeypatch):
    statement = dict(period_end="2025-12-31", scope=target.SCOPE,
        currency="CNY", source_binding={"path": "runtime/parent.pdf", "sha256": "a" * 64},
        balance_sheet={"book_equity_cny": {"current": "1000"}},
        income={}, cash_flow={})
    statement["ordinary_shares_evidence"] = dict(count="100", period_end="2025-12-31",
        unit="shares", scope="TOTAL_ISSUED_ORDINARY_SHARES",
        source_refs={"path": "runtime/shares.pdf", "sha256": "c" * 64})
    monkeypatch.setattr(target, "read_parent_direct_owner_cash_sources", lambda **kw: dict(
        statements=[statement], constraints=[], unresolved=["TEST_ONLY debt maturity unknown"],
        fund_commitment_evidence=[], status="TEST_ONLY_PARTIAL",
        working_capital_cash_component=None))
    monkeypatch.setattr(target, "read_parent_direct_cash_research", lambda **kw: dict(observed=[
        dict(symbol="600887", scope=target.SCOPE, period_end="2025-12-31",
             revenue="200", source_refs={"path": "runtime/operations.pdf", "sha256": "b" * 64})]))
    return dict(schema_version=target.SCHEMA, action="no_order", scope=target.SCOPE,
        currency="CNY", model_applicable=True, model_applicability_evidence=["TEST_ONLY"],
        symbol="600887", issuer_name="TEST_ONLY", computed_at=NOW.isoformat(),
        valuation_date="2025-12-31", owner_sources=[{"TEST_ONLY": True}],
        operating_sources=[{"TEST_ONLY": True}],
        fact_anchors={"book": dict(period_end="2025-12-31", section="balance_sheet",
                                  field="book_equity_cny", column="current"),
                      "revenue": dict(period_end="2025-12-31", section="operating",
                                      field="revenue", column="current")},
        opening={"book": {"classification": "FACT", "anchor": "book"}},
        scenarios={"bear": {"value": "1"}})


def test_parent_facts_reopen_sources_without_copying_prior_forecasts(monkeypatch, tmp_path):
    spec = _source(monkeypatch)
    first = target.read_parent_cash_agent_facts(
        root=tmp_path, spec_binding=_bound(tmp_path, spec), now=NOW)
    assert first["facts"]["book"]["value_cny"] == "1000"
    assert first["facts"]["revenue"]["value_cny"] == "200"
    assert first["forecast_scenarios_present"] is False
    assert first["ordinary_shares"]["count"] == "100"
    assert first["working_capital_cash_component"] is None
    assert "scenarios" not in first
    assert first["formal_eligibility"] is False and first["action"] == "no_order"
    spec["scenarios"] = {"bull": {"value": "999999"}}
    second = target.read_parent_cash_agent_facts(
        root=tmp_path, spec_binding=_bound(tmp_path, spec), now=NOW)
    assert second["input_fingerprint"] == first["input_fingerprint"]


def test_parent_facts_reject_bad_binding_scope_and_future(monkeypatch, tmp_path):
    spec = _source(monkeypatch)
    binding = _bound(tmp_path, spec)
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        target.read_parent_cash_agent_facts(root=tmp_path,
            spec_binding={**binding, "sha256": "0" * 64}, now=NOW)
    spec["scope"] = "CONSOLIDATED"
    with pytest.raises(ValueError, match="SOURCE_SCOPE_INVALID"):
        target.read_parent_cash_agent_facts(root=tmp_path,
            spec_binding=_bound(tmp_path, spec), now=NOW)
    spec["scope"] = target.SCOPE
    with pytest.raises(ValueError, match="FUTURE_SOURCE"):
        target.read_parent_cash_agent_facts(root=tmp_path,
            spec_binding=_bound(tmp_path, spec), now=datetime(2026, 11, 15, tzinfo=timezone.utc))
