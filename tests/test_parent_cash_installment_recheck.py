"""Direct tests for the source-bound installment choice and debt conservation."""
from decimal import Decimal

import pytest

from test_parent_cash_maturity_recheck import example
from value_investment_agent.application.research import parent_cash_installment_recheck as service


@pytest.mark.parametrize("exchange", [("40", "30", "25", "25"), ("12", "20", "100", "12"),
                                       ("50", "-1", "100", "0")])
def test_installment_excludes_investment_receipts_and_reserves(monkeypatch, exchange):
    generated, headroom, historical, expected = map(Decimal, exchange)
    context, evidence = example()
    context.update(ordinary_shares="1", cost_of_equity="0.10")
    for row in context["years"]:
        row["scheduled_owner_distribution_cny"] = "0"
    evidence["comparable_parent_net_repayment_observations"] = [
        dict(net_repayment_cny=str(historical + 10), source_sha256="1" * 64, period_end="2026-09-30"),
        dict(net_repayment_cny=str(historical), source_sha256="1" * 64, period_end="2025-09-30"),
    ]
    monkeypatch.setattr(service.kernel, "_step", lambda *args, **kwargs: (
        {}, {"cash": Decimal("100") + headroom - generated}))

    def flow(policy):
        return dict.fromkeys(("maintenance_capex", "growth_capex", "commitments_outside_capex",
                              "interest_outside_cfo", "other_mandatory_cash", "debt_repayment"), Decimal(0)) | {
                                  "operating_cash": generated, "cash_floor": Decimal("100"),
                                  "investment_cash_received": Decimal("1000000")}
    monkeypatch.setattr(service.kernel, "_flow", flow)
    plan = [{"opening_proxy_residual_cny": "70"}]
    amount, basis = service._installment(context, plan, evidence, Decimal(0))
    assert amount == expected
    assert basis["historical_net_repayment_observations"] == evidence["comparable_parent_net_repayment_observations"]
    assert Decimal(basis["historical_parent_net_repayment_cny"]) == historical


@pytest.mark.parametrize("amount", ["0", "30", "70"])
def test_installment_keeps_exact_principal_and_interest(monkeypatch, amount):
    context, evidence = example()
    installment = Decimal(amount)
    monkeypatch.setattr(service, "_installment", lambda *args: (installment, {}))
    corrected, plan, basis = service._prepare(context, evidence, Decimal(".05"), Decimal(1), Decimal(0))
    remaining = Decimal(70) - installment
    assert Decimal(plan[0]["closing_proxy_residual_cny"]) == remaining
    assert Decimal(plan[1]["opening_proxy_residual_cny"]) == remaining
    assert Decimal(plan[1]["assumed_proxy_repayment_cny"]) == remaining
    assert Decimal(plan[1]["interest_cny"]) == remaining * Decimal(".05")
    assert Decimal(plan[0]["interest_cny"]) == Decimal("4.50")
    assert Decimal(corrected["years"][1]["policy"]["debt_repayment"]) == installment + 20
    assert sum(Decimal(item["assumed_proxy_repayment_cny"]) for item in plan) == Decimal(70)
    assert all(Decimal(item["new_borrowing_cny"]) == 0 for item in plan)
    assert Decimal(basis["remaining_next_year_pressure_cny"]) == remaining
    assert corrected["years"][0] == context["years"][0]


def test_installment_refuses_absent_historical_net_repayment():
    with pytest.raises(ValueError, match="INSTALLMENT_HISTORICAL_NET_REPAYMENT_REQUIRED"):
        service._installment({}, [], dict(comparable_parent_net_repayment_observations=[dict(net_repayment_cny="-1")]),
                             Decimal(0))


def test_source_bound_repayment_history_uses_current_and_comparative_columns(monkeypatch):
    page = ("母公司现金流量表\n取得借款收到的现金 100.00 90.00\n"
            "偿还债务支付的现金 140.00 101.00\n")
    monkeypatch.setattr(service.maturity, "_source_pages", lambda *args: [""] * 13 + [page])
    matrix = dict(sources={"9M26": {"pdf_sha256": "1" * 64}})
    evidence = dict(year=2027, reported_9m_borrowing_cny="100", reported_9m_repayment_cny="140")
    history = service._net_repayment_history(None, {}, matrix, evidence)
    assert [(row["period_end"], row["net_repayment_cny"]) for row in history] == [
        ("2026-09-30", "40.00"), ("2025-09-30", "11.00")]
    assert all(row["physical_page"] == 14 and row["source_sha256"] == "1" * 64 for row in history)
    evidence["reported_9m_borrowing_cny"] = "99"
    with pytest.raises(ValueError, match="INSTALLMENT_PARENT_CASH_COLUMNS_MISMATCH"):
        service._net_repayment_history(None, {}, matrix, evidence)
