"""Shared FCFF valuation contract for research-only company cases."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from ..research_case import ResearchCase
from ..scenario_valuation import BridgeItem, ForecastYear, Terminal, value_scenario
from ..valuation_confidence import ConfidenceEvidence, evaluate_confidence
from .base import ValuationResult, merge_evidence_refs


MODEL_VERSION = "fcff-shared-scenario-v1"


@dataclass(frozen=True)
class FCFFScenarioInputs:
    """Explicit arithmetic inputs for one bear/base/bull scenario."""

    forecast: tuple[ForecastYear, ...]
    terminal: Terminal
    bridge: tuple[BridgeItem, ...]
    operating_exposure_ids: tuple[str, ...]
    ordinary_shares: Decimal
    share_evidence_refs: tuple[str, ...]
    currency: str = "CNY"
    valuation_date: date | None = None
    cash_flow_dates: tuple[date, ...] | None = None
    timing_evidence_refs: tuple[str, ...] = ()

    def calculate(self, scenario_id: str) -> dict[str, Any]:
        return value_scenario(
            scenario_id=scenario_id,
            forecast=self.forecast,
            terminal=self.terminal,
            bridge=self.bridge,
            operating_exposure_ids=self.operating_exposure_ids,
            ordinary_shares=self.ordinary_shares,
            share_evidence_refs=self.share_evidence_refs,
            currency=self.currency,
            valuation_date=self.valuation_date,
            cash_flow_dates=self.cash_flow_dates,
            timing_evidence_refs=self.timing_evidence_refs,
        )


@dataclass(frozen=True)
class FinancialFacts:
    """Authenticated inputs required to produce a per-share FCFF result.

    A reconciled profit figure alone is deliberately insufficient: the model
    requires explicit operating, bridge and share inputs with named evidence.
    """

    symbol: str
    as_of: date
    verified: bool
    evidence_refs: list[dict]
    blockers: list[str]
    operating_inputs: dict[str, Decimal | None] = field(default_factory=dict)
    scenario_inputs: dict[str, FCFFScenarioInputs] | None = None
    confidence: str = "低"
    confidence_evidence: ConfidenceEvidence | None = None

    REQUIRED_FCFF_INPUTS = (
        "ebit", "cash_tax_rate", "depreciation", "capex", "working_capital_change",
        "wacc", "net_debt", "non_operating_assets", "shares",
    )

    @property
    def missing_fcff_inputs(self) -> list[str]:
        return [name for name in self.REQUIRED_FCFF_INPUTS if self.operating_inputs.get(name) is None]


class ValuationModel(Protocol):
    def value(self, facts: FinancialFacts, case: ResearchCase) -> ValuationResult:
        """Return a research valuation without creating an execution instruction."""


@dataclass(frozen=True)
class FCFFValuationModel:
    """Common gate for FCFF implementations backed by the shared calculator."""

    model_type: str = "FCFF"

    def value(self, facts: FinancialFacts, case: ResearchCase) -> ValuationResult:
        if facts.symbol != case.symbol:
            raise ValueError("Financial facts and research case symbols must match")
        if facts.confidence not in {"高", "中", "低"}:
            raise ValueError("FCFF confidence must be 高, 中 or 低")
        refs = merge_evidence_refs(facts.evidence_refs, case.evidence_refs)
        if not refs:
            raise ValueError("FCFF research requires named evidence references")
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *( ["financial_facts_not_verified"] if not facts.verified else []),
        ]))

        scenarios = facts.scenario_inputs
        if not scenarios:
            blockers.extend("fcff_input_missing:" + name for name in facts.missing_fcff_inputs)
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={"scope": "FCFF input gate; no scenario arithmetic before verified facts"},
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers or ["fcff_scenario_inputs_not_registered"],
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        if set(scenarios) != {"bear", "base", "bull"}:
            blockers.append("fcff_scenarios_must_contain_exactly_bear_base_bull")
        if any(not isinstance(item, FCFFScenarioInputs) for item in scenarios.values()):
            blockers.append("fcff_scenario_inputs_must_be_typed")
        for name, scenario in scenarios.items():
            if (isinstance(scenario, FCFFScenarioInputs)
                    and scenario.valuation_date is not None
                    and scenario.valuation_date != facts.as_of):
                blockers.append(f"fcff_scenario_valuation_date_mismatch:{name}")
        if blockers:
            return ValuationResult(
                symbol=case.symbol,
                model_type=self.model_type,
                valuation_date=facts.as_of,
                bear_value=None,
                base_value=None,
                bull_value=None,
                confidence=facts.confidence,
                assumptions={"scope": "FCFF scenario gate"},
                sensitivities=[],
                evidence_refs=refs,
                blockers=blockers,
                status="not_ready",
                model_version=MODEL_VERSION,
            )

        results = {}
        for name in ("bear", "base", "bull"):
            results[name] = scenarios[name].calculate(name)

        confidence = facts.confidence
        confidence_policy = None
        if facts.confidence_evidence is not None:
            assessment = evaluate_confidence(facts.confidence_evidence)
            confidence = assessment.confidence
            confidence_policy = assessment.as_policy()

        def scenario_refs(item: dict[str, Any]) -> list[str]:
            refs = [*item["terminal_evidence_refs"], *item["share_evidence_refs"],
                    *item.get("timing_evidence_refs", ())]
            refs.extend(ref for row in item["annual_cash_flows"] for ref in row["evidence_refs"])
            refs.extend(ref for bridge in item["bridge"] for ref in bridge["evidence_refs"])
            return sorted(set(refs))

        return ValuationResult(
            symbol=case.symbol,
            model_type=self.model_type,
            valuation_date=facts.as_of,
            bear_value=results["bear"]["per_share_value"],
            base_value=results["base"]["per_share_value"],
            bull_value=results["bull"]["per_share_value"],
            confidence=confidence,
            assumptions={
                "scope": "annual explicit FCFF plus enterprise-to-equity bridge",
                "arithmetic": MODEL_VERSION,
                "status": "conditional_research_only",
                "disclaimer": "No market price, margin of safety, position or order is produced here.",
                **({"confidence_assessment": confidence_policy}
                   if confidence_policy is not None else {}),
            },
            sensitivities=[{
                "scenario": name,
                "per_share_value": str(item["per_share_value"]),
                "ordinary_equity_value": str(item["ordinary_equity_value"]),
                "operating_value": str(item["operating_value"]),
                "terminal_present_value": str(item["terminal_present_value"]),
                "terminal_reinvestment_rate": str(item["terminal_reinvestment_rate"]),
                "arithmetic_status": item["status"],
                "evidence_refs": scenario_refs(item),
            } for name, item in results.items()],
            evidence_refs=refs,
            blockers=[],
            status="conditional_research_only",
            model_version=MODEL_VERSION,
        )
