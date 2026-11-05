from copy import deepcopy

import pytest

from value_investment_agent.application.decision.value_model_identity import (
    project_catalog_identity, resolve_value_model_identity,
)
from value_investment_agent.valuation_router import VALUATION_MODEL_REGISTRY
from value_investment_agent.valuation_models.residual_income import DATED_MODEL_VERSION, MODEL_VERSION


@pytest.mark.parametrize("version", [MODEL_VERSION, DATED_MODEL_VERSION])
def test_real_catalog_identity_comes_from_registered_type_and_declared_version(version):
    registration = VALUATION_MODEL_REGISTRY.by_model_type("residual_income_or_equity_value")
    identity = resolve_value_model_identity(dict(model_type=registration.model_type, model_version=version),
                                            profile_id="quality_compounder")
    assert identity["model_id"] == registration.model_id
    assert identity["model_version"] == version
    assert len(identity["code_evidence"]) == 2
    assert all(len(row["sha256"]) == 64 for row in identity["code_evidence"])
    assert identity["scope"] == "REGISTERED_IMPLEMENTATION_IDENTITY_NOT_MODEL_APPROVAL"


@pytest.mark.parametrize("model_type,version,profile", [
    ("invented", DATED_MODEL_VERSION, "quality_compounder"),
    ("residual_income_or_equity_value", "invented-v99", "quality_compounder"),
    ("residual_income_or_equity_value", DATED_MODEL_VERSION, "unknown"),
    ("residual_income_or_equity_value", DATED_MODEL_VERSION, "cyclical_cash_return"),
])
def test_unknown_or_inapplicable_catalog_identity_stays_unknown(model_type, version, profile):
    assert resolve_value_model_identity(dict(model_type=model_type, model_version=version), profile_id=profile) is None


def test_public_projection_fills_only_absent_identity_without_approving_model():
    explanation = dict(model_id=None, model_validity=dict(model_id=None, status="UNKNOWN"),
        valuation=dict(model_type="residual_income_or_equity_value", model_version=DATED_MODEL_VERSION),
        price_context=dict(price_attractiveness=dict(profile_id="quality_compounder")))
    before = deepcopy(explanation)
    projected = project_catalog_identity(explanation)
    assert projected["model_id"] == "residual_income_or_equity_value"
    assert projected["model_validity"]["status"] == "UNKNOWN"
    assert explanation == before
    explanation["model_id"] = "existing-restored-id"
    assert project_catalog_identity(explanation)["model_id"] == "existing-restored-id"
