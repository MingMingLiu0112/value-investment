from __future__ import annotations

from datetime import datetime
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from test_m6_shadow_admission import _admitted
from test_m6_shadow_receipts import _config, _fixture as _shadow_fixture
from value_investment_agent import m6_event_admission as admission
from value_investment_agent import m6_exchange_sessions as exchange
from value_investment_agent.m6_operational_readiness import assess_session_ledger


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _fixture(monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    authorization = {"version": "auth", "payload": {
        "valid_until": "2026-09-25T00:00:00+00:00"}, "signature": "a"}
    shadow_admission = {"version": "shadow", "payload": {}, "signature": "b"}
    candidate_bundle = {"authorization": authorization}
    candidate_root = {"pinned_intake_head": {
        "record_sha256": "1" * 64, "pinned_at": "2026-09-24T15:12:00+08:00"}}
    operational_bundle = {
        "candidate_bundle": candidate_bundle, "admission": shadow_admission}
    operational_root = {
        "candidate_trust_root": candidate_root, "admission_public_key": public}
    result = {
        "schema_version": "m6-shadow-event-observation-v1",
        "offline_candidate_valid": True, "operational_event_proven": False,
        "verified_real_event_count": 0, "event_id": "event-1",
        "session_date": "2026-09-24", "source_sha256": "2" * 64,
        "source_index_sha256": "3" * 64, "observation_sha256": "4" * 64,
        "session_receipt_sha256": "5" * 64, "action": "no_order",
    }
    observation = {"observed_at": "2026-09-24T15:08:00+08:00"}
    candidate_evidence = {
        "shadow_bundle": candidate_bundle, "trust_root": candidate_root,
        "cutoff": datetime.fromisoformat("2026-09-24T15:30:00+08:00"),
        "calendar_evidence": {"venue": "SSE", "documents": []},
        "observation_bytes": _bytes(observation),
    }
    monkeypatch.setattr(admission, "completed_exchange_sessions",
                        lambda *args: {"venue": "SSE", "sessions": []})
    monkeypatch.setattr(admission, "verify_operational_shadow_bundle",
                        lambda *args, **kwargs: {"2026-09-24": "5" * 64})
    monkeypatch.setattr(admission, "verify_event_observation_candidate",
                        lambda **kwargs: result)
    payload = {
        "action": "no_order", "event_admission_id": "event-admission-1",
        "event_candidate_sha256": _sha(result), "event_id": "event-1",
        "session_date": "2026-09-24", "source_sha256": "2" * 64,
        "source_index_sha256": "3" * 64, "observation_sha256": "4" * 64,
        "session_receipt_sha256": "5" * 64,
        "operational_admission_sha256": _sha(shadow_admission),
        "authorization_sha256": _sha(authorization),
        "intake_head_sha256": "1" * 64,
        "admitted_at": "2026-09-24T15:13:00+08:00",
    }
    envelope = {"version": admission.VERSION, "payload": payload,
                "signature": key.sign(admission.PURPOSE + _bytes(payload)).hex()}
    return candidate_evidence, operational_bundle, operational_root, envelope, key


def test_exact_event_admission_grants_one_operational_event(monkeypatch):
    candidate, bundle, root, envelope, _ = _fixture(monkeypatch)
    result = admission.verify_operational_event_observation(
        candidate_evidence=candidate, operational_shadow_bundle=bundle,
        operational_shadow_trust_root=root, event_admission=envelope,
        approved_event_admission_sha256=_sha(envelope),
        required_sessions=20, required_events=1)
    assert result["operational_event_proven"] is True
    assert result["verified_real_event_count"] == 1
    assert result["action"] == "no_order"


@pytest.mark.parametrize("field", [
    "event_candidate_sha256", "event_id", "session_date", "source_sha256",
    "source_index_sha256", "observation_sha256", "session_receipt_sha256",
    "operational_admission_sha256", "authorization_sha256", "intake_head_sha256",
])
def test_event_admission_fails_closed_when_any_binding_changes(monkeypatch, field):
    candidate, bundle, root, envelope, key = _fixture(monkeypatch)
    envelope["payload"][field] = "f" * 64
    envelope["signature"] = key.sign(
        admission.PURPOSE + _bytes(envelope["payload"])).hex()
    with pytest.raises(ValueError):
        admission.verify_operational_event_observation(
            candidate_evidence=candidate, operational_shadow_bundle=bundle,
            operational_shadow_trust_root=root, event_admission=envelope,
            approved_event_admission_sha256=_sha(envelope),
            required_sessions=20, required_events=1)


def test_ledger_counts_only_verified_operational_event(monkeypatch):
    bundle, root, _, _, records = _admitted()
    _, _, calendar, _, _, _ = _shadow_fixture()
    records[-1]["real_event_materialized"] = True
    monkeypatch.setattr(exchange, "refetch_official_calendar", lambda _: {
        "source_sha256": [calendar["documents"][0]["sha256"]],
        "verified_at": "2026-09-24T08:20:00+00:00",
    })
    import value_investment_agent.m6_event_admission as event_module
    monkeypatch.setattr(event_module, "verify_operational_event_observation",
                        lambda **kwargs: {
                            "event_id": "event-1",
                            "session_date": records[-1]["session_date"],
                            "session_receipt_sha256": records[-1]["session_receipt_sha256"],
                        })
    event_evidence = [{
        "candidate_evidence": {}, "event_admission": {},
        "approved_event_admission_sha256": "a" * 64,
    }]
    result = assess_session_ledger(
        _config(), records, calendar_evidence=calendar, verify_live_calendar=True,
        operational_shadow_bundle=bundle, operational_shadow_trust_root=root,
        operational_event_evidence=event_evidence)
    assert result["evidence"]["real_events"] == 1
    assert result["evidence"]["verified_event_ids"] == ["event-1"]
