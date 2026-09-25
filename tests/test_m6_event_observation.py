"""Synthetic Shadow signatures never turn M5 research into real M6 event credit."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from value_investment_agent.m6_event_observation import (
    verify_event_observation_candidate,
)
from value_investment_agent.m6_shadow_receipts import VERSION


ROOT = Path(__file__).parents[1]
PDF = ROOT / ("runtime/m5-600519-disclosure-queue-20260924/source/600519/"
              "announcements/2026-07-18/1225431263.pdf")
REVIEWS = ROOT / ("runtime/m5-600519-disclosure-queue-20260924/"
                  "delegated-review-application-20260925/reviews.json")
RECEIPT = ROOT / ("runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/"
                  "m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json")
pytestmark = pytest.mark.skipif(
    not all(path.is_file() for path in (PDF, REVIEWS, RECEIPT)),
    reason="Archived ACTUAL M5 evidence is local and not included in public CI",
)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _public(key):
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def _sign(payload, key, purpose):
    return {"version": VERSION, "payload": payload,
            "signature": key.sign((purpose + "\0").encode() + _bytes(payload)).hex()}


def _fixture(*, mutate=None, valid_from="2026-07-01T00:00:00+08:00"):
    source, reviews, receipt = PDF.read_bytes(), REVIEWS.read_bytes(), RECEIPT.read_bytes()
    decision = next(item for item in json.loads(reviews)[0]["decisions"]
                    if item["announcement_id"] == "1225431263")
    event = next(item["event"] for item in json.loads(receipt)["receipt"]["ingest_results"]
                 if item.get("event", {}).get("event_id") ==
                 "m5-1f43cb646a5884b860d3cd98cdd5ff32")
    auth_key, runtime_key, witness_key = (Ed25519PrivateKey.generate() for _ in range(3))
    authorization = _sign({
        "action": "no_order", "authorization_id": "synthetic-only", "mode": "SHADOW",
        "venue": "SSE", "valid_from": valid_from,
        "valid_until": "2026-09-26T00:00:00+08:00",
        "deployment_sha256": "a" * 64, "config_sha256": "b" * 64,
        "scope_manifest_sha256": "d" * 64, "runtime_public_key": _public(runtime_key),
    }, auth_key, "M6-AUTHORIZATION")
    observation = {
        "schema_version": "m6-shadow-event-observation-v1", "action": "no_order",
        "symbol": "600519", "event_id": event["event_id"],
        "source_event_id": event["source_event_id"],
        "materiality_decision_id": decision["event_decision_id"],
        "source_sha256": _sha(source), "source_url": decision["source_ref"]["source_url"],
        "m5_review_file_sha256": _sha(reviews), "m5_receipt_file_sha256": _sha(receipt),
        "m5_receipt_id": json.loads(receipt)["receipt"]["receipt_id"],
        "m5_state_sha256": json.loads(receipt)["receipt"]["state_sha256"],
        "m6_authorization_sha256": _sha(_bytes(authorization)),
        "m6_run_id": "synthetic-shadow-run", "session_date": "2026-09-25",
        "observed_at": "2026-09-25T15:08:00+08:00",
    }
    if mutate:
        mutate(observation)
    observation_bytes = _bytes(observation)
    session = _sign({
        "action": "no_order", "authorization_sha256": _sha(_bytes(authorization)),
        "mode": "SHADOW", "venue": "SSE", "session_date": "2026-09-25",
        "run_id": "synthetic-shadow-run", "started_at": "2026-09-25T08:00:00+08:00",
        "completed_at": "2026-09-25T15:10:00+08:00", "status": "success",
        "resource_baseline_ok": True, "calendar_sha256": "c" * 64,
        "calendar_source_url": "https://www.sse.com.cn/synthetic-calendar",
        "deployment_sha256": "a" * 64, "config_sha256": "b" * 64,
        "artifact_sha256": _sha(observation_bytes), "previous_receipt_sha256": None,
    }, runtime_key, "M6-SESSION")
    witness = _sign({
        "action": "no_order", "session_receipt_sha256": _sha(_bytes(session)),
        "received_at": "2026-09-25T15:11:00+08:00", "sequence": 1,
        "previous_witness_sha256": None,
    }, witness_key, "M6-WITNESS")
    bundle = {"authorization": authorization,
              "sessions": [{"session": session, "witness": witness}]}
    trust = {"authorization_public_key": _public(auth_key),
             "witness_public_key": _public(witness_key),
             "approved_authorization_sha256": _sha(_bytes(authorization))}
    schedule = {"venue": "SSE", "sessions": [{
        "session_date": "2026-09-24", "sha256": "c" * 64,
        "source_url": "https://www.sse.com.cn/synthetic-calendar",
    }, {
        "session_date": "2026-09-25", "sha256": "c" * 64,
        "source_url": "https://www.sse.com.cn/synthetic-calendar",
    }]}
    return dict(source_bytes=source, materiality_review_bytes=reviews,
                m5_receipt_bytes=receipt, observation_bytes=observation_bytes,
                shadow_bundle=bundle, trust_root=trust, schedule=schedule,
                expected_materiality_review_sha256=_sha(reviews),
                expected_m5_receipt_sha256=_sha(receipt),
                approved_source_hosts=frozenset({"static.cninfo.com.cn"}),
                cutoff=datetime.fromisoformat("2026-09-25T15:30:00+08:00"))


def test_real_historical_m5_event_is_not_a_new_shadow_event():
    with pytest.raises(ValueError, match="retrospective"):
        verify_event_observation_candidate(**_fixture())


@pytest.mark.parametrize("mutate", [
    lambda row: row.update(event_id="m5-wrong"),
    lambda row: row.update(materiality_decision_id="wrong"),
    lambda row: row.update(m5_receipt_file_sha256="f" * 64),
    lambda row: row.update(m6_run_id="replayed-other-run"),
    lambda row: row.update(observed_at="2026-09-25T15:12:00+08:00"),
])
def test_rehashed_mismatched_event_is_rejected(mutate):
    with pytest.raises(ValueError):
        verify_event_observation_candidate(**_fixture(mutate=mutate))


def test_historical_event_before_authorization_is_rejected():
    with pytest.raises(ValueError, match="retrospective"):
        verify_event_observation_candidate(**_fixture(
            valid_from="2026-09-01T00:00:00+08:00"))


def test_source_tamper_and_unpinned_root_are_rejected():
    evidence = _fixture()
    with pytest.raises(ValueError):
        verify_event_observation_candidate(**{**evidence, "source_bytes": b"altered PDF"})
    forged = deepcopy(evidence["trust_root"])
    forged["approved_authorization_sha256"] = "e" * 64
    with pytest.raises(ValueError):
        verify_event_observation_candidate(**{**evidence, "trust_root": forged})


def test_duplicate_observation_key_is_rejected():
    evidence = _fixture()
    duplicate = evidence["observation_bytes"].replace(
        b'"action":"no_order"', b'"action":"no_order","action":"no_order"')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        verify_event_observation_candidate(**{**evidence, "observation_bytes": duplicate})
