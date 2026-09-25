"""Operational admission for one evidence-bound M6 event observation."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .m6_event_observation import (
    SCHEMA as CANDIDATE_SCHEMA,
    verify_event_observation_candidate,
)
from .m6_exchange_sessions import completed_exchange_sessions
from .m6_shadow_admission import verify_operational_shadow_bundle


VERSION = "m6-event-admission-v1"
PURPOSE = b"M6-EVENT-ADMISSION\0"
FIELDS = frozenset({
    "action", "event_admission_id", "event_candidate_sha256",
    "event_id", "session_date", "source_sha256", "source_index_sha256",
    "observation_sha256", "session_receipt_sha256",
    "operational_admission_sha256", "authorization_sha256",
    "intake_head_sha256", "admitted_at",
})
CANDIDATE_FIELDS = frozenset({
    "schema_version", "offline_candidate_valid", "operational_event_proven",
    "verified_real_event_count", "event_id", "session_date", "source_sha256",
    "source_index_sha256", "observation_sha256", "session_receipt_sha256",
    "action",
})


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("M6 event admission time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _require_offline_candidate_contract(candidate: object) -> Mapping[str, Any]:
    """Reject a promoted result even if an admission signer signs its hash."""
    if not isinstance(candidate, Mapping) or set(candidate) != CANDIDATE_FIELDS:
        raise ValueError("M6 event candidate contract schema differs")
    try:
        date.fromisoformat(str(candidate["session_date"]))
    except ValueError as error:
        raise ValueError("M6 event candidate contract session date is invalid") from error
    if (
        candidate["schema_version"] != CANDIDATE_SCHEMA
        or candidate["offline_candidate_valid"] is not True
        or candidate["operational_event_proven"] is not False
        or type(candidate["verified_real_event_count"]) is not int
        or candidate["verified_real_event_count"] != 0
        or candidate["action"] != "no_order"
        or not isinstance(candidate["event_id"], str)
        or not candidate["event_id"]
        or not all(_is_sha256(candidate[field]) for field in (
            "source_sha256", "source_index_sha256", "observation_sha256",
            "session_receipt_sha256",
        ))
    ):
        raise ValueError("M6 event candidate contract is not offline-only")
    return candidate


def verify_operational_event_observation(
    *, candidate_evidence: Mapping[str, Any],
    operational_shadow_bundle: Mapping[str, Any],
    operational_shadow_trust_root: Mapping[str, Any],
    event_admission: Mapping[str, Any],
    approved_event_admission_sha256: str,
    required_sessions: int,
    required_events: int,
) -> dict[str, Any]:
    """Promote one event only when candidate, session and admission all bind."""
    candidate_bundle = operational_shadow_bundle.get("candidate_bundle")
    candidate_root = operational_shadow_trust_root.get("candidate_trust_root")
    if (candidate_evidence.get("shadow_bundle") != candidate_bundle
            or candidate_evidence.get("trust_root") != candidate_root):
        raise ValueError("Event candidate is not bound to the operational Shadow bundle")
    cutoff = candidate_evidence.get("cutoff")
    calendar = candidate_evidence.get("calendar_evidence")
    if not isinstance(cutoff, datetime) or not isinstance(calendar, Mapping):
        raise ValueError("Event candidate calendar evidence is missing")
    schedule = completed_exchange_sessions(
        str(calendar.get("venue")), calendar.get("documents") or [], cutoff)
    operational_sessions = verify_operational_shadow_bundle(
        operational_shadow_bundle, operational_shadow_trust_root, schedule, cutoff,
        required_sessions=required_sessions, required_events=required_events)
    candidate = _require_offline_candidate_contract(
        verify_event_observation_candidate(**candidate_evidence))

    if (not isinstance(event_admission, Mapping)
            or set(event_admission) != {"version", "payload", "signature"}):
        raise ValueError("M6 event admission envelope schema differs")
    payload = event_admission["payload"]
    if (event_admission["version"] != VERSION
            or not isinstance(payload, Mapping) or set(payload) != FIELDS):
        raise ValueError("M6 event admission payload schema differs")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(
            operational_shadow_trust_root["admission_public_key"])))
        public_key.verify(bytes.fromhex(str(event_admission["signature"])),
                          PURPOSE + _canonical(payload))
    except (KeyError, TypeError, ValueError, InvalidSignature) as error:
        raise ValueError("M6 event admission signature is invalid") from error

    shadow_admission = operational_shadow_bundle["admission"]
    authorization = candidate_bundle["authorization"]
    pinned_head = candidate_root["pinned_intake_head"]
    observation = json.loads(candidate_evidence["observation_bytes"])
    admitted_at = _time(payload["admitted_at"])
    valid_until = _time(authorization["payload"]["valid_until"])
    expected = {
        "event_candidate_sha256": _sha(candidate),
        "event_id": candidate["event_id"],
        "session_date": candidate["session_date"],
        "source_sha256": candidate["source_sha256"],
        "source_index_sha256": candidate["source_index_sha256"],
        "observation_sha256": candidate["observation_sha256"],
        "session_receipt_sha256": candidate["session_receipt_sha256"],
        "operational_admission_sha256": _sha(shadow_admission),
        "authorization_sha256": _sha(authorization),
        "intake_head_sha256": pinned_head["record_sha256"],
    }
    if (
        _sha(event_admission) != approved_event_admission_sha256
        or payload["action"] != "no_order"
        or not payload["event_admission_id"]
        or any(payload[key] != value for key, value in expected.items())
        or candidate["session_date"] not in operational_sessions
        or operational_sessions[candidate["session_date"]] != candidate["session_receipt_sha256"]
        or not (_time(observation["observed_at"]) <= admitted_at <= valid_until)
        or admitted_at < _time(pinned_head["pinned_at"])
        or admitted_at > datetime.now(timezone.utc)
    ):
        raise ValueError("M6 event is not the exact approved operational observation")
    return {
        **candidate,
        "schema_version": VERSION,
        "operational_event_proven": True,
        "verified_real_event_count": 1,
        "event_admission_sha256": _sha(event_admission),
    }
