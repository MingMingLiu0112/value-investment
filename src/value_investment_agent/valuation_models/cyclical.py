"""Shared cyclical-normalized valuation contract for resource businesses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Protocol

from ..research_case import ResearchCase
from ..valuation_confidence import ConfidenceEvidence, evaluate_confidence
from .base import ValuationResult


MODEL_VERSION = "cyclical-normalized-equity-v1"


@dataclass(frozen=True)
class CyclicalFacts:
    """Authenticated mid-cycle and trough inputs for a resource business.

    Current-year profit, cash flow and low price/earnings are deliberately
    insufficient. The model requires explicit mid-cycle scenario profit,
    maintenance capital, resource life, discount basis, net cash and shares.
    """

    symbol: str
    as_of: date
    verified: bool
    confidence: str
    evidence_refs: list[dict]
    blockers: list[str]
    operating_inputs: dict[str, Decimal | None] = field(default_factory=dict)
    confidence_evidence: ConfidenceEvidence | None = None

    REQUIRED_CYCLICAL_INPUTS = (
        "bear_normalized_parent_operating_profit",
        "base_normalized_parent_operating_profit",
        "bull_normalized_parent_operating_profit",
        "cash_tax_rate",
        "maintenance_capex",
        "normalized_working_capital_change",
        "discount_rate",
        "long_term_growth",
        "resource_life_years",
        "net_cash_attributable_to_parent",
        "ordinary_shares",
        "trough_parent_operating_profit",
        "unit_cost",
    )

    @property
    def missing_cyclical_inputs(self) -> list[str]:
        return [name for name in self.REQUIRED_CYCLICAL_INPUTS
                if self.operating_inputs.get(name) is None]


class CyclicalValuationModel(Protocol):
    def value(self, facts: CyclicalFacts, case: ResearchCase) -> ValuationResult:
        """Return research valuation without creating an execution instruction."""


def _number(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def value_normalized_equity(*, facts: CyclicalFacts, scenario_name: str) -> dict[str, Any]:
    """Finite-horizon normalized distributable cash plus attributable net cash.

    This is explicit arithmetic only. It never converts a current profit into a
    permanent value and never uses a generic price multiple as the primary model.
    """
    inputs = facts.operating_inputs
    profit_name = scenario_name + "_normalized_parent_operating_profit"
    if profit_name not in facts.REQUIRED_CYCLICAL_INPUTS:
        raise ValueError("Unknown cyclical scenario")
    profit = _number(inputs[profit_name], "normalized profit")
    cash_tax_rate = _number(inputs["cash_tax_rate"], "cash tax rate")
    maintenance_capex = _number(inputs["maintenance_capex"], "maintenance capex")
    working_capital_change = _number(inputs["normalized_working_capital_change"], "working-capital change")
    discount_rate = _number(inputs["discount_rate"], "discount rate")
    long_term_growth = _number(inputs["long_term_growth"], "long-term growth")
    net_cash = _number(inputs["net_cash_attributable_to_parent"], "net cash")
    ordinary_shares = _number(inputs["ordinary_shares"], "ordinary shares")
    resource_life = inputs["resource_life_years"]

    if not isinstance(resource_life, int) or resource_life <= 0:
        raise ValueError("resource_life_years must be a positive integer")
    if not 0 <= cash_tax_rate <= 1:
        raise ValueError("cash_tax_rate must be between zero and one")
    if maintenance_capex < 0:
        raise ValueError("maintenance_capex must be nonnegative")
    if discount_rate <= 0 or long_term_growth <= -1 or long_term_growth >= discount_rate:
        raise ValueError("discount and growth rates require -1 < growth < discount")
    if ordinary_shares <= 0 or ordinary_shares != ordinary_shares.to_integral_value():
        raise ValueError("ordinary_shares must be a positive whole number")
    if profit <= 0:
        return {"scenario": scenario_name, "status": "blocked",
                "reason": "normalized_parent_operating_profit_must_be_positive"}

    distributable_cash = profit * (1 - cash_tax_rate) - maintenance_capex - working_capital_change
    if distributable_cash <= 0:
        return {"scenario": scenario_name, "status": "blocked",
                "reason": "normalized_distributable_cash_must_be_positive"}

    with localcontext() as context:
        context.prec = 40
        ratio = (1 + long_term_growth) / (1 + discount_rate)
        annuity_factor = (1 - ratio ** resource_life) / (discount_rate - long_term_growth)
        present_value = distributable_cash * annuity_factor
        equity_value = present_value + net_cash
        per_share_value = equity_value / ordinary_shares

    if equity_value <= 0 or per_share_value <= 0:
        return {"scenario": scenario_name, "status": "blocked",
                "reason": "ordinary_equity_value_must_be_positive"}

    return {
        "scenario": scenario_name,
        "status": "computed",
        "normalized_parent_operating_profit": profit,
        "normalized_distributable_cash": distributable_cash,
        "resource_life_years": resource_life,
        "present_value_of_normalized_cash": present_value,
        "net_cash_attributable_to_parent": net_cash,
        "ordinary_equity_value": equity_value,
        "per_share_value": per_share_value,
        "arithmetic_authenticated": False,
        "strategy_approved": False,
    }


@dataclass(frozen=True)
class CyclicalNormalizedValuationModel:
    """Shared gate for cyclical-normalized implementations."""

    model_type: str = "cyclical_normalized"

    def value(self, facts: CyclicalFacts, case: ResearchCase) -> ValuationResult:
        if facts.symbol != case.symbol:
            raise ValueError("Cyclical facts and research case symbols must match")
        if facts.confidence not in {"高", "中", "低"}:
            raise ValueError("Cyclical confidence must be 高, 中 or 低")
        refs = [*facts.evidence_refs, *case.evidence_refs]
        if not refs:
            raise ValueError("Cyclical research requires named evidence references")
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *(["financial_facts_not_verified"] if not facts.verified else []),
            *("cyclical_input_missing:" + name for name in facts.missing_cyclical_inputs),
        ]))
        if blockers:
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={"scope": "cyclical input gate; no scenario arithmetic before verified mid-cycle facts"},
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers or ["cyclical_scenario_inputs_not_registered"],
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        scenarios = {}
        for scenario_name in ("bear", "base", "bull"):
            scenarios[scenario_name] = value_normalized_equity(facts=facts, scenario_name=scenario_name)
        failed = [item for item in scenarios.values() if item["status"] != "computed"]
        if failed:
            blockers = ["cyclical_scenario_blocked:" + item["scenario"] + ":" + item["reason"] for item in failed]
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={"scope": "cyclical scenario gate"},
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers,
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        values = {name: item["per_share_value"] for name, item in scenarios.items()}
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
                "scope": "finite-horizon normalized distributable cash plus attributable net cash",
                "formula": "PV(normalized profit after cash tax - maintenance capex - normalized WC change; resource life; discount and growth) + net cash, divided by ordinary shares",
                "status": "conditional_research_only",
                "disclaimer": "No market price, margin of safety, position or order is produced here.",
                **({"confidence_assessment": confidence_policy}
                   if confidence_policy is not None else {}),
            },
            sensitivities=[
                {"scenario": item["scenario"], "normalized_profit": str(item["normalized_parent_operating_profit"]),
                 "distributable_cash": str(item["normalized_distributable_cash"]),
                 "ordinary_equity_value": str(item["ordinary_equity_value"]),
                 "per_share_value": str(item["per_share_value"])}
                for item in scenarios.values()
            ],
            evidence_refs=refs,
            blockers=[],
            status="conditional_research_only",
            model_version=MODEL_VERSION,
        )
