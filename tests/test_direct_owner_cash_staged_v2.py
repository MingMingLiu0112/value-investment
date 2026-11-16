"""No-network contract tests for the staged parent-cash draft."""
import json
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_staged_v2 as v2
from value_investment_agent.application.research import direct_owner_cash_agent_draft_v1 as adapter
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def context():
    return dict(valuation_date="2025-12-31", input_fingerprint="a" * 64,
                facts={"parent_revenue": {"value_cny": "100", "period_end": "2025-12-31"}})


def term(count):
    return dict(values=["1.25"] * count, evidence_anchors=["parent_revenue"],
                mechanism="Explicit cash mechanism", counter_evidence="Evidence can change",
                reopen_condition="Reopen on new filing")


def fixture(monkeypatch, source_context=None):
    monkeypatch.setattr(v2, "read_parent_cash_agent_facts", lambda **_: source_context or context())
    requests, responses = {}, {}
    for stage in v2.STAGES:
        request = v2.staged_parent_cash_request(root=".", spec_binding={}, scenario="base",
            stage=stage, generated_at=datetime.now(timezone.utc),
            prior_drafts={key: json.loads(responses[key].text)
                          for key in requests})
        packet = json.loads(request.user)
        if stage == "terminal":
            body = dict(terminal=dict(policy={key: term(1) for key in packet["required_fields"]},
                remaining_scheduled_events=[], max_transition_years=10, financing=None,
                rationale="Terminal cash rationale", counter_evidence="Terminal evidence risk",
                reopen_condition="Terminal filing trigger"), cost_of_equity=term(1))
        else:
            body = dict(years=packet["required_years"],
                series={key: term(10) for key in packet["required_fields"]})
            if stage == "operating":
                body.update(annual_notes=["Annual operating reason"] * 10,
                    rationale="Scenario cash rationale", counter_evidence="Scenario evidence risk",
                    reopen_condition="Scenario filing trigger")
        requests[stage] = request
        responses[stage] = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    return requests, responses


def test_stages_merge_exact_contract(monkeypatch):
    requests, responses = fixture(monkeypatch)
    draft = v2.merge_staged_parent_cash(scenario="base", source_fingerprint="a" * 64,
                                         requests=requests, responses=responses)
    assert set(draft["series"]) == v2.FIELDS["operating"] | v2.FIELDS["policy"]
    assert draft["years"] == list(range(2026, 2036))
    assert draft["schema_version"] == v2.DRAFT_VERSION
    assert all("source_fingerprint" not in json.loads(response.text) for response in responses.values())
    policy_context = json.loads(requests["policy"].user)
    assert policy_context["prior_forecast_assumptions_not_facts"]["operating"]["other_operating_cash"] == ["1.25"] * 10
    assert "Explicit cash mechanism" not in requests["policy"].user
    assert "Allowed evidence_anchors IDs only:" in requests["operating"].transport_output_contract
    assert "parent_revenue" in requests["operating"].transport_output_contract
    terminal_instruction = requests["terminal"].transport_output_contract
    assert "exactly two top-level keys: terminal, cost_of_equity" in terminal_instruction
    assert "No years, annual_notes, series" in terminal_instruction
    assert "exactly ONE decimal string" in terminal_instruction
    terminal_context = json.loads(requests["terminal"].user)
    assert "required_years" not in terminal_context
    assert terminal_context["terminal_reference_year"] == 2035
    assert terminal_context["prior_forecast_assumptions_not_facts"]["operating"]["revenue"] == "1.25"
    assert terminal_context["prior_forecast_assumptions_not_facts"]["policy"]["payout_ratio"] == "1.25"


def test_year_keyed_notes_are_losslessly_ordered_without_changing_raw(monkeypatch):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    years = body["years"]
    body["annual_notes"] = {str(year): f"Operating reason for year {year}"
                            for year in reversed(years)}
    raw = json.dumps(body)
    responses["operating"] = LLMResponse(raw, 100, 100, "MOCK")
    draft = v2.parse_staged_parent_cash_response(responses["operating"],
        request=requests["operating"], source_fingerprint="a" * 64)
    assert draft["annual_notes"] == [f"Operating reason for year {year}" for year in years]
    assert responses["operating"].text == raw


@pytest.mark.parametrize("bad_year", ["2036", None])
def test_year_keyed_notes_reject_missing_or_extra_year(monkeypatch, bad_year):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    body["annual_notes"] = {str(year): f"Operating reason for year {year}"
                            for year in body["years"]}
    del body["annual_notes"][str(body["years"][0])]
    if bad_year is not None:
        body["annual_notes"][bad_year] = "An unrequested year note"
    response = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    with pytest.raises(ValueError, match="PARENT_V2_NOTES_INVALID"):
        v2.parse_staged_parent_cash_response(response, request=requests["operating"],
            source_fingerprint="a" * 64)


def test_prose_list_preserves_every_written_counterpoint(monkeypatch):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    points = ["First concrete counter evidence", "Second concrete counter evidence"]
    body["series"]["cost"]["counter_evidence"] = points
    body["counter_evidence"] = points
    raw = json.dumps(body)
    response = LLMResponse(raw, 100, 100, "MOCK")
    result = v2.parse_staged_parent_cash_response(response,
        request=requests["operating"], source_fingerprint="a" * 64)
    assert result["series"]["cost"]["counter_evidence"] == "\n".join(points)
    assert result["counter_evidence"] == "\n".join(points)
    assert response.text == raw


@pytest.mark.parametrize("points", [[], ["too short"],
    ["Valid counter evidence", 123], ["Valid counter evidence"] * 9])
def test_prose_list_rejects_missing_or_nonprose_counterpoint(monkeypatch, points):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    body["series"]["cost"]["counter_evidence"] = points
    response = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    with pytest.raises(ValueError, match="PARENT_V2_EXPLANATION_REQUIRED"):
        v2.parse_staged_parent_cash_response(response,
            request=requests["operating"], source_fingerprint="a" * 64)


def test_exact_year_keyed_values_preserve_all_decimals_in_order(monkeypatch):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    years = body["years"]
    body["series"]["cost"]["values"] = {str(year): str(i + 1)
        for i, year in reversed(list(enumerate(years)))}
    raw = json.dumps(body)
    response = LLMResponse(raw, 100, 100, "MOCK")
    result = v2.parse_staged_parent_cash_response(response,
        request=requests["operating"], source_fingerprint="a" * 64)
    assert result["series"]["cost"]["values"] == [str(i + 1) for i in range(10)]
    assert response.text == raw


@pytest.mark.parametrize("extra", [True, False])
def test_year_keyed_values_reject_missing_or_extra_year(monkeypatch, extra):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    row = {str(year): "1.25" for year in body["years"]}
    del row[str(body["years"][0])]
    if extra:
        row["2036"] = "1.25"
    body["series"]["cost"]["values"] = row
    response = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    with pytest.raises(ValueError, match="PARENT_V2_VALUES_REQUIRED"):
        v2.parse_staged_parent_cash_response(response,
            request=requests["operating"], source_fingerprint="a" * 64)


def test_duplicate_existing_fact_id_does_not_create_new_evidence(monkeypatch):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    body["series"]["cost"]["evidence_anchors"] = ["parent_revenue", "parent_revenue"]
    raw = json.dumps(body)
    response = LLMResponse(raw, 100, 100, "MOCK")
    result = v2.parse_staged_parent_cash_response(response,
        request=requests["operating"], source_fingerprint="a" * 64)
    assert result["series"]["cost"]["evidence_anchors"] == ["parent_revenue"]
    assert response.text == raw


def test_single_trailing_brace_repair_preserves_sealed_response(monkeypatch):
    requests, responses = fixture(monkeypatch)
    raw = responses["terminal"].text + "}"
    response = LLMResponse(raw, 100, 100, "MOCK")
    result = v2.parse_staged_parent_cash_response(response,
        request=requests["terminal"], source_fingerprint="a" * 64)
    assert result["terminal"]["max_transition_years"] == 10
    assert response.text == raw


@pytest.mark.parametrize("suffix", ["}}", "{}", "garbage"])
def test_other_json_trailing_data_is_not_repaired(monkeypatch, suffix):
    requests, responses = fixture(monkeypatch)
    response = LLMResponse(responses["terminal"].text + suffix, 100, 100, "MOCK")
    with pytest.raises(ValueError, match="PARENT_V2_INVALID_JSON"):
        v2.parse_staged_parent_cash_response(response,
            request=requests["terminal"], source_fingerprint="a" * 64)


def test_policy_gross_maturity_cannot_be_netted_against_new_borrowing(monkeypatch):
    source = context()
    source["constraints"] = {"issued_financing": [dict(code="CP1", maturity="2026-12-30",
        principal_cny="100", actual_settlement_verified=False,
        outstanding_at_evaluation_cny=None, classification="FACT",
        scope="ISSUER_FINANCING_DISCLOSURE", currency="CNY")]}
    requests, responses = fixture(monkeypatch, source)
    body = json.loads(responses["policy"].text)
    body["series"]["new_borrowing"]["values"][0] = "100"
    with pytest.raises(ValueError, match="PARENT_V2_FINANCING_MATURITY_UNCOVERED"):
        v2.parse_staged_parent_cash_response(LLMResponse(json.dumps(body), 100, 100, "MOCK"),
            request=requests["policy"], source_fingerprint="a" * 64)
    body["series"]["debt_repayment"]["values"][0] = "100"
    assert v2.parse_staged_parent_cash_response(LLMResponse(json.dumps(body), 100, 100, "MOCK"),
        request=requests["policy"], source_fingerprint="a" * 64)["series"]["debt_repayment"]["values"][0] == "100"


@pytest.mark.parametrize("mutation", ["alias", "missing", "year", "source", "numeric"])
def test_rejects_invalid_operating_stage(monkeypatch, mutation):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["operating"].text)
    if mutation == "alias":
        body["series"]["operating_cash"] = body["series"].pop("other_operating_cash")
    elif mutation == "missing":
        del body["series"]["cost"]
    elif mutation == "year":
        body["years"][0] = 2027
    elif mutation == "source":
        body["series"]["cost"]["evidence_anchors"] = ["unknown"]
    else:
        body["series"]["cost"]["values"][0] = 1.25
    responses["operating"] = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    with pytest.raises(ValueError):
        v2.merge_staged_parent_cash(scenario="base", source_fingerprint="a" * 64,
                                     requests=requests, responses=responses)


def test_rejects_missing_terminal_field(monkeypatch):
    requests, responses = fixture(monkeypatch)
    body = json.loads(responses["terminal"].text)
    del body["terminal"]["policy"][next(iter(body["terminal"]["policy"]))]
    responses["terminal"] = LLMResponse(json.dumps(body), 100, 100, "MOCK")
    with pytest.raises(ValueError):
        v2.merge_staged_parent_cash(scenario="base", source_fingerprint="a" * 64,
                                     requests=requests, responses=responses)


def test_merged_stages_reach_existing_cash_compiler(monkeypatch, tmp_path):
    requests, responses = fixture(monkeypatch)
    drafts = {}
    for scenario in v2.SCENARIOS:
        own_requests = {}
        for stage, request in requests.items():
            payload = json.loads(request.user)
            payload["scenario"] = scenario
            own_requests[stage] = request.__class__(
                role=request.role, system=request.system,
                user=json.dumps(payload), output_schema=request.output_schema,
                max_completion_tokens=request.max_completion_tokens,
                transport_output_contract=request.transport_output_contract)
        drafts[scenario] = v2.merge_staged_parent_cash(
            scenario=scenario, source_fingerprint="a" * 64,
            requests=own_requests, responses=responses)
    monkeypatch.setattr(adapter, "read_parent_cash_agent_facts", lambda **_:
        dict(symbol="600887", valuation_date="2025-12-31", input_fingerprint="a" * 64,
             facts={"parent_revenue": {"period_end": "2025-12-31"},
                    "revenue": {"period_end": "2025-12-31"}}))
    monkeypatch.setattr(adapter, "_load_spec", lambda *_: dict(symbol="600887", scenarios={}))
    observed = []
    monkeypatch.setattr(adapter, "compile_source_bound_owner_cash", lambda **kwargs:
        observed.append(kwargs["spec"]) or {"TEST_ONLY": True})
    result = adapter.assemble_parent_cash_drafts(root=tmp_path,
        spec_binding={"path": "runtime/TEST_ONLY", "sha256": "b" * 64},
        drafts=drafts, generated_at=datetime.now(timezone.utc))
    assert result["compiled"] == {"TEST_ONLY": True}
    assert set(observed[0]["scenarios"]) == set(v2.SCENARIOS)
    assert len(observed[0]["scenarios"]["bear"]["years"]) == 10
