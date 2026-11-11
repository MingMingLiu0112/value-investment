"""Offline V8 split transport; no model or runner calls."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json

import pytest

from test_operating_horizon_annual_v3 import paired as paired_fixture
from test_operating_horizon_draft_v1 import context as base_context, payload as annual_payload
from test_operating_horizon_draft_v3 import payload as cash_fixture
from value_investment_agent.application.research.agent_review import operating_horizon_split_v8 as split
from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v3 as cash_v3
from value_investment_agent.application.research.agent_review.issuer_dividend_plan_v2 import URL


SOURCE = dict(path="TEST_ONLY/source.json", sha256="e" * 64)
ANNUAL_AT = datetime(2026, 11, 12, 0, tzinfo=timezone.utc)
CASH_AT = ANNUAL_AT + timedelta(hours=1)


@pytest.fixture
def split_context(base_context):
    value = deepcopy(paired_fixture.__wrapped__(base_context))
    value.update(symbol="600519", issuer_name="贵州茅台酒股份有限公司",
        as_of="2026-11-11", source_as_of="2026-11-11T22:00:00+08:00")
    value["issuer_dividend_plan"] = dict(
        schema_version="d2-issuer-dividend-plan-anchor-v2", symbol="600519",
        status="DISCLOSED_CONDITIONAL_ANNUAL_PAYOUT_PLAN",
        fiscal_years=[2024, 2025, 2026], minimum_ratios=["0.75"] * 3,
        profit_basis="consolidated_parent_attributable",
        distribution_basis="annual_total_cash_dividends", physical_pages=[1, 2],
        action="no_order", formal_eligibility=False,
        source_binding=dict(path="TEST_ONLY/issuer.pdf", sha256="c" * 64, source_url=URL),
        receipt_binding=dict(path="TEST_ONLY/receipt.json", sha256="d" * 64),
        available_at="2026-11-11T13:09:16+00:00")
    return value


def _annual():
    value = annual_payload([2027])
    for path in value["years"]["2027"]["operating_paths"].values():
        path["unit_cost_mechanism"] = "UNRESOLVED_SENSITIVITY"
        path["drivers"]["other_pretax_cny"]["evidence_ids"] = ["test:pre_tax_profit"]
        path["unit_cost_case"] = dict(
            mechanism="条件性采购投入价格下降，仍需核对实际采购合同",
            source_anchor_ids=["test:cost"],
            contrary_evidence_ids=["test:2026-06-30:cost"],
            reopen_condition="若下期同口径营业成本率继续上升则重新估计")
    return json.dumps(value, ensure_ascii=False)


def _cash(*, unknown=False):
    paths = deepcopy(cash_fixture(unknown=unknown)["years"]["2026"]["shareholder_cash_paths"])
    if not unknown:
        for path in paths.values():
            for term in (path[name] for name in (*split.full.RATIO_TERMS, *split.full.CASH_TERMS)):
                term["rationale"] = "Mechanism: historical profit and funding needs bound this conditional scenario."
    return json.dumps({"years": {"2027": {"shareholder_cash_paths": paths}}})


def _requests(context, annual):
    return split.build_requests(context, [2027], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=ANNUAL_AT)


def test_v8_request_binds_validated_2027_annual_and_expired_plan(split_context):
    annual = _annual()
    requests = _requests(split_context, annual)
    assert requests.binding["year"] == "2027"
    assert requests.binding["annual_response_sha256"]
    assert requests.binding["annual_request_sha256"] and requests.binding["cash_request_sha256"]
    assert "VALIDATED_2027_ANNUAL_V3=" in requests.cash.user
    assert "EXPIRED_ISSUER_PLAN_HISTORICAL_COUNTEREVIDENCE_V3=" in requests.cash.user
    assert "not a 2027 target minimum" in requests.cash.system
    assert requests.binding["source_binding_sha256"]


def test_annual_invalid_rejected_before_cash_request(split_context):
    value = json.loads(_annual())
    value["years"]["2027"]["operating_paths"]["base"].pop("unit_cost_case")
    with pytest.raises(ValueError, match="V3_UNIT_COST_CASE_REQUIRED"):
        _requests(split_context, json.dumps(value))


def test_source_or_annual_response_change_rejected(split_context):
    annual = _annual()
    request = _requests(split_context, annual)
    with pytest.raises(ValueError, match="SOURCE_REQUEST_OR_ANNUAL_CHANGED"):
        split.validate_responses(annual, _cash(), context=split_context, years=[2027],
            source_binding={**SOURCE, "sha256": "f" * 64}, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=CASH_AT)
    changed = deepcopy(split_context)
    changed["evidence"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="SOURCE_REQUEST_OR_ANNUAL_CHANGED"):
        split.validate_responses(annual, _cash(), context=changed, years=[2027],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=CASH_AT)
    with pytest.raises(ValueError, match="SOURCE_REQUEST_OR_ANNUAL_CHANGED"):
        split.validate_responses(annual + " ", _cash(), context=split_context, years=[2027],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=CASH_AT)


def test_full_source_context_projects_exact_timestamp_and_plan(split_context):
    full = deepcopy(split_context)
    full["as_of"] = full.pop("source_as_of")
    full["source_binding"] = deepcopy(SOURCE)
    requests = _requests(full, _annual())
    assert requests.binding["source_binding_sha256"]
    assert "source_as_of" in requests.cash.user
    with pytest.raises(ValueError, match="SOURCE_BINDING_MISMATCH"):
        split.build_requests(full, [2027],
            source_binding={**SOURCE, "sha256": "f" * 64},
            annual_response=_annual(), annual_generated_at=ANNUAL_AT)


def test_cash_generation_order_and_numeric_mechanism(split_context):
    annual = _annual()
    request = _requests(split_context, annual)
    with pytest.raises(ValueError, match="GENERATION_ORDER"):
        split.validate_responses(annual, _cash(), context=split_context, years=[2027],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=ANNUAL_AT - timedelta(seconds=1))
    bad = json.loads(_cash())
    bad["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]["rationale"] = "The old 75% plan applies."
    with pytest.raises(ValueError, match="NUMERIC_CASH_HISTORY_AND_MECHANISM_REQUIRED|EXPIRED_PLAN_CANNOT"):
        split.validate_responses(annual, json.dumps(bad), context=split_context, years=[2027],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=CASH_AT)


def test_unknown_cash_is_not_promoted_and_full_annotation_mismatch_fails_closed(split_context):
    annual = _annual()
    request = _requests(split_context, annual)
    with pytest.raises(split.FullValidatorBlocked, match="FULL_VALIDATOR_REJECTED_REQUIRED_ANNUAL_ANNOTATIONS_FAIL_CLOSED") as blocked:
        split.validate_responses(annual, _cash(unknown=True), context=split_context, years=[2027],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=ANNUAL_AT, cash_generated_at=CASH_AT)
    assert blocked.value.response_hashes["annual"] == request.binding["annual_response_sha256"]
    assert blocked.value.response_hashes["cash"]
    assert blocked.value.cash_policy_status == "INCOMPLETE_UNKNOWN_TERMS"
    assert blocked.value.full_validator_reason


def test_cash_v3_direct_numeric_and_unknown_contract(split_context):
    request = cash_v3.build_request(split_context, [2027])
    assert "EXPIRED_ISSUER_PLAN_HISTORICAL_COUNTEREVIDENCE_V3=" in request.user
    numeric = cash_v3.validate_response(_cash(), split_context, [2027], CASH_AT)
    assert numeric["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert numeric["historical_plan_context"]["policy_years"] == [2024, 2025, 2026]
    unknown = cash_v3.validate_response(_cash(unknown=True), split_context, [2027], CASH_AT)
    assert unknown["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert unknown["action"] == "no_order" and unknown["formal_eligibility"] is False


def test_cash_v3_rejects_expired_ratio_and_late_plan(split_context):
    copied = json.loads(_cash())
    copied["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]["value"] = "0.75"
    with pytest.raises(ValueError, match="EXPIRED_PLAN_CANNOT_SET_2027_CASH"):
        cash_v3.validate_response(json.dumps(copied), split_context, [2027], CASH_AT)
    split_context["issuer_dividend_plan"]["available_at"] = "2026-11-12T00:00:00+00:00"
    with pytest.raises(ValueError, match="PLAN_NOT_AVAILABLE_AT_EXACT_SOURCE_TIME"):
        cash_v3.build_request(split_context, [2027])


def test_cash_v3_rejects_standalone_response_and_future_plan_year(split_context):
    with pytest.raises(ValueError):
        cash_v3.validate_response(json.dumps({"shareholder_cash_paths": {}}),
            split_context, [2027], CASH_AT)
    with pytest.raises(ValueError, match="EXACT_2027_YEAR_REQUIRED"):
        cash_v3.build_request(split_context, [2028])
    malformed = json.loads(_cash(unknown=True))
    malformed["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"].update(
        value="0", unit="ratio")
    with pytest.raises(ValueError, match="UNKNOWN_CASH"):
        cash_v3.validate_response(json.dumps(malformed), split_context, [2027], CASH_AT)
