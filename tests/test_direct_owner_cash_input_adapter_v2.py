"""V2 descriptor and shared-service integration tests."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from test_direct_owner_cash_input_adapter_v1 import package as v1_package
from value_investment_agent.application.research import direct_owner_cash_input_adapter_v2 as adapter
from value_investment_agent.research_input import descriptor_sha256
from value_investment_agent.valuation_models import direct_owner_cash_v2 as model

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def package(*, scheduled="0"):
    result = deepcopy(v1_package())
    result["descriptor_version"] = adapter.DESCRIPTOR_VERSION
    result["dependencies"]["model_version"] = model.MODEL_VERSION
    result["facts"]["direct_owner_cash_contract"] = model.MODEL_VERSION
    for item in result["facts"]["scenario_inputs"].values():
        item["scenario_contract"] = model.SCENARIO_CONTRACT
        for year in item["years"]:
            year["scheduled_owner_distribution_cny"] = scheduled
    return result


def test_descriptor_roundtrip_hashes_v2_scheduled_cash():
    source = package(scheduled="0")
    descriptor = adapter.build_direct_owner_cash_descriptor(source)
    policy = json.loads(json.dumps(descriptor.as_policy()))
    restored = adapter.descriptor_from_payload(policy)
    assert restored.as_policy() == policy
    assert descriptor.input_sha256 == descriptor_sha256(descriptor)
    assert restored.input_sha256 == descriptor.input_sha256
    assert policy["descriptor_version"] == adapter.DESCRIPTOR_VERSION
    assert policy["facts"]["direct_owner_cash_contract"] == model.MODEL_VERSION
    assert policy["facts"]["scenario_inputs"]["base"]["years"][0]["scheduled_owner_distribution_cny"] == "0"


def test_shared_research_service_consumes_v2_router_and_keeps_no_order():
    outcome, descriptor = adapter.run_direct_owner_cash_research(package(), NOW)
    assert descriptor.dependencies.model_version == model.MODEL_VERSION
    assert outcome.valuation.model_version == model.MODEL_VERSION
    assert outcome.valuation.status == "conditional_research_only"
    assert outcome.valuation.assumptions["formal_eligibility"] is False
    assert outcome.valuation.assumptions["action"] == "no_order"
    assert outcome.decision_recommendation.action == "no_order"
    assert outcome.decision_recommendation.position_guidance is None


def test_descriptor_tampering_is_rejected_without_resealing():
    policy = adapter.build_direct_owner_cash_descriptor(package()).as_policy()
    policy["facts"]["scenario_inputs"]["base"]["years"][0]["scheduled_owner_distribution_cny"] = "1"
    with pytest.raises(ValueError, match="hash does not match|ROUNDTRIP_CHANGED"):
        adapter.descriptor_from_payload(policy)


@pytest.mark.parametrize("change", ["descriptor_extra", "scenario_extra", "wrong_version"])
def test_unknown_fields_and_cross_version_payloads_are_rejected(change):
    policy = adapter.build_direct_owner_cash_descriptor(package()).as_policy()
    if change == "descriptor_extra":
        policy["unregistered"] = True
    elif change == "scenario_extra":
        policy["facts"]["scenario_inputs"]["base"]["unknown"] = "1"
    else:
        policy["descriptor_version"] = "direct-owner-cash-input-v1"
    with pytest.raises(ValueError):
        adapter.descriptor_from_payload(policy)


def test_compilation_payload_diagnostic_is_not_a_valuation_input():
    source = package()
    for item in source["facts"]["scenario_inputs"].values():
        item.pop("scenario_contract")
        item["calculation"] = {"per_share_value": "999999"}
    outcome, descriptor = adapter.run_direct_owner_cash_research(source, NOW)
    assert outcome.valuation.base_value != 999999
    assert "calculation" not in descriptor.as_policy()["facts"]["scenario_inputs"]["base"]


def test_test_only_entry_uses_shared_service_and_sealed_snapshot():
    descriptor = adapter.build_direct_owner_cash_descriptor(package())
    outcome = adapter.run_test_only_direct_owner_cash(
        descriptor, execution_mode="TEST_ONLY", now_utc=lambda: NOW,
    )
    assert outcome.valuation.model_version == model.MODEL_VERSION
    assert outcome.decision_recommendation.action == "no_order"
    descriptor.facts.scenario_inputs["base"].years[0]["scheduled_owner_distribution_cny"] = "1"
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        adapter.run_test_only_direct_owner_cash(
            descriptor, execution_mode="TEST_ONLY", now_utc=lambda: NOW,
        )
