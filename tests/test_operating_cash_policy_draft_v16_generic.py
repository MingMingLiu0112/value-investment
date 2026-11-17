"""Plan-neutral cash contract; TEST_ONLY fixtures are not economic admission."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from test_operating_horizon_draft_v1 import context as base_context
from test_operating_horizon_split_v8 import _cash, _annual
from test_operating_horizon_annual_v3 import paired as paired_fixture
from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v16_generic as draft

AT = datetime(2026, 11, 12, tzinfo=timezone.utc)
PIN = {"path": "TEST_ONLY/source.json", "sha256": "c" * 64}


@pytest.fixture
def source(base_context):
    value = deepcopy(base_context)
    value.update(schema_version="operating-horizon-sources-v1",
        as_of=(AT - timedelta(hours=1)).isoformat(), source_binding=PIN,
        action="no_order", formal_eligibility=False)
    value["evidence"].append(dict(value["evidence"][0], id="test:dividend",
        field="historical_dividend", text="TEST_ONLY dividend paid", value="20"))
    return value


def response(source):
    payload = json.loads(_cash(unknown=True))
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for term in path.values():
            if isinstance(term, dict) and "evidence_ids" in term:
                term["evidence_ids"] = [source["evidence"][0]["id"]]
    return payload


def test_plan_optional_request_and_unknown_remain_unapproved(source):
    request = draft.build_request(source, PIN)
    assert "No issuer dividend plan is assumed" in request.system
    assert "TERM_HISTORICAL_CANDIDATE_IDS=" in request.user
    assert draft.candidates(source, PIN)["target_payout_ratio"] == ["test:dividend"]
    result = draft.validate_response(json.dumps(response(source)), source, PIN, AT)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


def test_numeric_cash_term_needs_relevant_historical_id(source):
    payload = response(source)
    term = payload["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]
    term.update(classification="FORECAST_ASSUMPTION", value="0.1", unit="ratio",
        rationale="Mechanism: TEST_ONLY 2025 parent dividend can conditionally change, subject to review.")
    with pytest.raises(ValueError, match="V16_GENERIC_NUMERIC_TERM_LACKS_BOUND_MECHANISM"):
        draft.validate_response(json.dumps(payload), source, PIN, AT)
    term["evidence_ids"] = ["test:dividend"]
    result = draft.validate_response(json.dumps(payload), source, PIN, AT)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"


def test_source_binding_time_and_future_evidence_rejected(source):
    with pytest.raises(ValueError, match="BOUND_SOURCE_REQUIRED"):
        draft.build_request(source, {"path": PIN["path"], "sha256": "d" * 64})
    with pytest.raises(ValueError, match="BOUND_SOURCE_REQUIRED"):
        draft.build_request({**source, "source_binding": {"path": "../escape", "sha256": "c" * 64}},
            {"path": "../escape", "sha256": "c" * 64})
    with pytest.raises(ValueError, match="SOURCE_TIME_INVALID"):
        draft.validate_response(json.dumps(response(source)), source, PIN, AT - timedelta(hours=2))
    source["evidence"][0]["available_at"] = (AT + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="EVIDENCE_UNAVAILABLE_OR_DUPLICATE"):
        draft.build_request(source, PIN)


def test_staged_cash_request_binds_validated_annual_response(base_context):
    source = deepcopy(paired_fixture.__wrapped__(base_context))
    source.update(schema_version="operating-horizon-sources-v1",
        as_of=(AT - timedelta(hours=1)).isoformat(), source_binding=PIN,
        action="no_order", formal_eligibility=False)
    annual = _annual()
    request, binding = draft.build_staged_cash_request(source, PIN, annual, AT)
    assert "VALIDATED_2027_ANNUAL_V3=" in request.user
    assert binding["annual_response_sha256"] and binding["cash_request_sha256"]
    assert binding["action"] == "no_order"
    with pytest.raises(ValueError):
        draft.build_staged_cash_request(source, PIN, "{}", AT)
    changed = deepcopy(source)
    changed["evidence"][0]["text"] += " changed"
    _, changed_binding = draft.build_staged_cash_request(changed, PIN, annual, AT)
    assert changed_binding["source_context_sha256"] != binding["source_context_sha256"]


def test_staged_replay_incomplete_cash_stays_unapproved(base_context):
    source = deepcopy(paired_fixture.__wrapped__(base_context))
    source.update(schema_version="operating-horizon-sources-v1",
        as_of=(AT - timedelta(hours=1)).isoformat(), source_binding=PIN,
        action="no_order", formal_eligibility=False)
    annual = _annual()
    _, binding = draft.build_staged_cash_request(source, PIN, annual, AT)
    result = draft.validate_staged_responses(annual, _cash(unknown=True),
        context=source, source_binding=PIN, binding=binding,
        annual_generated_at=AT, cash_generated_at=AT + timedelta(minutes=1))
    assert result["status"] == "WAITING_EVIDENCE"
    assert result["reason"] == "CASH_POLICY_INCOMPLETE"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    with pytest.raises(ValueError, match="STAGE_BINDING_CHANGED"):
        draft.validate_staged_responses(annual, _cash(unknown=True),
            context=source, source_binding=PIN, binding={**binding, "annual_response_sha256": "f" * 64},
            annual_generated_at=AT, cash_generated_at=AT + timedelta(minutes=1))


def test_staged_replay_complete_test_cash_has_deterministic_result(base_context):
    source = deepcopy(paired_fixture.__wrapped__(base_context))
    source.update(schema_version="operating-horizon-sources-v1",
        as_of=(AT - timedelta(hours=1)).isoformat(), source_binding=PIN,
        action="no_order", formal_eligibility=False)
    source["evidence"].append(dict(source["evidence"][0], id="test:dividend",
        field="historical_dividend", text="TEST_ONLY dividend paid"))
    source["evidence"].append(dict(source["evidence"][0], id="test:cash-fields",
        field="historical_cash_policy", text="TEST_ONLY dividend parent CFO capex working capital commitment"))
    annual = _annual()
    payload = json.loads(_cash())
    anchors = draft.candidates(source, PIN)
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for name, term in path.items():
            if name in anchors and term["classification"] != "UNKNOWN":
                term["evidence_ids"] = anchors[name][:1]
            elif isinstance(term, dict) and not term.get("evidence_ids"):
                term["evidence_ids"] = [source["evidence"][0]["id"]]
    _, binding = draft.build_staged_cash_request(source, PIN, annual, AT)
    result = draft.validate_staged_responses(annual, json.dumps(payload),
        context=source, source_binding=PIN, binding=binding,
        annual_generated_at=AT, cash_generated_at=AT + timedelta(minutes=1))
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result.get("stage_binding") == binding
    assert result.get("status") != "WAITING_EVIDENCE", result.get("full_validator_reason")
