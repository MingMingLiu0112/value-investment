from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import threading

import pytest

from value_investment_agent.m5_event_core import (
    CONFIDENCE_HIGH,
    EVENT_IDENTITY_SOURCE_ID_V2,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    INGEST_CONFLICT_REJECTED,
    INGEST_DUPLICATE,
    NAMESPACE_SIMULATED,
    SEVERITY_HIGH,
    ChangeEventInput,
    EventLedger,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_FACTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import (
    run_event_batch,
    run_event_batch_persisted,
)
from value_investment_agent.m5_event_run_state import M5EventRunState
from value_investment_agent.m5_event_state_store import (
    InMemoryM5EventRunStateStore,
    JsonM5EventRunStateStore,
    M5StateStoreConflict,
)
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)


TZ = timezone(timedelta(hours=8))
OBSERVED = datetime(2026, 9, 24, 16, 0, tzinfo=TZ)
OBSERVED_LATER = OBSERVED + timedelta(minutes=10)


def _event(*, source_event_id: str, at: datetime) -> ChangeEventInput:
    available_at = at - timedelta(minutes=5)
    return ChangeEventInput(
        source_event_id=source_event_id,
        source_id="cninfo",
        symbol="600519",
        event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        detected_at=available_at,
        available_at=available_at,
        effective_at=available_at,
        previous_state={},
        current_state={"value": source_event_id},
        severity=SEVERITY_HIGH,
        reason="synthetic M5 state-store fixture",
        evidence_refs=({"id": f"evidence-{source_event_id}"},),
        confidence=CONFIDENCE_HIGH,
        requires_human_review=True,
        namespace=NAMESPACE_SIMULATED,
    )


def _watermark(*, watermark_id: str, at: datetime) -> ScanWatermark:
    return ScanWatermark(
        watermark_id=watermark_id,
        scope="ALL",
        source="cninfo",
        coverage_through=at,
        retrieved_at=at,
        parser_version="state-store-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": f"scan-{watermark_id}"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts",
                kind=KIND_FACTS,
                symbol="*",
                inputs=(),
                version="state-store-v1",
                evidence_refs=({"id": "dependency-facts"},),
            ),
        )
    )


def _kwargs(*, batch_id: str, event_id: str, at: datetime = OBSERVED):
    return {
        "events": (_event(source_event_id=event_id, at=at),),
        "observed_times": (at,),
        "watermark": _watermark(watermark_id=f"scan-{batch_id}", at=at),
        "graph": _graph(),
        "run_id": "m5-persisted-run",
        "generated_at": at,
        "batch_id": batch_id,
    }


def test_persisted_batch_round_trip_and_replay_are_idempotent() -> None:
    store = InMemoryM5EventRunStateStore()
    first = run_event_batch_persisted(
        store=store,
        **_kwargs(batch_id="batch-1", event_id="event-1"),
    )

    loaded = store.load(state_key=first.state.state_key)
    assert loaded is not None
    assert loaded.to_json() == first.state.to_json()
    assert loaded.revision == 1

    replay = run_event_batch_persisted(
        store=store,
        **_kwargs(batch_id="batch-1", event_id="event-1"),
    )
    assert replay.idempotent_noop is True
    assert replay.receipt_id == first.receipt_id
    assert store.load(state_key=first.state.state_key).to_json() == loaded.to_json()


def test_source_id_v2_event_identity_remains_frozen() -> None:
    event = replace(
        _event(source_event_id="event-1", at=OBSERVED),
        event_identity_version=EVENT_IDENTITY_SOURCE_ID_V2,
    )
    ledger = EventLedger(namespace=NAMESPACE_SIMULATED)

    accepted = ledger.append(event, observed_at=OBSERVED)

    assert accepted.event is not None
    assert accepted.event.event_id == "m5-1d4c3461284b3d5fecdf91885f91beea"


def test_v2_identity_cannot_be_silently_mixed_with_v3_dedupe() -> None:
    event = _event(source_event_id="event-version-mix", at=OBSERVED)
    v2_event = replace(
        event,
        event_identity_version=EVENT_IDENTITY_SOURCE_ID_V2,
    )
    ledger = EventLedger(namespace=NAMESPACE_SIMULATED)
    first = ledger.append(v2_event, observed_at=OBSERVED)
    assert first.event is not None

    second = ledger.append(event, observed_at=OBSERVED_LATER)

    assert second.status == INGEST_CONFLICT_REJECTED
    assert second.event is None
    assert len(ledger) == 1


def test_v3_identity_normalizes_equivalent_timezone_offsets() -> None:
    local = _event(source_event_id="event-timezone-equivalent", at=OBSERVED)
    utc = replace(
        local,
        detected_at=local.detected_at.astimezone(timezone.utc),
        available_at=local.available_at.astimezone(timezone.utc),
        effective_at=local.effective_at.astimezone(timezone.utc),
    )

    assert local.source_fingerprint == utc.source_fingerprint
    local_ledger = EventLedger(namespace=NAMESPACE_SIMULATED)
    local_event = local_ledger.append(local, observed_at=OBSERVED).event
    utc_event = local_ledger.append(utc, observed_at=OBSERVED_LATER)
    assert local_event is not None
    assert utc_event.status == INGEST_DUPLICATE
    assert utc_event.event is not None
    assert utc_event.event.event_id == local_event.event_id


def test_persisted_pre_commit_failure_retries_once() -> None:
    store = InMemoryM5EventRunStateStore()

    def fail_commit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic persisted pre-commit failure")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(store, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="pre-commit"):
            run_event_batch_persisted(
                store=store,
                **_kwargs(batch_id="batch-retry", event_id="event-retry"),
            )

    assert store.load(state_key="m5-persisted-run") is None

    retry = run_event_batch_persisted(
        store=store,
        **_kwargs(batch_id="batch-retry", event_id="event-retry"),
    )

    persisted = store.load(state_key=retry.state.state_key)
    assert persisted is not None
    assert persisted.revision == 1
    assert len(persisted.event_ledger) == 1
    assert len(persisted.checkpoints.checkpoints()) == 1
    assert len(persisted.outbox.alerts()) == 1


def test_persisted_ambiguous_post_commit_retry_is_idempotent() -> None:
    store = InMemoryM5EventRunStateStore()
    original_commit = store.commit

    def commit_then_fail(*args: object, **kwargs: object) -> None:
        original_commit(*args, **kwargs)
        raise RuntimeError("synthetic persisted post-commit failure")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(store, "commit", commit_then_fail)
        with pytest.raises(RuntimeError, match="post-commit"):
            run_event_batch_persisted(
                store=store,
                **_kwargs(batch_id="batch-ambiguous", event_id="event-ambiguous"),
            )

    durable = store.load(state_key="m5-persisted-run")
    assert durable is not None
    assert durable.revision == 1
    assert len(durable.event_ledger) == 1
    assert len(durable.checkpoints.checkpoints()) == 1
    assert len(durable.outbox.alerts()) == 1

    replay = run_event_batch_persisted(
        store=store,
        **_kwargs(batch_id="batch-ambiguous", event_id="event-ambiguous"),
    )

    assert replay.idempotent_noop is True
    assert replay.state.to_json() == durable.to_json()
    assert len(store.load(state_key=durable.state_key).outbox.alerts()) == 1


def test_commit_rejects_stale_revision_and_same_revision_replacement() -> None:
    first = run_event_batch(
        **_kwargs(batch_id="batch-1", event_id="event-1"),
        state=None,
    )
    competing = run_event_batch(
        **_kwargs(batch_id="batch-2", event_id="event-2"),
        state=None,
    )
    store = InMemoryM5EventRunStateStore()
    store.commit(
        expected_revision=0,
        expected_sha256=None,
        state=first.state,
    )

    with pytest.raises(M5StateStoreConflict, match="revision changed"):
        store.commit(
            expected_revision=0,
            expected_sha256=None,
            state=competing.state,
        )

    with pytest.raises(M5StateStoreConflict, match="Same revision"):
        store.commit(
            expected_revision=1,
            expected_sha256=first.state.state_sha256(),
            state=competing.state,
        )


def test_json_store_round_trips_across_instances(tmp_path) -> None:
    root = tmp_path / "m5-state"
    first = run_event_batch_persisted(
        store=JsonM5EventRunStateStore(root),
        **_kwargs(batch_id="batch-1", event_id="event-1"),
    )

    restored_store = JsonM5EventRunStateStore(root)
    restored = restored_store.load(state_key=first.state.state_key)
    assert restored is not None
    assert restored.to_json() == first.state.to_json()
    assert (root / ".m5-event-state-store.lock").exists()

    second = run_event_batch_persisted(
        store=restored_store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED_LATER,
        ),
    )
    assert second.state.revision == 2


def test_persisted_wrapper_rejects_nonempty_snapshot_without_store() -> None:
    existing = run_event_batch(
        **_kwargs(batch_id="batch-1", event_id="event-1"),
        state=None,
    )
    store = InMemoryM5EventRunStateStore()

    with pytest.raises(M5StateStoreConflict, match="non-empty snapshot"):
        run_event_batch_persisted(
            store=store,
            state=existing.state,
            **_kwargs(batch_id="batch-2", event_id="event-2"),
        )


def test_json_store_rejects_corrupt_state_key_payload(tmp_path) -> None:
    root = tmp_path / "m5-state"
    store = JsonM5EventRunStateStore(root)
    payload = M5EventRunState.empty(state_key="stored-key").as_policy()
    path = store._state_path("requested-key")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="state_key"):
        store.load(state_key="requested-key")


def test_json_store_rejects_corrupt_payload_without_overwrite(tmp_path) -> None:
    root = tmp_path / "m5-state"
    store = JsonM5EventRunStateStore(root)
    state = run_event_batch(
        **_kwargs(batch_id="batch-1", event_id="event-1"),
        state=None,
    ).state
    path = store._state_path(state.state_key)
    path.write_text('{"schema_version": ', encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(json.JSONDecodeError):
        store.load(state_key=state.state_key)
    with pytest.raises(json.JSONDecodeError):
        store.commit(
            expected_revision=0,
            expected_sha256=None,
            state=state,
        )

    assert path.read_bytes() == before


def test_json_store_cross_instance_cas_allows_exactly_one_writer(tmp_path) -> None:
    root = tmp_path / "m5-state"
    first_store = JsonM5EventRunStateStore(root)
    second_store = JsonM5EventRunStateStore(root)
    first = run_event_batch(
        **_kwargs(batch_id="batch-1", event_id="event-1"),
        state=None,
    ).state
    second = first.clone()
    second = run_event_batch(
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED_LATER,
        ),
        state=second,
    ).state
    barrier = threading.Barrier(2)

    def commit(store: JsonM5EventRunStateStore, state: M5EventRunState) -> str:
        barrier.wait(timeout=5)
        try:
            store.commit(
                expected_revision=0,
                expected_sha256=None,
                state=state,
            )
        except M5StateStoreConflict:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            future.result()
            for future in (
                executor.submit(commit, first_store, first),
                executor.submit(commit, second_store, second),
            )
        )

    assert sorted(outcomes) == ["committed", "conflict"]
    persisted = first_store.load(state_key=first.state_key)
    assert persisted is not None
    assert persisted.revision == 1
    assert len(persisted.batch_records) == 1


def test_persisted_wrapper_rejects_stale_snapshot(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    first = run_event_batch_persisted(
        store=store,
        **_kwargs(batch_id="batch-1", event_id="event-1"),
    )
    stale = store.load(state_key=first.state.state_key)
    assert stale is not None
    run_event_batch_persisted(
        store=store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED_LATER,
        ),
    )

    with pytest.raises(M5StateStoreConflict, match="stale"):
        run_event_batch_persisted(
            store=store,
            state=stale,
            **_kwargs(
                batch_id="batch-3",
                event_id="event-3",
                at=OBSERVED_LATER + timedelta(minutes=10),
            ),
        )
