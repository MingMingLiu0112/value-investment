import importlib.util
from pathlib import Path

import pytest

from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_models.cyclical import (
    CyclicalFacts,
    CyclicalNormalizedValuationModel,
)
from value_investment_agent.valuation_models.fcff import FCFFValuationModel, FinancialFacts
from value_investment_agent.valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeEquityValuationModel,
)
from value_investment_agent.valuation_router import (
    ROUTE_MODEL_NOT_APPLICABLE,
    ROUTE_SUPPORTED,
    ROUTE_UNSUPPORTED,
    ValuationRouter,
    route_profile,
)


ROOT = Path(__file__).resolve().parents[1]
BUILD_SPEC = importlib.util.spec_from_file_location(
    "build_company_valuation_result", ROOT / "scripts" / "build_company_valuation_result.py",
)
BUILD_MODULE = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(BUILD_MODULE)


def test_mature_manufacturing_routes_to_the_shared_fcff_contract():
    route = route_profile("mature_manufacturing")

    assert route.status == ROUTE_SUPPORTED
    assert route.selected_model == "fcff"
    assert route.model_type == "FCFF"
    assert route.model_factory is FCFFValuationModel
    assert route.facts_contract is FinancialFacts
    assert route.blockers == []


def test_cyclical_cash_return_routes_to_the_shared_cyclical_contract():
    route = route_profile("cyclical_cash_return")

    assert route.status == ROUTE_SUPPORTED
    assert route.model_type == "cyclical_normalized"
    assert route.model_factory is CyclicalNormalizedValuationModel
    assert route.facts_contract is CyclicalFacts


def test_quality_compounder_routes_to_the_shared_residual_income_contract():
    route = route_profile("quality_compounder")

    assert route.status == ROUTE_SUPPORTED
    assert route.model_type == "residual_income_or_equity_value"
    assert route.model_factory is ResidualIncomeEquityValuationModel
    assert route.facts_contract is QualityCompounderFacts
    assert route.blockers == []


def test_cross_check_model_cannot_be_selected_as_primary():
    route = route_profile("mature_manufacturing", "relative_multiple")

    assert route.status == ROUTE_MODEL_NOT_APPLICABLE
    assert "model_not_primary_for_profile:relative_multiple:fcff" in route.blockers


def test_model_rejected_by_profile_is_not_routed():
    route = route_profile("quality_compounder", "fcff_default")

    assert route.status == ROUTE_MODEL_NOT_APPLICABLE
    assert route.model_factory is None


def test_unknown_model_is_rejected_without_a_fallback():
    route = ValuationRouter().route(PROFILES["mature_manufacturing"], "generic_pe")

    assert route.status == ROUTE_UNSUPPORTED
    assert "model_not_authorized_for_profile:generic_pe" in route.blockers


def test_routing_contract_has_no_symbol_parameter_or_symbol_state():
    route = ValuationRouter().route(PROFILES["mature_manufacturing"])
    policy = route.as_policy()

    assert "symbol" not in policy
    assert route.selected_model == PROFILES["mature_manufacturing"].primary_valuation_model


def test_unknown_profile_id_fails_closed():
    with pytest.raises(ValueError, match="Unknown research profile"):
        route_profile("missing_profile")


def test_fcff_builder_records_profile_based_route_without_writing_runtime_state():
    payload = BUILD_MODULE.build(
        symbol="000333",
        case_path=ROOT / "runtime/excel-mvp-research-cases/evidence.json",
        facts_path=ROOT / "runtime/company-research/midea-fcff-facts-20260922/evidence.json",
        model="fcff",
        profile_id="mature_manufacturing",
    )

    assert payload["result"]["status"] == "not_ready"
    assert payload["valuation_route"]["profile_id"] == "mature_manufacturing"
    assert payload["valuation_route"]["status"] == ROUTE_SUPPORTED
    assert payload["valuation_route"]["model_type"] == "FCFF"
    assert "symbol" not in payload["valuation_route"]


def test_fcff_builder_rejects_an_economically_incompatible_profile():
    with pytest.raises(ValueError, match="does not support"):
        BUILD_MODULE.build(
            symbol="000333",
            case_path=ROOT / "runtime/excel-mvp-research-cases/evidence.json",
            facts_path=ROOT / "runtime/company-research/midea-fcff-facts-20260922/evidence.json",
            model="fcff",
            profile_id="cyclical_cash_return",
        )
