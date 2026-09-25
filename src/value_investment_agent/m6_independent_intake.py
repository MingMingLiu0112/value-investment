"""Fail-closed verifier for externally anchored, append-only M6 intake records."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


VERSION = "m6-independent-intake-v1"
PURPOSE = b"M6-INDEPENDENT-INTAKE\0"
FIELDS = frozenset({
    "action", "intake_id", "key_epoch", "deployment_sha256",
    "receipt_sha256", "received_at", "sequence", "previous_record_sha256",
})


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("M6 intake timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def verify_independent_intake_chain(
    records: Sequence[Mapping[str, Any]],
    trust_root: Mapping[str, Any],
    pinned_head: Mapping[str, Any],
    *,
    cutoff: datetime,
) -> dict[str, str]:
    """Verify raw receipt bytes and a separately pinned append-only chain head."""
    if set(trust_root) != {
        "intake_id", "intake_public_key", "key_epoch", "deployment_sha256"
    }:
        raise ValueError("Externally configured M6 intake trust root is required")
    if set(pinned_head) != {"record_sha256", "sequence", "pinned_at"}:
        raise ValueError("Externally pinned M6 intake head is required")
    if not records:
        raise ValueError("M6 intake chain cannot be empty")
    if cutoff.tzinfo is None:
        raise ValueError("M6 intake cutoff must be timezone-aware")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(trust_root["intake_public_key"])))
    except (TypeError, ValueError) as error:
        raise ValueError("M6 intake public key is invalid") from error
    previous_hash = None
    previous_received = None
    verified: dict[str, str] = {}
    for expected_sequence, item in enumerate(records, 1):
        if set(item) != {"receipt_raw_base64", "record"}:
            raise ValueError("M6 intake evidence item schema differs")
        envelope = item["record"]
        if not isinstance(envelope, Mapping) or set(envelope) != {"version", "payload", "signature"}:
            raise ValueError("M6 intake signed envelope schema differs")
        payload = envelope["payload"]
        if envelope["version"] != VERSION or not isinstance(payload, Mapping) or set(payload) != FIELDS:
            raise ValueError("M6 intake payload schema differs")
        try:
            receipt_raw = base64.b64decode(item["receipt_raw_base64"], validate=True)
            signature = bytes.fromhex(str(envelope["signature"]))
            public_key.verify(signature, PURPOSE + _canonical(payload))
        except (TypeError, ValueError, InvalidSignature) as error:
            raise ValueError("M6 intake bytes or signature are invalid") from error
        receipt_sha = hashlib.sha256(receipt_raw).hexdigest()
        record_sha = hashlib.sha256(_canonical(envelope)).hexdigest()
        received = _time(payload["received_at"])
        if (
            not receipt_raw
            or payload["action"] != "no_order"
            or payload["intake_id"] != trust_root["intake_id"]
            or payload["key_epoch"] != trust_root["key_epoch"]
            or payload["deployment_sha256"] != trust_root["deployment_sha256"]
            or payload["receipt_sha256"] != receipt_sha
            or type(payload["sequence"]) is not int
            or payload["sequence"] != expected_sequence
            or payload["previous_record_sha256"] != previous_hash
            or received > cutoff.astimezone(timezone.utc)
            or received > datetime.now(timezone.utc)
            or (previous_received is not None and received <= previous_received)
        ):
            raise ValueError("M6 intake chain scope, order or time differs")
        if receipt_sha in verified:
            raise ValueError("M6 intake chain repeats receipt bytes")
        verified[receipt_sha] = record_sha
        previous_hash = record_sha
        previous_received = received
    pinned_at = _time(pinned_head["pinned_at"])
    if (
        type(pinned_head["sequence"]) is not int
        or pinned_head["sequence"] != len(records)
        or pinned_head["record_sha256"] != previous_hash
        or pinned_at < previous_received
        or pinned_at > cutoff.astimezone(timezone.utc) + timedelta(minutes=5)
        or pinned_at > datetime.now(timezone.utc)
    ):
        raise ValueError("M6 intake chain does not match the externally pinned head")
    return verified
