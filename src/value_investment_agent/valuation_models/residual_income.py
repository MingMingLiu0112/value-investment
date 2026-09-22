"""Shared quality-compounder residual-income equity valuation contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Protocol

from ..research_case import ResearchCase
from ..valuation_confidence import ConfidenceEvidence, evaluate_confidence
from .base import ValuationResult


MODEL_VERSION = "residual-income-equity-shared-v1"


@dataclass(frozen=True)
class ResidualIncomeScenarioInputs:
    """Explicit self-funded ROE assumptions for one bear/base/bull scenario."""

    cost_of_equity: Decimal
    forecast_roes: tuple[Decimal, ...]
    terminal_roe: Decimal
    terminal_growth: Decimal
    retention: Decimal = Decimal("0.30")


@dataclass(frozen=True)
class QualityCompounderFacts:
    """Authenticated equity and scenario inputs for a quality-compounder case.

    The model requires explicit residual-income assumptions. A historical ROE,
    current earnings multiple, or current share price is deliberately not a
    sufficient substitute.
    """

    symbol: str
    as_of: date
    verified: bool
    confidence: str
    evidence_refs: list[dict]
    blockers: list[str]
    operating_inputs: dict[str, Decimal | None] = field(default_factory=dict)
    scenario_inputs: dict[str, ResidualIncomeScenarioInputs] | None = None
    confidence_evidence: ConfidenceEvidence | None = None

    REQUIRED_COMMON_INPUTS = ("start_book_equity", "ordinary_shares")

    @property
    def missing_common_inputs(self) -> list[str]:
        return [
            name for name in self.REQUIRED_COMMON_INPUTS
            if self.operating_inputs.get(name) is None
        ]


class ResidualIncomeValuationModel(Protocol):
    def value(
        self,
        facts: QualityCompounderFacts,
        case: ResearchCase,
    ) -> ValuationResult:
        """Return a research valuation without creating an execution instruction."""


def scenario_value(
    start_book: Decimal,
    shares: Decimal,
    cost: Decimal,
    configuration: dict[str, object],
) -> dict[str, object]:
    """Calculate bounded residual-income and independently reconciled dividend value."""
    terminal_roe = Decimal(str(configuration["terminal_roe"]))
    terminal_growth = Decimal(str(configuration["terminal_growth"]))
    forecast_roes = [Decimal(str(value)) for value in configuration["forecast_roe"]]
    retention = Decimal(str(configuration.get("retention", "0.30")))
    if (
        any(
            not value.is_finite() for value in [
                start_book, shares, cost, terminal_roe, terminal_growth,
                retention, *forecast_roes,
            ]
        )
        or min(start_book, shares, cost, terminal_roe) <= 0
        or not forecast_roes
        or any(value < 0 for value in forecast_roes)
        or not Decimal(0) <= terminal_growth < cost
        or terminal_growth > terminal_roe
        or not Decimal(0) <= retention <= Decimal(1)
    ):
        raise ValueError(
            "Invalid equity basis or unsupported self-funded terminal assumptions"
        )

    book = start_book
    present_value_residual = Decimal("0")
    annuals = []
    with localcontext() as context:
        context.prec = 48
        present_value_dividends = Decimal(0)
        for year, roe in enumerate(forecast_roes, 1):
            income = roe * book
            residual_income = income - cost * book
            discount_factor = (Decimal("1") + cost) ** year
            present_value_residual += residual_income / discount_factor
            next_book = book + income * retention
            dividend = income * (Decimal(1) - retention)
            present_value_dividends += dividend / discount_factor
            annuals.append({
                "year": year,
                "opening_book_equity_cny": str(book),
                "roe_assumption": str(roe),
                "net_income_assumption_cny": str(income),
                "retention_assumption": str(retention),
                "dividend_assumption_cny": str(dividend),
                "residual_income_cny": str(residual_income),
                "discount_factor": str(discount_factor),
                "closing_book_equity_cny": str(next_book),
            })
            book = next_book

        terminal_residual = (terminal_roe - cost) * book
        terminal_value = terminal_residual / (cost - terminal_growth)
        present_value_terminal = terminal_value / (
            (Decimal("1") + cost) ** len(annuals)
        )
        equity_value = (
            start_book + present_value_residual + present_value_terminal
        )
        terminal_retention = terminal_growth / terminal_roe
        terminal_dividend = (terminal_roe - terminal_growth) * book
        dividend_equity_value = present_value_dividends + (
            terminal_dividend
            / (cost - terminal_growth)
            / ((Decimal("1") + cost) ** len(annuals))
        )
        reconciliation_difference = equity_value - dividend_equity_value
        if (
            abs(reconciliation_difference)
            > max(Decimal("0.01"), abs(equity_value) * Decimal("1e-24"))
        ):
            raise ValueError("Residual-income and dividend paths do not reconcile")
        if equity_value <= 0:
            raise ValueError(
                "Scenario has no positive equity value under these assumptions"
            )

    return {
        "cost_of_equity_cny_nominal": str(cost),
        "forecast_years": annuals,
        "terminal_roe": str(terminal_roe),
        "terminal_growth": str(terminal_growth),
        "terminal_opening_book_equity_cny": str(book),
        "terminal_retention_assumption": str(terminal_retention),
        "terminal_first_dividend_cny": str(terminal_dividend),
        "terminal_residual_income_cny": str(terminal_residual),
        "present_value_explicit_residual_income_cny": str(present_value_residual),
        "present_value_terminal_residual_income_cny": str(present_value_terminal),
        "conditional_equity_value_cny": str(equity_value),
        "conditional_value_per_2025_issued_share_cny": str(equity_value / shares),
        "dividend_crosscheck_equity_value_cny": str(dividend_equity_value),
        "dividend_crosscheck_difference_cny": str(reconciliation_difference),
        "terminal_residual_contribution_ratio": str(
            present_value_terminal / equity_value
        ),
    }


def current_projection(
    start_book: Decimal,
    profit: Decimal,
    cost: Decimal,
    growth: Decimal,
    payout: Decimal,
    growth_years: int,
    fade_years: int,
) -> list[Decimal]:
    """Project ROE from an authenticated profit anchor into an explicit fade."""
    if (
        any(
            not value.is_finite()
            for value in (start_book, profit, cost, growth, payout)
        )
        or min(start_book, profit, cost) <= 0
        or growth <= -1
        or not 0 <= payout <= 1
        or type(growth_years) is not int
        or growth_years < 1
        or type(fade_years) is not int
        or fade_years < 0
    ):
        raise ValueError("Invalid current projection assumptions")
    with localcontext() as context:
        context.prec = 48
        book, income, roes = start_book, profit, []
        for _ in range(growth_years):
            income *= 1 + growth
            roes.append(income / book)
            book += income * (1 - payout)
        last_roe = roes[-1]
        for step in range(1, fade_years + 1):
            roe = last_roe + (cost - last_roe) * Decimal(step) / fade_years
            roes.append(roe)
            book += roe * book * (1 - payout)
    return roes


def current_value(
    start_book: Decimal,
    shares: Decimal,
    profit: Decimal,
    cost: Decimal,
    growth: Decimal,
    payout: Decimal,
    growth_years: int,
    fade_years: int,
    terminal_growth: Decimal,
    basis_at: datetime,
    as_of: datetime,
) -> dict:
    """Transport a bounded projection to a later date and reprice its dividends."""
    if basis_at.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("Current valuation requires timezone-aware dates")
    first_payment = basis_at.replace(year=basis_at.year + 1)
    if not basis_at <= as_of < first_payment:
        raise ValueError("Current date is outside the first projected payment period")
    with localcontext() as context:
        context.prec = 48
        roes = current_projection(
            start_book, profit, cost, growth, payout, growth_years, fade_years
        )
        calculation = scenario_value(start_book, shares, cost, {
            "forecast_roe": roes,
            "retention": 1 - payout,
            "terminal_roe": cost,
            "terminal_growth": terminal_growth,
        })
        elapsed = (
            Decimal(str((as_of - basis_at).total_seconds()))
            / Decimal(str((first_payment - basis_at).total_seconds()))
        )
        transport = (1 + cost) ** elapsed
        origin_value = Decimal(calculation["conditional_equity_value_cny"])
        equity_value = origin_value * transport
        dividend_value = sum(
            Decimal(row["dividend_assumption_cny"])
            / (1 + cost) ** (Decimal(row["year"]) - elapsed)
            for row in calculation["forecast_years"]
        )
        count = len(roes)
        dividend_value += (
            Decimal(calculation["terminal_first_dividend_cny"])
            / (cost - terminal_growth)
            / (1 + cost) ** (Decimal(count) - elapsed)
        )
        if abs(equity_value - dividend_value) > Decimal("0.01"):
            raise ValueError(
                "Current-date dividend and residual-income values do not reconcile"
            )
        for row in calculation["forecast_years"]:
            row["assumed_payment_at"] = basis_at.replace(
                year=basis_at.year + row["year"]
            ).isoformat()
        calculation.pop("conditional_value_per_2025_issued_share_cny")
        return {
            "basis_origin_calculation": calculation,
            "income_growth_assumption": str(growth),
            "payout_assumption": str(payout),
            "fade_years": fade_years,
            "cost_of_equity_cny_nominal": str(cost),
            "basis_at": basis_at.isoformat(),
            "valuation_at": as_of.isoformat(),
            "fractional_first_year_elapsed": str(elapsed),
            "basis_to_valuation_factor": str(transport),
            "conditional_current_equity_value_cny": str(equity_value),
            "conditional_value_per_current_disclosed_share_cny": str(
                equity_value / shares
            ),
            "current_dividend_crosscheck_equity_value_cny": str(dividend_value),
            "current_dividend_crosscheck_difference_cny": str(
                equity_value - dividend_value
            ),
            "terminal_dividend_value_share": str(
                (
                    Decimal(calculation["terminal_first_dividend_cny"])
                    / (cost - terminal_growth)
                    / (1 + cost) ** (Decimal(count) - elapsed)
                )
                / equity_value
            ),
        }


def _shared_scenario_calculation(
    facts: QualityCompounderFacts,
    scenario: ResidualIncomeScenarioInputs,
) -> dict[str, Any]:
    start_book = facts.operating_inputs["start_book_equity"]
    shares = facts.operating_inputs["ordinary_shares"]
    if start_book is None or shares is None:
        raise ValueError("Common residual-income equity inputs are missing")
    calculation = scenario_value(start_book, shares, scenario.cost_of_equity, {
        "forecast_roe": scenario.forecast_roes,
        "retention": scenario.retention,
        "terminal_roe": scenario.terminal_roe,
        "terminal_growth": scenario.terminal_growth,
    })
    calculation["per_share_value"] = calculation.pop(
        "conditional_value_per_2025_issued_share_cny"
    )
    return calculation


@dataclass(frozen=True)
class ResidualIncomeEquityValuationModel:
    """Common quality-compounder gate without market-price or order semantics."""

    model_type: str = "residual_income_or_equity_value"

    def value(
        self,
        facts: QualityCompounderFacts,
        case: ResearchCase,
    ) -> ValuationResult:
        if facts.symbol != case.symbol:
            raise ValueError("Quality-compounder facts and research case symbols must match")
        if facts.confidence not in {"高", "中", "低"}:
            raise ValueError("Quality-compounder confidence must be 高, 中 or 低")
        refs = [*facts.evidence_refs, *case.evidence_refs]
        if not refs:
            raise ValueError("Quality-compounder research requires named evidence references")
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *(["financial_facts_not_verified"] if not facts.verified else []),
            *(
                "quality_compounder_input_missing:" + name
                for name in facts.missing_common_inputs
            ),
        ]))
        scenarios = facts.scenario_inputs
        if not scenarios:
            blockers.append("quality_compounder_scenario_inputs_not_registered")

        if blockers or scenarios is None:
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={
                    "scope": (
                        "quality-compounder input gate; no residual-income arithmetic "
                        "before verified equity and scenario facts"
                    ),
                },
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers or [
                    "quality_compounder_scenario_inputs_not_registered"
                ],
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        if set(scenarios) != {"bear", "base", "bull"}:
            blockers.append(
                "quality_compounder_scenarios_must_contain_exactly_bear_base_bull"
            )
        if any(
            not isinstance(item, ResidualIncomeScenarioInputs)
            for item in scenarios.values()
        ):
            blockers.append("quality_compounder_scenario_inputs_must_be_typed")
        if blockers:
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={"scope": "quality-compounder scenario gate"},
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers,
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        calculations = {
            name: _shared_scenario_calculation(facts, scenario)
            for name, scenario in scenarios.items()
        }
        values = {
            name: Decimal(item["per_share_value"])
            for name, item in calculations.items()
        }

        confidence = facts.confidence
        confidence_policy = None
        if facts.confidence_evidence is not None:
            assessment = evaluate_confidence(facts.confidence_evidence)
            confidence = assessment.confidence
            confidence_policy = assessment.as_policy()

        return ValuationResult(
            symbol=case.symbol,
            model_type=self.model_type,
            valuation_date=facts.as_of,
            bear_value=values["bear"],
            base_value=values["base"],
            bull_value=values["bull"],
            confidence=confidence,
            assumptions={
                "scope": (
                    "explicit residual income plus independently reconciled "
                    "dividend capacity"
                ),
                "formula": (
                    "Equity value = opening equity + PV(explicit residual income) "
                    "+ PV(terminal residual income), divided by ordinary shares"
                ),
                "status": "conditional_research_only",
                "disclaimer": (
                    "No market price, margin of safety, position or order is "
                    "produced here."
                ),
                **(
                    {"confidence_assessment": confidence_policy}
                    if confidence_policy is not None else {}
                ),
            },
            sensitivities=[
                {
                    "scenario": name,
                    "cost_of_equity": item["cost_of_equity_cny_nominal"],
                    "ordinary_equity_value": item["conditional_equity_value_cny"],
                    "per_share_value": item["per_share_value"],
                    "terminal_residual_contribution_ratio": item[
                        "terminal_residual_contribution_ratio"
                    ],
                    "dividend_crosscheck_difference": item[
                        "dividend_crosscheck_difference_cny"
                    ],
                    "arithmetic_status": "research_arithmetic_only",
                }
                for name, item in calculations.items()
            ],
            evidence_refs=refs,
            blockers=[],
            status="conditional_research_only",
            model_version=MODEL_VERSION,
        )
