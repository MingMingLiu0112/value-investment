"""Direct v2 cash draft contract tests; synthetic response, no provider calls."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from test_operating_horizon_draft_v3 import context as base_context, payload
from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v2 as draft


NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


@pytest.fixture
def context(base_context):
    result = deepcopy(base_context)
    result.update(symbol="600519", issuer_name="贵州茅台酒股份有限公司", as_of="2026-11-12")
    result["issuer_dividend_plan"] = dict(
        schema_version="d2-issuer-dividend-plan-anchor-v2", symbol="600519",
        status="DISCLOSED_CONDITIONAL_ANNUAL_PAYOUT_PLAN",
        fiscal_years=[2024, 2025, 2026], minimum_ratios=["0.75"] * 3,
        profit_basis="consolidated_parent_attributable",
        distribution_basis="annual_total_cash_dividends", physical_pages=[1, 2],
        action="no_order", formal_eligibility=False,
        source_binding=dict(path="artifacts/current/issuer.pdf", sha256="c" * 64,
            source_url=draft.URL),
        receipt_binding=dict(path="artifacts/current/receipt.json", sha256="d" * 64),
        available_at="2026-11-11T13:09:16+00:00")
    return result


def _response(context):
    result = {"years": {"2026": {"shareholder_cash_paths":
        deepcopy(payload()["years"]["2026"]["shareholder_cash_paths"])}}}
    evidence_id = draft.policy_context_v2(context, [2026])["evidence_id"]
    for path in result["years"]["2026"]["shareholder_cash_paths"].values():
        path["target_payout_ratio"].update(value="0.4",
            rationale="Conditional issuer target is separate from this forecast assumption based on profit history.",
            evidence_ids=[evidence_id, "test:pre_tax_profit"])
    return result


def test_request_and_response_keep_plan_target_separate_from_forecast(context):
    original = deepcopy(context)
    request = draft.build_request(context, [2026])
    plan = draft.policy_context_v2(context, [2026])
    target_schema = request.output_schema["properties"]["years"]["properties"]["2026"][
        "properties"]["shareholder_cash_paths"]["properties"]["base"]["properties"]
    assert plan["evidence_id"] in target_schema["target_payout_ratio"]["properties"]["evidence_ids"]["items"]["enum"]
    assert plan["evidence_id"] not in target_schema["accessible_profit_ratio"]["properties"]["evidence_ids"]["items"]["enum"]
    assert plan["source_binding"] == context["issuer_dividend_plan"]["source_binding"]
    assert plan["receipt_binding"] == context["issuer_dividend_plan"]["receipt_binding"]
    assert "SOURCE_BOUND_ISSUER_DIVIDEND_PLAN_V2=" in request.user
    assert "not a forecast payout ratio" in request.system
    result = draft.validate_response(json.dumps(_response(context)), context, [2026], NOW)
    assert result["policy_context"]["disclosed_policy_target_2026"]["minimum_ratio"] == "0.75"
    assert result["years"]["2026"]["shareholder_cash_paths"]["base"]["terms"]["target_payout_ratio"]["value"] == "0.4"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert context == original


@pytest.mark.parametrize("mutation,match", [
    (lambda c: c["issuer_dividend_plan"].pop("receipt_binding"), "BINDING_REQUIRED"),
    (lambda c: c["issuer_dividend_plan"].pop("source_binding"), "BINDING_REQUIRED"),
    (lambda c: c["issuer_dividend_plan"].update(symbol="000568"), "IDENTITY_INVALID"),
    (lambda c: c["issuer_dividend_plan"].update(available_at="2026-11-13T00:00:00+08:00"), "NOT_AVAILABLE"),
    (lambda c: c["issuer_dividend_plan"].update(minimum_ratios=["0.75", "0.75", "0.80"]), "IDENTITY_INVALID"),
])
def test_invalid_plan_context_rejected(context, mutation, match):
    mutation(context)
    with pytest.raises(ValueError, match=match):
        draft.build_request(context, [2026])


def test_no_2027_extrapolation(context):
    for years in ([2027], [2026, 2027]):
        with pytest.raises(ValueError, match="NO_EXTRAPOLATION"):
            draft.build_request(context, years)
        with pytest.raises(ValueError, match="NO_EXTRAPOLATION"):
            draft.validate_response(json.dumps(_response(context)), context, years, NOW)


def test_policy_target_can_remain_unknown_without_forecast(context):
    result = _response(context)
    evidence_id = draft.policy_context_v2(context, [2026])["evidence_id"]
    for path in result["years"]["2026"]["shareholder_cash_paths"].values():
        path["target_payout_ratio"] = dict(classification="UNKNOWN", value=None,
            unit="not_quantified", rationale="Conditional plan does not establish a forecast payout.",
            evidence_ids=[evidence_id])
    accepted = draft.validate_response(json.dumps(result), context, [2026], NOW)
    assert accepted["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert accepted["policy_context"]["disclosed_policy_target_2026"]["minimum_ratio"] == "0.75"


@pytest.mark.parametrize("change,match", [
    ("cash_citation", "CANNOT_ESTABLISH_PARENT_CASH"),
    ("missing_policy", "MUST_CITE_POLICY"),
    ("policy_only_forecast", "NOT_FORECAST"),
    ("parent_denominator", "DENOMINATOR_OR_CASH_INFERENCE"),
])
def test_policy_cannot_be_promoted_to_forecast_or_parent_cash(context, change, match):
    result = _response(context)
    paths = result["years"]["2026"]["shareholder_cash_paths"]
    term = paths["base"]["target_payout_ratio"]
    evidence_id = draft.policy_context_v2(context, [2026])["evidence_id"]
    if change == "cash_citation":
        paths["base"]["accessible_profit_ratio"]["evidence_ids"] = [evidence_id]
    elif change == "missing_policy":
        term["evidence_ids"] = ["test:pre_tax_profit"]
    elif change == "policy_only_forecast":
        term["evidence_ids"] = [evidence_id]
    else:
        term["rationale"] = "Conditional plan proves parent net profit forecast assumption."
    with pytest.raises(ValueError, match=match):
        draft.validate_response(json.dumps(result), context, [2026], NOW)
