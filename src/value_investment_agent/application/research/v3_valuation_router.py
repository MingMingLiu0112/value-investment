"""Explicit model registry for the v3 terminal-economic research path."""
from __future__ import annotations

from ...valuation_models.residual_income import QualityCompounderFacts
from ...valuation_models.residual_income_path_v3 import ResidualIncomeContractDispatcher
from ...valuation_router import (
    ValuationModelRegistration, ValuationModelRegistry, ValuationRouter,
)


def build_v3_valuation_router() -> ValuationRouter:
    registry = ValuationModelRegistry((ValuationModelRegistration(
        model_id="residual_income_or_equity_value",
        model_type="residual_income_or_equity_value",
        model_factory=ResidualIncomeContractDispatcher,
        facts_contract=QualityCompounderFacts,
        required_inputs=(*QualityCompounderFacts.REQUIRED_COMMON_INPUTS, "scenario_inputs"),
    ),))
    return ValuationRouter(registry=registry)
