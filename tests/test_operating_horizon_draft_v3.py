from copy import deepcopy
import json
import pytest

from test_operating_horizon_draft_v2 import valid, context, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v3 as mod


def payload(*, unknown=False):
    value = valid()
    for row in value["years"].values():
        paths = {}
        for scenario in ("bear", "base", "bull"):
            terms = {}
            for name in mod.RATIO_TERMS:
                terms[name] = dict(classification="UNKNOWN" if unknown else "FORECAST_ASSUMPTION",
                    value=None if unknown else "0.4", unit="not_quantified" if unknown else "ratio",
                    rationale="来源锚定的未批准政策假设", evidence_ids=["test:pre_tax_profit"])
            for name in mod.CASH_TERMS:
                terms[name] = dict(classification="UNKNOWN" if unknown else "FORECAST_ASSUMPTION",
                    value=None if unknown else "100", unit="not_quantified" if unknown else "CNY",
                    rationale="来源锚定的未批准政策假设", evidence_ids=["test:pre_tax_profit"])
            paths[scenario] = {**terms, "counter_evidence":"现金路径需要独立复核", "reopen_condition":"新报告披露后复核"}
        row["shareholder_cash_paths"] = paths
    return value


def test_complete_appendix_is_source_bound_but_stays_unapproved(context):
    out = mod.validate_response(json.dumps(payload()), context, [2026], NOW)
    assert out["schema_version"] == mod.VERSION
    assert out["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert out["years"]["2026"]["shareholder_cash_paths"]["base"]["complete"] is True
    assert out["valuation_produced"] is False and out["action"] == "no_order"


def test_unknown_term_cannot_be_defaulted_and_blocks_cash_consumption(context):
    out = mod.validate_response(json.dumps(payload(unknown=True)), context, [2026], NOW)
    assert out["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert out["years"]["2026"]["shareholder_cash_paths"]["bear"]["complete"] is False


def test_single_year_gateway_transport_misplacement_is_normalized_then_strictly_validated(context):
    value = payload()
    value["years"]["shareholder_cash_paths"] = value["years"]["2026"].pop("shareholder_cash_paths")
    out = mod.validate_response(json.dumps(value), context, [2026], NOW)
    assert out["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert out["years"]["2026"]["shareholder_cash_paths"]["base"]["complete"] is True


def test_single_year_root_level_policy_transport_is_normalized_without_changing_terms(context):
    value = payload()
    paths = value["years"]["2026"].pop("shareholder_cash_paths")
    value["shareholder_cash_paths"] = paths
    out = mod.validate_response(json.dumps(value), context, [2026], NOW)
    assert out["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert out["years"]["2026"]["shareholder_cash_paths"]["bear"]["terms"]["target_payout_ratio"]["value"] == "0.4"


def test_root_level_policy_transport_with_extra_or_duplicate_fields_fails(context):
    value = payload()
    value["shareholder_cash_paths"] = value["years"]["2026"].pop("shareholder_cash_paths")
    value["unexpected"] = {}
    with pytest.raises(ValueError, match="Exact operating driver fields required"):
        mod.validate_response(json.dumps(value), context, [2026], NOW)
    value.pop("unexpected")
    value["years"]["2026"]["shareholder_cash_paths"] = deepcopy(value["shareholder_cash_paths"])
    with pytest.raises(ValueError, match="Exact operating driver fields required"):
        mod.validate_response(json.dumps(value), context, [2026], NOW)


def test_root_level_transport_never_repairs_wrong_economic_unit(context):
    value = payload()
    value["shareholder_cash_paths"] = value["years"]["2026"].pop("shareholder_cash_paths")
    value["shareholder_cash_paths"]["base"]["target_payout_ratio"]["unit"] = "ratio_of_parent_net_income"
    with pytest.raises(ValueError, match="CASH_POLICY_TERM_CLASSIFICATION_OR_UNIT_INVALID"):
        mod.validate_response(json.dumps(value), context, [2026], NOW)


def test_gateway_transport_misplacement_is_not_normalized_for_multi_year_or_extra_fields(context):
    value = payload()
    value["years"]["shareholder_cash_paths"] = value["years"]["2026"].pop("shareholder_cash_paths")
    value["years"]["unexpected"] = {}
    with pytest.raises(ValueError, match="Exact operating driver fields required"):
        mod.validate_response(json.dumps(value), context, [2026], NOW)


@pytest.mark.parametrize("mutate,code", [
    (lambda p: p["years"]["2026"]["shareholder_cash_paths"]["base"].__setitem__("unexpected", "x"), "(?i)exact"),
    (lambda p: p["years"]["2026"]["shareholder_cash_paths"]["base"]["target_payout_ratio"].update(value="1.2"), "OUT_OF_RANGE"),
    (lambda p: p["years"]["2026"]["shareholder_cash_paths"]["base"]["commitment_cash_cny"].update(evidence_ids=["fabricated"]), "CITATION"),
    (lambda p: p["years"]["2026"]["shareholder_cash_paths"]["base"]["reserve_ratio"].update(classification="UNKNOWN", value="0", unit="ratio"), "UNKNOWN_CASH"),
])
def test_invalid_or_fabricated_cash_policy_terms_fail_closed(context, mutate, code):
    value = payload(); mutate(value)
    with pytest.raises(ValueError, match=code):
        mod.validate_response(json.dumps(value), context, [2026], NOW)


def test_prompt_has_no_implicit_cash_defaults(context):
    request = mod.build_request(context, [2026])
    assert "Do not default any missing term to zero" in request.system
    assert "shareholder_cash_paths belongs inside each years.<year> object" in request.system
    assert "never use status" in request.system
    assert "use literal ratio" in request.transport_output_contract
    assert "ratio_of_parent_net_income" in request.system
    assert "shareholder_cash_paths" in request.output_schema["properties"]["years"]["properties"]["2026"]["required"]


def test_compact_policy_prompt_names_legal_terms_and_rejects_provider_aliases(context):
    from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v1 as compact
    request = compact.build_request(context, [2026])
    assert "target_payout_ratio" in request.transport_output_contract
    assert "commitment_cash_cny" in request.transport_output_contract
    assert "dividend_payout_ratio" in request.transport_output_contract
    assert "evidence_ids is always a non-empty array" in request.transport_output_contract
    assert "counter_evidence and reopen_condition are plain non-empty JSON strings" in request.transport_output_contract
