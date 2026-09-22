import importlib.util
import json
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_finance_cost_scope_sensitivity",
    ROOT / "scripts" / "analyze_moutai_finance_cost_scope_sensitivity.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_finance_cost_scale_is_explicit_research_only_and_does_not_admit_trade():
    result = MODULE.analyze()
    assert Decimal(result["observed_price_cny"]) == Decimal("1275.16")
    assert Decimal(result["finance_reference_scale"]["annualized_reference_scale_cny"]) == Decimal("1548000000")
    assert len(result["results"]) == 1296
    assert result["scope_approved"] is False
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
    assert result["robust_no_entry_under_this_sensitivity"] is True


def test_zero_case_reproduces_and_reference_case_never_decreases_value():
    result = MODULE.analyze()
    rows = {}
    for row in result["results"]:
        key = tuple(row[field] for field in ("scenario", "discount_rate", "capital_anchor", "nwc_case", "reserve_days", "payment_basis", "tax_case"))
        rows.setdefault(key, {})[row["reference_scale_multiplier"]] = row
    assert len(rows) == 648
    for group in rows.values():
        zero, reference = group["0"], group["1"]
        assert Decimal(zero["incremental_conditional_equity_cny"]) == 0
        assert Decimal(zero["adjusted_conditional_equity_cny"]) == Decimal(zero["original_conditional_equity_cny"])
        assert Decimal(reference["adjusted_conditional_equity_cny"]) >= Decimal(reference["original_conditional_equity_cny"])


def test_expense_ceiling_reconciles_independently_and_keeps_crossing_counterexamples():
    result = MODULE.analyze()
    forecast = json.loads(MODULE.OPERATING.read_text(encoding="utf-8"))
    dcf = json.loads(MODULE.DCF.read_text(encoding="utf-8"))
    equity = json.loads(MODULE.INTEGRATED.read_text(encoding="utf-8"))
    ceiling = result["expense_removal_ceiling"]
    assert len(ceiling["cases"]) == len(equity["results"])
    for row, source in zip(ceiling["cases"], equity["results"]):
        annual = next(item["annual_calculations"] for item in dcf["results"]
                      if all(item[k] == source[k] for k in ("scenario", "capital_anchor", "nwc_case", "discount_rate")))
        amounts = [sum(float(period["future_operating_amounts"][k]) for k in
                       ("surcharges", "selling", "admin", "research")) * (1 - float(a["cash_tax_rate"]))
                   for period, a in zip(forecast["results"][source["scenario"]], annual)]
        pv = sum(amount * float(a["discount_factor"]) for amount, a in zip(amounts, annual))
        pv += amounts[-1] / float(source["discount_rate"]) * float(annual[-1]["discount_factor"])
        expected = (float(source["conditional_equity_value"]) + pv) / float(source["disclosed_share_assumption"])
        assert abs(expected - float(row["all_shared_expenses_removed_value_cny"])) < 0.000001
    crossing = [row for row in ceiling["cases"] if row["crosses_30pct_entry"]]
    assert len(crossing) == ceiling["crossing_cases"] == 72
    assert {(row["scenario"], row["discount_rate"]) for row in crossing} == {("bull", "0.06")}
    assert result["simulation_eligible"] is False
