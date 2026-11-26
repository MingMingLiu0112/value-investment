"""Conditional maturity timing must conserve the debt pool and its cash interest."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import parent_cash_maturity_recheck as recheck
from value_investment_agent.application.product.common import _native_path


def example():
    first = {"new_borrowing": "20", "debt_repayment": "30"}
    later = {"new_borrowing": "9", "debt_repayment": "20", "interest_outside_cfo": "3"}
    context = dict(opening={"debt": "100"}, years=[dict(year=2026, policy=first),
                   *(dict(year=y, policy=dict(later)) for y in (2027, 2028, 2029))],
                   terminal=dict(policy=dict(new_borrowing="10", debt_repayment="10", interest_outside_cfo=".50"),
                                 financing={"mode": "CONSTANT_DEBT_REFINANCING"}))
    return context, dict(year=2027, proxy_residual_cny="70", known_principal_cny="20")


@pytest.mark.parametrize(("pay_year", "expected"), [
    (2027, [(90, 0, 4.5), (0, 0, 0), (0, 0, 0)]),
    (2028, [(20, 70, 4.5), (70, 0, 3.5), (0, 0, 0)]),
])
def test_each_endpoint_preserves_principal_and_interest(pay_year, expected):
    context, evidence = example()
    snapshot = deepcopy(context)
    updated, plan = recheck._prepare(context, evidence, Decimal(".05"), Decimal("1"), pay_year)
    assert context == snapshot and context["years"][0] == updated["years"][0]
    for row, cash, (repay, remaining, interest) in zip(plan, updated["years"][1:], expected, strict=True):
        assert Decimal(row["new_borrowing_cny"]) == Decimal(cash["policy"]["new_borrowing"]) == 0
        assert Decimal(row["closing_proxy_residual_cny"]) == remaining
        assert Decimal(row["interest_cny"]) == Decimal(cash["policy"]["interest_outside_cfo"]) == interest
        assert Decimal(cash["policy"]["debt_repayment"]) == repay
    assert updated["terminal"] == {"policy": dict(new_borrowing="0", debt_repayment="0", interest_outside_cfo="0")}


@pytest.mark.parametrize(("fault", "error"), [
    ("incomplete_horizon", "EXPLICIT_YEARS"), ("skipped_year", "EXPLICIT_YEARS"),
    ("unexplained_opening_debt", "OPENING_POOL"), ("other_interest", "TERMINAL_FINANCING"),
    ("unexplained_terminal_borrowing", "TERMINAL_FINANCING"),
])
def test_unsupported_cash_boundaries_fail_closed(fault, error):
    context, evidence = example()
    if fault == "incomplete_horizon":
        context["years"] = context["years"][:2]
    elif fault == "skipped_year":
        context["years"][1]["year"] = 2026
    elif fault == "unexplained_opening_debt":
        context["opening"]["debt"] = "75"
    elif fault == "other_interest":
        context["terminal"]["policy"]["interest_outside_cfo"] = "2"
    else:
        context["terminal"]["policy"]["new_borrowing"] = "11"
    with pytest.raises(ValueError, match=error):
        recheck._prepare(context, evidence, Decimal(".05"), Decimal("1"), 2028)


@pytest.mark.parametrize(("result", "statuses"), [
    (dict(status="REJECTED", ledger={"year": 2028}), ["BEFORE_FIRST_FAILURE", "NOT_COMPLETED", "NOT_REACHED"]),
    (dict(status="CALCULATED"), ["CALCULATED_CONDITIONAL"] * 3),
])
def test_plan_zero_balance_does_not_mark_a_rejected_repayment_as_completed(result, statuses):
    plan = [dict(year=y, closing_proxy_residual_cny="70" if y == 2027 else "0") for y in (2027, 2028, 2029)]
    outcome = recheck._with_payment_plan(result, plan)
    assert outcome["financing_rows_basis"] == "CONDITIONAL_PAYMENT_PLAN"
    assert outcome["first_failed_year"] == result.get("ledger", {}).get("year")
    assert [r["payment_status"] for r in outcome["financing_rows"]] == statuses


def test_original_statement_line_must_be_unique():
    line = "短期借款 1,200.20 666.00"
    assert recheck._statement_amount(line, "短期借款") == Decimal("1200.20")
    with pytest.raises(ValueError, match="UNIQUE_ORIGINAL"):
        recheck._statement_amount(line + "\n" + line, "短期借款")


@pytest.mark.skipif(not os.environ.get("VALUE_FUNDING_REVISION_REAL_ROOT"), reason="requires vf1 source archive")
def test_real_ed62_originals_and_all_six_cash_paths(tmp_path):
    root = Path(os.environ["VALUE_FUNDING_REVISION_REAL_ROOT"]).resolve()
    task = "rt-07724f7f1c8566420935f07b70c846a1"
    digest = "ed62be290ebcffebf47e1c22cd235d77767e42f1d8b13ff4f1273875257c0a19"
    folder = Path(_native_path(root / "runtime/parent-cash-task-backed-receipts" / task / "funding-revisions" / digest))
    snapshot = {p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    result = recheck.run_check(root, task, digest, datetime.now(timezone.utc))
    assert snapshot == {p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    assert result["schema_version"] == "parent-cash-maturity-recheck-v1"
    assert result["parent_receipt"] == digest and result["task_id"] == task
    assert result["predecessor_input"] == "bf871783c5f27aeb098419c45c656ecea702fd9d74a3706ba2325d0d8cb53934"
    assert result["symbol"] == "600887" and result["valuation_date"] == "2025-12-31"
    assert result["action"] == "no_order" and all(result[key] is False for key in
        ("current_comparable", "formal_eligibility", "current_research_range_adopted"))
    evidence = result["maturity_evidence"]
    expected = dict(known_principal_cny="3500000000", proxy_residual_cny="8779665769.24",
                    q3_carrying_basket_cny="8153071465.18", proxy_minus_basket_cny="626594304.06",
                    q3_short_borrowing_cny="7529908914.86", total_repayment_min_cny="3500000000",
                    total_repayment_max_cny="12279665769.24", registration_ceiling_cny="45000000000",
                    observed_issuance_cny="45000000000", assumed_future_borrowing_cny="0")
    assert all(Decimal(evidence[k]) == Decimal(v) for k,v in expected.items())
    assert evidence["first_year"] == 2026 and evidence["zero_new_borrowing_from_year"] == 2027
    assert evidence["first_year_issue_proceeds_basis"] == "DISCLOSED_ISSUANCE_ASSUMED_RECEIVED_AT_PAR"
    assert Decimal(evidence["first_year_issue_proceeds_assumed_at_par_cny"]) == Decimal("45000000000")
    assert evidence["q3_basket_components_cny"]["其他流动负债整行"] == "535402071.80"
    assert evidence["actual_unknown_maturity_cny"] is evidence["actual_total_principal_upper_cny"] is None
    assert evidence["short_borrowing_window_start"] == "2026-10-01" and evidence["short_borrowing_window_end"] == "2027-09-30"
    assert result["status"] == "REJECTED" and result["scenarios"]["bear"]["ledger"]["year"] == 2027
    assert [(r["maturity"], Decimal(r["principal_cny"])) for r in evidence["known_maturities"]] == [
        ("2027-11-12", Decimal("3500000000"))]
    for name, gap in [("bear", "7197611949.212575"), ("base", "3272834622.2900"), ("bull", "1671030863.464875")]:
        rejected = result["scenarios"][name]
        assert rejected["status"] == "REJECTED" and rejected["ledger"]["year"] == 2027
        assert Decimal(rejected["ledger"]["shortfall_cny"]) == Decimal(gap)
    alt = result["alternative_scenarios"]
    assert alt["bear"]["ledger"]["year"] == 2028
    assert Decimal(alt["bear"]["ledger"]["shortfall_cny"]) == Decimal("3951173492.950250")
    assert alt["base"]["per_share_value"] == "8.98717961207652398919117565669938023327721586267"
    assert alt["bull"]["per_share_value"] == "11.9958147420251084907227153529895226339978384764"
    for pay_year, name in [(2027,"scenarios"), (2028,"alternative_scenarios")]:
        assert set(result[name]) == {"bear","base","bull"}
        for scenario in result[name].values():
            rows = scenario["financing_rows"]
            assert scenario["financing_rows_basis"] == "CONDITIONAL_PAYMENT_PLAN" and rows[0]["year"] == 2027
            failed = scenario["first_failed_year"]
            if scenario["status"] == "REJECTED":
                assert failed == scenario["ledger"]["year"]
                assert [r["payment_status"] for r in rows if r["year"] == failed] == ["NOT_COMPLETED"]
                assert all(r["payment_status"] == "NOT_REACHED" for r in rows if r["year"] > failed)
            else:
                assert failed is None and all(r["payment_status"] == "CALCULATED_CONDITIONAL" for r in rows)
            assert all(Decimal(r["new_borrowing_cny"]) == 0 for r in rows)
            assert sum(Decimal(r["assumed_proxy_repayment_cny"]) for r in rows) == Decimal("8779665769.24")
            assert next(r for r in rows if r["year"] == pay_year)["assumed_proxy_repayment_cny"] == "8779665769.24"
            if scenario["status"] == "CALCULATED":
                assert Decimal(scenario["terminal_closing_debt_cny"]) == 0
                assert Decimal(scenario["per_share_value"]) > 0
            else:
                assert scenario["status"] == "REJECTED" and "per_share_value" not in scenario
                assert Decimal(scenario["ledger"]["shortfall_cny"]) > 0
    # Make the exact real outcome available to the integration run under its review basetemp.
    (tmp_path / "maturity-recheck.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
