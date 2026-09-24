from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

import pytest

import value_investment_agent.m5_event_run as m5_event_run
from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_core import (
    CONFIDENCE_HIGH,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    SEVERITY_HIGH,
    ChangeEventInput,
    EventLedger,
    event_ledger_from_payload,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_FACTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import run_event_batch
from value_investment_agent.m5_event_run_state import (
    M5EventRunState,
    m5_event_run_state_from_payload,
)
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
    TaskLockStore,
)


TZ = timezone(timedelta(hours=8))
OBSERVED = datetime(2026, 9, 24, 16, 0, tzinfo=TZ)
OBSERVED_LATER = OBSERVED + timedelta(minutes=10)


def _state_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _digest(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()


def _legacy_event_id(payload: Mapping[str, Any]) -> str:
    refs = tuple(dict(item) for item in payload["evidence_refs"])
    fingerprint = _digest(
        "event",
        payload["namespace"],
        payload["symbol"],
        payload["source_event_id"],
        payload["event_type"],
        _state_digest(payload["previous_state"]),
        _state_digest(payload["current_state"]),
        payload["severity"],
        payload["reason"],
        _state_digest({"refs": refs}),
        payload["confidence"],
        payload.get("correction_of_event_id") or "",
        payload.get("supersedes_event_id") or "",
    )
    return "m5-" + _digest("event-id", fingerprint)[:32]


def _event(
    *,
    source_event_id: str,
    observed_at: datetime,
    source_id: str = "cninfo",
    current_state: Mapping[str, Any] | None = None,
) -> ChangeEventInput:
    available_at = observed_at - timedelta(minutes=5)
    return ChangeEventInput(
        source_event_id=source_event_id,
        source_id=source_id,
        symbol="600519",
        event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        detected_at=available_at,
        available_at=available_at,
        effective_at=available_at,
        previous_state={},
        current_state=current_state or {"value": "1.0"},
        severity=SEVERITY_HIGH,
        reason="synthetic M5 run-state boundary fixture",
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
        parser_version="boundary-v1",
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
                version="boundary-v1",
                evidence_refs=({"id": "dependency-facts"},),
            ),
        )
    )


def _run(
    *,
    state: M5EventRunState | None,
    batch_id: str,
    event_id: str,
    at: datetime = OBSERVED,
    run_id: str = "m5-run-1",
    current_state: Mapping[str, Any] | None = None,
    lock_store: TaskLockStore | None = None,
    lock_owner: str = "offline-m5-runner",
    lock_token: str = "m5-offline-token",
    expected_revision: int | None = None,
):
    return run_event_batch(
        events=(
            _event(
                source_event_id=event_id,
                observed_at=at,
                current_state=current_state,
            ),
        ),
        observed_times=(at,),
        watermark=_watermark(watermark_id=f"scan-{batch_id}", at=at),
        graph=_graph(),
        run_id=run_id,
        generated_at=at,
        state=state,
        batch_id=batch_id,
        lock_store=lock_store,
        lock_owner=lock_owner,
        lock_token=lock_token,
        expected_revision=expected_revision,
    )


def _payload(state: M5EventRunState) -> dict[str, Any]:
    return json.loads(state.to_json())


def test_export_import_then_second_batch_continues() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    restored = m5_event_run_state_from_payload(_payload(first.state))

    assert restored.to_json() == first.state.to_json()
    assert restored.revision == 1
    assert len(restored.event_ledger) == 1

    second = _run(
        state=restored,
        batch_id="batch-2",
        event_id="event-2",
        at=OBSERVED_LATER,
    )

    assert second.state.revision == 2
    assert second.accepted_event_count == 1
    assert [item.source_event_id for item in second.state.event_ledger.events()] == [
        "event-1",
        "event-2",
    ]
    assert len(second.state.checkpoints.checkpoints()) == 2
    assert [item.last_sequence for item in second.state.checkpoints.checkpoints()] == [
        1,
        2,
    ]
    assert len(second.state.outbox.alerts()) == 2


def test_same_batch_replay_is_noop_and_changed_inputs_fail_closed() -> None:
    first = _run(state=None, batch_id="batch-idempotent", event_id="event-1")
    replay = _run(
        state=first.state,
        batch_id="batch-idempotent",
        event_id="event-1",
    )

    assert replay.idempotent_noop is True
    assert replay.receipt_id == first.receipt_id
    assert replay.state.to_json() == first.state.to_json()

    with pytest.raises(ValueError, match="already used with different inputs"):
        _run(
            state=first.state,
            batch_id="batch-idempotent",
            event_id="event-1",
            current_state={"value": "2.0"},
        )

    assert first.state.revision == 1
    assert len(first.state.event_ledger) == 1


def test_rejected_new_batch_is_committed_not_claimed_as_replay() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    future_event = _event(source_event_id="event-future", observed_at=OBSERVED_LATER)

    rejected = run_event_batch(
        events=(future_event,),
        observed_times=(OBSERVED,),
        watermark=_watermark(watermark_id="scan-batch-rejected", at=OBSERVED),
        graph=_graph(),
        run_id="m5-run-1",
        generated_at=OBSERVED,
        state=first.state,
        batch_id="batch-rejected",
    )

    assert rejected.idempotent_noop is False
    assert rejected.accepted_event_count == 0
    assert rejected.state.revision == 2
    assert len(rejected.state.event_ledger) == 1
    assert len(rejected.state.batch_records) == 2

    replay = run_event_batch(
        events=(future_event,),
        observed_times=(OBSERVED,),
        watermark=_watermark(watermark_id="scan-batch-rejected", at=OBSERVED),
        graph=_graph(),
        run_id="m5-run-1",
        generated_at=OBSERVED_LATER,
        state=rejected.state,
        batch_id="batch-rejected",
    )
    assert replay.idempotent_noop is True
    assert replay.receipt_id == rejected.receipt_id
    assert replay.generated_at == rejected.generated_at
    assert replay.state.to_json() == rejected.state.to_json()


def test_old_batch_replays_after_later_watermark() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    second = _run(
        state=first.state,
        batch_id="batch-2",
        event_id="event-2",
        at=OBSERVED_LATER,
    )

    replay = _run(
        state=second.state,
        batch_id="batch-1",
        event_id="event-1",
    )

    assert replay.idempotent_noop is True
    assert replay.receipt_id == first.receipt_id
    assert replay.generated_at == first.generated_at
    assert replay.state.to_json() == second.state.to_json()
    assert [item.event_id for item in replay.alerts] == [
        item.event_id for item in first.alerts
    ]


def test_expected_revision_blocks_stale_snapshot_without_mutation() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    payload_before = first.state.to_json()

    with pytest.raises(ValueError, match="expected_revision"):
        _run(
            state=first.state,
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED_LATER,
            expected_revision=0,
        )
    assert first.state.revision == 1
    assert first.state.to_json() == payload_before

    committed = _run(
        state=first.state,
        batch_id="batch-2",
        event_id="event-2",
        at=OBSERVED_LATER,
        expected_revision=1,
    )
    assert committed.state.revision == 2


def test_cross_ledger_reference_and_checkpoint_holes_fail_closed() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")

    unknown_event = _payload(first.state)
    unknown_event["outbox"]["alerts"][0]["event_id"] = "m5-unknown-event"
    with pytest.raises(ValueError, match="unknown event"):
        m5_event_run_state_from_payload(unknown_event)

    weakened_alert = _payload(first.state)
    weakened_alert["outbox"]["alerts"][0]["severity"] = "LOW"
    with pytest.raises(ValueError, match="severity"):
        m5_event_run_state_from_payload(weakened_alert)

    no_review_alert = _payload(first.state)
    no_review_alert["outbox"]["alerts"][0]["requires_human_review"] = False
    with pytest.raises(ValueError, match="review requirement"):
        m5_event_run_state_from_payload(no_review_alert)

    checkpoint_hole = _payload(first.state)
    checkpoint = checkpoint_hole["checkpoints"]["checkpoints"][0]
    checkpoint["last_sequence"] = 0
    checkpoint["ingested_event_ids"] = []
    with pytest.raises(ValueError, match="does not cover all events"):
        m5_event_run_state_from_payload(checkpoint_hole)

    duplicate_event = _payload(first.state)
    duplicated = deepcopy(duplicate_event["event_ledger"]["events"][0])
    duplicated["sequence"] = 2
    duplicate_event["event_ledger"]["events"].append(duplicated)
    with pytest.raises(ValueError, match="duplicate event_id"):
        m5_event_run_state_from_payload(duplicate_event)


def test_revision_sequence_and_watermark_regressions_fail_closed() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")

    revision_regression = _payload(first.state)
    revision_regression["revision"] = 0
    with pytest.raises(ValueError, match="does not match its latest batch record"):
        m5_event_run_state_from_payload(revision_regression)

    sequence_regression = _payload(first.state)
    sequence_regression["event_ledger"]["events"][0]["sequence"] = 2
    with pytest.raises(ValueError, match="sequence is not contiguous"):
        m5_event_run_state_from_payload(sequence_regression)

    watermark_regression = _payload(first.state)
    watermarks = watermark_regression["watermarks"]["watermarks"]
    regressed = deepcopy(watermarks[-1])
    regressed["watermark_id"] = "scan-regressed"
    regressed["coverage_through"] = OBSERVED - timedelta(minutes=1)
    watermarks.append(regressed)
    with pytest.raises(ValueError, match="regression"):
        m5_event_run_state_from_payload(watermark_regression)


def test_actual_unknown_namespace_and_non_no_order_action_fail_closed() -> None:
    with pytest.raises(ValueError, match="SIMULATED"):
        M5EventRunState.empty(state_key="actual-state", namespace=NAMESPACE_ACTUAL)
    with pytest.raises(ValueError, match="SIMULATED"):
        M5EventRunState.empty(state_key="unknown-state", namespace="UNKNOWN")

    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    state_action = _payload(first.state)
    state_action["action"] = "BUY"
    with pytest.raises(ValueError, match="no_order"):
        m5_event_run_state_from_payload(state_action)

    event_action = _payload(first.state)
    event_action["event_ledger"]["events"][0]["action"] = "BUY"
    with pytest.raises(ValueError, match="no_order"):
        m5_event_run_state_from_payload(event_action)

    assert ACTION_NO_ORDER == "no_order"


def test_legacy_event_id_without_source_id_loads_but_new_field_tampering_fails() -> None:
    ledger = EventLedger(namespace=NAMESPACE_SIMULATED)
    accepted = ledger.append(
        _event(source_event_id="legacy-event", observed_at=OBSERVED),
        observed_at=OBSERVED,
    )
    assert accepted.event is not None

    legacy_payload = deepcopy(ledger.as_policy())
    legacy_event = legacy_payload["events"][0]
    del legacy_event["source_id"]
    del legacy_event["effective_at"]
    legacy_event["event_id"] = _legacy_event_id(legacy_event)

    restored = event_ledger_from_payload(legacy_payload)
    assert len(restored) == 1
    assert restored.events()[0].source_id == "unspecified-source"

    tampered = deepcopy(ledger.as_policy())
    tampered_event = tampered["events"][0]
    tampered_event["requires_human_review"] = not tampered_event[
        "requires_human_review"
    ]
    with pytest.raises(ValueError, match="Event id does not match"):
        event_ledger_from_payload(tampered)

    unsafe_legacy = deepcopy(legacy_payload)
    unsafe_event = unsafe_legacy["events"][0]
    unsafe_event["effective_at"] = OBSERVED_LATER.isoformat()
    unsafe_event["event_id"] = _legacy_event_id(unsafe_event)
    with pytest.raises(ValueError, match="Legacy event"):
        event_ledger_from_payload(unsafe_legacy)


def test_receipt_binding_rejects_namespace_forgery_and_detects_state_mutation() -> None:
    receipt = _run(state=None, batch_id="batch-1", event_id="event-1")

    with pytest.raises(ValueError, match="namespace"):
        replace(receipt, namespace=NAMESPACE_ACTUAL)
    with pytest.raises(ValueError, match="state hash"):
        replace(receipt, state_sha256="0" * 64)

    assert receipt.as_policy()["batch_id"] == "batch-1"


def test_pre_commit_exception_leaves_input_unchanged_and_retry_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = M5EventRunState.empty(state_key="m5-run-1")

    def fail_commit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic pre-commit failure")

    monkeypatch.setattr(m5_event_run.CheckpointLedger, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="pre-commit"):
        _run(state=state, batch_id="batch-retry", event_id="event-retry")
    monkeypatch.undo()

    assert state.revision == 0
    assert len(state.event_ledger) == 0
    assert state.checkpoints.checkpoints() == ()
    assert state.outbox.alerts() == ()

    retry = _run(state=state, batch_id="batch-retry", event_id="event-retry")

    assert retry.state.revision == 1
    assert len(retry.state.event_ledger) == 1
    assert len(retry.state.checkpoints.checkpoints()) == 1
    assert len(retry.state.outbox.alerts()) == 1


def test_post_commit_exception_replay_does_not_duplicate_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_state = m5_event_run.M5EventRunState
    captured: list[M5EventRunState] = []

    def fail_after_state_construction(*args: object, **kwargs: object) -> None:
        captured.append(original_state(*args, **kwargs))
        raise RuntimeError("synthetic post-commit failure")

    fail_after_state_construction.empty = original_state.empty  # type: ignore[attr-defined]
    monkeypatch.setattr(m5_event_run, "M5EventRunState", fail_after_state_construction)
    with pytest.raises(RuntimeError, match="post-commit"):
        _run(state=None, batch_id="batch-post-commit", event_id="event-post-commit")
    monkeypatch.undo()

    assert len(captured) == 1
    durable_state = captured[0]
    assert durable_state.revision == 1
    assert len(durable_state.event_ledger) == 1
    assert len(durable_state.checkpoints.checkpoints()) == 1
    assert len(durable_state.outbox.alerts()) == 1

    replay = _run(
        state=durable_state,
        batch_id="batch-post-commit",
        event_id="event-post-commit",
    )

    assert replay.idempotent_noop is True
    assert replay.state.to_json() == durable_state.to_json()
    assert len(replay.state.event_ledger) == 1
    assert len(replay.state.checkpoints.checkpoints()) == 1
    assert len(replay.state.outbox.alerts()) == 1


def test_different_run_ids_contend_on_the_same_state_lock() -> None:
    first = _run(state=None, batch_id="batch-1", event_id="event-1")
    locks = TaskLockStore()
    held = locks.acquire(
        scope=f"M5:state:{first.state.state_key}",
        owner="worker-b",
        token="token-b",
        now=OBSERVED + timedelta(minutes=5),
        lease_seconds=600,
    )
    assert held.lock is not None

    with pytest.raises(ValueError, match="Could not acquire"):
        _run(
            state=first.state,
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED_LATER,
            run_id="worker-b-run",
            lock_store=locks,
            lock_owner="worker-b",
            lock_token="different-token",
        )

    assert first.state.revision == 1
    assert len(first.state.event_ledger) == 1
