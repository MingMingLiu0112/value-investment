import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_conditional_replay", ROOT / "scripts" / "replay_moutai_historical_conditional_valuation.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_replay_is_point_in_time_and_never_approves_a_value_or_trade():
    rows = json.loads(MODULE.INPUT.read_text(encoding="utf-8"))
    replay = MODULE.replay(rows, MODULE.read_cases())
    assert len(replay) == 2674
    assert all(row["input_available_at"] <= row["decision_at"] for row in replay)
    assert all(row["formal_fair_value"] is None and not row["valuation_approved"] and not row["trade_approved"] for row in replay)


def test_first_annual_case_is_blocked_and_later_cases_preserve_denominator_gap():
    cases = MODULE.read_cases()
    first_values, first_blockers = MODULE.conditional_values(cases[0], None)
    assert first_values == []
    assert "prior_annual_operating_nwc_not_available" in first_blockers
    values, blockers = MODULE.conditional_values(cases[1], cases[0])
    assert not blockers
    assert any(row["per_share_value_cny"] is None and row["status"].startswith("blocked_") for row in values)
    assert any(row["per_share_value_cny"] is not None for row in values)


def test_frozen_inputs_reproduce_identical_experimental_replay():
    rows = json.loads(MODULE.INPUT.read_text(encoding="utf-8"))
    assert MODULE.replay(rows, MODULE.read_cases()) == MODULE.replay(rows, MODULE.read_cases())


def test_shared_cost_allocation_does_not_scale_direct_product_profit():
    current, prior = MODULE.read_cases()[1:3]
    values, blockers = MODULE.conditional_values(prior, current)
    assert not blockers
    shared = MODULE.Decimal(prior["facts"]["shared_cost_proxy_cny"])
    direct = MODULE.Decimal(prior["facts"]["direct_revenue_less_cost_cny"])
    row_100 = next(row for row in values if row["industrial_share"] == "1.00" and row["per_share_value_cny"] is not None)
    row_80 = next(row for row in values if row["industrial_share"] == "0.80" and row["per_share_value_cny"] is not None
                      and all(row[key] == row_100[key] for key in ("nwc", "tax_rate", "wacc", "terminal_growth")))
    delta_after_tax = shared * MODULE.Decimal("0.20") * (MODULE.Decimal("1") - MODULE.Decimal(row_100["tax_rate"]))
    assert MODULE.Decimal(row_100["fcff_proxy_cny"]) + delta_after_tax == MODULE.Decimal(row_80["fcff_proxy_cny"])
    assert direct - shared == MODULE.Decimal(prior["facts"]["operating_subtotal_cny"])


def test_research_export_keeps_experimental_replay_outside_formal_value_path():
    import sys
    sys.path.insert(0, str(ROOT / 'src'))
    from value_investment_agent.company_research_export import load_historical_conditional_replay_status
    text = load_historical_conditional_replay_status(ROOT)
    assert '2603日' in text
    assert '不是正式合理价' in text
