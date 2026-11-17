"""TEST_ONLY annual cash sufficiency checks for numbered parent evidence."""
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_staged_v3 as staged
from value_investment_agent.domain.valuation.parent_direct_operating_cash import SCOPE


def test_numbered_annual_history_drives_cash_preflight(monkeypatch, tmp_path):
    spec = {
        "symbol": "000568", "valuation_date": "2025-12-31",
        "opening": {"cash": {"classification": "FACT", "anchor": "cash"}},
    }
    historical = {
        "symbol": "000568", "scope": SCOPE, "currency": "CNY",
        "classification": "FACT", "period_start": "2025-01-01",
        "period_end": "2025-12-31", "source_refs": [{"TEST_ONLY": True}],
        "revenue": "100", "cost": "50", "customer_cash": "90",
        "supplier_cash": "40", "cfo": "30",
    }
    monkeypatch.setattr(staged, "_load_spec", lambda *_args: spec)
    monkeypatch.setattr(staged, "_historical_parent_operating_cash",
                        lambda **_kwargs: historical)
    context = {
        "symbol": "000568", "valuation_date": "2025-12-31",
        "opening_fact_anchors": {"cash": "cash"},
        "facts": {"cash": {"field": "closing_cash_and_equivalents_cny",
                           "period_end": "2025-12-31", "scope": SCOPE,
                           "value_cny": "5"}},
    }
    operating = {
        "years": [2026],
        "series": {name: {"values": [value]} for name, value in {
            "revenue": "100", "cost": "50", "other_operating_cash": "-20",
        }.items()},
    }
    policy = {
        "years": [2026],
        "series": {name: {"values": ["0"]} for name in (
            "investment_cash_received", "new_borrowing", "maintenance_capex",
            "growth_capex", "commitments_outside_capex", "debt_repayment",
            "interest_outside_cfo", "other_mandatory_cash", "cash_floor")},
    }
    args = dict(root=tmp_path, spec_binding={"TEST_ONLY": True},
                evaluated_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
                context=context, operating=operating, policy=policy)
    staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["maintenance_capex"]["values"] = ["40"]
    with pytest.raises(ValueError, match="UNFUNDED_CASH_REQUIREMENT:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
