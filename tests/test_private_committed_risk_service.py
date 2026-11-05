"""Private declaration lifecycle with isolated facts, IO and ACTUAL contract checks."""
from datetime import datetime
from pathlib import Path
import json

import pytest

from test_private_committed_risk import isolated_clock
from test_private_ips_policy import confirm_policy
from test_portfolio_risk_assessment import _attributes
from value_investment_agent.application.portfolio.private_committed_risk import PrivateCommittedRiskService
from value_investment_agent.application.portfolio import private_committed_risk as declarations
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalConflict, JournalValidationError,
)
from value_investment_agent.application.product import dual_sleeve_risk as file_review

NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")
ARGS = dict(authenticated_subject="LOCAL_OPERATOR", now=NOW)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root, private = tmp_path / "repo", tmp_path / "private"
    root.mkdir()
    private.mkdir()
    def isolated_path(path, **kwargs):
        candidate = Path(path).resolve()
        assert candidate.is_relative_to(private) and kwargs["private_root"] == private
        if kwargs.get("must_exist") and not candidate.is_file():
            raise ValueError("Required private declaration file missing")
        return candidate
    monkeypatch.setattr(declarations, "require_private_data_path", isolated_path)
    monkeypatch.setattr(file_review, "require_private_data_path", isolated_path)
    monkeypatch.setattr(projection, "_verified_prices", lambda *a: {"300364": {
        "price_cny": "20", "trade_date": NOW.date().isoformat(), "price_admitted": True,
        "current_pit": True, "bundle_sha256": "a" * 64}})
    monkeypatch.setattr(projection, "_verified_attributes", lambda *a, **k: [_attributes(symbol="300364").as_policy()])
    def make(account="ISOLATED_PRIVATE_FIXTURE", initialize=True, separate_sleeves=False):
        journal = PrivateJournal(private / (account + ".jsonl"))
        service = PrivatePortfolioService(journal)
        if initialize:
            service.initialize(dict(idempotency_key="TEST_ONLY-init", expected_revision=0,
                account_scope=account, as_of="2026-10-10", cash_cny="8000",
                holdings=[dict(symbol="300364", exchange="SZSE", quantity="100", cost_basis_cny="2000")],
                sleeve_allocations={"300364": ({"CORE_VALUE": "50", "HOTSPOT_SATELLITE": "50"}
                    if separate_sleeves else {"CORE_VALUE": "100"})}, policy={},
                confirmed_at="2026-10-10T20:00:00+08:00", confirmation_note="TEST_ONLY isolated fixture"))
            confirm_policy(service)
            service.reconcile(dict(idempotency_key="TEST_ONLY-statement", expected_revision=len(service.records()),
                reconciled_at=NOW.isoformat(), confirmation_note="TEST_ONLY external statement",
                account_evidence={"id": "TEST_ONLY-statement", "kind": "broker_statement"}))
        return service, PrivateCommittedRiskService(journal, repository_root=root, private_root=private)
    return make, root, private


def request(service, value="100", key="TEST_ONLY-risk"):
    view = service.read(**ARGS)
    return dict(expected_revision=view["revision"], account_scope=view["account_scope"],
        journal_tip_sha256=view["journal_tip_sha256"], idempotency_key=key,
        read_and_confirmed=True, confirmation_note="TEST_ONLY explicit declared amount",
        amounts=[dict(symbol=row["symbol"], sleeve=row["sleeve"], committed_risk_cny=value,
            evidence_ref="TEST_ONLY-explicit-risk-basis") for row in view["allocations"]])


def test_confirm_correct_restart_and_current_source_preserve_accounting(setup):
    make, root, _ = setup
    ledger, service = make()
    before = ledger.portfolio_view(generated_at=NOW)
    body = request(service)
    first = service.confirm(body, **ARGS)
    assert first["status"] == "COMMITTED_RISK_CONFIRMED"
    assert first["revision"] == body["expected_revision"] + 1
    assert first["request_binding"]["journal_tip_sha256"] == body["journal_tip_sha256"]
    assert first["formal_eligibility"] is first["changes_holdings"] is False
    assert first["ledger_written"] is True
    assert service.confirm(body, **ARGS) == first
    source = service.source(**ARGS)
    result = projection.review_private_risk_rehearsal(ledger.journal,
        repository_root=root, generated_at=NOW, today=NOW.date(), committed_risk_source=source)
    assert "CORE_VALUE:risk_unknown" not in result["blockers"]
    correction = request(service, "75", "TEST_ONLY-correction")
    second = service.confirm(correction, **ARGS)
    assert second["revision"] == first["revision"] + 1
    assert second["confirmation_sha256"] != first["confirmation_sha256"]
    assert second["allocations"][0]["committed_risk_cny"] == "75"
    with pytest.raises(JournalConflict):
        projection.review_private_risk_rehearsal(ledger.journal, repository_root=root,
            generated_at=NOW, committed_risk_source=source)
    restarted = PrivateCommittedRiskService(PrivateJournal(ledger.journal.path), repository_root=root,
        private_root=service.private_root)
    assert restarted.read(**ARGS)["confirmation_status"] == "CONFIRMED"
    assert restarted.source(**ARGS) is not None
    after = ledger.portfolio_view(generated_at=NOW)
    for key in ("cash_cny", "realized_pnl_cny", "cost_basis_total_cny", "positions", "trades"):
        assert before[key] == after[key]


def test_missing_public_facts_do_not_block_confirmation_and_later_qualify(setup, monkeypatch):
    make, _, _ = setup
    ledger, service = make()
    attributes = projection._verified_attributes
    monkeypatch.setattr(projection, "_verified_attributes", lambda *a, **k: None)
    first = service.confirm(request(service), **ARGS)
    assert first["confirmation_status"] == "CONFIRMED"
    assert first["qualification_status"] == "BLOCKED_PRIVATE_INPUT"
    assert service.source(**ARGS) is None
    original = list(service.private_root.rglob("input.json"))[0].read_bytes()
    monkeypatch.setattr(projection, "_verified_attributes", attributes)
    assert service.source(**ARGS) is not None
    assert list(service.private_root.rglob("input.json"))[0].read_bytes() == original


@pytest.mark.parametrize("account", ["TEST_ONLY_ACCOUNT", "test-only-account", "SIMULATED_ACCOUNT", "SYNTHETIC_ACCOUNT"])
def test_test_only_saves_without_production_source(setup, account):
    ledger, service = setup[0](account)
    result = service.confirm(request(service), **ARGS)
    assert result["confirmation_status"] == "CONFIRMED"
    assert result["namespace"] == "SIMULATED"
    assert result["qualification_status"] == "TEST_ONLY_NOT_ACTUAL"
    assert service.source(**ARGS) is None


def test_empty_and_pending_views_do_not_break_risk_reads(setup):
    make, _, _ = setup
    _, empty = make("EMPTY", initialize=False)
    assert empty.read(**ARGS)["status"] == "NOT_CONNECTED"
    assert empty.source(**ARGS) is None
    ledger, service = make()
    service.confirm(request(service), **ARGS)
    ledger.prepare_policy(dict(idempotency_key="TEST_ONLY-draft", expected_revision=len(ledger.records()),
        policy={"investable_assets_cny": "10000"}))
    assert service.source(**ARGS) is None
    assert "PENDING_DRAFT_EXISTS" in service.read(**ARGS)["blockers"]
    assert ledger.portfolio_view(generated_at=NOW)["cash_cny"] == "8000"


@pytest.mark.parametrize("fault", ["revision", "tip", "account", "ack", "negative", "unknown", "duplicate", "missing", "extra", "evidence", "subject"])
def test_invalid_confirmation_cannot_append_or_save(setup, fault):
    ledger, service = setup[0]()
    body = request(service)
    args = dict(ARGS)
    if fault == "revision": body["expected_revision"] -= 1
    elif fault == "tip": body["journal_tip_sha256"] = "b" * 64
    elif fault == "account": body["account_scope"] = "OTHER"
    elif fault == "ack": body["read_and_confirmed"] = False
    elif fault == "negative": body["amounts"][0]["committed_risk_cny"] = "-1"
    elif fault == "unknown": body["amounts"][0]["committed_risk_cny"] = None
    elif fault == "duplicate": body["amounts"] *= 2
    elif fault == "missing": body["amounts"] = []
    elif fault == "extra": body["private_root"] = "forged"
    elif fault == "evidence": body["amounts"][0]["evidence_ref"] = ""
    else: args["authenticated_subject"] = ""
    before = ledger.journal.path.read_bytes()
    with pytest.raises((ValueError, JournalConflict)):
        service.confirm(body, **args)
    assert ledger.journal.path.read_bytes() == before
    assert list(service.private_root.rglob("declaration.json")) == []


def test_file_tamper_rejects_source_without_destroying_accounting(setup):
    ledger, service = setup[0]()
    service.confirm(request(service), **ARGS)
    original = list(service.private_root.rglob("input.json"))[0]
    original.write_text("{}", encoding="utf-8")
    with pytest.raises(JournalValidationError, match="hash mismatch"):
        service.source(**ARGS)
    assert ledger.portfolio_view(generated_at=NOW)["cash_cny"] == "8000"


def test_failed_atomic_publication_does_not_append(setup, monkeypatch):
    ledger, service = setup[0]()
    body = request(service)
    before = ledger.journal.path.read_bytes()
    monkeypatch.setattr(declarations.os, "rename", lambda *a: (_ for _ in ()).throw(OSError("TEST_ONLY failure")))
    with pytest.raises(OSError): service.confirm(body, **ARGS)
    assert ledger.journal.path.read_bytes() == before
    assert list(service.private_root.rglob("declaration.json")) == []


def test_same_revision_second_writer_conflicts(setup):
    ledger, service = setup[0]()
    first, second = request(service), request(service, "25", "TEST_ONLY-second")
    service.confirm(first, **ARGS)
    with pytest.raises(JournalConflict): service.confirm(second, **ARGS)
    assert len([r for r in ledger.records() if r["kind"] == "COMMITTED_RISK_CONFIRMED"]) == 1


@pytest.mark.parametrize("initialize", [False, True])
def test_absent_declaration_never_enters_private_source_guards(setup, monkeypatch, initialize):
    _, service = setup[0](initialize=initialize)
    def forbidden(*args, **kwargs):
        raise AssertionError("Undeclared legacy journal must not enter source-only guards")
    monkeypatch.setattr(service, "_prepare", forbidden)
    monkeypatch.setattr(service, "_context", forbidden)
    assert service.source(**ARGS) is None


def test_pending_policy_invalidates_source_before_private_guards(setup, monkeypatch):
    ledger, service = setup[0]()
    service.confirm(request(service), **ARGS)
    ledger.prepare_policy(dict(idempotency_key="TEST_ONLY-pending", expected_revision=len(ledger.records()),
        policy={"investable_assets_cny": "10000"}))
    monkeypatch.setattr(service, "_prepare", lambda *args: pytest.fail("Pending journal entered source guard"))
    assert service.source(**ARGS) is None


def test_active_declaration_cannot_be_read_by_another_subject(setup):
    ledger, service = setup[0]()
    service.confirm(request(service), **ARGS)
    with pytest.raises(JournalValidationError, match="identity differs"):
        service.source(authenticated_subject="OTHER_OPERATOR", now=NOW)
    assert ledger.portfolio_view(generated_at=NOW)["cash_cny"] == "8000"


def test_same_security_risk_amounts_remain_separate_by_sleeve_after_restart(setup):
    ledger, service = setup[0](separate_sleeves=True)
    body = request(service)
    for row in body["amounts"]:
        row["committed_risk_cny"] = "75" if row["sleeve"] == "CORE_VALUE" else "25"
    service.confirm(body, **ARGS)
    restarted = PrivateCommittedRiskService(PrivateJournal(ledger.journal.path),
        repository_root=service.root, private_root=service.private_root)
    rows = restarted.read(**ARGS)["allocations"]
    assert {row["sleeve"]: (row["quantity"], row["cost_basis_cny"], row["committed_risk_cny"])
        for row in rows} == {"CORE_VALUE": ("50", "1000", "75"), "HOTSPOT_SATELLITE": ("50", "1000", "25")}
    assert restarted.source(**ARGS) is not None


@pytest.mark.parametrize("tamper", [False, True])
def test_append_interruption_reuses_immutable_declaration_on_retry(setup, monkeypatch, tamper):
    ledger, service = setup[0]()
    body = request(service)
    append = ledger.journal.append
    before = ledger.journal.path.read_bytes()
    def fail(**kwargs):
        raise OSError("TEST_ONLY interruption after file publication")
    monkeypatch.setattr(ledger.journal, "append", fail)
    with pytest.raises(OSError):
        service.confirm(body, **ARGS)
    assert ledger.journal.path.read_bytes() == before
    saved = list(service.private_root.rglob("declaration.json"))[0]
    original = saved.read_bytes()
    monkeypatch.setattr(ledger.journal, "append", append)
    if tamper:
        declaration = json.loads(original)
        declaration["amounts"][0]["committed_risk_cny"] = "999"
        saved.write_text(json.dumps(declaration), encoding="utf-8")
        with pytest.raises(JournalValidationError, match="explicit request"):
            service.confirm(body, **ARGS)
        assert ledger.journal.path.read_bytes() == before
        return
    assert service.confirm(body, **ARGS)["status"] == "COMMITTED_RISK_CONFIRMED"
    assert saved.read_bytes() == original
    assert service.source(**ARGS) is not None
