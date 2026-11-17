"""TEST_ONLY: split transport never makes a lone model reply E2-ready."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_operating_horizon_draft_v2 import context, NOW
from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_split_v6 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

SOURCE = {"path": "TEST_ONLY/original.pdf", "sha256": "c" * 64}


def parts(value):
    annual = deepcopy(value)
    cash = annual["years"]["2026"].pop("shareholder_cash_paths")
    annual = json.dumps(annual)
    return annual, json.dumps({"year": "2026",
        "annual_response_sha256": hashlib.sha256(annual.encode("utf-8")).hexdigest(),
        "shareholder_cash_paths": cash})


def check(context, annual, cash, **changes):
    binding = mod.build_requests(context, [2026], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=NOW).binding
    return mod.validate_responses(annual, cash, context=context, years=[2026],
        source_binding=SOURCE, binding=binding, annual_generated_at=NOW,
        cash_generated_at=NOW, **changes)


def test_two_complete_parts_pass_existing_strict_annual_and_cash_validation(context):
    annual, cash = parts(payload())
    result = check(context, annual, cash)
    assert result["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"
    assert result["split_contract"]["source_binding_sha256"]
    request = mod.build_requests(context, [2026], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=NOW)
    assert request.annual.max_completion_tokens == 4096
    assert request.cash.max_completion_tokens == 4096
    assert set(request.cash.output_schema["properties"]) == {"year", "annual_response_sha256", "shareholder_cash_paths"}
    cash_input = json.loads(request.cash.user)
    assert cash_input["annual_response_sha256"] == request.binding["annual_response_sha256"]
    assert set(cash_input["validated_annual_scenarios"]["scenarios"]) == {"bear", "base", "bull"}
    assert cash_input["validated_annual_scenarios"]["scenarios"]["base"]["pretax_profit_range_cny"]


@pytest.mark.parametrize("mutation,match", [
    (lambda p: p["shareholder_cash_paths"]["base"]["operating_wc_cash_cny"].update(
        classification="UNKNOWN", value="0", unit="CNY"), "UNKNOWN_CASH"),
    (lambda p: p["shareholder_cash_paths"]["base"]["commitment_cash_cny"].update(
        evidence_ids=["forged"]), "CITATION"),
    (lambda p: p.update(year="2027"), "V6_CASH_YEAR_MISMATCH"),
])
def test_cash_reply_fails_closed(context, mutation, match):
    annual, cash = parts(payload())
    changed = json.loads(cash); mutation(changed)
    with pytest.raises(ValueError, match=match):
        check(context, annual, json.dumps(changed))


def test_annual_reply_and_changed_source_fail_closed(context):
    annual, cash = parts(payload())
    changed = json.loads(annual)
    changed["years"]["2026"]["operating_paths"]["base"]["drivers"]["volume_change"]["evidence_ids"] = ["forged"]
    with pytest.raises(ValueError, match="CITATION"):
        check(context, json.dumps(changed), cash)
    binding = mod.build_requests(context, [2026], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=NOW).binding
    with pytest.raises(ValueError, match="SOURCE_OR_REQUEST_CHANGED"):
        mod.validate_responses(annual, cash, context=context, years=[2026],
            source_binding={**SOURCE, "sha256": "d" * 64}, binding=binding,
            annual_generated_at=NOW, cash_generated_at=NOW)


def test_missing_part_future_source_and_multi_year_rejected(context):
    annual, _ = parts(payload())
    with pytest.raises((ValueError, TypeError)):
        check(context, annual, None)
    with pytest.raises(ValueError, match="EXACTLY_ONE_YEAR"):
        mod.build_annual_request(context, [2026, 2027], source_binding=SOURCE)
    context["evidence"][0]["available_at"] = "2027-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="future"):
        mod.build_annual_request(context, [2026], source_binding=SOURCE)


def test_swapped_valid_annual_response_cannot_match_cash_request(context):
    original, cash = parts(payload())
    binding = mod.build_requests(context, [2026], source_binding=SOURCE,
        annual_response=original, annual_generated_at=NOW).binding
    swapped = json.loads(original)
    swapped["years"]["2026"]["operating_paths"]["base"]["drivers"]["volume_change"].update(
        lower="0.02", upper="0.02")
    swapped = json.dumps(swapped)
    with pytest.raises(ValueError, match="V6_SPLIT_SOURCE_OR_REQUEST_CHANGED"):
        mod.validate_responses(swapped, cash, context=context, years=[2026],
            source_binding=SOURCE, binding=binding,
            annual_generated_at=NOW, cash_generated_at=NOW)
    forged_cash = json.loads(cash)
    forged_cash["annual_response_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V6_CASH_ANNUAL_RESPONSE_MISMATCH"):
        check(context, original, json.dumps(forged_cash))


def test_unknown_remains_unknown_and_mixed_model_parts_rejected(context):
    annual, cash = parts(payload(unknown=True))
    result = check(context, annual, cash)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert result["years"]["2026"]["shareholder_cash_paths"]["base"]["complete"] is False
    first = LLMResponse(annual, 10, 20, "deepseek-flash")
    second = LLMResponse(cash, 10, 20, "other-model")
    with pytest.raises(ValueError, match="MODEL_OR_TYPE_MISMATCH"):
        check(context, first, second)
