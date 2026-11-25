"""Offline admission, publication recovery and legacy receipt regressions."""
from contextlib import nullcontext
from hashlib import sha256
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion
from value_investment_agent.application.research.agent_review.parent_cash_task_v3 import ParentCashTaskServiceV3
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes


@pytest.fixture
def setup(tmp_path):
    def put(name, value):
        path = tmp_path / "runtime" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256(raw).hexdigest())

    spec = dict(symbol="600887", action="no_order", model_applicable=True,
                source_adapter_version="UNNUMBERED_OFFICIAL_CNINFO_V2")
    case = dict(symbol="600887", profile_id="quality_compounder",
                schema_version="m1-valuation-package-v2", research_case=dict(symbol="600887"))
    distribution = dict(symbol="600887", action="no_order", formal_eligibility=False,
                        successor_adopted=False, main_range_adopted=False,
                        schema_version="parent-owner-distribution-successor-receipt-v2")
    binding = put("spec.json", spec)
    entry = dict(symbol="600887", spec_binding=binding,
                 case_package_binding=put("case.json", case),
                 implemented_distribution_receipt_binding=put("distribution.json", distribution))
    document = dict(schema_version="parent-cash-task-case-bindings-v1",
                    specs={binding["sha256"]: entry})
    registry = tmp_path / "config" / "parent-cash-task-case-bindings-v1.json"
    registry.parent.mkdir()

    def save():
        registry.write_text(json.dumps(document), encoding="utf-8")

    save()
    calls = []
    task_id = "rt-" + "1" * 32
    native = ParentCashTaskServiceV3(tmp_path)

    class Service:
        root = tmp_path
        _bound = staticmethod(native._bound)

        def create(self, **kwargs):
            calls.append(("create", kwargs))
            return dict(task_id=task_id, status="SUCCEEDED", action="no_order")

        def run(self, identifier):
            assert identifier == task_id
            calls.append("run")

        def _directory(self, identifier):
            return tmp_path / "runtime" / identifier

        def _lock(self, *args):
            return nullcontext()

        def _load(self, identifier):
            return (dict(spec_binding=binding, mode="LIVE_PARENT_CASH_V3"),
                    dict(status="SUCCEEDED"), dict(path="runtime/head.json", sha256="a" * 64))

    return locals()


@pytest.mark.parametrize("fault,error", [
    ("registry", "PARENT_TASK_CASE_BINDING_REQUIRED"),
    ("entry", "PARENT_TASK_CASE_BINDING_REQUIRED"),
    ("case", "PARENT_TASK_CASE_BINDING_REQUIRED"),
    ("path", "PARENT_TASK_SPEC_BINDING_MISMATCH"),
    ("case_issuer", "PARENT_TASK_CASE_PROFILE_OR_ISSUER_MISMATCH"),
    ("profile", "PARENT_TASK_CASE_PROFILE_OR_ISSUER_MISMATCH"),
    ("distribution", "PARENT_TASK_IMPLEMENTED_DISTRIBUTION_BINDING_REQUIRED"),
    ("distribution_issuer", "PARENT_TASK_DISTRIBUTION_RECEIPT_INVALID"),
    ("distribution_hash", "hash mismatch"),
    ("case_hash", "hash mismatch"),
    ("spec_hash", "hash mismatch"),
])
def test_exact_preflight_rejects_before_create_or_schedule(setup, monkeypatch, fault, error):
    x = setup
    entry, binding = x["entry"], dict(x["binding"])
    if fault == "registry":
        x["registry"].unlink()
    elif fault == "entry":
        x["document"]["specs"].clear()
    elif fault in {"case", "distribution"}:
        entry.pop("case_package_binding" if fault == "case" else "implemented_distribution_receipt_binding")
    elif fault == "path":
        binding["path"] = "runtime/other.json"
    elif fault in {"case_issuer", "profile"}:
        case = dict(x["case"])
        case["symbol" if fault == "case_issuer" else "profile_id"] = "invalid"
        entry["case_package_binding"] = x["put"]("bad-case.json", case)
    elif fault == "distribution_issuer":
        entry["implemented_distribution_receipt_binding"] = x["put"](
            "bad-distribution.json", dict(x["distribution"], symbol="000568"))
    else:
        name = fault.removesuffix("_hash") + ".json"
        (x["tmp_path"] / "runtime" / name).write_text("{}", encoding="utf-8")
    if fault != "registry":
        x["save"]()
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: x["tmp_path"])
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", lambda _: x["Service"]())
    monkeypatch.setattr(routes, "authorize", lambda *a, **k: None)
    monkeypatch.setattr(routes, "run_and_seal_parent_cash_task",
                        lambda *a: pytest.fail("must not schedule rejected input"))
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=x["tmp_path"], sessions=None, port=0)
    response = TestClient(app).post("/api/v1/operating-research/parent-cash-tasks/v3",
                                   json=dict(spec_binding=binding, request_key="offline-test"))
    assert response.status_code == 422
    assert error in response.json()["reason"]
    assert x["calls"] == []


@pytest.mark.parametrize("missing", ["case_package_binding", "implemented_distribution_receipt_binding"])
def test_successful_unsealed_task_explicitly_rejects_missing_bindings(setup, monkeypatch, missing):
    x = setup
    x["entry"].pop(missing)
    x["save"]()
    monkeypatch.setattr(completion, "build_parent_cash_task_receipt",
                        lambda **kw: pytest.fail("must not fall back to zero distributions"))
    error = ("PARENT_TASK_CASE_BINDING_REQUIRED" if missing == "case_package_binding"
             else "PARENT_TASK_IMPLEMENTED_DISTRIBUTION_BINDING_REQUIRED")
    for _ in range(2):
        with pytest.raises(ValueError, match=error):
            completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])
    assert not completion.valuation_receipt_path(x["tmp_path"], x["task_id"]).exists()
    head = x["Service"]()._load(x["task_id"])[2]
    publication = completion.read_valuation_publication(x["tmp_path"], x["task_id"], head)
    assert publication["valuation_receipt_status"] == "BLOCKED"
    assert publication["valuation_blockage"]["reason_code"] == error


def _mock_verified_replay(x):
    def replay(*, root, receipt_binding, now):
        assert (root / receipt_binding["path"]).is_file()
        head = x["Service"]()._load(x["task_id"])[2]
        return dict(provenance=dict(task_id=x["task_id"], task_record_binding=head),
                    action="no_order", formal_eligibility=False)
    return replay


def test_invalid_cold_replay_leaves_no_published_valuation(setup, monkeypatch):
    x = setup

    def build(*, output_dir, **kwargs):
        path = output_dir / "receipt.json"
        path.parent.mkdir()
        raw = b"complete-looking but not replayable"
        path.write_bytes(raw)
        return dict(path=path.relative_to(x["tmp_path"]).as_posix(), sha256=sha256(raw).hexdigest())

    def replay(**kwargs):
        raise ValueError("PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED")

    monkeypatch.setattr(completion, "build_distribution_receipt", build)
    monkeypatch.setattr(completion, "replay_task_receipt", replay)
    with pytest.raises(ValueError, match="PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED"):
        completion.seal_completed_parent_cash_task(x["Service"](), x["task_id"])
    assert not completion.valuation_receipt_path(x["tmp_path"], x["task_id"]).exists()
    head = x["Service"]()._load(x["task_id"])[2]
    publication = completion.read_valuation_publication(x["tmp_path"], x["task_id"], head)
    assert publication["valuation_blockage"]["reason_code"] == "PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED"


def test_publication_failure_retries_distribution_builder_and_is_idempotent(setup, monkeypatch):
    x = setup
    attempts = []

    def build(**kw):
        attempts.append(kw)
        assert kw["distribution_binding"] == x["entry"]["implemented_distribution_receipt_binding"]
        if len(attempts) == 1:
            raise OSError("offline publication interruption")
        output = kw["output_dir"]
        output.mkdir()
        raw = b"complete distribution receipt"
        path = output / "receipt.json"
        path.write_bytes(raw)
        return dict(path=path.relative_to(x["tmp_path"]).as_posix(), sha256=sha256(raw).hexdigest())

    monkeypatch.setattr(completion, "build_distribution_receipt", build)
    monkeypatch.setattr(completion, "replay_task_receipt", _mock_verified_replay(x))
    monkeypatch.setattr(completion, "build_parent_cash_task_receipt",
                        lambda **kw: pytest.fail("wrong builder"))
    with pytest.raises(OSError, match="interruption"):
        completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])
    completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])
    path = completion.valuation_receipt_path(x["tmp_path"], x["task_id"])
    retained = path.read_bytes()
    head = x["Service"]()._load(x["task_id"])[2]
    assert completion.valuation_blockage_path(x["tmp_path"], x["task_id"]).is_file()
    assert completion.read_valuation_publication(x["tmp_path"], x["task_id"], head) == dict(
        valuation_receipt_status="SEALED_REPLAY_REQUIRED", valuation_blockage=None)
    x["registry"].unlink()
    completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])
    assert path.read_bytes() == retained
    assert len(attempts) == 2
    assert attempts[0]["output_dir"] != attempts[1]["output_dir"]


def test_seal_retry_does_not_accept_or_overwrite_a_corrupt_retained_receipt(setup, monkeypatch):
    x = setup
    path = completion.valuation_receipt_path(x["tmp_path"], x["task_id"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"damaged immutable receipt")

    def reject(**kwargs):
        assert kwargs["receipt_binding"]["path"] == path.relative_to(x["tmp_path"]).as_posix()
        raise ValueError("PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED")

    monkeypatch.setattr(completion, "replay_task_receipt", reject)
    monkeypatch.setattr(completion, "build_distribution_receipt",
                        lambda **_: pytest.fail("must preserve original receipt"))
    with pytest.raises(ValueError, match="PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED"):
        completion.seal_completed_parent_cash_task(x["Service"](), x["task_id"])
    assert path.read_bytes() == b"damaged immutable receipt"
    failure = json.loads(completion.valuation_blockage_path(
        x["tmp_path"], x["task_id"]).read_bytes())
    assert failure["reason_code"] == "PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED"


def test_exact_historical_spec_is_not_replaced_by_active_company_spec(setup):
    x = setup
    x["document"]["active_spec_by_symbol"] = {"600887": "b" * 64}
    x["save"]()
    assert completion.preflight_parent_cash_task(x["Service"](), x["binding"]) == (
        x["entry"]["case_package_binding"], x["entry"]["implemented_distribution_receipt_binding"])


def test_valid_direct_post_preflights_then_creates_and_seals(setup, monkeypatch):
    x = setup
    events = []
    original = completion.preflight_parent_cash_task

    def preflight(service, binding):
        result = original(service, binding)
        events.append("verified")
        return result

    def build(**kw):
        assert x["calls"][0][0] == "create"
        assert events == ["verified"]
        assert kw["distribution_binding"] == x["entry"]["implemented_distribution_receipt_binding"]
        events.append("sealed")
        path = kw["output_dir"] / "receipt.json"
        path.parent.mkdir()
        path.write_bytes(b"offline complete")
        return dict(path=path.relative_to(x["tmp_path"]).as_posix(),
                    sha256=sha256(path.read_bytes()).hexdigest())

    monkeypatch.setattr(routes, "preflight_parent_cash_task", preflight)
    monkeypatch.setattr(completion, "build_distribution_receipt", build)
    monkeypatch.setattr(completion, "replay_task_receipt", _mock_verified_replay(x))
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: x["tmp_path"])
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", lambda _: x["Service"]())
    monkeypatch.setattr(routes, "authorize", lambda *a, **k: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=x["tmp_path"], sessions=None, port=0)
    response = TestClient(app).post("/api/v1/operating-research/parent-cash-tasks/v3",
                                   json=dict(spec_binding=x["binding"], request_key="offline-test"))
    assert response.status_code == 202
    assert events == ["verified", "sealed"]
    assert completion.valuation_receipt_path(x["tmp_path"], x["task_id"]).is_file()


@pytest.mark.parametrize("missing,reason", [
    ("case_package_binding", "PARENT_TASK_CASE_BINDING_REQUIRED"),
    ("implemented_distribution_receipt_binding", "PARENT_TASK_IMPLEMENTED_DISTRIBUTION_BINDING_REQUIRED"),
])
def test_blockage_survives_api_restart_and_gets_are_read_only(setup, monkeypatch, missing, reason):
    x = setup
    x["entry"].pop(missing)
    x["save"]()
    with pytest.raises(ValueError, match=reason):
        completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])

    class Service(x["Service"]):
        base = x["tmp_path"] / "tasks"

    directory = Service.base / x["task_id"]
    directory.mkdir(parents=True)
    (directory / "input.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: x["tmp_path"])
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", lambda _: Service())
    monkeypatch.setattr(routes, "authorize", lambda *a, **k: None)

    def snapshot():
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in x["tmp_path"].rglob("*") if p.is_file()}

    before = snapshot()
    calls = list(x["calls"])
    # Separate apps/services prove the status is on disk, not held in a closure.
    for _ in range(2):
        app = FastAPI()
        routes.register_parent_cash_history_routes(app, project=x["tmp_path"], sessions=None, port=0)
        client = TestClient(app)
        history = client.get("/api/v1/operating-research/parent-cash-tasks/history?symbol=600887")
        assert history.status_code == 200
        row = history.json()["items"][0]
        assert row["status"] == "SUCCEEDED"
        assert row["valuation_receipt_status"] == "BLOCKED"
        assert row["valuation_blockage"]["reason_code"] == reason
        url = f"/api/v1/operating-research/parent-cash-tasks/v3/{x['task_id']}/valuation"
        response = client.get(url, params=dict(symbol="600887"))
        assert response.status_code == 409
        assert response.json()["status"] == "PARENT_TASK_VALUATION_BLOCKED"
        assert response.json()["valuation_blockage"]["reason_code"] == reason
        assert response.json()["reason"] == reason
        assert client.get(url, params=dict(symbol="000568")).status_code == 422
    assert snapshot() == before
    assert x["calls"] == calls


def test_blockage_is_head_bound_and_does_not_expose_raw_errors(setup, monkeypatch):
    x = setup

    def fail(**kw):
        raise OSError("private path and provider credentials must not be published")

    monkeypatch.setattr(completion, "build_distribution_receipt", fail)
    with pytest.raises(OSError):
        completion.run_and_seal_parent_cash_task(x["Service"](), x["task_id"])
    path = completion.valuation_blockage_path(x["tmp_path"], x["task_id"])
    assert b"credentials" not in path.read_bytes()
    head = x["Service"]()._load(x["task_id"])[2]
    row = completion.read_valuation_publication(x["tmp_path"], x["task_id"], head)
    assert row["valuation_blockage"]["reason_code"] == "PARENT_TASK_PUBLICATION_IO_ERROR"
    assert completion.read_valuation_publication(
        x["tmp_path"], x["task_id"], dict(head, sha256="b" * 64)) == dict(
            valuation_receipt_status="NOT_SEALED", valuation_blockage=None)
