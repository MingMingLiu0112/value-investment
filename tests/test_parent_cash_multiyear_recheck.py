"""Direct tests for caps, cash floors and preservation of unpaid principal."""
from copy import deepcopy
from decimal import Decimal

import pytest

from value_investment_agent.application.research import parent_cash_multiyear_recheck as service


def _context(cash_by_year):
    base = dict.fromkeys(service.kernel.FLOW_KEYS, "0")
    base.update(parent_profit="10", cash_floor="100")
    years = [dict(year=year, scheduled_owner_distribution_cny="0",
                  policy=dict(base, operating_cash=str(cash), debt_repayment="10" if year == 2026 else "0"))
             for year, cash in enumerate(cash_by_year, 2026)]
    context = dict(opening=dict(book="500", debt="100", cash="150", capacity="100"), years=years,
                   terminal=dict(policy=dict(base, new_borrowing="10", debt_repayment="10",
                                             interest_outside_cfo="0.50")),
                   ordinary_shares="1", cost_of_equity="0.1")
    evidence = dict(year=2027, proxy_residual_cny="70", known_principal_cny="20",
                    comparable_parent_net_repayment_observations=[dict(net_repayment_cny="60"),
                                                                   dict(net_repayment_cny="30")])
    return context, evidence


def _prepare(context, evidence):
    known = [dict(maturity="2027-11-12", principal_cny="20")]
    return service._prepare(context, evidence, Decimal(".05"), Decimal("1"), Decimal(0), known,
                            {"prospective_debt_service": {"issues": []}})


@pytest.mark.parametrize("cash_by_year, amounts, remaining", [
    ([10, 100, 100, 100], ["30", "30", "10"], "0"),
    ([10, 100, 10, 100], ["30", "8", "30"], "2"),
])
def test_every_year_uses_same_cap_and_retains_unpaid_debt(cash_by_year, amounts, remaining):
    original, evidence = _context(cash_by_year)
    snapshot = deepcopy(original)
    revised, plan, basis, blocked = _prepare(original, evidence)
    assert original == snapshot and revised["years"][0] == original["years"][0]
    assert [Decimal(row["assumed_proxy_repayment_cny"]) for row in plan] == list(map(Decimal, amounts))
    assert [Decimal(row["known_principal_cny"]) for row in plan] == [20, 0, 0]
    assert all(row["new_borrowing_cny"] == "0" for row in plan)
    assert Decimal(plan[-1]["closing_proxy_residual_cny"]) == Decimal(remaining)
    assert basis["annual_historical_net_repayment_cap_cny"] == "30"
    assert basis["financing_condition_verified"] is False
    assert [Decimal(row["interest_cny"]) for row in plan[:2]] == [Decimal("4.50"), Decimal("2.00")]
    if remaining == "0":
        assert blocked is None
    else:
        assert blocked["status"] == "REJECTED"
        assert blocked["reason"] == "MULTIYEAR_TERMINAL_PRINCIPAL_REMAINS"
        assert Decimal(blocked["ledger"]["remaining_proxy_principal_cny"]) == Decimal(remaining)
        assert blocked["ledger"]["year"] == 2030


@pytest.mark.parametrize("values, amount", [
    (("70", "30", "80", "8.019"), "8.01"),
    (("70", "30", "6.20", "100"), "6.20"),
    (("70", "30", "80", "-1"), "0"),
])
def test_annual_payment_respects_both_nonborrowed_cash_limits(values, amount):
    assert service._payment(*map(Decimal, values)) == Decimal(amount)


def test_known_principal_still_blocks_at_the_cash_floor():
    context, evidence = _context([10, 0, 100, 100])
    context["opening"]["cash"] = "100"
    _, plan, _, result = _prepare(context, evidence)
    assert result["reason"] == "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027"
    assert [row["known_principal_cny"] for row in plan] == ["20"]
    assert Decimal(plan[0]["closing_proxy_residual_cny"]) == 70



def test_terminal_rejection_keeps_cash_gap_ledger_optional():
    context, evidence = _context([10, 100, 10, 100])
    matrix = {"prospective_debt_service": {"issues": [{"due": "2027-11-12", "face_cny": "20"}]}}
    row = service._calculate(context, {}, Decimal(0), Decimal(0), matrix, evidence,
                             Decimal(".05"), Decimal(1), None, "base")
    assert row["status"] == "REJECTED" and row["first_failed_year"] == 2030
    assert "ledger" not in row and "per_share_value" not in row
    assert Decimal(row["terminal_principal_rejection"]["remaining_proxy_principal_cny"]) == 2
