"""The page resumes one exact native replay without entering the paid V3 runner."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from value_investment_agent.application.research import parent_cash_funding_continuation_v1 as continuation
from value_investment_agent.application.research import parent_cash_funding_revision_v1 as revision
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes
from value_investment_agent.presentation.web_api import parent_cash_funding_revisions as funding


TASK = "rt-" + "a" * 32
SYMBOL = "600887"
HEAD = {"path": "runtime/task.json", "sha256": "a" * 64}
SPEC = {"path": "runtime/spec.json", "sha256": "b" * 64}


@pytest.fixture
def page(tmp_path, monkeypatch):
    def bind(label, document):
        raw = json.dumps(document).encode()
        digest = sha256(raw).hexdigest()
        pin = dict(file=f"{label}-{digest}.json", sha256=digest)
        return pin, raw

    terms = dict(known_maturities=[dict(code="123456", maturity="2027-04-01", principal_cny="80")],
                 unknown_balance_is_forecast=True, unknown_rate_assumptions=dict(bear="0.05", base="0.03", bull="0.02"),
                 residual_principal_cny="20", cash_interest_9m_verified_floor="2", mixed_less_dividend_cny="3")
    adj, adj_data = bind("reassessment-spec", {"financing_revision": terms})
    matrix, matrix_data = bind("financing-evidence", {"prospective_debt_service": {
        "five_scp_conditional_coupon_2026Q4": "1", "mtn_conditional_coupon_2027": "2"}})
    receipt = dict(previous_task_status="FAILED", parent_head=HEAD, registered_spec=SPEC, originals_matrix=matrix,
                   current_reassessment=dict(revised_spec=adj))
    raw = json.dumps(receipt).encode()
    digest = sha256(raw).hexdigest()
    folder = Path(funding._native_path(funding.directory(tmp_path, TASK) / digest))
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_bytes(raw)
    (folder / matrix["file"]).write_bytes(matrix_data)
    (folder / adj["file"]).write_bytes(adj_data)
    store = tmp_path / "tasks"
    (store / TASK).mkdir(parents=True)
    (store / TASK / "input.json").write_bytes(b"{}")

    class Service:
        def __init__(self, root):
            self.root, self.base = root, root / "tasks"

        def _load(self, task_id):
            assert task_id == TASK
            return {"spec_binding": SPEC, "mode": "LIVE_PARENT_CASH_V3"}, {"status": "FAILED"}, HEAD

        def _bound(self, binding):
            assert binding == SPEC
            return {"symbol": SYMBOL}

    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", Service)
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda root: root)
    performed = []
    prior = {"status": "REJECTED", "scenario_rows": {"bear": {"year": 2027}}, "current_research_range_adopted": False}

    monkeypatch.setattr(revision, "_verify_parent", lambda *args: {"symbol": SYMBOL})
    monkeypatch.setattr(funding, "_project", lambda *args: dict(input_descriptor_sha256="c"*64,
        valuation_date="2025-12-31", current_reassessment=prior))

    def corrected(root, task_id, selected, now):
        assert (root, task_id, selected) == (tmp_path, TASK, digest)
        performed.append("fixed")
        return dict(schema_version="fixed-owner-payment-cash-recheck-v1", symbol=SYMBOL, task_id=TASK,
                    parent_receipt=digest, predecessor_input=adj["sha256"], valuation_date="2025-12-31",
                    status="REJECTED", formal_eligibility=False, current_comparable=False, action="no_order",
                    scenarios={"bear": dict(status="REJECTED", ledger={"year": 2026, "floor_cny": "40"}),
                               "base": dict(status="CALCULATED"), "bull": dict(status="CALCULATED")})

    checker = SimpleNamespace(run_check=corrected, __file__=__file__, __name__="test_only")
    monkeypatch.setattr(continuation, "_checker", lambda: checker)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=0)
    url = f"/api/v1/operating-research/parent-cash-tasks/v3/{TASK}/funding-revisions/{digest}/replay?symbol={SYMBOL}"
    return SimpleNamespace(client=TestClient(app), url=url, folder=folder, digest=digest, checker=checker,
                           performed=performed, prior=prior, adj=adj["sha256"], root=tmp_path)


def allow(monkeypatch):
    monkeypatch.setattr(routes, "authorize", lambda *args, **kwargs: None)


def test_authorized_post_seals_exact_delta_and_get_reopens_without_provider(page, monkeypatch):
    assert page.client.post(page.url, json={}).status_code in (401, 403)
    allow(monkeypatch)
    assert page.client.get(page.url).status_code == 404
    assert page.client.post(page.url, json={"request_key": "old"}).status_code == 422
    assert page.client.post(page.url.replace(SYMBOL, "600519")).status_code == 404
    assert page.client.post(page.url.replace(page.digest, "f"*64)).status_code == 404
    assert page.performed == []
    initial = page.client.post(page.url, json={})
    assert initial.status_code == 200 and initial.headers["cache-control"] == "no-store"
    row = initial.json()
    assert row["current_reassessment"] == page.prior
    assert row["fixed_payment_recheck"]["scenarios"]["bear"]["ledger"] == {"year": 2026, "floor_cny": "40"}
    assert row["financing_terms"]["unknown_rate_assumptions"]["base"] == "0.03"
    assert (row["receipt_sha256"], row["reassessment_spec_sha256"]) == (page.digest, page.adj)
    assert row["action"] == "no_order" and row["new_llm_calls"] == 0
    assert row["status"] == "REPLAYED" and row["original_task_status"] == "FAILED"
    assert row["current_comparable"] is row["formal_eligibility"] is False
    assert row == page.client.get(page.url).json() == page.client.post(page.url).json()
    assert page.performed == ["fixed"]
    seal, = (page.folder.parent.parent / "funding-continuations" / page.digest / continuation.VERSION).glob("*.json")
    altered = json.loads(seal.read_bytes())
    altered["fixed_payment_recheck"]["status"] = "CALCULATED"
    seal.write_text(json.dumps(altered), encoding="utf-8")
    assert page.client.get(page.url).status_code == page.client.post(page.url).status_code == 422
    assert page.performed == ["fixed"]


def test_interruption_retries_same_version_and_overlapping_post_cannot_publish(page, monkeypatch):
    allow(monkeypatch)
    run = page.checker.run_check

    def broken(*args):
        raise ValueError("incomplete calculation")

    monkeypatch.setattr(page.checker, "run_check", broken)
    assert page.client.post(page.url).status_code == 422
    assert page.client.get(page.url).status_code == 404
    entered, release = Event(), Event()

    def pause(*args):
        entered.set()
        assert release.wait(10)
        return run(*args)

    monkeypatch.setattr(page.checker, "run_check", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(page.client.post, page.url)
        try:
            assert entered.wait(10)
            second = page.client.post(page.url)
            assert second.status_code == 409 and second.json()["status"] == "CONTINUATION_IN_PROGRESS"
        finally:
            release.set()
        assert first.result().status_code == 200
    assert page.performed == ["fixed"]


@pytest.mark.skipif(not os.environ.get("VALUE_FUNDING_REVISION_REAL_ROOT"), reason="requires registered source tree")
def test_native_fixed_payment_archive_replay_persists_only_in_execution_root(tmp_path, monkeypatch):
    from decimal import Decimal

    archive = Path(os.environ["VALUE_FUNDING_REVISION_REAL_ROOT"]).resolve()
    task_id = "rt-07724f7f1c8566420935f07b70c846a1"
    digest = "ed62be290ebcffebf47e1c22cd235d77767e42f1d8b13ff4f1273875257c0a19"
    task = archive / "runtime/research-task-execution-v1/parent-cash-task-v3" / task_id

    def snapshot():
        return {p: sha256(p.read_bytes()).hexdigest() for p in task.rglob("*.json")}

    before = snapshot()
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    allow(monkeypatch)

    def open_page():
        app = FastAPI()
        routes.register_parent_cash_history_routes(app, project=archive, sessions=None, port=0)
        return TestClient(app)

    client = open_page()
    url = f"/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/funding-revisions/{digest}/replay?symbol=600887"
    assert client.get(url).status_code == 404 and not (tmp_path / "runtime").exists()
    response = client.post(url, json={})
    assert response.status_code == 200, response.text
    seal = response.json()
    assert seal["source_owner"] == "READ_ONLY_ARCHIVE"
    assert seal["original_task_status"] == seal["paid_task_status"] == "FAILED"
    assert seal["new_llm_calls"] == 0 and seal["action"] == "no_order"
    assert seal["current_reassessment"]["scenario_rows"]["bear"]["before"] == "6306969832.537425"
    result = seal["fixed_payment_recheck"]
    assert result["parent_receipt"] == digest and result["predecessor_input"] == seal["reassessment_spec_sha256"]
    assert Decimal(result["source_payment"]["paid_cny"]) == 99_994_405
    assert result["status"] == "REJECTED" and set(result["scenarios"]) == {"bear", "base", "bull"}
    ledger = result["scenarios"]["bear"]["ledger"]
    assert Decimal(ledger["shortfall_cny"]) == Decimal(ledger["floor_cny"]) - Decimal(ledger["cash_before_distribution_cny"])
    assert Decimal(ledger["shortfall_cny"]) > Decimal(result["predecessor_shortfall_cny"])
    assert result["scenarios"]["base"]["status"] == result["scenarios"]["bull"]["status"] == "CALCULATED"
    assert open_page().get(url).json() == client.post(url, json={}).json() == seal
    assert snapshot() == before
    files = list(Path(funding._native_path(tmp_path / "runtime")).rglob("*.json"))
    assert len(files) == 1 and files[0].stem == sha256(files[0].read_bytes()).hexdigest() == seal["continuation_sha256"]


@pytest.mark.parametrize("fault", ["parent_receipt", "predecessor_input", "action", "status", "scenarios"])
def test_wrong_checker_identity_or_incomplete_result_cannot_be_sealed(page, monkeypatch, fault):
    allow(monkeypatch)
    run = page.checker.run_check

    def changed(*args):
        result = run(*args)
        result[fault] = {} if fault == "scenarios" else "other"
        return result

    monkeypatch.setattr(page.checker, "run_check", changed)
    assert page.client.post(page.url).status_code == 422
    assert page.client.get(page.url).status_code == 404


def test_reopening_requires_intact_revised_spec(page, monkeypatch):
    allow(monkeypatch)
    assert page.client.post(page.url).status_code == 200
    (page.folder / f"reassessment-spec-{page.adj}.json").write_bytes(b"{}")
    assert page.client.get(page.url).status_code == page.client.post(page.url).status_code == 422
    assert page.performed == ["fixed"]


def test_version_selection_cannot_fall_back_to_existing_seal(page, monkeypatch):
    allow(monkeypatch)
    legacy = page.client.post(page.url, json={}).json()
    assert legacy["continuation_version"] == "fixed-payment-v1"
    assert page.client.get(page.url + "&version=maturity-v1").status_code == 404
    for query in ("&version=unknown", "&version=maturity-v1&version=fixed-payment-v1"):
        assert page.client.post(page.url + query, json={}).status_code == 422
    assert page.client.get(page.url).json() == legacy


def test_maturity_post_is_sealed_separately_and_keeps_prior_get(page, monkeypatch):
    from value_investment_agent.application.research import parent_cash_maturity_recheck as maturity

    allow(monkeypatch)
    legacy = page.client.post(page.url, json={}).json()
    def changed(*args):
        checked = page.checker.run_check(*args)
        return dict(checked, schema_version="parent-cash-maturity-recheck-v1",
                    alternative_scenarios=checked["scenarios"], current_research_range_adopted=False)
    monkeypatch.setattr(maturity, "run_check", changed)
    url = page.url + "&version=maturity-v1"
    result = page.client.post(url, json={})
    assert result.status_code == 200, result.text
    current = result.json()
    assert current["continuation_sha256"] != legacy["continuation_sha256"]
    assert current["maturity_recheck"]["status"] == "REJECTED"
    assert current == page.client.get(url).json() == page.client.post(url).json()
    assert page.client.get(page.url).json() == legacy
    assert page.performed == ["fixed", "fixed"]
