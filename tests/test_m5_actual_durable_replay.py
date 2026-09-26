"""Replay the archived 600519 ACTUAL request in isolated durable stores."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from value_investment_agent.m5_event_run import (
    apply_run_request,
    m5_event_run_receipt_from_payload,
    run_event_batch,
    run_event_batch_persisted,
)
from value_investment_agent.m5_event_state_store import (
    JsonM5EventRunReceiptStore,
    JsonM5EventRunStateStore,
)
from value_investment_agent.m5_run_request import M5EventRunRequest


ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", Path(__file__).resolve().parents[1]))
BASE = ROOT / "runtime/m5-600519-disclosure-rescan-20260925"
REQUEST = BASE / "actual-valid-application-20260925/request.json"
RECEIPT = BASE / "actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"


def test_legacy_actual_request_requires_explicit_read_only_replay():
    if not REQUEST.is_file():
        pytest.skip("Archived 600519 ACTUAL request is unavailable")
    with pytest.raises(ValueError, match="read-only"):
        M5EventRunRequest.from_payload(
            json.loads(REQUEST.read_text(encoding="utf-8"))
        )


def test_legacy_actual_authorization_cannot_create_a_new_run(tmp_path: Path):
    if not REQUEST.is_file() or not RECEIPT.is_file():
        pytest.skip("Archived 600519 ACTUAL request and receipt are unavailable")
    request = M5EventRunRequest.from_payload(
        json.loads(REQUEST.read_text(encoding="utf-8")),
        allow_legacy_read_only=True,
    )
    with pytest.raises(ValueError, match="read-only replay only"):
        apply_run_request(
            request=request,
            store=JsonM5EventRunStateStore(
                tmp_path / "empty-state",
                allow_legacy_read_only=True,
            ),
            receipt_store=JsonM5EventRunReceiptStore(
                tmp_path / "empty-receipts",
                allow_legacy_read_only=True,
            ),
            allow_legacy_read_only=True,
        )
    assert not list((tmp_path / "empty-receipts").glob("*.json"))
    assert not list((tmp_path / "empty-state").glob("*.json"))


def test_legacy_authorization_cannot_bypass_read_only_runner_gate(tmp_path: Path):
    if not REQUEST.is_file() or not RECEIPT.is_file():
        pytest.skip("Archived 600519 ACTUAL request and receipt are unavailable")
    request = M5EventRunRequest.from_payload(
        json.loads(REQUEST.read_text(encoding="utf-8")),
        allow_legacy_read_only=True,
    )

    with pytest.raises(ValueError, match="read-only"):
        run_event_batch(
            events=request.events,
            observed_times=request.observed_times,
            watermark=request.watermark,
            graph=request.dependency_graph,
            run_id=request.run_id,
            generated_at=request.generated_at,
            namespace=request.namespace,
            batch_id=request.batch_id,
            actual_offline_authorization=request.actual_offline_authorization,
        )
    with pytest.raises(ValueError, match="read-only"):
        run_event_batch_persisted(
            events=request.events,
            observed_times=request.observed_times,
            watermark=request.watermark,
            graph=request.dependency_graph,
            run_id=request.run_id,
            generated_at=request.generated_at,
            store=JsonM5EventRunStateStore(
                tmp_path / "state",
                allow_legacy_read_only=True,
            ),
            namespace=request.namespace,
            batch_id=request.batch_id,
            actual_offline_authorization=request.actual_offline_authorization,
        )
    assert not list((tmp_path / "state").glob("*.json"))


def test_real_actual_request_replay_matches_archived_receipt(tmp_path: Path):
    if not REQUEST.is_file() or not RECEIPT.is_file():
        pytest.skip("Archived 600519 ACTUAL request and receipt are unavailable")
    archived = m5_event_run_receipt_from_payload(
        json.loads(RECEIPT.read_text(encoding="utf-8"))["receipt"],
        allow_legacy_read_only=True,
    )
    state_root = tmp_path / "state"
    receipt_root = tmp_path / "receipts"
    store = JsonM5EventRunStateStore(
        state_root,
        allow_legacy_read_only=True,
    )
    store.commit(
        expected_revision=0,
        expected_sha256=None,
        state=archived.state,
    )

    request = M5EventRunRequest.from_payload(
        json.loads(REQUEST.read_text(encoding="utf-8")),
        allow_legacy_read_only=True,
    )
    receipt_store = JsonM5EventRunReceiptStore(
        receipt_root,
        allow_legacy_read_only=True,
    )
    receipt_store.publish(receipt=archived, request=request)

    replayed = apply_run_request(
        request=request,
        store=store,
        receipt_store=receipt_store,
        allow_legacy_read_only=True,
    )
    assert replayed.replayed is archived.idempotent_noop
    assert replayed.receipt.audit_fingerprint() == archived.audit_fingerprint()
    assert len(replayed.receipt.active_events) == 2

    second = apply_run_request(
        request=M5EventRunRequest.from_payload(
            json.loads(REQUEST.read_text(encoding="utf-8")),
            allow_legacy_read_only=True,
        ),
        store=JsonM5EventRunStateStore(
            state_root,
            allow_legacy_read_only=True,
        ),
        receipt_store=JsonM5EventRunReceiptStore(
            receipt_root,
            allow_legacy_read_only=True,
        ),
        allow_legacy_read_only=True,
    )
    assert second.replayed is archived.idempotent_noop
    assert second.receipt.audit_fingerprint() == archived.audit_fingerprint()
    assert second.receipt.state_sha256 == archived.state_sha256
