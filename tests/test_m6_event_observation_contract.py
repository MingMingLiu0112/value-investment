"""Portable synthetic tests for the M6 event lineage boundary."""
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace

import pytest

from value_investment_agent import m6_event_observation as observation


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _fixture(monkeypatch, *, published_at="2026-09-25T09:00:00+08:00"):
    source = b"%PDF-synthetic-source"
    review_payload = {"synthetic_review": True}
    review_bytes = _bytes([review_payload])
    receipt_bytes = _bytes({"synthetic_receipt": True})
    decision = SimpleNamespace(
        event_decision_id="decision-1", human_decision="MATERIAL_REQUIRES_RECALCULATION",
        reviewed_at=datetime.fromisoformat("2026-09-25T09:30:00+08:00"),
        published_at=datetime.fromisoformat(published_at), symbol="600519",
        source_sha256=_sha(source), source_ref={
            "id": "source-1", "source_status": "SOURCE_ARCHIVED",
            "source_url": "https://example.test/a.pdf"},
    )
    event = SimpleNamespace(event_id="m5-event-1", symbol="600519",
                            source_event_id="materiality-review:decision-1",
                            current_state={"source_sha256": _sha(source),
                                           "source_ref_id": "source-1",
                                           "source_ref_sha256": _sha(source)})
    review = SimpleNamespace(decisions=(decision,), action="no_order",
                             as_policy=lambda: review_payload)
    receipt = SimpleNamespace(namespace="ACTUAL", action="no_order",
                              active_events=(event,), receipt_id="m5-receipt-1",
                              state_sha256="a" * 64,
                              ingest_results=(SimpleNamespace(event=event, status="ACCEPTED"),),
                              checkpoint=SimpleNamespace(ingested_event_ids=(event.event_id,)),
                              generated_at=datetime.fromisoformat(
                                  "2026-09-25T10:00:00+08:00"))
    monkeypatch.setattr(observation, "event_materiality_review_from_payload",
                        lambda _: review)
    monkeypatch.setattr(observation.M5EventRunReceipt, "from_payload",
                        lambda _: receipt)
    monkeypatch.setattr(observation, "verify_shadow_bundle",
                        lambda *args: {"2026-09-25": "c" * 64})
    auth = {"payload": {"valid_from": "2026-09-25T08:00:00+08:00"}}
    row = {
        "schema_version": observation.SCHEMA, "action": "no_order", "symbol": "600519",
        "event_id": event.event_id, "source_event_id": event.source_event_id,
        "materiality_decision_id": decision.event_decision_id,
        "source_sha256": _sha(source), "source_url": decision.source_ref["source_url"],
        "m5_review_file_sha256": _sha(review_bytes),
        "m5_receipt_file_sha256": _sha(receipt_bytes),
        "m5_receipt_id": receipt.receipt_id, "m5_state_sha256": receipt.state_sha256,
        "m6_authorization_sha256": observation._canonical_sha(auth),
        "m6_run_id": "shadow-1", "session_date": "2026-09-25",
        "observed_at": "2026-09-25T15:08:00+08:00",
    }
    raw = _bytes(row)
    session = {"payload": {
        "run_id": "shadow-1", "session_date": "2026-09-25",
        "artifact_sha256": _sha(raw),
        "started_at": "2026-09-25T09:00:00+08:00",
        "completed_at": "2026-09-25T15:10:00+08:00",
    }}
    evidence = dict(source_bytes=source, materiality_review_bytes=review_bytes,
                    m5_receipt_bytes=receipt_bytes, observation_bytes=raw,
                    shadow_bundle={"authorization": auth,
                                   "sessions": [{"session": session}]},
                    trust_root={}, schedule={"sessions": [
                        {"session_date": "2026-09-24"},
                        {"session_date": "2026-09-25"},
                    ]},
                    expected_materiality_review_sha256=_sha(review_bytes),
                    expected_m5_receipt_sha256=_sha(receipt_bytes),
                    approved_source_hosts=frozenset({"example.test"}),
                    cutoff=datetime.fromisoformat("2026-09-25T15:30:00+08:00"))
    return evidence, row


def _replace_row(evidence, row):
    updated = dict(evidence)
    updated["observation_bytes"] = _bytes(row)
    updated["shadow_bundle"] = json.loads(json.dumps(evidence["shadow_bundle"]))
    updated["shadow_bundle"]["sessions"][0]["session"]["payload"][
        "artifact_sha256"] = _sha(updated["observation_bytes"])
    return updated


def test_lineage_candidate_never_grants_operational_credit(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    result = observation.verify_event_observation_candidate(**evidence)
    assert result["offline_candidate_valid"] is True
    assert result["operational_event_proven"] is False
    assert result["verified_real_event_count"] == 0
    assert result["action"] == "no_order"


@pytest.mark.parametrize("field,value", [
    ("event_id", "other-event"),
    ("source_event_id", "materiality-review:other"),
    ("materiality_decision_id", "other-decision"),
    ("m5_receipt_file_sha256", "f" * 64),
    ("m6_run_id", "other-run"),
    ("observed_at", "2026-09-25T15:12:00+08:00"),
])
def test_fully_rehashed_id_run_or_time_mismatch_fails(monkeypatch, field, value):
    evidence, row = _fixture(monkeypatch)
    row[field] = value
    with pytest.raises(ValueError):
        observation.verify_event_observation_candidate(**_replace_row(evidence, row))


def test_source_bytes_and_historical_publication_fail(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError):
        observation.verify_event_observation_candidate(**{
            **evidence, "source_bytes": b"%PDF-swapped"})
    old, _ = _fixture(monkeypatch, published_at="2026-07-18T00:00:00+08:00")
    with pytest.raises(ValueError, match="retrospective"):
        observation.verify_event_observation_candidate(**old)


def test_external_pins_and_source_host_are_required(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError, match="expected hashes"):
        observation.verify_event_observation_candidate(**{
            **evidence, "expected_m5_receipt_sha256": "f" * 64})
    with pytest.raises(ValueError, match="lineage"):
        observation.verify_event_observation_candidate(**{
            **evidence, "approved_source_hosts": frozenset({"other.test"})})


def test_missing_prior_session_cannot_define_arrival_window(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError, match="Prior official session"):
        observation.verify_event_observation_candidate(**{
            **evidence, "schedule": {"sessions": [{"session_date": "2026-09-25"}]}})
