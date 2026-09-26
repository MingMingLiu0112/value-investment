from __future__ import annotations

from datetime import datetime
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from test_m6_shadow_receipts import _bytes, _config, _fixture, _hash
from authorization_trust_registry_fixture import pin_test_trust_root
from value_investment_agent import m6_exchange_sessions as exchange
from value_investment_agent.m6_operational_readiness import assess_session_ledger
from value_investment_agent.m6_shadow_admission import (
    PURPOSE, VERSION, verify_operational_shadow_bundle,
)


def _admitted():
    candidate, candidate_root, calendar, schedule, records, _ = _fixture()
    key = Ed25519PrivateKey.generate()
    payload = {
        "action": "no_order", "admission_id": "synthetic-admission",
        "authorization_sha256": _hash(candidate["authorization"]),
        "scope_manifest_sha256": candidate["authorization_artifacts"]["scope_manifest"]["sha256"],
        "deployment_sha256": candidate["authorization_artifacts"]["deployment_manifest"]["sha256"],
        "config_sha256": candidate["authorization_artifacts"]["runtime_config"]["sha256"],
        "intake_head_sha256": candidate_root["pinned_intake_head"]["record_sha256"],
        "intake_head_sequence": candidate_root["pinned_intake_head"]["sequence"],
        "venue": "SSE", "valid_from": "2026-09-01T00:00:00+00:00",
        "valid_until": "2026-09-25T00:00:00+00:00",
        "minimum_real_sessions": 2, "minimum_real_events": 1,
        "reset_policy_sha256": hashlib.sha256(b"synthetic-reset-policy").hexdigest(),
        "issued_at": "2026-09-24T15:13:30+08:00",
    }
    envelope = {"version": VERSION, "payload": payload,
                "signature": key.sign(PURPOSE + _bytes(payload)).hex()}
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    root = {"candidate_trust_root": candidate_root, "admission_public_key": public,
            "approved_admission_sha256": _hash(envelope)}
    pin_test_trust_root(root)
    bundle = {"candidate_bundle": candidate, "admission": envelope}
    cutoff = datetime.fromisoformat(calendar["observation_cutoff"])
    return bundle, root, schedule, cutoff, records


def test_exact_external_admission_promotes_only_verified_candidate_sessions():
    bundle, root, schedule, cutoff, _ = _admitted()
    result = verify_operational_shadow_bundle(
        bundle, root, schedule, cutoff, required_sessions=2, required_events=1)
    assert len(result) == 2


def test_operational_ledger_counts_admitted_sessions_but_not_unverified_events(monkeypatch):
    bundle, root, _, _, records = _admitted()
    _, _, calendar, _, _, _ = _fixture()
    monkeypatch.setattr(exchange, "refetch_official_calendar", lambda _: {
        "source_sha256": [calendar["documents"][0]["sha256"]],
        "verified_at": "2026-09-24T08:20:00+00:00",
    })
    result = assess_session_ledger(
        _config(), records, calendar_evidence=calendar, verify_live_calendar=True,
        operational_shadow_bundle=bundle,
        operational_shadow_trust_root=root,
    )
    assert result["evidence"]["verified_actual_sessions"] == 2
    assert result["evidence"]["latest_streak"] == 2
    assert result["evidence"]["real_events"] == 0
    assert result["status"] == "NOT_STARTED"


@pytest.mark.parametrize("field", [
    "authorization_sha256", "scope_manifest_sha256", "deployment_sha256",
    "config_sha256", "intake_head_sha256", "minimum_real_sessions",
    "minimum_real_events", "reset_policy_sha256",
])
def test_admission_fails_closed_for_any_scope_change(field):
    bundle, root, schedule, cutoff, _ = _admitted()
    bundle["admission"]["payload"][field] = "f" * 64 if "sha256" in field else 999
    with pytest.raises(ValueError):
        verify_operational_shadow_bundle(
            bundle, root, schedule, cutoff, required_sessions=2, required_events=1)
