"""Replay the archived 600519 ACTUAL request in isolated durable stores."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from value_investment_agent.m5_event_run import apply_run_request, m5_event_run_receipt_from_payload
from value_investment_agent.m5_event_state_store import (
    JsonM5EventRunReceiptStore,
    JsonM5EventRunStateStore,
    M5_RECEIPT_ALREADY_PUBLISHED,
    M5_RECEIPT_PUBLISHED,
)
from value_investment_agent.m5_run_request import M5EventRunRequest


ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", Path(__file__).resolve().parents[1]))
BASE = ROOT / "runtime/m5-600519-disclosure-rescan-20260925"
REQUEST = BASE / "actual-valid-application-20260925/request.json"
RECEIPT = BASE / "actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"


def test_real_actual_request_cold_replay_matches_archived_receipt(tmp_path: Path):
    if not REQUEST.is_file() or not RECEIPT.is_file():
        pytest.skip("Archived 600519 ACTUAL request and receipt are unavailable")
    request = M5EventRunRequest.from_payload(json.loads(REQUEST.read_text(encoding="utf-8")))
    archived = m5_event_run_receipt_from_payload(
        json.loads(RECEIPT.read_text(encoding="utf-8"))["receipt"]
    )
    state_root = tmp_path / "state"
    receipt_root = tmp_path / "receipts"

    first = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(state_root),
        receipt_store=JsonM5EventRunReceiptStore(receipt_root),
    )
    assert first.replayed is False
    assert first.publication.status == M5_RECEIPT_PUBLISHED
    assert first.receipt.audit_fingerprint() == archived.audit_fingerprint()
    assert len(first.receipt.active_events) == 2

    second = apply_run_request(
        request=M5EventRunRequest.from_payload(json.loads(REQUEST.read_text(encoding="utf-8"))),
        store=JsonM5EventRunStateStore(state_root),
        receipt_store=JsonM5EventRunReceiptStore(receipt_root),
    )
    assert second.replayed is True
    assert second.publication.status == M5_RECEIPT_ALREADY_PUBLISHED
    assert second.receipt.audit_fingerprint() == first.receipt.audit_fingerprint()
    assert second.receipt.state_sha256 == first.receipt.state_sha256
