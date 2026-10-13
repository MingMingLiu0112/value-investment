"""WEB-D2 P0.2 acceptance: cross-process atomicity of the private portfolio journal.

Every test drives the real ``PrivatePortfolioService`` over an on-disk
``PrivateJournal``. Concurrency tests use ``multiprocessing`` with the spawn
context, so the checks exercise the OS-level cross-process lock instead of
threads inside one interpreter. The journal path is handed to ``PrivateJournal``
directly, which deliberately bypasses the private-root guard.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import time
from pathlib import Path
from queue import Empty

import pytest

from value_investment_agent.application.portfolio.private_portfolio_service import (
    JournalConflict,
    JournalValidationError,
    PrivateJournal,
    PrivatePortfolioService,
    PrivateStoreUnavailable,
)
from value_investment_agent.domain.portfolio.dual_sleeve_records import canonical_bytes

CTX = mp.get_context("spawn")

BASELINE = {
    "idempotency_key": "init-1",
    "expected_revision": 0,
    "account_scope": "acct-demo",
    "as_of": "2026-10-10",
    "cash_cny": "500000.00",
    "holdings": [{"symbol": "600519", "exchange": "SSE", "quantity": "1000",
                  "cost_basis_cny": "1500000.00"}],
    "sleeve_allocations": {"600519": {"CORE_VALUE": "600", "HOTSPOT_SATELLITE": "400"}},
    "policy": {"investable_assets_cny": "2000000", "max_single_security_pct": "10"},
    "confirmation_note": "initial confirm",
    "confirmed_at": "2026-10-10T20:00:00+08:00",
}

FILL_ONE = {
    "transaction_id": "T1", "side": "BUY", "sleeve": "CORE_VALUE",
    "symbol": "600519", "exchange": "SSE", "quantity": "200",
    "price_cny": "1500.00", "fees_cny": "5.00", "trade_date": "2026-10-12",
    "next_sell_session": "2026-10-13", "trading_unit": "100",
}

FILL_TWO = {
    "transaction_id": "T2", "side": "BUY", "sleeve": "HOTSPOT_SATELLITE",
    "symbol": "600519", "exchange": "SSE", "quantity": "100",
    "price_cny": "1500.00", "fees_cny": "1.00", "trade_date": "2026-10-12",
    "next_sell_session": "2026-10-13", "trading_unit": "100",
}


def _init_request(**overrides):
    request = dict(BASELINE)
    request["holdings"] = [dict(row) for row in BASELINE["holdings"]]
    request.update(overrides)
    return request


def _fill_request(**overrides):
    request = {"idempotency_key": "fill-1", "expected_revision": 1, "fill": dict(FILL_ONE)}
    request.update(overrides)
    return request


def _confirm_request(prepared_digest, **overrides):
    request = {
        "idempotency_key": "fill-1-confirm",
        "expected_revision": 2,
        "prepared_record_sha256": prepared_digest,
        "confirmed_at": "2026-10-12T21:00:00+08:00",
        "confirmation_note": "confirmed",
    }
    request.update(overrides)
    return request


def _service(path: Path, *, lock_timeout_seconds: float = 10.0) -> PrivatePortfolioService:
    return PrivatePortfolioService(
        PrivateJournal(path, lock_timeout_seconds=lock_timeout_seconds)
    )


def _seed_prepared_journal(path: Path, *, fill: dict | None = None):
    service = _service(path)
    service.initialize(_init_request())
    draft, digest = service.prepare_fill(fill if fill is not None else _fill_request())
    return service, draft, digest


def _assert_hash_chain(path: Path) -> None:
    """Recompute the journal hash chain from raw lines with the module canonicalization."""
    previous = None
    for line in path.read_text(encoding="utf-8").splitlines():
        assert line.strip()
        record = json.loads(line)
        assert record["previous_record_sha256"] == previous
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        assert hashlib.sha256(canonical_bytes(payload)).hexdigest() == record["record_sha256"]
        previous = record["record_sha256"]


def _await_outcomes(queue, processes, count, *, timeout=45.0):
    outcomes = []
    deadline = time.monotonic() + timeout
    while len(outcomes) < count and time.monotonic() < deadline:
        try:
            outcomes.append(queue.get(timeout=0.5))
        except Empty:
            if all(process.exitcode is not None for process in processes):
                break
    if len(outcomes) < count:
        raise AssertionError(
            f"workers reported {len(outcomes)}/{count} results; exit codes "
            f"{[process.exitcode for process in processes]}"
        )
    return outcomes


def _await_message(queue, process, *, timeout=45.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return queue.get(timeout=0.5)
        except Empty:
            if process.exitcode is not None:
                raise AssertionError(f"worker exited early with code {process.exitcode}")
    raise AssertionError("worker did not report in time")


def _kill(processes):
    for process in processes:
        if process.is_alive():
            process.kill()
            process.join(timeout=10)


# Module-level workers only: spawn pickles them by name, so every argument is plain data.


def _confirm_worker(journal_path, request, barrier, queue):
    from value_investment_agent.application.portfolio.private_portfolio_service import (
        JournalConflict,
        PrivateJournal,
        PrivatePortfolioService,
    )

    service = PrivatePortfolioService(PrivateJournal(Path(journal_path)))
    barrier.wait(timeout=60)
    try:
        payload, digest = service.confirm_fill(request)
    except JournalConflict as error:
        queue.put({"outcome": "conflict", "code": error.code, "message": str(error)})
    except Exception as error:  # pragma: no cover - reported instead of swallowed
        queue.put({"outcome": "error", "error": f"{type(error).__name__}: {error}"})
    else:
        queue.put({"outcome": "ok", "payload": payload, "digest": digest})


def _record_fill_worker(journal_path, prepare_request, confirm_request, barrier, queue,
                        max_attempts=200):
    """Race one full prepare+confirm workflow, refreshing the revision after conflicts."""
    from value_investment_agent.application.portfolio.private_portfolio_service import (
        JournalConflict,
        PrivateJournal,
        PrivatePortfolioService,
    )

    service = PrivatePortfolioService(PrivateJournal(Path(journal_path)))
    barrier.wait(timeout=60)
    attempts = []
    revision = int(prepare_request["expected_revision"])
    prepared_digest = None
    for _ in range(max_attempts):
        try:
            if prepared_digest is None:
                payload, digest = service.prepare_fill(
                    {**prepare_request, "expected_revision": revision}
                )
                prepared_digest = digest
                revision = int(payload["revision"])
                attempts.append({"kind": "prepare", "outcome": "ok", "code": None})
            else:
                payload, digest = service.confirm_fill({
                    **confirm_request,
                    "prepared_record_sha256": prepared_digest,
                    "expected_revision": revision,
                })
                attempts.append({"kind": "confirm", "outcome": "ok", "code": None})
                queue.put({"outcome": "ok", "attempts": attempts,
                           "digest": digest, "payload": payload})
                return
        except JournalConflict as error:
            attempts.append({
                "kind": "prepare" if prepared_digest is None else "confirm",
                "outcome": "conflict",
                "code": error.code,
            })
            with service.journal.transaction() as records:
                revision = len(records)
            time.sleep(0.02)
    queue.put({"outcome": "error", "error": "retry budget exhausted", "attempts": attempts})


def _hold_lock_then_die_worker(journal_path, acquired_event):
    from value_investment_agent.application.portfolio.private_portfolio_service import (
        PrivateJournal,
    )

    journal = PrivateJournal(Path(journal_path))
    with journal.transaction():
        acquired_event.set()
        os._exit(9)


def _hold_lock_until_released_worker(journal_path, queue, release_event):
    from value_investment_agent.application.portfolio.private_portfolio_service import (
        PrivateJournal,
    )

    journal = PrivateJournal(Path(journal_path))
    with journal.transaction():
        queue.put("locked")
        if not release_event.wait(timeout=60):
            os._exit(8)


def test_concurrent_confirms_of_same_draft_commit_exactly_one_fill(tmp_path):
    path = tmp_path / "journal.jsonl"
    _, _, draft_digest = _seed_prepared_journal(path)
    barrier = CTX.Barrier(2)
    queue = CTX.Queue()
    requests = [
        _confirm_request(draft_digest, idempotency_key="confirm-a"),
        _confirm_request(draft_digest, idempotency_key="confirm-b"),
    ]
    processes = [
        CTX.Process(target=_confirm_worker, args=(str(path), request, barrier, queue))
        for request in requests
    ]
    try:
        for process in processes:
            process.start()
        outcomes = _await_outcomes(queue, processes, 2)
        for process in processes:
            process.join(timeout=10)
    finally:
        _kill(processes)

    assert [process.exitcode for process in processes] == [0, 0]
    assert sorted(item["outcome"] for item in outcomes) == ["conflict", "ok"]
    loser = next(item for item in outcomes if item["outcome"] == "conflict")
    assert loser["code"] == "VERSION_CONFLICT"
    winner = next(item for item in outcomes if item["outcome"] == "ok")
    assert winner["payload"]["status"] == "FILL_CONFIRMED"
    assert winner["payload"]["cash_cny"] == "199995.00"
    assert len(winner["digest"]) == 64

    records = PrivateJournal(path).read()
    assert [record["kind"] for record in records] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED"]
    view = _service(path).portfolio_view()
    assert view["revision"] == 3
    assert view["cash_cny"] == "199995.00"
    assert view["realized_pnl_cny"] == "0"
    assert view["positions"][0]["quantity"] == "1200"
    assert {row["sleeve"]: row["quantity"] for row in view["positions"][0]["sleeves"]} == {
        "CORE_VALUE": "800", "HOTSPOT_SATELLITE": "400"}
    assert len(view["trades"]) == 1

    control_service, _, control_digest = _seed_prepared_journal(tmp_path / "control.jsonl")
    control_service.confirm_fill(_confirm_request(control_digest, idempotency_key="control-confirm"))
    control_view = control_service.portfolio_view()
    assert view["cash_cny"] == control_view["cash_cny"] == "199995.00"
    assert view["positions"] == control_view["positions"]
    _assert_hash_chain(path)


def test_two_processes_race_different_fills_and_retry_until_both_land(tmp_path):
    """Two processes commit two different fills from the same starting revision.

    One journal admits only one pending draft at a time (``prepare_fill`` raises
    ``PENDING_DRAFT_EXISTS`` otherwise), so the two different drafts are produced
    by racing the two full prepare+confirm workflows rather than by pre-seeding
    two simultaneous drafts. Every attempt must stay in {ok, JournalConflict};
    the losing process refreshes to the current revision and retries until both
    fills are committed exactly once and the journal stays readable.
    """
    path = tmp_path / "journal.jsonl"
    service = _service(path)
    service.initialize(_init_request())
    barrier = CTX.Barrier(2)
    queue = CTX.Queue()
    jobs = [
        (_fill_request(idempotency_key="fill-a", expected_revision=1),
         _confirm_request("0" * 64, idempotency_key="confirm-a")),
        (_fill_request(idempotency_key="fill-b", expected_revision=1, fill=dict(FILL_TWO)),
         _confirm_request("0" * 64, idempotency_key="confirm-b")),
    ]
    processes = [
        CTX.Process(target=_record_fill_worker,
                    args=(str(path), prepare_request, confirm_request, barrier, queue))
        for prepare_request, confirm_request in jobs
    ]
    try:
        for process in processes:
            process.start()
        outcomes = _await_outcomes(queue, processes, 2)
        for process in processes:
            process.join(timeout=10)
    finally:
        _kill(processes)

    assert [process.exitcode for process in processes] == [0, 0]
    assert all(item["outcome"] == "ok" for item in outcomes), outcomes
    attempts = [attempt for item in outcomes for attempt in item["attempts"]]
    assert all(attempt["outcome"] in {"ok", "conflict"} for attempt in attempts)
    assert all(attempt["code"] in {None, "VERSION_CONFLICT", "PENDING_DRAFT_EXISTS"}
               for attempt in attempts), attempts
    assert any(attempt["outcome"] == "conflict" for attempt in attempts), attempts

    records = PrivateJournal(path).read()
    assert [record["kind"] for record in records] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED",
        "FILL_PREPARED", "FILL_CONFIRMED"]
    assert [record["body"]["fill"]["transaction_id"] for record in records
            if record["kind"] == "FILL_CONFIRMED"] in (["T1", "T2"], ["T2", "T1"])
    view = _service(path).portfolio_view()
    assert view["revision"] == 5
    assert view["cash_cny"] == "49994.00"
    assert view["realized_pnl_cny"] == "0"
    assert {trade["transaction_id"] for trade in view["trades"]} == {"T1", "T2"}
    assert len(view["trades"]) == 2
    assert view["positions"][0]["quantity"] == "1300"
    assert {row["sleeve"]: row["quantity"] for row in view["positions"][0]["sleeves"]} == {
        "CORE_VALUE": "800", "HOTSPOT_SATELLITE": "500"}
    _assert_hash_chain(path)


def test_same_key_and_payload_is_idempotent_sequentially_and_across_processes(tmp_path):
    path = tmp_path / "journal.jsonl"
    service, _, draft_digest = _seed_prepared_journal(path)
    request = _confirm_request(draft_digest, idempotency_key="confirm-idem")

    first_payload, first_digest = service.confirm_fill(request)
    stable_bytes = path.read_bytes()
    replay_payload, replay_digest = service.confirm_fill(request)
    assert replay_payload == first_payload
    assert replay_digest == first_digest
    assert path.read_bytes() == stable_bytes

    barrier = CTX.Barrier(2)
    queue = CTX.Queue()
    processes = [
        CTX.Process(target=_confirm_worker, args=(str(path), dict(request), barrier, queue))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = _await_outcomes(queue, processes, 2)
        for process in processes:
            process.join(timeout=10)
    finally:
        _kill(processes)

    assert [process.exitcode for process in processes] == [0, 0]
    assert [item["outcome"] for item in outcomes] == ["ok", "ok"], outcomes
    assert {item["digest"] for item in outcomes} == {first_digest}
    assert all(item["payload"] == first_payload for item in outcomes)
    assert path.read_bytes() == stable_bytes
    assert [record["kind"] for record in PrivateJournal(path).read()] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED"]


def test_same_key_with_different_payload_is_idempotency_conflict(tmp_path):
    path = tmp_path / "journal.jsonl"
    service, _, draft_digest = _seed_prepared_journal(path)
    request = _confirm_request(draft_digest, idempotency_key="confirm-key")
    service.confirm_fill(request)
    stable_bytes = path.read_bytes()

    with pytest.raises(JournalConflict) as error:
        _service(path).confirm_fill({**request, "confirmation_note": "a different note"})
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert path.read_bytes() == stable_bytes
    assert len(PrivateJournal(path).read()) == 3


def test_network_retry_returns_the_stored_record_without_appending(tmp_path):
    path = tmp_path / "journal.jsonl"
    service, _, draft_digest = _seed_prepared_journal(path)
    request = _confirm_request(draft_digest, idempotency_key="confirm-retry")

    service.confirm_fill(request)  # response discarded: the "network dropped" case
    stored_bytes = path.read_bytes()

    payload, digest = _service(path).confirm_fill(request)
    stored = PrivateJournal(path).read()[-1]
    assert stored["kind"] == "FILL_CONFIRMED"
    assert digest == stored["record_sha256"]
    assert payload == stored["response"]
    assert path.read_bytes() == stored_bytes
    assert [record["kind"] for record in PrivateJournal(path).read()] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED"]


def test_truncated_tail_fails_closed_without_mutating_bytes(tmp_path):
    path = tmp_path / "journal.jsonl"
    _, _, draft_digest = _seed_prepared_journal(path)
    with path.open("ab") as stream:
        stream.write(b'{"schema_version": "private-portfolio-journal-v1", "sequence": 3')
    corrupt_bytes = path.read_bytes()

    with pytest.raises(JournalValidationError):
        PrivateJournal(path).read()
    fresh = _service(path)
    with pytest.raises(JournalValidationError):
        fresh.prepare_fill(_fill_request(idempotency_key="fill-3", expected_revision=2))
    with pytest.raises(JournalValidationError):
        fresh.confirm_fill(_confirm_request(draft_digest, idempotency_key="confirm-3"))
    with pytest.raises(JournalValidationError):
        # Must never silently degrade to an empty NOT_CONNECTED portfolio.
        _service(path).portfolio_view()
    assert path.read_bytes() == corrupt_bytes


def test_lock_is_released_when_holder_process_dies(tmp_path):
    path = tmp_path / "journal.jsonl"
    service = _service(path)
    service.initialize(_init_request())
    acquired = CTX.Event()
    child = CTX.Process(target=_hold_lock_then_die_worker, args=(str(path), acquired))
    try:
        child.start()
        assert acquired.wait(timeout=45), "worker never acquired the lock"
        child.join(timeout=30)
        assert child.exitcode == 9

        started = time.monotonic()
        with _service(path, lock_timeout_seconds=2.0).journal.transaction() as records:
            acquired_in = time.monotonic() - started
            assert len(records) == 1
        assert acquired_in < 1.5, "the dead holder must not leave a stale lock behind"
        assert _service(path).portfolio_view()["status"] == "CONNECTED"
    finally:
        _kill([child])


def test_live_lock_holder_times_out_writes_without_mutating_ledger(tmp_path):
    path = tmp_path / "journal.jsonl"
    service = _service(path)
    service.initialize(_init_request())
    queue = CTX.Queue()
    release = CTX.Event()
    child = CTX.Process(target=_hold_lock_until_released_worker,
                        args=(str(path), queue, release))
    request = _fill_request(idempotency_key="fill-blocked", expected_revision=1)
    try:
        child.start()
        assert _await_message(queue, child) == "locked"
        clean_bytes = path.read_bytes()

        started = time.monotonic()
        with pytest.raises(PrivateStoreUnavailable):
            _service(path, lock_timeout_seconds=0.5).prepare_fill(request)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.4, "the write must wait for the lock deadline, not fail instantly"
        assert path.read_bytes() == clean_bytes
        assert [record["kind"] for record in PrivateJournal(path).read()] == [
            "BASELINE_CONFIRMED"]
    finally:
        release.set()
        child.join(timeout=30)
        _kill([child])

    assert child.exitcode == 0
    payload, _ = _service(path).prepare_fill(request)
    assert payload["status"] == "FILL_PREPARED"


def test_restart_replays_portfolio_and_hash_chain(tmp_path):
    path = tmp_path / "journal.jsonl"
    service = _service(path)
    service.initialize(_init_request())
    _, digest_one = service.prepare_fill(_fill_request())
    service.confirm_fill(_confirm_request(digest_one, idempotency_key="confirm-1"))
    _, digest_two = service.prepare_fill(
        _fill_request(idempotency_key="fill-2", expected_revision=3, fill=dict(FILL_TWO))
    )
    service.confirm_fill(
        _confirm_request(digest_two, idempotency_key="confirm-2", expected_revision=4)
    )
    before = service.portfolio_view()

    restarted = _service(path)
    after = restarted.portfolio_view()
    assert after == before
    assert after["revision"] == 5
    assert after["cash_cny"] == "49994.00"
    assert after["realized_pnl_cny"] == "0"
    assert {trade["transaction_id"] for trade in after["trades"]} == {"T1", "T2"}
    assert after["positions"][0]["quantity"] == "1300"
    _assert_hash_chain(path)
    records = PrivateJournal(path).read()
    assert [record["kind"] for record in records] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED",
        "FILL_PREPARED", "FILL_CONFIRMED"]
