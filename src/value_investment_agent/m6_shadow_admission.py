"""Guarded promotion of M6 Shadow candidates after explicit signed admission."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .m6_shadow_receipts import _verify_shadow_bundle_contents
from .operations.authorization.trust_root_registry import require_pinned_trust_root


VERSION = "m6-shadow-admission-v1"
PURPOSE = b"M6-SHADOW-ADMISSION\0"
FIELDS = frozenset({
    "action", "admission_id", "authorization_sha256", "scope_manifest_sha256",
    "deployment_sha256", "config_sha256", "intake_head_sha256",
    "intake_head_sequence", "venue", "valid_from", "valid_until",
    "minimum_real_sessions", "minimum_real_events", "reset_policy_sha256",
    "issued_at",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("M6 admission time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def verify_operational_shadow_bundle(
    operational_bundle: Mapping[str, Any],
    operational_trust_root: Mapping[str, Any],
    schedule: Mapping[str, Any],
    cutoff: datetime,
    *,
    required_sessions: int,
    required_events: int,
) -> dict[str, str]:
    """Return countable session hashes only after exact external admission."""
    if set(operational_bundle) != {"candidate_bundle", "admission"}:
        raise ValueError("Operational Shadow bundle schema differs")
    if set(operational_trust_root) != {
        "candidate_trust_root", "admission_public_key", "approved_admission_sha256"
    }:
        raise ValueError("Externally pinned operational Shadow trust root is required")
    require_pinned_trust_root(operational_trust_root)
    candidate = operational_bundle["candidate_bundle"]
    candidate_root = operational_trust_root["candidate_trust_root"]
    # The candidate root is not independently pinned; it is a nested field in
    # the operational root whose fingerprint was just checked against the
    # registry. Re-running the public pin check here would reject correctly
    # admitted bundles whose inner root is intentionally derived.
    verified = _verify_shadow_bundle_contents(
        candidate,
        candidate_root,
        schedule,
        cutoff,
        operational_root=operational_trust_root,
    )
    envelope = operational_bundle["admission"]
    if not isinstance(envelope, Mapping) or set(envelope) != {"version", "payload", "signature"}:
        raise ValueError("M6 admission envelope schema differs")
    payload = envelope["payload"]
    if envelope["version"] != VERSION or not isinstance(payload, Mapping) or set(payload) != FIELDS:
        raise ValueError("M6 admission payload schema differs")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(str(operational_trust_root["admission_public_key"])))
        public_key.verify(bytes.fromhex(str(envelope["signature"])), PURPOSE + _canonical(payload))
    except (TypeError, ValueError, InvalidSignature) as error:
        raise ValueError("M6 admission signature is invalid") from error
    admission_sha = hashlib.sha256(_canonical(envelope)).hexdigest()
    authorization = candidate["authorization"]
    authorization_payload = authorization["payload"]
    authorization_sha = hashlib.sha256(_canonical(authorization)).hexdigest()
    artifact_hashes = {
        name: candidate["authorization_artifacts"][name]["sha256"]
        for name in ("scope_manifest", "deployment_manifest", "runtime_config")
    }
    pinned_head = candidate_root["pinned_intake_head"]
    pinned_at = _time(pinned_head["pinned_at"])
    issued_at = _time(payload["issued_at"])
    valid_from = _time(payload["valid_from"])
    valid_until = _time(payload["valid_until"])
    signer_keys = {
        operational_trust_root["admission_public_key"],
        candidate_root["authorization_public_key"],
        candidate_root["witness_public_key"],
        candidate_root["intake_trust_root"]["intake_public_key"],
        authorization_payload["runtime_public_key"],
    }
    if (
        len(signer_keys) != 5
        or admission_sha != operational_trust_root["approved_admission_sha256"]
        or payload["action"] != "no_order"
        or not payload["admission_id"]
        or payload["authorization_sha256"] != authorization_sha
        or payload["scope_manifest_sha256"] != artifact_hashes["scope_manifest"]
        or payload["deployment_sha256"] != artifact_hashes["deployment_manifest"]
        or payload["config_sha256"] != artifact_hashes["runtime_config"]
        or payload["intake_head_sha256"] != pinned_head["record_sha256"]
        or payload["intake_head_sequence"] != pinned_head["sequence"]
        or payload["venue"] != schedule["venue"]
        or payload["minimum_real_sessions"] != required_sessions
        or payload["minimum_real_events"] != required_events
        or not _SHA256.fullmatch(str(payload["reset_policy_sha256"]))
        or valid_from < _time(authorization_payload["valid_from"])
        or valid_until > _time(authorization_payload["valid_until"])
        or not valid_from <= pinned_at <= issued_at <= valid_until
        or cutoff.astimezone(timezone.utc) > valid_until
        or issued_at > datetime.now(timezone.utc)
    ):
        raise ValueError("M6 admission is not the exact approved operational scope")
    return verified
