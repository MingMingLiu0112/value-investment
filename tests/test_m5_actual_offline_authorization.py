from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json

import pytest

from m5_actual_authorization_fixture import synthetic_actual_receipt
from test_m5_run_request import REVIEWED_AT, RUN_ID
from value_investment_agent.m5_actual_offline_authorization import (
    M5ActualOfflineAuthorization,
    actual_offline_authorization_from_payload,
    verify_m5_actual_approval_receipt,
)
from value_investment_agent.operations.authorization.m5_actual_approval_receipt import (
    PURPOSE,
)
from value_investment_agent.m5_event_core import NAMESPACE_ACTUAL
from value_investment_agent.m5_event_run_state import (
    M5EventRunState,
    m5_event_run_state_from_payload,
)


def _verified():
    fixture = synthetic_actual_receipt()
    capability = verify_m5_actual_approval_receipt(
        fixture["bundle"],
        fixture["trust_root"],
        expected_subject=fixture["subject"],
        at=REVIEWED_AT,
    )
    return fixture, capability


def test_actual_capability_cannot_be_constructed_from_plausible_hex():
    with pytest.raises(TypeError, match="verified approval receipt"):
        M5ActualOfflineAuthorization(
            authorization_id="fabricated",
            review_provenance="USER_CONFIRMED_DELEGATED_REVIEW",
            review_sha256="a" * 64,
            queue_sha256="b" * 64,
            dependency_graph_sha256="c" * 64,
            authorized_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        )


def test_signed_actual_receipt_issues_sealed_no_order_capability():
    fixture, capability = _verified()
    assert capability.as_policy()["action"] == "no_order"
    assert capability.as_policy()["scheduler_enabled"] is False
    assert capability.as_policy()["notification_enabled"] is False
    assert capability.as_policy()["production_database_write"] is False
    capability.verify(
        graph=fixture["graph"],
        events=fixture["batch"].events,
        observed_times=fixture["batch"].observed_times,
        run_id=RUN_ID,
        batch_id=RUN_ID,
        stream_id=RUN_ID,
        symbol=fixture["batch"].symbol,
    )
    restored = actual_offline_authorization_from_payload(capability.as_policy())
    assert restored.as_policy() == capability.as_policy()


def test_actual_state_round_trips_only_with_embedded_signed_capability():
    _, capability = _verified()
    state = M5EventRunState.empty(
        state_key="actual-offline-600887",
        namespace=NAMESPACE_ACTUAL,
        actual_offline_authorization=capability,
    )
    restored = m5_event_run_state_from_payload(state.as_policy())
    assert restored.actual_offline_authorization is not None
    assert restored.actual_offline_authorization.as_policy() == capability.as_policy()


def test_actual_receipt_rejects_forged_approval_hash_and_wrong_receipt():
    fixture, _ = _verified()
    trust = deepcopy(fixture["trust_root"])
    trust["approved_receipt_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="not the approved append-only head"):
        verify_m5_actual_approval_receipt(fixture["bundle"], trust)

    with pytest.raises(ValueError, match="expected capability"):
        verify_m5_actual_approval_receipt(
            fixture["bundle"],
            fixture["trust_root"],
            expected_receipt_sha256="f" * 64,
        )


def test_actual_receipt_rejects_signature_tampering():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    bundle["receipt_chain"][0]["payload"]["authorization_id"] = "tampered"
    with pytest.raises(ValueError, match="signature is invalid"):
        verify_m5_actual_approval_receipt(bundle, fixture["trust_root"])


def test_actual_receipt_rejects_wrong_event_identity():
    fixture, _ = _verified()
    subject = deepcopy(fixture["subject"])
    subject["event_ids"] = ["different-event"]
    with pytest.raises(ValueError, match="event identity"):
        verify_m5_actual_approval_receipt(
            fixture["bundle"],
            fixture["trust_root"],
            expected_subject=subject,
        )


def test_actual_receipt_rejects_modified_reviewed_bytes():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    raw = b'{"changed":true}'
    bundle["reviewed_artifacts"]["reviews"] = {
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    with pytest.raises(ValueError, match="reviewed bytes"):
        verify_m5_actual_approval_receipt(bundle, fixture["trust_root"])


def test_actual_receipt_rejects_modified_bridge_bytes_and_wrong_graph_scope():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    raw = b"[]"
    bundle["reviewed_artifacts"]["bridge_batches"] = {
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    with pytest.raises(ValueError, match="reviewed bytes"):
        verify_m5_actual_approval_receipt(bundle, fixture["trust_root"])

    bundle = deepcopy(fixture["bundle"])
    graph_receipt = json.loads(fixture["graph_receipt_raw"])
    graph_receipt["symbol"] = "000001"
    raw = json.dumps(
        graph_receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    bundle["reviewed_artifacts"]["graph_receipt"] = {
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    with pytest.raises(ValueError, match="reviewed bytes"):
        verify_m5_actual_approval_receipt(bundle, fixture["trust_root"])


def test_actual_receipt_rejects_replayed_or_duplicate_chain():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    trust = deepcopy(fixture["trust_root"])
    first = bundle["receipt_chain"][0]
    first_hash = hashlib.sha256(
        json.dumps(
            first,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    replayed_payload = deepcopy(first["payload"])
    replayed_payload["sequence"] = 2
    replayed_payload["previous_receipt_sha256"] = first_hash
    replay = {
        "version": first["version"],
        "payload": replayed_payload,
        "signature": fixture["private_key"].sign(
            PURPOSE
            + json.dumps(
                replayed_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hex(),
    }
    bundle["receipt_chain"].append(replay)
    trust["approved_sequence"] = 2
    trust["approved_receipt_sha256"] = hashlib.sha256(
        json.dumps(
            replay,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    trust["approved_previous_receipt_sha256"] = first_hash
    with pytest.raises(ValueError, match="replayed approval"):
        verify_m5_actual_approval_receipt(bundle, trust)


def test_actual_receipt_rejects_duplicate_approval_under_new_authorization_id():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    trust = deepcopy(fixture["trust_root"])
    first = bundle["receipt_chain"][0]
    first_hash = hashlib.sha256(
        json.dumps(
            first,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    duplicate_payload = deepcopy(first["payload"])
    duplicate_payload["authorization_id"] = "second-authorization"
    duplicate_payload["sequence"] = 2
    duplicate_payload["previous_receipt_sha256"] = first_hash
    duplicate = {
        "version": first["version"],
        "payload": duplicate_payload,
        "signature": fixture["private_key"].sign(
            PURPOSE
            + json.dumps(
                duplicate_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hex(),
    }
    bundle["receipt_chain"].append(duplicate)
    trust["approved_sequence"] = 2
    trust["approved_receipt_sha256"] = hashlib.sha256(
        json.dumps(
            duplicate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    trust["approved_previous_receipt_sha256"] = first_hash
    with pytest.raises(ValueError, match="replayed approval"):
        verify_m5_actual_approval_receipt(bundle, trust)


def test_actual_capability_cannot_be_repurposed_to_another_event_or_run():
    fixture, capability = _verified()
    with pytest.raises(ValueError, match="run_id"):
        capability.verify(run_id="different-run")
    with pytest.raises(ValueError, match="event identity"):
        capability.verify(events=(), observed_times=())


def _resign_receipt(
    fixture: dict,
    payload: dict,
) -> tuple[dict, dict]:
    receipt = deepcopy(fixture["bundle"]["receipt_chain"][0])
    receipt["payload"] = payload
    receipt["signature"] = fixture["private_key"].sign(
        PURPOSE
        + json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hex()
    receipt_sha256 = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    trust_root = deepcopy(fixture["trust_root"])
    trust_root["approved_receipt_sha256"] = receipt_sha256
    return receipt, trust_root


def test_actual_receipt_requires_signed_valid_until():
    fixture, _ = _verified()
    payload = deepcopy(fixture["bundle"]["receipt_chain"][0]["payload"])
    payload.pop("valid_until")
    receipt, trust_root = _resign_receipt(fixture, payload)
    bundle = deepcopy(fixture["bundle"])
    bundle["receipt_chain"] = [receipt]

    with pytest.raises(ValueError, match="payload schema differs"):
        verify_m5_actual_approval_receipt(
            bundle,
            trust_root,
            expected_subject=fixture["subject"],
            at=REVIEWED_AT,
        )


def test_actual_receipt_rejects_inverted_validity_window():
    fixture, _ = _verified()
    payload = deepcopy(fixture["bundle"]["receipt_chain"][0]["payload"])
    payload["valid_until"] = payload["authorized_at"]
    receipt, trust_root = _resign_receipt(fixture, payload)
    bundle = deepcopy(fixture["bundle"])
    bundle["receipt_chain"] = [receipt]

    with pytest.raises(ValueError, match="validity window is invalid"):
        verify_m5_actual_approval_receipt(
            bundle,
            trust_root,
            expected_subject=fixture["subject"],
            at=REVIEWED_AT,
        )


def test_actual_receipt_enforces_inclusive_validity_boundaries():
    fixture, _ = _verified()
    payload = fixture["bundle"]["receipt_chain"][0]["payload"]
    authorized_at = datetime.fromisoformat(payload["authorized_at"])
    valid_until = datetime.fromisoformat(payload["valid_until"])

    with pytest.raises(ValueError, match="before its approval"):
        verify_m5_actual_approval_receipt(
            fixture["bundle"],
            fixture["trust_root"],
            expected_subject=fixture["subject"],
            at=authorized_at - timedelta(microseconds=1),
        )
    at_start = verify_m5_actual_approval_receipt(
        fixture["bundle"],
        fixture["trust_root"],
        expected_subject=fixture["subject"],
        at=authorized_at,
    )
    at_end = verify_m5_actual_approval_receipt(
        fixture["bundle"],
        fixture["trust_root"],
        expected_subject=fixture["subject"],
        at=valid_until,
    )
    assert at_start.valid_until == at_end.valid_until == valid_until

    with pytest.raises(ValueError, match="expired"):
        verify_m5_actual_approval_receipt(
            fixture["bundle"],
            fixture["trust_root"],
            expected_subject=fixture["subject"],
            at=valid_until + timedelta(microseconds=1),
        )


def test_actual_receipt_rejects_tampered_valid_until():
    fixture, _ = _verified()
    bundle = deepcopy(fixture["bundle"])
    bundle["receipt_chain"][0]["payload"]["valid_until"] = (
        datetime.fromisoformat(
            bundle["receipt_chain"][0]["payload"]["valid_until"]
        )
        + timedelta(days=1)
    ).isoformat()

    with pytest.raises(ValueError, match="signature is invalid"):
        verify_m5_actual_approval_receipt(
            bundle,
            fixture["trust_root"],
            expected_subject=fixture["subject"],
            at=REVIEWED_AT,
        )


def test_actual_capability_cannot_be_replayed_after_expiry():
    fixture, capability = _verified()
    valid_until = datetime.fromisoformat(
        fixture["bundle"]["receipt_chain"][0]["payload"]["valid_until"]
    )
    after_expiry = valid_until + timedelta(microseconds=1)

    with pytest.raises(ValueError, match="expired"):
        capability.verify(at=after_expiry)
    with pytest.raises(ValueError, match="expired"):
        actual_offline_authorization_from_payload(
            capability.as_policy(),
            at=after_expiry,
        )
