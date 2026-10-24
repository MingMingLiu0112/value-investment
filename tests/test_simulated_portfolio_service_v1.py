"""Persistent SIM uses native accounting; no actual account or market qualification."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from value_investment_agent.application.portfolio.simulated_portfolio_service_v1 import (
    create_simulated_portfolio_service,
)
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, SimulatedAccountContext, JournalValidationError,
)


def now():
    return datetime.now(timezone.utc).isoformat()


def factory(root, name="paper-a", sources=None):
    return create_simulated_portfolio_service(repository_root=root, account_id=name,
        research_sources=sources)


def initialize(service):
    return service.initialize(dict(confirmed_hypothetical=True, idempotency_key="init",
        expected_revision=0, cash_cny="10000", holdings=[], sleeve_allocations={}, policy={},
        as_of="2026-10-20", confirmed_at=now(), confirmation_note="Explicit hypothetical budget"))


def fill(service, tx, *, side="BUY", symbol="600519", sleeve="CORE_VALUE", quantity="100",
         day="2026-10-21"):
    payload = dict(transaction_id=tx, side=side, sleeve=sleeve, symbol=symbol,
        exchange="SSE" if symbol.startswith("6") else "SZSE", quantity=quantity,
        price_cny="10", fees_cny="5", trade_date=day)
    if side == "BUY":
        payload.update(trading_unit="100", next_sell_session="2026-10-22" if day == "2026-10-21" else "2026-10-23")
    _, digest = service.prepare_fill(dict(confirmed_hypothetical=True, idempotency_key=tx,
        expected_revision=service.read()["revision"], fill=payload))
    request = dict(confirmed_hypothetical=True, idempotency_key=tx + "-confirm",
        expected_revision=service.read()["revision"], prepared_record_sha256=digest,
        confirmed_at=now(), confirmation_note="Manual hypothetical fill, not a strategy signal")
    result = service.confirm_fill(request)
    assert service.confirm_fill(request) == result
    return result


def source(root, symbol="600519"):
    path = "runtime/public-research/test-only-" + symbol + ".json"
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(symbol=symbol, scope="TEST_ONLY")), encoding="utf-8")
    return dict(path=path, sha256=sha256(p.read_bytes()).hexdigest(), symbol=symbol, available_at=now())


def entry(service, digest, source_id="core"):
    return service.confirm_entry_hypothesis(dict(confirmed_hypothetical=True,
        idempotency_key="entry-" + digest, expected_revision=service.read()["revision"],
        fill_record_sha256=digest, source_id=source_id,
        confirmation_note="Explicit simulated thesis, not original PIT or approval",
        narrative=dict(thesis="Conditional cash return thesis", hold_logic="Only while evidence holds",
            invalidation_conditions=["Permanent earnings impairment"])))


def test_bound_baseline_restart_fifo_entry_and_two_sleeves(tmp_path):
    sources = {"core": source(tmp_path), "swing": source(tmp_path, "300750")}
    service = factory(tmp_path, sources=sources)
    initialize(service)
    _, first = fill(service, "A")
    entry(service, first)
    _, second = fill(service, "B", day="2026-10-22")
    # Same account: the second sleeve consumes the same cash, not another allocation.
    fill(service, "S", symbol="300750", sleeve="HOTSPOT_SATELLITE", day="2026-10-22")
    restarted = factory(tmp_path, sources=sources)
    assert restarted.read() == service.read()
    view = restarted.read()
    assert view["portfolio"]["cash_cny"] == "6985"
    assert view["risk_snapshot"]["namespace"] == "SIMULATED"
    assert view["account_context"] == dict(namespace="SIMULATED", account_id="paper-a",
        version="persistent-simulated-portfolio-v1")
    assert view["risk_snapshot_binding"]["account_context"] == view["account_context"]
    records = PrivateJournal(tmp_path / "runtime/simulated-portfolios-v1/paper-a/journal.jsonl").read()
    assert records[0]["body"]["account_context"] == view["account_context"]
    assert view["risk_snapshot_binding"]["baseline_record_sha256"] == records[0]["record_sha256"]
    assert view["entries"][0]["hypothesis"]["thesis"] == "Conditional cash return thesis"
    _, sold = fill(restarted, "sell", side="SELL", quantity="100", day="2026-10-22")
    consumed = restarted.entry_consumption(sell_fill_sha256=sold)
    assert consumed["consumed_entry_fill_sha256"] == [first]
    assert consumed["after"][second]["remaining_quantity"] == "100"
    assert restarted.read()["entries"][0]["remaining_quantity"] == "0"
    assert restarted.read()["formal_eligibility"] is False


def test_actual_sim_and_cross_account_refusal(tmp_path):
    sim = factory(tmp_path, sources={"core": source(tmp_path)})
    initialize(sim)
    path = tmp_path / "runtime/simulated-portfolios-v1/paper-a/journal.jsonl"
    with pytest.raises(JournalValidationError, match="context mismatch"):
        PrivatePortfolioService(PrivateJournal(path)).records()
    with pytest.raises(JournalValidationError, match="context mismatch"):
        PrivatePortfolioService(PrivateJournal(path), account_context=SimulatedAccountContext("paper-b")).records()
    other = factory(tmp_path, "paper-b", {"core": source(tmp_path)})
    initialize(other)
    _, digest = fill(sim, "A")
    before = other.read()
    with pytest.raises(JournalValidationError, match="belong"):
        entry(other, digest)
    assert other.read() == before
    actual_path = tmp_path / "actual-test-only.jsonl"
    actual = PrivatePortfolioService(PrivateJournal(actual_path))
    actual.initialize(dict(idempotency_key="init", expected_revision=0, account_scope="TEST_ONLY_ACTUAL",
        as_of="2026-10-20", cash_cny="10000", holdings=[], sleeve_allocations={}, policy={},
        confirmed_at=now(), confirmation_note="TEST_ONLY"))
    with pytest.raises(JournalValidationError, match="context mismatch"):
        PrivatePortfolioService(PrivateJournal(actual_path), account_context=SimulatedAccountContext("paper-a")).records()


@pytest.mark.parametrize("field,value", [("namespace", "ACTUAL"), ("path", "elsewhere"),
    ("account_scope", "ACTUAL"), ("account_id", "other")])
def test_request_cannot_select_authority_or_path(tmp_path, field, value):
    service = factory(tmp_path)
    with pytest.raises(JournalValidationError):
        service.initialize(dict(confirmed_hypothetical=True, **{field: value}))
    assert service.read()["revision"] == 0


def test_unsafe_account_id_rejected(tmp_path):
    for account in ("../x", "74bb/receipt", "", "a.b"):
        with pytest.raises(JournalValidationError):
            factory(tmp_path, account)


def test_linked_storage_rejected(tmp_path):
    target = tmp_path / "other-test-only"
    target.mkdir()
    parent = tmp_path / "runtime/simulated-portfolios-v1"
    parent.mkdir(parents=True)
    try:
        (parent / "paper-a").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit test symlinks")
    with pytest.raises(JournalValidationError, match="links"):
        factory(tmp_path)


def test_source_tamper_future_and_cross_security_refused(tmp_path):
    ref = source(tmp_path)
    service = factory(tmp_path, sources={"core": ref})
    initialize(service)
    _, digest = fill(service, "A")
    p = tmp_path / ref["path"]
    p.write_bytes(b"tampered TEST_ONLY source")
    before = service.read()
    with pytest.raises(JournalValidationError, match="hash mismatch"):
        entry(service, digest)
    assert service.read() == before
    future = dict(source(tmp_path), available_at="2099-01-01T00:00:00+00:00")
    with pytest.raises(JournalValidationError, match="unavailable"):
        entry(factory(tmp_path, sources={"core": future}), digest)
    with pytest.raises(JournalValidationError, match="security mismatch"):
        entry(factory(tmp_path, sources={"core": source(tmp_path, "300750")}), digest)


def test_cancel_draft_t1_and_confirmed_correction_unsupported(tmp_path):
    service = factory(tmp_path)
    initialize(service)
    fill(service, "A")
    revision = service.read()["revision"]
    with pytest.raises(JournalValidationError, match="sellable"):
        fill(service, "same-day", side="SELL")
    assert service.read()["revision"] == revision
    _, digest = service.prepare_fill(dict(confirmed_hypothetical=True, idempotency_key="draft",
        expected_revision=revision, fill=dict(transaction_id="cancel", side="SELL", sleeve="CORE_VALUE",
            symbol="600519", exchange="SSE", quantity="100", price_cny="10", fees_cny="5", trade_date="2026-10-22")))
    service.cancel_fill(dict(confirmed_hypothetical=True, idempotency_key="cancel",
        expected_revision=revision + 1, prepared_record_sha256=digest, cancelled_at=now(), reason="Hypothesis cancelled"))
    before = service.read()
    with pytest.raises(JournalValidationError, match="CORRECTION_UNSUPPORTED"):
        service.correct_confirmed_fill({})
    assert service.read() == before
    assert before["portfolio"]["cash_cny"] == "8995"


def test_explicit_hypothetical_ips_and_reconciliation_remain_simulated(tmp_path):
    from datetime import date
    from value_investment_agent.application.portfolio.simulated_trade_journey import _policy
    service = factory(tmp_path)
    initialize(service)
    _, digest = service.prepare_policy(dict(confirmed_hypothetical=True, idempotency_key="ips",
        expected_revision=1, policy=_policy(date(2026, 10, 20))))
    service.confirm_policy(dict(confirmed_hypothetical=True, idempotency_key="ips-confirm",
        expected_revision=2, prepared_record_sha256=digest, confirmed_at=now(),
        confirmation_note="Only explicit hypothetical budgets"))
    view = service.read()
    assert view["portfolio"]["policy"]["core_value_budget_cny"] == "5000"
    assert view["policy"]["sensitivity"] == "SIMULATED_EXPLICIT_HYPOTHESIS"
    service.reconcile(dict(confirmed_hypothetical=True, idempotency_key="reconcile",
        expected_revision=3, reconciled_at=now(), confirmation_note="Internal simulated accounting"))
    assert service.read()["risk_snapshot"]["namespace"] == "SIMULATED"
    fill(service, "after-snapshot")
    refreshed = service.read()["risk_snapshot"]
    assert refreshed["namespace"] == "SIMULATED" and refreshed["account_scope"] == "SIMULATED:paper-a"


def test_original_source_tamper_after_confirmation_fails_read(tmp_path):
    ref = source(tmp_path)
    service = factory(tmp_path, sources={"core": ref})
    initialize(service)
    _, digest = fill(service, "A")
    entry(service, digest)
    (tmp_path / ref["path"]).write_bytes(b"Changed source after confirmation")
    with pytest.raises(JournalValidationError, match="hash mismatch"):
        factory(tmp_path).read()


CHILD = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_simulated_portfolio_service_v1 import factory,initialize,fill,entry,source
root=Path(sys.argv[1]); phase=sys.argv[2]
ref=json.loads((root/'server-source.json').read_text())
s=factory(root,sources={'core':ref})
if phase=='one':
 initialize(s); _,digest=fill(s,'A'); entry(s,digest)
elif phase=='two':
 assert s.read()['portfolio']['cash_cny']=='8995'
 assert s.read()['entries'][0]['hypothesis']['thesis']=='Conditional cash return thesis'
 fill(s,'next-day',day='2026-10-22')
print(json.dumps(s.read()))
'''


def test_two_processes_persist_across_two_sessions(tmp_path):
    ref = source(tmp_path)
    (tmp_path / "server-source.json").write_text(json.dumps(ref), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONDONTWRITEBYTECODE="1")
    def child(phase):
        return json.loads(subprocess.check_output([sys.executable, "-B", "-c", CHILD, str(tmp_path), phase],
            env=env, cwd=Path(__file__).resolve().parents[1], text=True, encoding="utf-8"))
    first = child("one")
    second = child("two")
    third = child("read")
    assert first["portfolio"]["cash_cny"] == "8995"
    assert second["portfolio"]["cash_cny"] == "7990"
    assert second == third
    assert second["revision"] == first["revision"] + 2
    assert second["entries"][0] == first["entries"][0]


@pytest.mark.skipif(not os.environ.get("PERSISTENT_SIM_PUBLIC_ROOT"), reason="Optional retained public originals")
def test_sealed_74bb_cannot_be_opened_as_a_persistent_account(tmp_path):
    origin = Path(os.environ["PERSISTENT_SIM_PUBLIC_ROOT"])
    raw = (origin / "runtime/swing-simulated-lifecycle/74bb1ed2e7944ea08d484464293409a6/SIMULATED-journal.jsonl").read_bytes()
    target = tmp_path / "runtime/simulated-portfolios-v1/paper-a/journal.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    with pytest.raises(JournalValidationError, match="context mismatch"):
        factory(tmp_path)
    assert target.read_bytes() == raw


@pytest.mark.skipif(not os.environ.get("PERSISTENT_SIM_PUBLIC_ROOT"), reason="Optional retained public originals")
def test_real_core_and_swing_hash_references_are_not_qualification(tmp_path):
    origin = Path(os.environ["PERSISTENT_SIM_PUBLIC_ROOT"])
    paths = {"core": ("600519", "runtime/source-native-pending/3bb7bfe05c3f4c7d9a52d34b07588087/candidate.json"),
        "swing": ("300750", "runtime/swing-simulated-lifecycle/74bb1ed2e7944ea08d484464293409a6/receipt.json")}
    refs = {}
    before = {}
    for key, (symbol, relative) in paths.items():
        original = origin / relative
        raw = original.read_bytes()
        before[relative] = sha256(raw).hexdigest()
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        refs[key] = dict(path=relative, sha256=sha256(raw).hexdigest(), symbol=symbol, available_at=now())
    service = factory(tmp_path, sources=refs)
    initialize(service)
    for key, symbol, sleeve in [("core", "600519", "CORE_VALUE"), ("swing", "300750", "HOTSPOT_SATELLITE")]:
        _, digest = fill(service, key, symbol=symbol, sleeve=sleeve)
        entry(service, digest, key)
    restored = factory(tmp_path, sources=refs).read()
    assert restored["formal_eligibility"] is False and restored["position_guidance"] is None
    assert len(restored["entries"]) == 2
    for item in restored["entries"]:
        bound = json.loads(item["hypothesis"]["research_version"])
        assert bound["sha256"] == before[bound["path"]]
    assert all(sha256((origin / p).read_bytes()).hexdigest() == h for p, h in before.items())
