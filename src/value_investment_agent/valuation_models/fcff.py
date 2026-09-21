"""Shared FCFF valuation contract for research-only company cases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from ..research_case import ResearchCase
from .base import ValuationResult


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
        refs = [*facts.evidence_refs, *case.evidence_refs]
        if not refs:
            raise ValueError("FCFF research requires named evidence references")
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *( ["financial_facts_not_verified"] if not facts.verified else []),
        ]))
        return ValuationResult(
            symbol=case.symbol,
            model_type=self.model_type,
            valuation_date=facts.as_of,
            bear_value=None,
            base_value=None,
            bull_value=None,
            current_price=None,
            margin_to_bear=None,
            margin_to_base=None,
            confidence="低",
            assumptions={"scope": "FCFF input gate; no scenario arithmetic before verified facts"},
            sensitivities=[],
            evidence_refs=refs,
            blockers=blockers or ["fcff_scenario_inputs_not_registered"],
            status="not_ready",
        )
