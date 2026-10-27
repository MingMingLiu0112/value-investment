"""V4 annual-retention RI adapter with an exact economic terminal contract.

CNY nominal inputs only. Dated timing uses the legacy first-payment convention. The inherited
scalar retention is a compatibility field, required to remain at its default;
forecast_retentions is the sole explicit-period retention authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from ..research_case import ResearchCase
from ..domain.valuation.joint_capital_cash_path_v4 import (
    TerminalEconomicContract,
    value_terminal_economic_contract,
)
from ..valuation_confidence import evaluate_confidence
from .base import ValuationResult, merge_evidence_refs
from .residual_income import (
    QualityCompounderFacts, ResidualIncomeScenarioInputs,
    valuation_time_factor,
)

MODEL_VERSION = "residual-income-equity-path-v4"


@dataclass(frozen=True)
class ResidualIncomePathScenarioInputs(ResidualIncomeScenarioInputs):
    forecast_retentions: tuple[Decimal, ...] = field(kw_only=True)
    currency: str = field(default="CNY", kw_only=True)
    terminal_economic_contract: TerminalEconomicContract = field(kw_only=True)

    def __post_init__(self) -> None:
        if self.currency != "CNY":
            raise ValueError("Annual retention path supports CNY only")
        if not isinstance(self.forecast_roes, tuple) or not isinstance(self.forecast_retentions, tuple):
            raise ValueError("Forecast ROEs and retentions must be tuples")
        if not self.forecast_roes or len(self.forecast_roes) != len(self.forecast_retentions):
            raise ValueError("Forecast retention length must match nonempty ROEs")
        numbers = (self.cost_of_equity, self.terminal_roe, self.terminal_growth,
                   self.retention, *self.forecast_roes, *self.forecast_retentions)
        if any(not isinstance(v, Decimal) or not v.is_finite() for v in numbers):
            raise ValueError("Scenario inputs must be finite Decimals")
        if self.retention != Decimal("0.30"):
            raise ValueError("Scalar retention must remain default; use forecast_retentions")
        if any(not 0 <= v <= 1 for v in self.forecast_retentions):
            raise ValueError("Forecast retentions must be within [0, 1]")
        if not Decimal(0) < self.cost_of_equity < Decimal(1):
            raise ValueError("Annual retention path requires cost of equity in (0, 1)")
        if any(v < 0 for v in (*self.forecast_roes, self.terminal_roe)):
            raise ValueError("Annual retention path requires nonnegative ROEs")
        if not isinstance(self.terminal_economic_contract, TerminalEconomicContract):
            raise ValueError("V4 annual retention scenarios require a terminal economic contract")


def _annual_clean_surplus_row(
    *, book: Decimal, shares: Decimal, cost: Decimal, roe: Decimal,
    retention: Decimal,
) -> dict[str, str]:
    """One explicit RI year without the legacy Gordon-growth gate."""
    if any(not isinstance(value, Decimal) or not value.is_finite()
           for value in (book, shares, cost, roe, retention)):
        raise ValueError("Annual clean-surplus inputs must be finite Decimals")
    if book <= 0 or shares <= 0 or not Decimal(0) < cost < Decimal(1):
        raise ValueError("Annual clean-surplus basis and cost must be positive")
    if roe < 0 or not Decimal(0) <= retention <= Decimal(1):
        raise ValueError("Annual ROE and retention are outside the supported range")
    income = roe * book
    residual_income = income - cost * book
    dividend = income * (Decimal(1) - retention)
    closing_book = book + income * retention
    return {
        "opening_book_equity_cny": str(book),
        "roe_assumption": str(roe),
        "net_income_assumption_cny": str(income),
        "retention_assumption": str(retention),
        "dividend_assumption_cny": str(dividend),
        "residual_income_cny": str(residual_income),
        "closing_book_equity_cny": str(closing_book),
    }


def scenario_calculation(
    facts: QualityCompounderFacts,
    scenario: ResidualIncomePathScenarioInputs,
) -> dict[str, Any]:
    """Pure arithmetic, not a verified-facts gate; call model.value for admission."""
    if not isinstance(scenario, ResidualIncomePathScenarioInputs):
        raise ValueError("Annual retention scenario must be typed")
    start_book = facts.operating_inputs.get("start_book_equity")
    shares = facts.operating_inputs.get("ordinary_shares")
    if any(not isinstance(v, Decimal) or not v.is_finite() or v <= 0
           for v in (start_book, shares)):
        raise ValueError("Equity and shares must be positive finite Decimals")
    with localcontext() as context:
        context.prec = 48
        book = start_book
        residual_pv = dividend_pv = Decimal(0)
        annuals = []
        for year, (roe, retention) in enumerate(
            zip(scenario.forecast_roes, scenario.forecast_retentions, strict=True), 1
        ):
            row = _annual_clean_surplus_row(
                book=book, shares=shares, cost=scenario.cost_of_equity,
                roe=roe, retention=retention,
            )
            discount = (1 + scenario.cost_of_equity) ** year
            row.update(year=year, discount_factor=str(discount))
            annuals.append(row)
            residual_pv += Decimal(row["residual_income_cny"]) / discount
            dividend_pv += Decimal(row["dividend_assumption_cny"]) / discount
            book = Decimal(row["closing_book_equity_cny"])
        contract = scenario.terminal_economic_contract
        if abs(contract.opening_book - book) > Decimal("1e-24"):
            raise ValueError("Terminal contract does not continue explicit closing book")
        terminal_economics = value_terminal_economic_contract(
            contract, scenario.cost_of_equity,
        )
        terminal_equity = terminal_economics["equity_value"]
        terminal_pv = (terminal_equity - book) / discount
        terminal_dividend_value = terminal_equity / discount
        equity = start_book + residual_pv + terminal_pv
        ddm = dividend_pv + terminal_dividend_value
        difference = equity - ddm
        if abs(difference) > max(Decimal("0.01"), abs(equity) * Decimal("1e-24")):
            raise ValueError("Residual-income and dividend paths do not reconcile")
        if equity <= 0:
            raise ValueError("Scenario has no positive equity value")
        result = {
            "cost_of_equity_cny_nominal": str(scenario.cost_of_equity),
            "terminal_roe": str(scenario.terminal_roe),
            "terminal_growth": str(scenario.terminal_growth),
            "terminal_growth_status": "NON_AUTHORITATIVE_ACCOUNTING_DIAGNOSTIC",
            "terminal_opening_book_equity_cny": str(book),
            "model_version": MODEL_VERSION,
            "retention_policy": "new_typed_ignores_legacy_default",
            "forecast_years": annuals,
            "present_value_explicit_residual_income_cny": str(residual_pv),
            "present_value_terminal_residual_income_cny": str(terminal_pv),
            "conditional_equity_value_cny": str(equity),
            "per_share_value": str(equity / shares),
            "dividend_crosscheck_equity_value_cny": str(ddm),
            "dividend_crosscheck_difference_cny": str(difference),
            "terminal_residual_contribution_ratio": str(terminal_pv / equity),
            **({
                "terminal_mechanism": terminal_economics["mechanism"],
                "terminal_economic_value_cny": str(terminal_economics["equity_value"]),
                "terminal_distribution_value_cny": str(terminal_economics["distribution_value"]),
                "terminal_convergence_residual_cny": str(terminal_economics["convergence_residual"]),
                "terminal_clean_surplus_bridge_residual_cny": str(terminal_economics["clean_surplus_bridge_residual"]),
                "terminal_value_error_bound_cny": str(terminal_economics["absolute_error_bound_cny"]),
                "terminal_value_relative_error_bound": str(terminal_economics["relative_error_bound"]),
                "terminal_value_method": terminal_economics["valuation_method"],
                "terminal_last_scheduled_event_year": terminal_economics["last_scheduled_event_year"],
                "terminal_years_evaluated": terminal_economics["years_evaluated"],
                "terminal_first_dividend_cny": str(terminal_economics["first_distribution"]),
            } if terminal_economics is not None else {}),
        }
        return _apply_timing(result, facts, scenario, shares)



def _apply_timing(
    calculation: dict[str, Any],
    facts: QualityCompounderFacts,
    scenario: ResidualIncomePathScenarioInputs,
    shares: Decimal,
) -> dict[str, Any]:
    timing = facts.valuation_timing
    if timing is None:
        return calculation
    if timing.valuation_at.astimezone(ZoneInfo("Asia/Shanghai")).date() != facts.as_of:
        raise ValueError("Residual-income valuation time does not match facts as-of")
    with localcontext() as context:
        context.prec = 48
        elapsed, factor = valuation_time_factor(
            scenario.cost_of_equity, timing.basis_at, timing.valuation_at,
        )
        origin = Decimal(calculation["conditional_equity_value_cny"])
        current = origin * factor
        cost = scenario.cost_of_equity
        dividend = sum(
            Decimal(row["dividend_assumption_cny"])
            / (1 + cost) ** (Decimal(row["year"]) - elapsed)
            for row in calculation["forecast_years"]
        )
        dividend += Decimal(calculation["terminal_economic_value_cny"]) / (
            (1 + cost) ** (Decimal(len(scenario.forecast_roes)) - elapsed)
        )
        if abs(current - dividend) > Decimal("0.01"):
            raise ValueError("Dated residual-income and dividend paths do not reconcile")
        calculation.update({
            "basis_origin_equity_value_cny": str(origin),
            "basis_to_valuation_factor": str(factor),
            "conditional_equity_value_cny": str(current),
            "per_share_value": str(current / shares),
            "dividend_crosscheck_equity_value_cny": str(dividend),
            "dividend_crosscheck_difference_cny": str(current - dividend),
            "valuation_timing": timing.as_policy(),
        })
    return calculation

@dataclass(frozen=True)
class ResidualIncomePathValuationModel:
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
        timing = facts.valuation_timing
        model_version = MODEL_VERSION
        if timing is not None and timing.valuation_at.astimezone(ZoneInfo("Asia/Shanghai")).date() != facts.as_of:
            raise ValueError("Residual-income valuation time does not match facts as-of")
        refs = merge_evidence_refs(facts.evidence_refs, case.evidence_refs)
        if timing is not None:
            refs = merge_evidence_refs(refs, list(timing.evidence_refs))
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
                model_version=model_version,
            )

        if set(scenarios) != {"bear", "base", "bull"}:
            blockers.append(
                "quality_compounder_scenarios_must_contain_exactly_bear_base_bull"
            )
        if any(
            not isinstance(item, ResidualIncomePathScenarioInputs)
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
                model_version=model_version,
            )

        calculations = {
            name: scenario_calculation(facts, scenario)
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
                    "conditional residual income with an algebraic dividend-path "
                    "cross-check; not evidence of issuer distributable cash or "
                    "dividend sustainability"
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
                **({"valuation_timing": timing.as_policy()} if timing is not None else {}),
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
                    **({"basis_to_valuation_factor": item["basis_to_valuation_factor"]} if timing is not None else {}),
                }
                for name, item in calculations.items()
            ],
            evidence_refs=refs,
            blockers=[],
            status="conditional_research_only",
            model_version=model_version,
        )


# These are result identities, not approval or registration declarations.
from .residual_income import (
    MODEL_VERSION as LEGACY_MODEL_VERSION,
    DATED_MODEL_VERSION as LEGACY_DATED_MODEL_VERSION,
    ResidualIncomeEquityValuationModel,
)

SUPPORTED_MODEL_VERSIONS = (
    LEGACY_MODEL_VERSION, LEGACY_DATED_MODEL_VERSION, MODEL_VERSION,
)


@dataclass(frozen=True)
class ResidualIncomeContractDispatcher(ResidualIncomeEquityValuationModel):
    """Dispatch explicit scenario contracts without changing legacy arithmetic.

    Empty/missing and ordinary legacy scenarios retain the old gates and version.
    Any path scenario makes this a v4 path contract: every supplied scenario must
    then be path-typed. Mixed contracts raise before any arithmetic.
    """

    def value(
        self, facts: QualityCompounderFacts, case: ResearchCase,
    ) -> ValuationResult:
        scenarios = facts.scenario_inputs
        if scenarios and any(
            isinstance(item, ResidualIncomePathScenarioInputs)
            for item in scenarios.values()
        ):
            if not all(
                isinstance(item, ResidualIncomePathScenarioInputs)
                for item in scenarios.values()
            ):
                raise ValueError("Mixed residual-income scenario contracts are unsupported")
            return ResidualIncomePathValuationModel(
                model_type=self.model_type,
            ).value(facts, case)
        return super().value(facts, case)
