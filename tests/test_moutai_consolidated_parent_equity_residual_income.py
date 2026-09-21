from decimal import Decimal
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_parent_equity_residual_income", ROOT / "scripts" / "value_moutai_consolidated_parent_equity.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_bounded_residual_income_scenarios_are_ordered_and_not_formal_values():
    result = MODULE.build()
    values = [Decimal(row["conditional_value_per_2025_issued_share_cny"]) for row in result["results"]]
    assert values[0] <= values[1] <= values[2]
    assert all(Decimal(row["terminal_growth"]) < Decimal(row["cost_of_equity_cny_nominal"])
               for row in result["results"])
    assert all(Decimal(year["retention_assumption"]) == Decimal("0.30")
               for row in result["results"] for year in row["forecast_years"])
    assert result["formal_fair_value"] is None
    assert result["safety_margin"] is None
    assert result["valuation_approved"] is False
    assert result["simulation_eligible"] is False
    assert result["trade_approved"] is False
    assert result["model_version"] == "moutai-consolidated-parent-equity-residual-income-v2"
    assert result["facts"]["report_available_at"] == "2026-04-18T00:00:00+08:00"
    assert result["facts"]["share_evidence"]["monetary_capital_used_as_shares"] is False
    assert all(abs(Decimal(row["dividend_crosscheck_difference_cny"])) < Decimal("0.01")
               for row in result["results"])


def test_legacy_facts_with_early_disclosure_cannot_be_reused(monkeypatch):
    path = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-20260913T102909Z/evidence.json"
    monkeypatch.setattr(MODULE, "INPUT", path)
    monkeypatch.setattr(MODULE, "INPUT_SHA256", MODULE.digest(path))
    with pytest.raises(ValueError, match="fact chain"):
        MODULE.build()


@pytest.mark.parametrize("terminal_roe", ["0.08", "0.10", "0.12"])
def test_terminal_uses_opening_equity_and_allows_below_cost_returns(terminal_roe):
    result = MODULE.scenario_value(Decimal("1000"), Decimal("10"), Decimal("0.10"), {
        "forecast_roe": ("0.12",), "terminal_roe": terminal_roe, "terminal_growth": "0.02"})
    # One explicit dividend of 84; retained earnings leave 1,036 of equity.
    expected_terminal_dividend = (Decimal(terminal_roe) - Decimal("0.02")) * Decimal("1036")
    expected_equity = (Decimal("84") + expected_terminal_dividend / Decimal("0.08")) / Decimal("1.10")
    assert abs(Decimal(result["conditional_equity_value_cny"]) - expected_equity) < Decimal("1e-20")
    assert Decimal(result["terminal_opening_book_equity_cny"]) == Decimal("1036")
    if terminal_roe == "0.08":
        assert Decimal(result["conditional_equity_value_cny"]) < Decimal("1000")
        assert Decimal(result["present_value_terminal_residual_income_cny"]) < 0


def test_cost_of_equity_returns_value_the_claim_at_book():
    result = MODULE.scenario_value(Decimal("1000"), Decimal("10"), Decimal("0.10"), {
        "forecast_roe": ("0.10", "0.10"), "terminal_roe": "0.10", "terminal_growth": "0.02"})
    assert Decimal(result["conditional_equity_value_cny"]) == Decimal("1000")
    assert Decimal(result["terminal_residual_income_cny"]) == 0


@pytest.mark.parametrize("cost,roe,growth", [("0.10", "0.12", "0.10"),
                                            ("0.10", "0.01", "0.02"),
                                            ("NaN", "0.12", "0.02")])
def test_invalid_or_unfunded_terminal_assumptions_are_rejected(cost, roe, growth):
    with pytest.raises(ValueError):
        MODULE.scenario_value(Decimal("1000"), Decimal("10"), Decimal(cost), {
            "forecast_roe": ("0.12",), "terminal_roe": roe, "terminal_growth": growth})


def test_retained_capital_does_not_automatically_compound_historical_profit():
    roes = MODULE.current_projection(Decimal("1000"), Decimal("200"), Decimal("0.08"),
                                    Decimal("0"), Decimal("0.75"), 5, 5)
    result = MODULE.scenario_value(Decimal("1000"), Decimal("10"), Decimal("0.08"), {
        "forecast_roe": roes, "retention": "0.25", "terminal_roe": "0.08", "terminal_growth": "0.02"})
    annuals = result["forecast_years"]
    assert all(abs(Decimal(row["net_income_assumption_cny"]) - 200) < Decimal("1e-20") for row in annuals[:5])
    assert Decimal(annuals[4]["closing_book_equity_cny"]) > Decimal(annuals[0]["closing_book_equity_cny"])
    assert Decimal(annuals[4]["roe_assumption"]) < Decimal(annuals[0]["roe_assumption"])
    assert Decimal(annuals[-1]["roe_assumption"]) == Decimal("0.08")
    assert Decimal(result["terminal_residual_income_cny"]) == 0
    assert Decimal(result["terminal_first_dividend_cny"]) > 0


def test_current_time_transport_matches_independent_future_dividend_prices():
    basis = datetime.fromisoformat("2026-06-30T23:59:59+08:00")
    args = (Decimal("1000"), Decimal("10"), Decimal("200"), Decimal("0.08"),
            Decimal("0"), Decimal("0.75"), 5, 5, Decimal("0.02"), basis)
    origin = MODULE.current_value(*args, basis)
    later = MODULE.current_value(*args, datetime.fromisoformat("2026-09-14T19:50:50+08:00"))
    assert Decimal(later["conditional_current_equity_value_cny"]) > Decimal(origin["conditional_current_equity_value_cny"])
    assert abs(Decimal(later["current_dividend_crosscheck_difference_cny"])) < Decimal("0.01")
    assert later["basis_origin_calculation"] == origin["basis_origin_calculation"]
    assert "conditional_value_per_2025_issued_share_cny" not in later["basis_origin_calculation"]
    assert later["basis_origin_calculation"]["forecast_years"][0]["assumed_payment_at"] == "2027-06-30T23:59:59+08:00"
    with pytest.raises(ValueError, match="payment period"):
        MODULE.current_value(*args, datetime.fromisoformat("2027-07-01T00:00:00+08:00"))


def test_current_model_rejects_capital_refresh_collected_after_valuation_time():
    with pytest.raises(ValueError, match="Capital refresh was not available"):
        MODULE.build_current(ROOT / "docs/moutai-current-equity-policy-v1.json",
                             datetime.fromisoformat("2026-09-16T19:50:50+08:00"))


@pytest.mark.parametrize("as_of", ["2026-06-30T23:59:59+08:00", "2026-08-16T00:00:00+08:00",
                                   "2026-09-14T19:50:48+08:00", "2026-09-15T15:00:00+08:00",
                                   "2026-09-14T19:50:50"])
def test_current_model_cannot_backfill_policy_or_use_uncovered_date(as_of):
    with pytest.raises(ValueError):
        MODULE.build_current(ROOT / "docs/moutai-current-equity-policy-v1.json", datetime.fromisoformat(as_of))


def test_current_model_rejects_modified_source_bytes(monkeypatch):
    original = MODULE.digest
    monkeypatch.setattr(MODULE, "digest", lambda path: "wrong" if path.name == "600519-1225475868.pdf" else original(path))
    with pytest.raises(ValueError, match="source changed"):
        MODULE.build_current(ROOT / "docs/moutai-current-equity-policy-v1.json",
                             datetime.fromisoformat("2026-09-14T19:50:50+08:00"))
