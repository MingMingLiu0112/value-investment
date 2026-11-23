"""TEST_ONLY capital-context contracts; no provider or network."""
import json
from copy import deepcopy
import pytest
from value_investment_agent.application.research import direct_owner_cash_policy_capital_v1 as capital
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest

def policy(borrowings, repayments):
    return {"years": list(range(2026, 2026+len(borrowings))), "series": {
        "new_borrowing": {"values": borrowings}, "debt_repayment": {"values": repayments}}}

def test_policy_receives_opening_assumption_without_promoting_it():
    opening={"debt": {"classification":"FORECAST_ASSUMPTION","value":"60000000000",
        "evidence_anchors":["book"],"rationale":"Conditional opening principal, not observed balance"}}
    basis=capital.opening_debt_basis(opening,{})
    req=LLMRequest(role="FUNDAMENTAL",system="unchanged",user='{"required_years":[2026]}',
        output_schema={"type":"object"})
    revised=capital.policy_capital_request(req,basis)
    assert json.loads(revised.user)["opening_debt_basis"]["amount_cny"]=="60000000000"
    assert json.loads(revised.user)["opening_debt_basis"]["classification"]=="FORECAST_ASSUMPTION"
    assert json.loads(revised.user)["debt_balance_contract"]["refinancing_guaranteed"] is False
    assert revised.output_schema==req.output_schema and req.user=='{"required_years":[2026]}'

def test_negative_principal_rejected_at_policy_stage():
    # Values reproduce the arithmetic from the archived policy, not a new forecast.
    with pytest.raises(ValueError,match="FORECAST_DEBT_NEGATIVE"):
        capital.validate_policy_debt({"amount_cny":"60000000000"},
            policy(["182711547658.23"],["244001881888.99"]))

def test_multiyear_rollforward_preserves_real_decimal_precision():
    result=capital.validate_policy_debt({"amount_cny":"100.01"},
        policy(["20.02","0"],["30.01","90.02"]))
    assert [r["closing_debt_cny"] for r in result]==["90.02","0.00"]
    assert result[1]["opening_debt_cny"]=="90.02"

def test_total_liabilities_anchor_remains_upper_bound():
    basis=capital.opening_debt_basis({"debt":{"classification":"FORECAST_ASSUMPTION",
        "anchor":"liab","factor":"1"}},{"liab":{"value_cny":"100","field":"liabilities_cny"}})
    assert basis["scope"]=="ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"

@pytest.mark.parametrize("bad",["-1","NaN","Infinity"])
def test_invalid_capital_rejected(bad):
    with pytest.raises(ValueError):
        capital.opening_debt_basis({"debt":{"classification":"FORECAST_ASSUMPTION","value":bad}},{})

def test_missing_year_and_unknown_do_not_get_filled():
    row=policy(["0","0"],["0","0"])
    row["years"]=[2026,2028]
    with pytest.raises(ValueError,match="YEARS_INVALID"):
        capital.validate_policy_debt({"amount_cny":"100"},row)
    with pytest.raises((KeyError,ValueError)):
        capital.opening_debt_basis({"debt":{"classification":"UNKNOWN"}},{})

def test_reject_does_not_repair_policy():
    row=policy(["0"],["101"])
    original=deepcopy(row)
    with pytest.raises(ValueError):
        capital.validate_policy_debt({"amount_cny":"100"},row)
    assert row==original


@pytest.mark.parametrize("change", ["reported_hash", "service_bytes"])
def test_legacy_capital_compatibility_rejects_unreviewed_service(monkeypatch, change):
    from hashlib import sha256
    from pathlib import Path
    from value_investment_agent.application.research.agent_review import parent_cash_task_v3 as task

    # No service construction, task store, provider or ledger is needed.
    service = object.__new__(task.ParentCashTaskServiceV3)
    monkeypatch.setattr(service, "_bound", lambda _binding: {})
    current = task._implementation()
    pinned = {name: digest for name, digest in current.items()
              if name != capital.__name__}
    pinned[task.__name__] = "af998baf6d5a8192afc5218a670c2694b1d474efc7283782841546822c2ad384"
    spec = {"implementation_sha256": pinned, "spec_binding": {}}
    assert service._implementation_matches(spec)

    if change == "reported_hash":
        current[task.__name__] = "f" * 64
    else:
        service_path = Path(task.__file__)
        read_bytes = Path.read_bytes
        raw = read_bytes(service_path)
        changed = raw.replace(b"MODEL_AUTHORIZATION_CHANGED",
                              b"UNREVIEWED_AUTHORIZATION_CHANGE")
        assert changed != raw
        # Simulate a real edit: the reported hash agrees with the new bytes,
        # but the reviewed-content hash must still reject the revision.
        current[task.__name__] = sha256(changed).hexdigest()
        monkeypatch.setattr(Path, "read_bytes", lambda path:
                            changed if path == service_path else read_bytes(path))
    monkeypatch.setattr(task, "_implementation", lambda: dict(current))
    assert service._implementation_matches(spec) is False


@pytest.mark.parametrize("prior_service_hash", [
    "af998baf6d5a8192afc5218a670c2694b1d474efc7283782841546822c2ad384",
    "38cd85ac4835bf0494e8682798d3e25903b64dd7e59ce1c1c130c26ae81e03b0",
], ids=["historical-lf", "historical-crlf"])
def test_legacy_capital_compatibility_accepts_reviewed_line_endings(monkeypatch, prior_service_hash):
    from value_investment_agent.application.research.agent_review import parent_cash_task_v3 as task

    service = object.__new__(task.ParentCashTaskServiceV3)
    monkeypatch.setattr(service, "_bound", lambda _binding: {})
    pinned = {name: digest for name, digest in task._implementation().items()
              if name != capital.__name__}
    pinned[task.__name__] = prior_service_hash
    spec = {"implementation_sha256": pinned, "spec_binding": {}}
    assert service._implementation_matches(spec) is True
    request = LLMRequest(role="FUNDAMENTAL", system="historical policy",
                         user='{"stage":"policy"}', output_schema={"type": "object"})
    assert service._wire(spec, "policy", request) is request

    # Accepting service line endings must not waive unrelated module pins.
    pinned[task.operating_wire.__name__] = "f" * 64
    assert service._implementation_matches(spec) is False


def test_operating_retry_contract_preserves_historical_wire():
    from value_investment_agent.application.research.agent_review import parent_cash_task_v3 as service

    fields = ("years", "series", "annual_notes", "rationale", "counter_evidence", "reopen_condition")
    request = LLMRequest(
        role="FUNDAMENTAL", system="Historical system", user="{}",
        output_schema={"properties": dict.fromkeys(fields, {}), "required": list(fields)},
    )
    pinned = {"implementation_sha256": {service.operating_wire.__name__: "fixture"}}
    legacy = service.ParentCashTaskServiceV3._wire(pinned, "operating", request)
    v1 = service.ParentCashTaskServiceV3._wire(
        dict(pinned, operating_series_wire="INPUTS_ONLY_V1"), "operating", request,
    )
    v2 = service.ParentCashTaskServiceV3._wire(
        dict(pinned, operating_series_wire="INPUTS_ONLY_V2"), "operating", request,
    )
    assert "never emit operating_cash" not in legacy.transport_output_contract
    assert "never emit operating_cash" in v1.transport_output_contract
    assert "exactly ten plain JSON strings" not in v1.transport_output_contract
    assert "exactly ten plain JSON strings" in v2.transport_output_contract
    assert v2.output_schema == v1.output_schema == legacy.output_schema
    assert v2.user == v1.user == legacy.user
