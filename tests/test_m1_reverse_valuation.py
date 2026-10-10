from __future__ import annotations

from decimal import Decimal
from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from value_investment_agent import m1_valuation_package_builder
from value_investment_agent.quote_snapshot import (
    QUOTE_STATUS_VERIFIED_CLOSE,
    QuoteSnapshot,
)
from value_investment_agent.m1_reverse_valuation import (
    STATUS_ABOVE_ENVELOPE,
    STATUS_BELOW_ENVELOPE,
    STATUS_CONDITIONAL_SOLUTION,
    _bounded_inverse,
    reverse_for_descriptor,
)
from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_reverse_valuation_inputs(monkeypatch):
    # Reverse diagnostics consume facts and quotes, not dividend research assets.
    monkeypatch.setattr(
        m1_valuation_package_builder,
        "optional_dividend_result_for_symbol",
        lambda root, symbol: None,
    )
    prices = {"600887": "26.77", "600741": "14.92", "000651": "38.18"}

    def fixture_quote(payload, *, root):
        symbol = payload["fixture_symbol"]
        evidence = f"synthetic reverse valuation close: {symbol}:{prices[symbol]}"
        return QuoteSnapshot(
            symbol=symbol,
            quote_date=date(2026, 9, 22),
            current_price=Decimal(prices[symbol]),
            status=QUOTE_STATUS_VERIFIED_CLOSE,
            evidence_refs=[{
                "id": f"reverse_test_quote_{symbol}",
                "kind": "synthetic_test_fixture",
                "sha256": sha256(evidence.encode("utf-8")).hexdigest(),
            }],
        )

    monkeypatch.setattr(m1_valuation_package_builder, "build_quote", fixture_quote)


def _results(symbol: str):
    payload = dict(load_descriptor_payloads(ROOT)[symbol])
    payload["quote"] = {"fixture_symbol": symbol}
    # Event-scan admission is covered separately; this diagnostic does not use it.
    payload["model_validity_input"] = None
    descriptor = build_descriptor(
        payload,
        root=ROOT,
    )
    assert descriptor.distribution_result is None
    return descriptor, {
        result.driver: result
        for result in reverse_for_descriptor(descriptor)
    }


def test_residual_income_reverse_valuation_stays_inside_registered_envelope():
    _, results = _results("600887")

    terminal = results["terminal_roe"]
    cost = results["cost_of_equity"]

    assert terminal.target_price == Decimal("26.77")
    assert terminal.status == STATUS_ABOVE_ENVELOPE
    assert terminal.solution is None
    assert terminal.repriced_value is None
    assert terminal.lower_bound == Decimal("0.09")
    assert terminal.upper_bound == Decimal("0.17")
    assert terminal.action == "no_order"

    assert cost.status == STATUS_ABOVE_ENVELOPE
    assert cost.lower_bound == Decimal("0.0682")
    assert cost.upper_bound == Decimal("0.0918")
    assert cost.solution is None


def test_fcff_reverse_valuation_reports_below_the_registered_envelope():
    _, results = _results("600741")

    roic = results["terminal_roic"]
    wacc = results["wacc"]

    assert roic.target_price == Decimal("14.92")
    assert roic.status == STATUS_BELOW_ENVELOPE
    assert roic.lower_bound == Decimal("0.06")
    assert roic.upper_bound == Decimal("0.10")
    assert roic.solution is None
    assert roic.action == "no_order"

    assert wacc.status == STATUS_BELOW_ENVELOPE
    assert wacc.lower_bound == Decimal("0.0732")
    assert wacc.upper_bound == Decimal("0.0968")
    assert wacc.solution is None


def test_gree_reverse_valuation_uses_verified_quote_without_solution():
    _, results = _results("000651")

    assert set(results) == {"terminal_roic", "wacc"}
    assert all(result.status == STATUS_BELOW_ENVELOPE for result in results.values())
    assert all(
        result.target_price == Decimal("38.18")
        for result in results.values()
    )
    assert all(result.solution is None for result in results.values())
    assert all(result.action == "no_order" for result in results.values())


def test_bounded_inverse_solves_without_extending_envelope():
    increasing = _bounded_inverse(
        target=Decimal("102"),
        lower=Decimal("-0.05"),
        upper=Decimal("0.05"),
        value_at=lambda driver: Decimal("100") * (Decimal("1") + driver),
        increasing=True,
    )
    decreasing = _bounded_inverse(
        target=Decimal("95"),
        lower=Decimal("0.01"),
        upper=Decimal("0.10"),
        value_at=lambda driver: Decimal("100") * (Decimal("1") - driver),
        increasing=False,
    )

    assert increasing["status"] == STATUS_CONDITIONAL_SOLUTION
    assert abs(Decimal(increasing["solution"]) - Decimal("0.02")) < Decimal("0.000001")
    assert decreasing["status"] == STATUS_CONDITIONAL_SOLUTION
    assert abs(Decimal(decreasing["solution"]) - Decimal("0.05")) < Decimal("0.000001")


def test_bounded_inverse_rejects_non_monotonic_envelope():
    with pytest.raises(ValueError, match="monotonic"):
        _bounded_inverse(
            target=Decimal("100"),
            lower=Decimal("0"),
            upper=Decimal("1"),
            value_at=lambda driver: Decimal("100") - driver,
            increasing=True,
        )
