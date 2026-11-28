"""Task history integration with synthetic versioned financing receipts."""
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes
from value_investment_agent.presentation.web_api import parent_cash_funding_revisions as funding
from value_investment_agent.application.research import parent_cash_funding_revision_v1 as replay
from value_investment_agent.research_run_contract import canonical_contract_payload

TASK = "rt-" + "a" * 32
SYMBOL = "600887"
HEAD = {"path": "runtime/task.json", "sha256": "a" * 64}
SPEC = {"path": "runtime/spec.json", "sha256": "b" * 64}


def pack(root, *, fault="", assess=True, matrix_mode=None):
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
    financing = dict(source_spec=SPEC)
    if matrix_mode:
        matrix = {"action": "no_order", "sources": {"report": {"pdf_sha256": pin["sha256"]}}, "flag": [True]}
        compact = bind("financing-evidence", matrix)
        if matrix_mode == "different":
            matrix["flag"] = [1]
        original = json.dumps(matrix, indent=2).encode()
        original_sha = sha256(original).hexdigest()
        financing["originals_matrix_sha256"] = compact["sha256"] if matrix_mode == "same" else original_sha
        if matrix_mode not in ("same", "missing"):
            siblings[f"source-matrix-{original_sha}.json"] = b"{}" if matrix_mode == "corrupt" else original
    if fault == "missing_extra":
        financing["extra_source_bindings"] = [dict(pin, path="runtime/other.pdf")]
    spec = bind("spec", dict(**identity, financing_revision=financing))
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
    if matrix_mode:
        receipt["originals_matrix"] = compact
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
    ("valuation", "VALUATION_HASH"), ("missing_extra", "SOURCE_BINDING")])
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
    Path(funding._native_path(folder)).rename(funding._native_path(outside))
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(outside), funding._native_path(folder))
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


@pytest.mark.parametrize(("mode", "error"), [
    ("same", None), ("repacked", None), ("missing", "SOURCE_MATRIX_HASH"),
    ("corrupt", "SOURCE_MATRIX_HASH"), ("different", "SOURCE_BINDING"),
])
def test_original_matrix_bytes_and_content_agree_in_both_readers(tmp_path, mode, error):
    version = pack(tmp_path, matrix_mode=mode)
    folder = funding.directory(tmp_path, TASK) / version
    public, = funding.read_revisions(tmp_path, TASK, SYMBOL, HEAD, SPEC)
    assert public["status"] == ("UNAVAILABLE" if error else "VERIFIED")
    assert public.get("reason") == error

    receipt = replay._sibling(folder, "receipt", version)
    spec = replay._sibling(folder, "spec", receipt["revision_spec"])
    matrix_pin = receipt["originals_matrix"]
    matrix = replay._sibling(folder, "financing-evidence", matrix_pin)

    def read_original(digest):
        assert mode != "same"
        return replay._sibling(folder, "source-matrix", dict(file=f"source-matrix-{digest}.json", sha256=digest))

    def check():
        replay.verify_source_set(receipt["inputs"], receipt["inputs"], spec["financing_revision"],
                                 matrix, matrix_pin["sha256"], read_original)
    if error:
        with pytest.raises((ValueError, FileNotFoundError)):
            check()
    else:
        check()


REAL_TASK = "rt-07724f7f1c8566420935f07b70c846a1"
REAL_VERSION = "ed62be290ebcffebf47e1c22cd235d77767e42f1d8b13ff4f1273875257c0a19"


@pytest.fixture
def real_bundle():
    directory = os.environ.get("VALUE_FUNDING_REVISION_REAL_ROOT")
    if not directory:
        pytest.skip("Set VALUE_FUNDING_REVISION_REAL_ROOT to the vf1 source tree for the real replay")
    root = Path(directory).resolve()
    folder = funding.directory(root, REAL_TASK) / REAL_VERSION
    return root, folder, replay._sibling(folder, "receipt", REAL_VERSION)


def test_real_ed62_each_scenario_unchanged_and_unadopted(real_bundle, monkeypatch):
    root, folder, receipt = real_bundle
    claim = receipt["current_reassessment"]
    revised = replay._sibling(folder, "reassessment-spec", claim["revised_spec"])
    original_compiler = replay.compile_source_bound_owner_cash_v2
    orders = []
    financing_rows = []

    def compile_spec(**kwargs):
        if orders or kwargs["spec"] == revised:
            assert kwargs["spec"] == revised
            orders.append(next(iter(kwargs["spec"]["scenarios"])))
        return original_compiler(**kwargs)

    original_split = replay.annual_financing_row_v1

    def split(**row):
        details = original_split(**row)
        financing_rows.append(details)
        return details

    monkeypatch.setattr(replay, "compile_source_bound_owner_cash_v2", compile_spec)
    monkeypatch.setattr(replay, "annual_financing_row_v1", split)
    actual = replay.replay(root, REAL_TASK, REAL_VERSION, datetime.now(timezone.utc))
    assert sorted(orders) == ["base", "bear", "bull"]
    assert actual["verified_source_count"] == 21 and actual["valuation_date"] == "2025-12-31"
    assert actual["action"] == "no_order" and actual["current_comparable"] is actual["formal_eligibility"] is False
    assert actual["values"]["base"] == "11.5116817435840185224103788855316406659002247626"
    assert receipt["previous_task_status"] == "FAILED" and actual["current_reassessment"] == {
        "status": "REJECTED", "current_research_range_adopted": False,
        "scenario_rows": {
            "bear": dict(status="REJECTED", reason="DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027",
                         year=2027, before="6306969832.537425", floor="13404587376.75", scheduled="0"),
            "base": dict(status="CALCULATED", per_share_value="9.32912100924600589279659166699807236074544452357"),
            "bull": dict(status="CALCULATED", per_share_value="12.8321399850801461433074380515963999675776921102"),
        },
    }
    for year in range(2027, 2036):
        annual = [row for row in financing_rows if row["year"] == year]
        assert len(annual) == 6
        for row in annual:
            assert Decimal(row["disclosed_unsettled_maturities_cny"]) == (3500000000 if year == 2027 else 0)
            if year == 2027:
                assert row["other_forecast_principal_payments_cny"] == "8779665769.24"
    for name, key, bad in [
        ("bear", "year", 2028), ("bear", "before", "0"), ("bear", "floor", "0"),
        ("bear", "reason", "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2028"),
        ("base", "per_share_value", "11.51"), ("bull", "per_share_value", "14.67"),
    ]:
        changed = deepcopy(claim)
        changed["scenario_rows"][name][key] = bad
        with pytest.raises(ValueError, match=f"SCENARIO_CHANGED:{name}"):
            replay._compare_rows(changed, actual["current_reassessment"]["scenario_rows"])
    with pytest.raises(ValueError, match="SCOPE_CHANGED"):
        replay._compare_rows(dict(claim, current_research_range_adopted=True), claim["scenario_rows"])


@pytest.mark.parametrize(("fault", "error"), [
    ("parent_head", "PARENT_NOT_IN_CHAIN"), ("previous_task_status", "PARENT_CHANGED"),
    ("registered_spec", "PARENT_CHANGED"), ("valuation_date", "CONTEXT_CHANGED"),
    ("filename", "FILENAME_CHANGED"), ("missing_extra", "SOURCE_SET_CHANGED"),
    ("duplicate", "SOURCE_BINDING"), ("unrelated", "SOURCE_SET_CHANGED"),
    ("missing_matrix", "MATRIX_MISSING"),
])
def test_resealed_ed62_counterexamples(tmp_path, real_bundle, monkeypatch, fault, error):
    real_root, folder, receipt = real_bundle
    original_inputs = list(receipt["inputs"])
    if fault == "filename":
        receipt["descriptor"]["file"] = receipt["valuation"]["file"]
    elif fault == "missing_extra":
        spec = replay._sibling(folder, "spec", receipt["revision_spec"])
        receipt["inputs"].remove(spec["financing_revision"]["extra_source_bindings"][0])
    elif fault == "duplicate":
        receipt["inputs"].append(receipt["inputs"][0])
    elif fault == "unrelated":
        receipt["inputs"].append(dict(receipt["inputs"][0], path="runtime/unrelated.pdf"))
    elif fault == "missing_matrix":
        del receipt["originals_matrix"]
    else:
        receipt[fault] = {"parent_head": SPEC, "previous_task_status": "COMPLETED", "registered_spec": HEAD,
                          "valuation_date": "2025-12-30"}[fault]
    data = json.dumps(receipt, sort_keys=True).encode()
    version = sha256(data).hexdigest()
    copy = Path(funding._native_path(funding.directory(tmp_path, REAL_TASK) / version))
    copy.mkdir(parents=True)
    for item in Path(funding._native_path(folder)).iterdir():
        if item.name != "receipt.json":
            shutil.copyfile(item, copy / item.name)
    (copy / "receipt.json").write_bytes(data)
    if fault == "valuation_date":
        for pin in original_inputs:
            destination = tmp_path / pin["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real_root / pin["path"], destination)
    # Keep the real verified task chain in place. Only the revision copy is resealed.
    verify_parent = replay._verify_parent
    monkeypatch.setattr(replay, "_verify_parent", lambda _, r, task_id: verify_parent(real_root, r, task_id))
    with pytest.raises(ValueError, match=error):
        replay.replay(tmp_path, REAL_TASK, version, datetime.now(timezone.utc))


def test_replay_refuses_wrong_annual_split(real_bundle, monkeypatch):
    _, folder, receipt = real_bundle
    matrix = replay._sibling(folder, "financing-evidence", receipt["originals_matrix"])
    spec = replay._sibling(folder, "spec", receipt["revision_spec"])
    monkeypatch.setattr(replay, "annual_financing_row_v1", lambda **row: {"other_forecast_principal_payments_cny": "0"})
    with pytest.raises(ValueError, match="OTHER_PRINCIPAL_CHANGED"):
        replay._verify_debt_service(spec, matrix)


def test_unrecognized_diagnostic_version_and_error_fail_closed(monkeypatch):
    monkeypatch.setattr(replay, "_DIAGNOSTIC_SOURCES", [(replay.kernel, "0" * 64)])
    with pytest.raises(ValueError, match="DIAGNOSTIC_VERSION"):
        replay._rerun_reassessment(None, {}, None, None)
    with pytest.raises(ValueError, match="DIAGNOSTIC_FRAME"):
        replay._rejected_run(ValueError("DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027"), {}, "bear")


def test_paid_buyback_cannot_disappear_or_be_counted_in_optional_payout_twice():
    from test_direct_parent_owner_cash_v1 import inputs
    from value_investment_agent.application.research.parent_cash_fixed_payment_recheck import _scenario

    ctx = inputs()
    ctx["years"][0]["scheduled_owner_distribution_cny"] = "0"
    source = {"years": [{"year": 2027, "policy": {"payout_ratio": {"value": "1"}}}]}
    result = _scenario(ctx, source, Decimal(10), Decimal(70), {}, [])
    row = result["calculation"]["annual_rows"][0]
    assert Decimal(row["scheduled_owner_distribution_cny"]) == 10
    assert Decimal(row["conditional_distribution_cny"]) == 70
    assert Decimal(row["closing_cash_cny"]) == 20
    assert Decimal(result["per_share_value"]) == 10
    with pytest.raises(ValueError, match="OPTIONAL_TARGET_DOES_NOT_RECONCILE"):
        _scenario(ctx, source, Decimal(10), Decimal(80), {}, [])


def test_fixed_payment_deficit_explains_known_principal_unknown_timing_and_interest():
    from value_investment_agent.application.research.parent_cash_fixed_payment_recheck import _ledger

    flow = {k:Decimal(v) for k,v in dict(operating_cash="44", investment_cash_received="0", new_borrowing="0",
        maintenance_capex="6", growth_capex="0", commitments_outside_capex="0", other_mandatory_cash="0",
        debt_repayment="123", interest_outside_cfo="5", cash_floor="134").items()}
    terms = [{"maturity":"2027-11-12", "principal_cny":"35"}]
    matrix = {"prospective_debt_service":{"issues":[{"due":"2027-11-12","coupon_if_act365_to_maturity":"0.5"}]}}
    row = _ledger({"cash":Decimal("153")}, flow, 2027, Decimal(0), matrix, terms)
    assert Decimal(row["cash_before_distribution_cny"]) == 63
    assert Decimal(row["assumed_other_repayment_cny"]) == 88
    assert Decimal(row["coverage_before_unknown_repayment_cny"]) == 17
    assert Decimal(row["shortfall_cny"]) == 71
    assert Decimal(row["other_interest_cny"]) == Decimal("4.5")
    with pytest.raises(ValueError, match="KNOWN_MATURITY_UNCOVERED"):
        _ledger({"cash":Decimal("153")}, dict(flow, debt_repayment=Decimal(34)), 2027, Decimal(0), matrix, terms)
