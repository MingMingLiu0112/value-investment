"""Cash replay must distinguish a historical closing balance from new cash."""
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import parent_h1_opening_cash_v1 as opening


def test_replays_exact_parent_h1_and_rejects_wrong_period_or_cash(tmp_path, monkeypatch):
    spec = dict(action="no_order", scope=opening.SCOPE, currency="CNY",
                source_adapter_version="NUMBERED_CNINFO_V2", symbol="600001",
                issuer_name="TEST_ONLY", owner_sources=[])
    monkeypatch.setattr(opening, "_read", lambda *_: spec)
    fields = dict(opening_cash_cny="100", closing_cash_cny="106",
                  cfo_cny="20", cfi_cny="-6", cff_cny="-7", fx_cny="-1",
                  reported_net_change_cny="6")
    period = "2026-06-30"
    h1 = dict(symbol="600001", period_start="2026-01-01", period_end=period,
              period_basis="H1", scope=opening.SCOPE, currency="CNY",
              checks={"cash_statement_reconciled": True},
              cash_flow={opening._FIELDS[key]: {"current": amount, "source_refs": [{"field": key}]}
                         for key, amount in fields.items()})
    monkeypatch.setattr(opening, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_: {"statements": [h1]})
    args = dict(root=tmp_path, spec_binding={"path": "runtime/spec.json", "sha256": "a"*64},
                now=datetime(2026, 11, 21, tzinfo=timezone.utc))
    result = opening.read_parent_h1_opening_cash(period_end=period, **args)
    assert result["forward_opening_cash_cny"] == "106"
    assert result["historical_flows_already_consumed"] is True
    assert result["comparison_date_cash_cny"] is result["distribution_capacity_cny"] is None
    assert result["field_sources"]["closing_cash_cny"] == [{"field": "closing_cash_cny"}]
    with pytest.raises(ValueError, match="H1_OPENING_EXACT_PERIOD_REQUIRED"):
        opening.read_parent_h1_opening_cash(period_end="2026-12-31", **args)
    h1["cash_flow"][opening._FIELDS["closing_cash_cny"]]["current"] = "107"
    with pytest.raises(ValueError, match="do not reconcile exactly"):
        opening.read_parent_h1_opening_cash(period_end=period, **args)
