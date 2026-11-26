"""Task history integration with synthetic versioned financing receipts."""
import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes
from value_investment_agent.presentation.web_api import parent_cash_funding_revisions as funding
from value_investment_agent.research_run_contract import canonical_contract_payload

TASK = "rt-" + "a" * 32
SYMBOL = "600887"
HEAD = {"path": "runtime/task.json", "sha256": "a" * 64}
SPEC = {"path": "runtime/spec.json", "sha256": "b" * 64}


def pack(root, *, fault="", assess=True):
    def raw(obj):
        return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()
    siblings = {}
    def bind(label, obj):
        data = raw(obj)
        digest = sha256(data).hexdigest()
        name = f"{label}-{digest}.json"
        siblings[name] = data
        return dict(file=name, sha256=digest)

    source = root / "runtime/source.pdf"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"TEST_ONLY")
    pin = dict(path="runtime/source.pdf", sha256=sha256(source.read_bytes()).hexdigest())
    date = "2025-12-31"
    identity = dict(symbol=SYMBOL, valuation_date=date)
    spec = bind("spec", dict(**identity, financing_revision=dict(source_spec=SPEC)))
    contract = dict(schema_version=funding.SCHEMA, predecessor_task=TASK, predecessor_task_head=HEAD,
                    registered_spec=SPEC, spec_sha256=spec["sha256"], raw_source_bindings=[pin])
    descriptor = dict(symbol=SYMBOL, source_contract=contract, point_in_time=dict(valuation_date=date))
    digest = sha256(canonical_contract_payload(descriptor).encode()).hexdigest()
    desc = bind("descriptor", dict(descriptor, input_sha256=digest))
    row = dict(year=2026, private_note="DO_NOT_PROJECT", **dict.fromkeys(funding.CASH_FIELDS, "20"))
    calculations = {key: dict(per_share_value="10", annual_rows=[row]) for key in ("bear","base","bull")}
    value = bind("valuation", dict(**identity, status="conditional_research_only",
                                   bear_value="10", base_value="10", bull_value="10",
                                   assumptions=dict(scenario_calculations=calculations)))
    receipt = dict(schema_version=funding.SCHEMA, task_id=TASK, **identity, parent_head=HEAD, registered_spec=SPEC,
                   completed_at="2026-01-02T01:00:00+00:00", input_descriptor_sha256=digest, inputs=[pin],
                   revision_spec=spec, descriptor=desc, valuation=value, provenance="DETERMINISTIC_RESEARCH_REVISION",
                   action="no_order", formal_eligibility=False, current_comparable=False)
    if assess:
        receipt["current_reassessment"] = dict(status="REJECTED", reason="OPERATING_CASH_REASSESSMENT_REJECTED",
            scenario_rows={"base":dict(status="REJECTED", reason="CASH_FLOOR", year="2027", floor="90",
                                       before="40", private_note="DO_NOT_PROJECT")}, current_research_range_adopted=False)
    if fault == "identity": receipt["parent_head"] = SPEC
    if fault == "path": value["file"] = "../outside.json"
    if fault == "source": receipt["inputs"] = [dict(pin, path="runtime/../private.json")]
    if fault == "fingerprint": receipt["input_descriptor_sha256"] = "0" * 64
    data = raw(receipt)
    folder = funding.directory(root, TASK) / sha256(data).hexdigest()
    folder = Path(funding._native_path(folder))
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_bytes(data if fault != "receipt" else b"{}")
    for name, data in siblings.items():
        (folder/name).write_bytes(data if fault != "valuation" or not name.startswith("valuation-") else b"{}")
    return folder.name


@pytest.mark.parametrize(("fault", "reason"), [("identity", "TASK_IDENTITY"), ("path", "VALUATION_HASH"),
    ("source", "SOURCE_BINDING"), ("fingerprint", "DESCRIPTOR_IDENTITY"), ("receipt", "RECEIPT_HASH"),
    ("valuation", "VALUATION_HASH")])
def test_bad_revision_leaves_valid_neighbor_and_failed_task(tmp_path, monkeypatch, fault, reason):
    good = pack(tmp_path, assess=False)
    bad = pack(tmp_path, fault=fault)
    class Service:
        def __init__(self, root):
            self.root = root
            self.base = root / "tasks"
        def _load(self, task):
            assert task == TASK
            return {"spec_binding": SPEC}, {"status": "FAILED"}, HEAD
        def _bound(self, original):
            assert original == SPEC
            return {"symbol": SYMBOL}

    task = tmp_path / "tasks" / TASK
    task.mkdir(parents=True)
    (task / "input.json").write_text("{}")
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", Service)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=0)
    url = f"/api/v1/operating-research/parent-cash-tasks/v3/{TASK}/funding-revisions"
    client = TestClient(app)
    assert client.get(url,params={"symbol":SYMBOL}).status_code in (401,403)
    monkeypatch.setattr(routes, "authorize", lambda *a, **kw: None)
    assert client.get(url,params={"symbol":"600519"}).status_code == 404
    response = client.get(url, params={"symbol":SYMBOL})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["original_task_status"] == "FAILED" and data["current_comparable"] is False
    valid, failed = data["revisions"]
    assert valid["receipt_sha256"] == good and valid["current_reassessment"] is None
    assert failed == dict(receipt_sha256=bad, status="UNAVAILABLE", reason=reason)
    assert "DO_NOT_PROJECT" not in response.text and "runtime/" not in response.text


def test_long_sibling_paths_under_task_root(tmp_path):
    root = tmp_path / ("long-review-slot-" + "z" * 36)
    root.mkdir()
    version = pack(root)
    folder = funding.directory(root, TASK) / version
    assert max(len(str(folder / p.name)) for p in Path(funding._native_path(folder)).iterdir()) > 260
    row, = funding.read_revisions(root, TASK, SYMBOL, HEAD, SPEC)
    assert row["status"] == "VERIFIED"


def test_reparse_directory_cannot_supply_even_correctly_hashed_bytes(tmp_path):
    import os
    version = pack(tmp_path)
    folder = funding.directory(tmp_path, TASK) / version
    outside = tmp_path / "elsewhere"
    folder.rename(outside)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(outside), str(folder))
    else:
        folder.symlink_to(outside, target_is_directory=True)
    row, = funding.read_revisions(tmp_path, TASK, SYMBOL, HEAD, SPEC)
    assert row == dict(status="UNAVAILABLE", reason="RECEIPT_HASH", receipt_sha256=version)


def test_financing_terms_project_principal_and_interest_with_no_private_fields():
    maturity = dict(code="012345678", maturity="2027-11-12", principal_cny="3500000000", private_note="HIDDEN")
    terms = dict(known_maturities=[maturity], residual_principal_cny="8779665769.24",
                 unknown_balance_is_forecast=True, cash_interest_9m_verified_floor="468655890.42",
                 mixed_less_dividend_cny="654500766.38", unknown_rate_assumptions=dict(base=".04",bear=".05",bull=".02"))
    terms["unknown_rate_assumptions"] = {k:"0"+v for k,v in terms["unknown_rate_assumptions"].items()}
    result = funding._financing_terms({"financing_revision":terms}, {"prospective_debt_service":{
        "five_scp_conditional_coupon_2026Q4":"115075068.50", "mtn_conditional_coupon_2027":"49920547.95"}})
    assert result["known_maturities"] == [{k:maturity[k] for k in ("code","maturity","principal_cny")}]
    assert result["residual_principal_cny"] == "8779665769.24" and result["mtn_conditional_coupon_2027"] == "49920547.95"
    assert result["cash_interest_9m_verified_floor"] == "468655890.42" and "HIDDEN" not in str(result)


def test_current_rejection_is_independent_of_historical_receipt(tmp_path):
    pack(tmp_path)
    row, = funding.read_revisions(tmp_path, TASK, SYMBOL, HEAD, SPEC)
    assert row["status"] == "VERIFIED" and row["current_reassessment"]["status"] == "REJECTED"
    assert row["current_reassessment"]["scenario_rows"]["base"] == dict(
        status="REJECTED", reason="CASH_FLOOR", year=2027, floor="90", before="40")
    assert set(row["scenarios"]) == {"bear", "base", "bull"} and not row["current_comparable"]
    assert not row["current_reassessment"]["current_research_range_adopted"]
