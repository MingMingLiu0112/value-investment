from __future__ import annotations

import pytest

from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_models.cyclical import (
    CyclicalFacts,
    CyclicalNormalizedValuationModel,
)
from value_investment_agent.valuation_models.fcff import (
    FCFFValuationModel,
    FinancialFacts,
)
from value_investment_agent.valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeEquityValuationModel,
)
from value_investment_agent.valuation_router import (
    VALUATION_MODEL_REGISTRY,
    ValuationModelRegistration,
    ValuationModelRegistry,
    ValuationRouter,
    route_profile,
)


def test_registry_maps_model_ids_types_builders_and_fact_contracts():
    assert VALUATION_MODEL_REGISTRY.get("fcff").model_factory is FCFFValuationModel
    assert VALUATION_MODEL_REGISTRY.by_model_type("FCFF").facts_contract is FinancialFacts
    assert isinstance(VALUATION_MODEL_REGISTRY.build("fcff"), FCFFValuationModel)
    assert isinstance(
        VALUATION_MODEL_REGISTRY.by_model_type("cyclical_normalized").build(),
        CyclicalNormalizedValuationModel,
    )
    assert VALUATION_MODEL_REGISTRY.get(
        "residual_income_or_equity_value"
    ).facts_contract is QualityCompounderFacts
    assert isinstance(
        VALUATION_MODEL_REGISTRY.by_model_type(
            "residual_income_or_equity_value"
        ).build(),
        ResidualIncomeEquityValuationModel,
    )


def test_registry_exposes_explicit_required_input_contracts():
    fcff = VALUATION_MODEL_REGISTRY.required_inputs("fcff")
    cyclical = VALUATION_MODEL_REGISTRY.required_inputs("cyclical_normalized")
    residual = VALUATION_MODEL_REGISTRY.required_inputs(
        "residual_income_or_equity_value"
    )

    assert set(FinancialFacts.REQUIRED_FCFF_INPUTS) <= set(fcff)
    assert "scenario_inputs" in fcff
    assert set(CyclicalFacts.REQUIRED_CYCLICAL_INPUTS) <= set(cyclical)
    assert set(QualityCompounderFacts.REQUIRED_COMMON_INPUTS) <= set(residual)
    assert "scenario_inputs" in residual


def test_profile_allowed_models_do_not_use_symbol_or_unsupported_models():
    for profile_id in (
        "quality_compounder",
        "mature_manufacturing",
        "cyclical_cash_return",
    ):
        profile = PROFILES[profile_id]
        allowed = VALUATION_MODEL_REGISTRY.allowed_models(profile)

        assert allowed[0] == profile.primary_valuation_model
        assert set(allowed) == (
            {profile.primary_valuation_model, *profile.cross_check_models}
            - set(profile.unsupported_models)
        )
        assert not set(allowed) & set(profile.unsupported_models)


def test_router_policy_exposes_model_and_required_input_contract_without_symbol():
    route = route_profile("mature_manufacturing")
    policy = route.as_policy()

    assert policy["selected_model"] == "fcff"
    assert policy["model_type"] == "FCFF"
    assert policy["facts_contract"] == "FinancialFacts"
    assert set(FinancialFacts.REQUIRED_FCFF_INPUTS) <= set(
        policy["required_inputs"]
    )
    assert "symbol" not in policy


def test_route_builder_returns_the_registered_model_instance():
    route = route_profile("cyclical_cash_return")
    model = route.build_model()

    assert isinstance(model, CyclicalNormalizedValuationModel)
    assert model.model_type == "cyclical_normalized"


def test_registry_rejects_duplicate_ids_and_model_types():
    base = VALUATION_MODEL_REGISTRY.get("fcff")
    assert base is not None
    registry = ValuationModelRegistry([base])

    duplicate_id = ValuationModelRegistration(
        "fcff",
        "duplicate",
        FCFFValuationModel,
        FinancialFacts,
        ("ebit",),
    )
    with pytest.raises(ValueError, match="Duplicate model id"):
        registry.register(duplicate_id)

    duplicate_type = ValuationModelRegistration(
        "duplicate",
        "FCFF",
        FCFFValuationModel,
        FinancialFacts,
        ("ebit",),
    )
    with pytest.raises(ValueError, match="Duplicate model type"):
        registry.register(duplicate_type)


def test_router_accepts_an_explicit_registry_instance():
    router = ValuationRouter(VALUATION_MODEL_REGISTRY)
    route = router.route(PROFILES["quality_compounder"])

    assert route.status == "SUPPORTED"
    assert route.model_type == "residual_income_or_equity_value"
    assert route.required_inputs

