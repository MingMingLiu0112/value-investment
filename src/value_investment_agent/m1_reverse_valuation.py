"""Bounded reverse valuation for M1 research packages.

These calculations invert only pre-registered scenario envelopes.  A result
outside the envelope is reported as outside, never extended to manufacture a
matching discount rate or terminal return.  No market price is treated as the
intrinsic value and no order is produced.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Callable, Mapping, Sequence

from .quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE
from .research_input import ResearchInputDescriptor
from .valuation_models.fcff import FCFFScenarioInputs, FinancialFacts
from .valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
    scenario_value,
)

STATUS_CONDITIONAL_SOLUTION = "conditional_solution"
STATUS_ABOVE_ENVELOPE = "above_registered_envelope"
STATUS_BELOW_ENVELOPE = "below_registered_envelope"
STATUS_PENDING_EXTERNAL_DATA = "pending_external_data"
STATUS_NOT_READY = "not_ready"

COST_OF_EQUITY_LOWER = Decimal("0.0682")
COST_OF_EQUITY_UPPER = Decimal("0.0918")
WACC_LOWER = Decimal("0.0732")
WACC_UPPER = Decimal("0.0968")


@dataclass(frozen=True)
class ReverseValuationResult:
    """One bounded inverse with explicit target, driver and evidence."""

    symbol: str
    model_type: str
    driver: str
    target_price: Decimal | None
    quote_date: date | None
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    lower_value: Decimal | None
    upper_value: Decimal | None
    status: str
    solution: Decimal | None
    repriced_value: Decimal | None
    evidence_refs: list[dict[str, Any]]
    blockers: list[str]
    action: str = "no_order"

    def __post_init__(self) -> None:
        if not self.symbol or len(self.symbol) != 6 or not self.symbol.isdigit():
            raise ValueError("Reverse valuation requires a six-digit symbol")
        if not self.model_type.strip() or not self.driver.strip():
            raise ValueError("Reverse valuation model type and driver are required")
        if self.action != "no_order":
            raise ValueError("Reverse valuation must remain no_order")
        object.__setattr__(self, "evidence_refs", [
            dict(ref) for ref in self.evidence_refs
        ])
        object.__setattr__(self, "blockers", list(dict.fromkeys(self.blockers)))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "model_type": self.model_type,
            "driver": self.driver,
            "target_price": _decimal(self.target_price),
            "quote_date": _date(self.quote_date),
            "lower_bound": _decimal(self.lower_bound),
            "upper_bound": _decimal(self.upper_bound),
            "lower_value": _decimal(self.lower_value),
            "upper_value": _decimal(self.upper_value),
            "status": self.status,
            "solution": _decimal(self.solution),
            "repriced_value": _decimal(self.repriced_value),
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "action": self.action,
        }


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _merge_refs(
    *groups: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Reverse valuation evidence requires ids")
            existing = merged.get(ref_id)
            if existing is not None and existing != ref:
                raise ValueError(
                    f"Reverse valuation evidence conflict: {ref_id}"
                )
            merged[ref_id] = ref
    return list(merged.values())


def _bounded_inverse(
    *,
    target: Decimal,
    lower: Decimal,
    upper: Decimal,
    value_at: Callable[[Decimal], Decimal],
    increasing: bool,
) -> dict[str, Any]:
    if (
        not all(value.is_finite() for value in (target, lower, upper))
        or target <= 0
        or lower >= upper
    ):
        raise ValueError("Reverse valuation target and bounds are invalid")
    lower_value = value_at(lower)
    upper_value = value_at(upper)
    if not all(
        value.is_finite() and value > 0
        for value in (lower_value, upper_value)
    ):
        raise ValueError("Reverse valuation envelope must be positive")
    if increasing and lower_value >= upper_value:
        raise ValueError("Increasing reverse envelope must be monotonic")
    if not increasing and lower_value <= upper_value:
        raise ValueError("Decreasing reverse envelope must be monotonic")

    base = {
        "target": target,
        "lower_bound": lower,
        "upper_bound": upper,
        "lower_value": lower_value,
        "upper_value": upper_value,
    }
    envelope_low = min(lower_value, upper_value)
    envelope_high = max(lower_value, upper_value)
    if target < envelope_low:
        return {**base, "status": STATUS_BELOW_ENVELOPE,
                "solution": None, "repriced_value": None}
    if target > envelope_high:
        return {**base, "status": STATUS_ABOVE_ENVELOPE,
                "solution": None, "repriced_value": None}

    left, right = lower, upper
    left_value, right_value = lower_value, upper_value
    for _ in range(100):
        middle = (left + right) / Decimal(2)
        middle_value = value_at(middle)
        if (
            not middle_value.is_finite()
            or middle_value < envelope_low
            or middle_value > envelope_high
        ):
            raise ValueError("Reverse valuation value is not monotonic")
        if (
            abs(middle_value - target)
            <= max(Decimal("0.000001"), target * Decimal("0.0000001"))
        ):
            return {
                **base,
                "status": STATUS_CONDITIONAL_SOLUTION,
                "solution": middle,
                "repriced_value": middle_value,
            }
        if (middle_value < target) == increasing:
            left = middle
        else:
            right = middle
    raise ValueError("Reverse valuation did not converge")


def _quality_scenario_value(
    facts: QualityCompounderFacts,
    scenario: ResidualIncomeScenarioInputs,
) -> Callable[[Decimal], Decimal]:
    start_book = facts.operating_inputs.get("start_book_equity")
    shares = facts.operating_inputs.get("ordinary_shares")
    if start_book is None or shares is None:
        raise ValueError("Residual-income reverse valuation lacks equity inputs")

    def value_at(terminal_roe: Decimal) -> Decimal:
        calculation = scenario_value(
            start_book,
            shares,
            scenario.cost_of_equity,
            {
                "forecast_roe": scenario.forecast_roes,
                "retention": scenario.retention,
                "terminal_roe": terminal_roe,
                "terminal_growth": scenario.terminal_growth,
            },
        )
        return Decimal(calculation["conditional_value_per_2025_issued_share_cny"])

    return value_at


def _quality_cost_value(
    facts: QualityCompounderFacts,
    scenario: ResidualIncomeScenarioInputs,
) -> Callable[[Decimal], Decimal]:
    start_book = facts.operating_inputs.get("start_book_equity")
    shares = facts.operating_inputs.get("ordinary_shares")
    if start_book is None or shares is None:
        raise ValueError("Residual-income reverse valuation lacks equity inputs")

    def value_at(cost_of_equity: Decimal) -> Decimal:
        calculation = scenario_value(
            start_book,
            shares,
            cost_of_equity,
            {
                "forecast_roe": scenario.forecast_roes,
                "retention": scenario.retention,
                "terminal_roe": scenario.terminal_roe,
                "terminal_growth": scenario.terminal_growth,
            },
        )
        return Decimal(calculation["conditional_value_per_2025_issued_share_cny"])

    return value_at


def _fcff_roic_value(
    scenario: FCFFScenarioInputs,
) -> Callable[[Decimal], Decimal]:
    def value_at(terminal_roic: Decimal) -> Decimal:
        terminal = replace(scenario.terminal, roic=terminal_roic)
        return Decimal(
            replace(scenario, terminal=terminal).calculate("base")["per_share_value"]
        )

    return value_at


def _fcff_wacc_value(
    scenario: FCFFScenarioInputs,
) -> Callable[[Decimal], Decimal]:
    def value_at(wacc: Decimal) -> Decimal:
        forecast = tuple(
            replace(year, wacc=wacc) for year in scenario.forecast
        )
        terminal = replace(scenario.terminal, wacc=wacc)
        return Decimal(
            replace(scenario, forecast=forecast, terminal=terminal)
            .calculate("base")["per_share_value"]
        )

    return value_at


def _pending(symbol: str, model_type: str, driver: str, blockers: Sequence[str]) -> ReverseValuationResult:
    return ReverseValuationResult(
        symbol=symbol,
        model_type=model_type,
        driver=driver,
        target_price=None,
        quote_date=None,
        lower_bound=None,
        upper_bound=None,
        lower_value=None,
        upper_value=None,
        status=STATUS_PENDING_EXTERNAL_DATA,
        solution=None,
        repriced_value=None,
        evidence_refs=[],
        blockers=list(blockers),
    )


def reverse_for_descriptor(
    descriptor: ResearchInputDescriptor,
) -> tuple[ReverseValuationResult, ...]:
    """Build every registered reverse diagnostic for one descriptor."""
    facts = descriptor.facts
    model_type = {
        "quality_compounder": "residual_income_or_equity_value",
        "mature_manufacturing": "FCFF",
    }.get(descriptor.profile_id, "unsupported")

    quote = descriptor.quote
    if quote is None or quote.current_price is None or quote.quote_date is None:
        blockers = ["a verified dated close quote is required for reverse valuation"]
        if isinstance(facts, QualityCompounderFacts):
            return (
                _pending(facts.symbol, model_type, "terminal_roe", blockers),
                _pending(facts.symbol, model_type, "cost_of_equity", blockers),
            )
        if isinstance(facts, FinancialFacts):
            return (
                _pending(facts.symbol, model_type, "terminal_roic", blockers),
                _pending(facts.symbol, model_type, "wacc", blockers),
            )
        return (_pending(descriptor.symbol, "unsupported", "unsupported", blockers),)
    if quote.status != QUOTE_STATUS_VERIFIED_CLOSE:
        return reverse_for_descriptor(
            replace(descriptor, quote=None),
        )

    evidence_refs = _merge_refs(facts.evidence_refs, quote.evidence_refs)
    target = quote.current_price

    if isinstance(facts, QualityCompounderFacts):
        scenarios = facts.scenario_inputs or {}
        base = scenarios.get("base")
        if not isinstance(base, ResidualIncomeScenarioInputs):
            return (
                _pending(facts.symbol, model_type, "terminal_roe", facts.blockers),
                _pending(facts.symbol, model_type, "cost_of_equity", facts.blockers),
            )
        roes = [scenario.terminal_roe for scenario in scenarios.values()]
        roe_bounds = (min(roes), max(roes))
        terminal = _bounded_inverse(
            target=target,
            lower=roe_bounds[0],
            upper=roe_bounds[1],
            value_at=_quality_scenario_value(facts, base),
            increasing=True,
        )
        cost = _bounded_inverse(
            target=target,
            lower=COST_OF_EQUITY_LOWER,
            upper=COST_OF_EQUITY_UPPER,
            value_at=_quality_cost_value(facts, base),
            increasing=False,
        )
        return (
            ReverseValuationResult(
                symbol=facts.symbol,
                model_type=model_type,
                driver="terminal_roe",
                target_price=target,
                quote_date=quote.quote_date,
                lower_bound=terminal["lower_bound"],
                upper_bound=terminal["upper_bound"],
                lower_value=terminal["lower_value"],
                upper_value=terminal["upper_value"],
                status=terminal["status"],
                solution=terminal["solution"],
                repriced_value=terminal["repriced_value"],
                evidence_refs=evidence_refs,
                blockers=list(facts.blockers),
            ),
            ReverseValuationResult(
                symbol=facts.symbol,
                model_type=model_type,
                driver="cost_of_equity",
                target_price=target,
                quote_date=quote.quote_date,
                lower_bound=cost["lower_bound"],
                upper_bound=cost["upper_bound"],
                lower_value=cost["lower_value"],
                upper_value=cost["upper_value"],
                status=cost["status"],
                solution=cost["solution"],
                repriced_value=cost["repriced_value"],
                evidence_refs=evidence_refs,
                blockers=list(facts.blockers),
            ),
        )

    if isinstance(facts, FinancialFacts):
        scenarios = facts.scenario_inputs or {}
        base = scenarios.get("base")
        if not isinstance(base, FCFFScenarioInputs):
            return (
                _pending(facts.symbol, model_type, "terminal_roic", facts.blockers),
                _pending(facts.symbol, model_type, "wacc", facts.blockers),
            )
        roics = [scenario.terminal.roic for scenario in scenarios.values()]
        roic = _bounded_inverse(
            target=target,
            lower=min(roics),
            upper=max(roics),
            value_at=_fcff_roic_value(base),
            increasing=True,
        )
        wacc = _bounded_inverse(
            target=target,
            lower=WACC_LOWER,
            upper=WACC_UPPER,
            value_at=_fcff_wacc_value(base),
            increasing=False,
        )
        return (
            ReverseValuationResult(
                symbol=facts.symbol,
                model_type=model_type,
                driver="terminal_roic",
                target_price=target,
                quote_date=quote.quote_date,
                lower_bound=roic["lower_bound"],
                upper_bound=roic["upper_bound"],
                lower_value=roic["lower_value"],
                upper_value=roic["upper_value"],
                status=roic["status"],
                solution=roic["solution"],
                repriced_value=roic["repriced_value"],
                evidence_refs=evidence_refs,
                blockers=list(facts.blockers),
            ),
            ReverseValuationResult(
                symbol=facts.symbol,
                model_type=model_type,
                driver="wacc",
                target_price=target,
                quote_date=quote.quote_date,
                lower_bound=wacc["lower_bound"],
                upper_bound=wacc["upper_bound"],
                lower_value=wacc["lower_value"],
                upper_value=wacc["upper_value"],
                status=wacc["status"],
                solution=wacc["solution"],
                repriced_value=wacc["repriced_value"],
                evidence_refs=evidence_refs,
                blockers=list(facts.blockers),
            ),
        )

    return (_pending(descriptor.symbol, "unsupported", "unsupported",
                     ["reverse valuation model is not registered"]),)
