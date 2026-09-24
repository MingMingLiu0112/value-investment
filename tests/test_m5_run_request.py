"""Durable, replayable M5 run requests end to end (synthetic data only)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json

import pytest

from value_investment_agent.event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_REQUIRES_RECALCULATION,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_VALUATION_INPUTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import (
    M5EventRunReceipt,
    apply_run_request,
)
from value_investment_agent.m5_event_state_store import (
    JsonM5EventRunReceiptStore,
    JsonM5EventRunStateStore,
    M5_RECEIPT_ALREADY_PUBLISHED,
    M5_RECEIPT_PUBLISHED,
    M5StateStoreConflict,
)
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)
from value_investment_agent.m5_materiality_bridge import (
    MaterialityBridgeBatch,
    build_materiality_bridge_batch,
)
from value_investment_agent.m5_run_request import (
    M5_RUN_REQUEST_SCHEMA,
    M5EventRunRequest,
    build_run_request,
    build_run_request_from_bridge_batch,
)


TZ = timezone(timedelta(hours=8))
PUBLISHED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=TZ)
REVIEWED_AT = datetime(2026, 9, 24, 9, 30, tzinfo=TZ)
RUN_ID = "600887-synthetic-run-20260924"
ANNOUNCEMENT_ID = "1225549001"


def _decision(
    human_decision: str,
    *,
    announcement_id: str = ANNOUNCEMENT_ID,
) -> EventMaterialityDecision:
    recalc = human_decision == DECISION_REQUIRES_RECALCULATION
    return EventMaterialityDecision(
        event_decision_id=f"event-decision-{announcement_id}",
        symbol="600887",
        announcement_id=announcement_id,
        title="synthetic offline fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"pdf-{announcement_id}",
            "path": f"synthetic/{announcement_id}.pdf",
            "sha256": "c" * 64,
        },
        source_sha256="c" * 64,
        machine_candidate_reason="synthetic title rule candidate",
        human_decision=human_decision,
        affected_domains=("balance_sheet_risk",) if recalc else (),
        affected_fact_fields=("total_debt",) if recalc else (),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=recalc,
        requires_model_stale=recalc,
        requires_followup=False,
        reviewed_at=REVIEWED_AT,
        review_notes=("synthetic offline review note",),
    )


def _review(decision: EventMaterialityDecision) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-synthetic-event-review-20260924",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol="600887",
        scan_id="600887-synthetic-scan-20260924",
        scan_sha256="d" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=date(2026, 9, 24),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=(decision,),
        evidence_refs=({"id": "synthetic-scan"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts-600887",
                kind=KIND_FACTS,
                symbol="600887",
                inputs=(),
                version="synthetic-v1",
                evidence_refs=({"id": "facts"},),
            ),
            DependencyNode(
                node_id="valuation-inputs-600887",
                kind=KIND_VALUATION_INPUTS,
                symbol="600887",
                inputs=("facts-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "valuation"},),
            ),
            DependencyNode(
                node_id="model-validity-600887",
                kind=KIND_MODEL_VALIDITY,
                symbol="600887",
                inputs=(),
                version="synthetic-v1",
                evidence_refs=({"id": "model"},),
            ),
            DependencyNode(
                node_id="decision-review-600887",
                kind=KIND_DECISION_REVIEW,
                symbol="600887",
                inputs=("valuation-inputs-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "decision"},),
            ),
            DependencyNode(
                node_id="current-status-600887",
                kind=KIND_CURRENT_STATUS,
                symbol="600887",
                inputs=("decision-review-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "status"},),
            ),
        )
    )


def _watermark(*, watermark_id: str = "synthetic-scan-20260924") -> ScanWatermark:
    return ScanWatermark(
        watermark_id=watermark_id,
        scope="600887",
        source="synthetic-cninfo",
        coverage_through=REVIEWED_AT,
        retrieved_at=REVIEWED_AT,
        parser_version="synthetic-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": "synthetic-scan"},),
    )


def _batch(human_decision: str = DECISION_REQUIRES_RECALCULATION):
    return build_materiality_bridge_batch(
        _review(_decision(human_decision)),
        namespace="SIMULATED",
    )


def _request(
    *,
    batch: MaterialityBridgeBatch | None = None,
    watermark_id: str = "synthetic-scan-20260924",
    announcement_id: str = ANNOUNCEMENT_ID,
) -> M5EventRunRequest:
    if batch is None:
        batch = _batch()
    assert batch is not None
    if announcement_id != ANNOUNCEMENT_ID:
        batch = build_materiality_bridge_batch(
            _review(
                _decision(
                    DECISION_REQUIRES_RECALCULATION,
                    announcement_id=announcement_id,
                )
            ),
            namespace="SIMULATED",
        )
    return build_run_request_from_bridge_batch(
        batch,
        run_id=RUN_ID,
        generated_at=REVIEWED_AT,
        watermark=_watermark(watermark_id=watermark_id),
        graph=_graph(),
    )


class _FailingCommitStore:
    """Simulates a process death immediately before the state commit."""

    def __init__(self, inner: JsonM5EventRunStateStore) -> None:
        self.inner = inner

    def load(self, *, state_key: str):
        return self.inner.load(state_key=state_key)

    def commit(self, *, expected_revision, expected_sha256, state):
        raise RuntimeError("simulated crash before the state commit")


class _FailingPublishStore:
    """Simulates a process death immediately after the state commit."""

    def __init__(self, inner: JsonM5EventRunReceiptStore) -> None:
        self.inner = inner

    def load(self, *, receipt_id: str):
        return self.inner.load(receipt_id=receipt_id)

    def publish(self, *, receipt, request):
        raise RuntimeError("simulated crash after the state commit")


def test_bridge_batch_round_trips_and_rejects_tampering():
    batch = _batch()

    restored = MaterialityBridgeBatch.from_payload(
        json.loads(batch.to_json())
    )

    assert restored.as_policy() == batch.as_policy()
    payload = json.loads(batch.to_json())
    payload["plans"][0]["human_decision"] = DECISION_ALREADY_INCORPORATED
    with pytest.raises(ValueError):
        MaterialityBridgeBatch.from_payload(payload)
    payload = json.loads(batch.to_json())
    payload["plans"][0]["direct_kinds"] = ["financial_facts"]
    with pytest.raises(ValueError):
        MaterialityBridgeBatch.from_payload(payload)
    payload = json.loads(batch.to_json())
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="keys do not match"):
        MaterialityBridgeBatch.from_payload(payload)


def test_run_request_round_trips_and_rejects_tampering():
    request = _request()

    restored = M5EventRunRequest.from_payload(json.loads(request.to_json()))

    assert restored.as_policy() == request.as_policy()
    assert restored.request_sha256() == request.request_sha256()
    assert restored.request_fingerprint() == request.request_fingerprint()
    payload = json.loads(request.to_json())
    payload["observed_times"] = [
        (REVIEWED_AT + timedelta(minutes=1)).isoformat()
    ]
    with pytest.raises(ValueError):
        M5EventRunRequest.from_payload(payload)
    payload = json.loads(request.to_json())
    payload["request_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        M5EventRunRequest.from_payload(payload)
    payload = json.loads(request.to_json())
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="keys do not match"):
        M5EventRunRequest.from_payload(payload)


def test_run_request_rejects_empty_direct_kinds_and_unknown_events():
    with pytest.raises(ValueError, match="cannot be empty"):
        build_run_request(
            run_id=RUN_ID,
            generated_at=REVIEWED_AT,
            events=tuple(_batch().events),
            observed_times=tuple(_batch().observed_times),
            watermark=_watermark(),
            graph=_graph(),
            direct_kinds_by_source_event_id={
                "materiality-review:event-decision-1225549001": ()
            },
        )
    with pytest.raises(ValueError, match="unknown events"):
        build_run_request(
            run_id=RUN_ID,
            generated_at=REVIEWED_AT,
            events=tuple(_batch().events),
            observed_times=tuple(_batch().observed_times),
            watermark=_watermark(),
            graph=_graph(),
            direct_kinds_by_source_event_id={"not-an-event": ("financial_facts",)},
        )


def test_silent_batch_request_carries_no_events(tmp_path):
    request = _request(batch=_batch(DECISION_ALREADY_INCORPORATED))

    assert request.events == ()
    assert request.observed_times == ()
    result = apply_run_request(
        request=M5EventRunRequest.from_payload(
            json.loads(request.to_json())
        ),
        store=JsonM5EventRunStateStore(tmp_path / "state"),
        receipt_store=JsonM5EventRunReceiptStore(tmp_path / "receipts"),
    )

    assert result.publication is not None
    assert result.publication.status == M5_RECEIPT_PUBLISHED
    assert result.receipt.active_events == ()
    assert result.receipt.silent_ok is True
    assert result.receipt.state.revision == 1


def test_apply_run_request_publishes_once_and_replays_after_restart(tmp_path):
    request = _request()
    state_root = tmp_path / "state"
    receipt_root = tmp_path / "receipts"

    first = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(state_root),
        receipt_store=JsonM5EventRunReceiptStore(receipt_root),
    )

    assert first.replayed is False
    assert first.publication is not None
    assert first.publication.status == M5_RECEIPT_PUBLISHED
    assert first.receipt.accepted_event_count == 1
    assert first.receipt.state.revision == 1
    assert len(first.receipt.state.batch_records) == 1
    assert len(first.receipt.state.checkpoints.checkpoints()) == 1
    assert first.receipt.state_sha256 == first.receipt.state.state_sha256()

    # A second process reopens both stores from disk and replays the same
    # request, including the request artifact round-tripped through JSON.
    reloaded_request = M5EventRunRequest.from_payload(
        json.loads(request.to_json())
    )
    second = apply_run_request(
        request=reloaded_request,
        store=JsonM5EventRunStateStore(state_root),
        receipt_store=JsonM5EventRunReceiptStore(receipt_root),
    )

    assert second.replayed is True
    assert second.publication is not None
    assert second.publication.status == M5_RECEIPT_ALREADY_PUBLISHED
    assert second.publication.artifact_sha256 == first.publication.artifact_sha256
    assert second.receipt.receipt_id == first.receipt.receipt_id
    assert second.receipt.state.revision == 1
    assert len(second.receipt.state.batch_records) == 1
    assert len(second.receipt.state.checkpoints.checkpoints()) == 1
    assert len(second.receipt.state.outbox.alerts()) == 1
    assert second.receipt.audit_fingerprint() == first.receipt.audit_fingerprint()

    stored = JsonM5EventRunReceiptStore(receipt_root).load(
        receipt_id=first.receipt.receipt_id
    )
    assert stored is not None
    assert stored.audit_fingerprint() == first.receipt.audit_fingerprint()
    assert stored.state_sha256 == first.receipt.state_sha256


def test_apply_run_request_recovers_from_pre_commit_failure(tmp_path):
    request = _request()
    state_store = JsonM5EventRunStateStore(tmp_path / "state")
    receipt_store = JsonM5EventRunReceiptStore(tmp_path / "receipts")

    with pytest.raises(RuntimeError, match="before the state commit"):
        apply_run_request(
            request=request,
            store=_FailingCommitStore(state_store),
            receipt_store=receipt_store,
        )

    assert state_store.load(state_key=request.stream_id) is None
    assert receipt_store.load(receipt_id="m5-run-missing") is None

    retry = apply_run_request(
        request=request,
        store=state_store,
        receipt_store=receipt_store,
    )

    assert retry.replayed is False
    assert retry.publication is not None
    assert retry.publication.status == M5_RECEIPT_PUBLISHED
    assert retry.receipt.state.revision == 1
    assert len(retry.receipt.state.batch_records) == 1
    assert len(retry.receipt.state.checkpoints.checkpoints()) == 1
    stored = state_store.load(state_key=request.stream_id)
    assert stored is not None
    assert stored.revision == 1
    assert len(stored.batch_records) == 1


def test_apply_run_request_recovers_from_post_commit_failure(tmp_path):
    request = _request()
    state_store = JsonM5EventRunStateStore(tmp_path / "state")
    receipt_store = JsonM5EventRunReceiptStore(tmp_path / "receipts")

    with pytest.raises(RuntimeError, match="after the state commit"):
        apply_run_request(
            request=request,
            store=state_store,
            receipt_store=_FailingPublishStore(receipt_store),
        )

    committed = state_store.load(state_key=request.stream_id)
    assert committed is not None
    assert committed.revision == 1
    assert len(committed.batch_records) == 1

    retry = apply_run_request(
        request=request,
        store=state_store,
        receipt_store=receipt_store,
    )

    assert retry.replayed is True
    assert retry.publication is not None
    assert retry.publication.status == M5_RECEIPT_PUBLISHED
    assert retry.receipt.state.revision == 1
    assert len(retry.receipt.state.batch_records) == 1
    assert len(retry.receipt.state.checkpoints.checkpoints()) == 1
    again = apply_run_request(
        request=request,
        store=state_store,
        receipt_store=receipt_store,
    )
    assert again.publication is not None
    assert again.publication.status == M5_RECEIPT_ALREADY_PUBLISHED
    assert again.receipt.receipt_id == retry.receipt.receipt_id
    assert again.receipt.state.revision == 1


def test_receipt_store_rejects_tampered_artifact(tmp_path):
    request = _request()
    receipt_store = JsonM5EventRunReceiptStore(tmp_path / "receipts")
    result = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(tmp_path / "state"),
        receipt_store=receipt_store,
    )
    assert result.publication is not None
    path = result.publication.path

    payload = json.loads(open(path, encoding="utf-8").read())
    payload["receipt"]["silent_ok"] = not payload["receipt"]["silent_ok"]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(ValueError, match="hash does not match"):
        receipt_store.load(receipt_id=result.receipt.receipt_id)

    payload = json.loads(open(path, encoding="utf-8").read())
    payload["receipt"]["state_sha256"] = "0" * 64
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(ValueError):
        receipt_store.load(receipt_id=result.receipt.receipt_id)


def test_receipt_artifact_rejects_unknown_keys(tmp_path):
    request = _request()
    result = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(tmp_path / "state"),
        receipt_store=None,
    )
    payload = result.receipt.to_artifact_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="keys do not match"):
        M5EventRunReceipt.from_payload(payload)


def test_receipt_store_rejects_foreign_request_binding(tmp_path):
    request = _request()
    receipt_store = JsonM5EventRunReceiptStore(tmp_path / "receipts")
    result = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(tmp_path / "state"),
        receipt_store=receipt_store,
    )
    foreign = _request(watermark_id="synthetic-scan-tampered")

    assert foreign.request_id != request.request_id
    with pytest.raises(ValueError, match="not bound"):
        receipt_store.publish(receipt=result.receipt, request=foreign)


def test_receipt_store_conflicts_on_a_different_batch(tmp_path):
    receipt_store = JsonM5EventRunReceiptStore(tmp_path / "receipts")
    first = apply_run_request(
        request=_request(),
        store=JsonM5EventRunStateStore(tmp_path / "first-state"),
        receipt_store=receipt_store,
    )
    second = apply_run_request(
        request=_request(announcement_id="1225549002"),
        store=JsonM5EventRunStateStore(tmp_path / "second-state"),
        receipt_store=None,
    )

    assert second.receipt.receipt_id == first.receipt.receipt_id
    assert (
        second.receipt.audit_fingerprint()
        != first.receipt.audit_fingerprint()
    )
    with pytest.raises(M5StateStoreConflict):
        receipt_store.publish(
            receipt=second.receipt,
            request=_request(announcement_id="1225549002"),
        )


def test_run_request_schema_is_versioned():
    payload = json.loads(_request().to_json())

    assert payload["schema_version"] == M5_RUN_REQUEST_SCHEMA
    assert payload["action"] == "no_order"
    payload["schema_version"] = "m5-event-run-request-v0"
    with pytest.raises(ValueError, match="Unknown M5 run request schema"):
        M5EventRunRequest.from_payload(payload)
