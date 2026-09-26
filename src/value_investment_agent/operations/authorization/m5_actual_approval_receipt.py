"""Signed, append-only approval receipts for offline M5 ACTUAL runs.

The receipt bundle is deliberately self-contained: it carries the exact
reviewed artifacts and the hash-linked approval chain.  The trust root is a
separate externally pinned object.  A receipt is not an execution permission;
it only lets an ACTUAL offline run consume the reviewed evidence it binds.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .trust_root_registry import require_pinned_trust_root


RECEIPT_VERSION_V1 = "m5-actual-approval-receipt-v1"
RECEIPT_VERSION = "m5-actual-approval-receipt-v2"
BUNDLE_VERSION = "m5-actual-approval-receipt-bundle-v2"
TRUST_ROOT_VERSION = "m5-actual-approval-trust-root-v1"
AUTHORIZATION_SCHEMA_VERSION = "m5-actual-offline-authorization-v3"
LEGACY_AUTHORIZATION_SCHEMA_VERSION = "m5-actual-offline-authorization-v1"
PURPOSE = b"M5-ACTUAL-APPROVAL\0"

USER_CONFIRMED_DELEGATED_REVIEW = "USER_CONFIRMED_DELEGATED_REVIEW"
ARTIFACT_NAMES = frozenset(
    {
        "reviews",
        "bridge_batches",
        "current_queue",
        "reconciliation",
        "graph_receipt",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "action",
        "authorization_id",
        "review_provenance",
        "authorized_at",
        "valid_until",
        "sequence",
        "previous_receipt_sha256",
        "reviewed_artifact_sha256",
        "subject",
    }
)
SUBJECT_FIELDS = frozenset(
    {
        "run_id",
        "batch_id",
        "stream_id",
        "symbol",
        "review_id",
        "event_ids",
        "event_identity_sha256",
        "dependency_graph_sha256",
        "review_sha256",
        "queue_sha256",
        "current_queue_sha256",
        "bridge_batches_sha256",
        "graph_receipt_sha256",
        "reconciliation_sha256",
    }
)
LEGACY_AUTHORIZATION_FIELDS = frozenset(
    {
        "authorization_id",
        "review_provenance",
        "review_sha256",
        "queue_sha256",
        "dependency_graph_sha256",
        "authorized_at",
        "scheduler_enabled",
        "notification_enabled",
        "production_database_write",
        "action",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_REGISTRY: dict[int, str] = {}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _required_sha256(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field_name} must be SHA-256 hex")
    return text


def _timestamp(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field_name} is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _use_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("M5 approval evaluation time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validity_window(
    authorized_at: datetime,
    valid_until: datetime,
) -> tuple[datetime, datetime]:
    authorized_at = _timestamp(authorized_at, "authorized_at")
    valid_until = _timestamp(valid_until, "valid_until")
    if authorized_at >= valid_until:
        raise ValueError("M5 ACTUAL capability validity window is invalid")
    return authorized_at, valid_until


def _json_value(raw: bytes, field_name: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field_name} contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{field_name} must be valid UTF-8 JSON") from error


def _artifact_hashes(reviewed_artifacts: object) -> tuple[dict[str, str], dict[str, bytes]]:
    if not isinstance(reviewed_artifacts, Mapping) or set(reviewed_artifacts) != ARTIFACT_NAMES:
        raise ValueError("M5 approval reviewed artifact set is incomplete")
    hashes: dict[str, str] = {}
    raw_bytes: dict[str, bytes] = {}
    for name in sorted(ARTIFACT_NAMES):
        envelope = reviewed_artifacts[name]
        if not isinstance(envelope, Mapping) or set(envelope) != {"raw_base64", "sha256"}:
            raise ValueError(f"M5 approval artifact envelope differs: {name}")
        try:
            raw = base64.b64decode(envelope["raw_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError(f"M5 approval artifact bytes are invalid: {name}") from error
        digest = hashlib.sha256(raw).hexdigest()
        if not raw or digest != _required_sha256(envelope["sha256"], f"{name} sha256"):
            raise ValueError(f"M5 approval artifact bytes do not match their hash: {name}")
        hashes[name] = digest
        raw_bytes[name] = raw
    return hashes, raw_bytes


def _decode_subject(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SUBJECT_FIELDS:
        raise ValueError("M5 approval subject schema differs")
    event_ids = value["event_ids"]
    if not isinstance(event_ids, list) or any(not isinstance(item, str) or not item.strip() for item in event_ids):
        raise ValueError("M5 approval subject event_ids must be a JSON string list")
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("M5 approval subject contains duplicate event ids")
    return {
        "run_id": _required_text(value["run_id"], "run_id"),
        "batch_id": _required_text(value["batch_id"], "batch_id"),
        "stream_id": _required_text(value["stream_id"], "stream_id"),
        "symbol": _required_text(value["symbol"], "symbol"),
        "review_id": _required_text(value["review_id"], "review_id"),
        "event_ids": list(event_ids),
        "event_identity_sha256": _required_sha256(value["event_identity_sha256"], "event_identity_sha256"),
        "dependency_graph_sha256": _required_sha256(value["dependency_graph_sha256"], "dependency_graph_sha256"),
        "review_sha256": _required_sha256(value["review_sha256"], "review_sha256"),
        "queue_sha256": _required_sha256(value["queue_sha256"], "queue_sha256"),
        "current_queue_sha256": _required_sha256(value["current_queue_sha256"], "current_queue_sha256"),
        "bridge_batches_sha256": _required_sha256(value["bridge_batches_sha256"], "bridge_batches_sha256"),
        "graph_receipt_sha256": _required_sha256(value["graph_receipt_sha256"], "graph_receipt_sha256"),
        "reconciliation_sha256": _required_sha256(value["reconciliation_sha256"], "reconciliation_sha256"),
    }


def _event_identity_from_batch(batch: Mapping[str, Any]) -> tuple[list[str], str]:
    plans = batch.get("plans")
    if not isinstance(plans, list):
        raise ValueError("M5 approval bridge batch plans differ")
    events: list[dict[str, Any]] = []
    observed_times: list[str] = []
    event_ids: list[str] = []
    for plan in plans:
        if not isinstance(plan, Mapping):
            raise ValueError("M5 approval bridge plan differs")
        event = plan.get("event")
        if event is None:
            continue
        if not isinstance(event, Mapping):
            raise ValueError("M5 approval bridge event differs")
        events.append(dict(event))
        observed_times.append(str(event.get("detected_at")))
        event_ids.append(_required_text(event.get("source_event_id"), "event source_event_id"))
    identity = _sha256({"events": events, "observed_times": observed_times})
    return event_ids, identity


def event_identity_sha256(
    events: Sequence[object], observed_times: Sequence[datetime]
) -> str:
    """Return the exact event/observation identity used by a receipt subject."""
    if len(events) != len(observed_times):
        raise ValueError("Every event requires one observed_at timestamp")
    policies: list[dict[str, Any]] = []
    times: list[str] = []
    for event, observed_at in zip(events, observed_times):
        if not hasattr(event, "as_policy"):
            raise ValueError("M5 approval event identity requires event policy objects")
        policy = event.as_policy()
        if not isinstance(policy, Mapping):
            raise ValueError("M5 approval event policy differs")
        policies.append(dict(policy))
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise ValueError("M5 approval observed_at must be timezone-aware")
        times.append(observed_at.isoformat())
    return _sha256({"events": policies, "observed_times": times})


def build_subject(
    *,
    run_id: str,
    batch_id: str,
    stream_id: str,
    symbol: str,
    review_id: str,
    event_ids: Sequence[str],
    event_identity_sha256_value: str,
    dependency_graph_sha256: str,
    review_sha256: str,
    queue_sha256: str,
    current_queue_sha256: str,
    bridge_batches_sha256: str,
    graph_receipt_sha256: str,
    reconciliation_sha256: str,
) -> dict[str, Any]:
    """Build a canonical receipt subject for a signer/approval adapter."""
    return _decode_subject(
        {
            "run_id": run_id,
            "batch_id": batch_id,
            "stream_id": stream_id,
            "symbol": symbol,
            "review_id": review_id,
            "event_ids": list(event_ids),
            "event_identity_sha256": event_identity_sha256_value,
            "dependency_graph_sha256": dependency_graph_sha256,
            "review_sha256": review_sha256,
            "queue_sha256": queue_sha256,
            "current_queue_sha256": current_queue_sha256,
            "bridge_batches_sha256": bridge_batches_sha256,
            "graph_receipt_sha256": graph_receipt_sha256,
            "reconciliation_sha256": reconciliation_sha256,
        }
    )


def graph_sha256(graph: object) -> str:
    """Hash the exact serialized dependency graph used by a run."""
    if not hasattr(graph, "as_policy"):
        raise ValueError("Actual offline authorization requires a dependency graph")
    payload = graph.as_policy()
    if not isinstance(payload, Mapping):
        raise ValueError("Actual offline authorization graph payload differs")
    return _sha256(dict(payload))


def _parse_receipt(
    envelope: object,
    public_key: Ed25519PublicKey,
) -> tuple[dict[str, Any], str]:
    if not isinstance(envelope, Mapping) or set(envelope) != {"version", "payload", "signature"}:
        raise ValueError("M5 approval receipt envelope schema differs")
    if envelope["version"] != RECEIPT_VERSION or not isinstance(envelope["payload"], Mapping):
        raise ValueError("M5 approval receipt version differs")
    payload = dict(envelope["payload"])
    if set(payload) != RECEIPT_FIELDS:
        raise ValueError("M5 approval receipt payload schema differs")
    try:
        signature = bytes.fromhex(str(envelope["signature"]))
    except (TypeError, ValueError) as error:
        raise ValueError("M5 approval receipt signature is invalid") from error
    try:
        public_key.verify(signature, PURPOSE + _canonical(payload))
    except (InvalidSignature, ValueError, TypeError) as error:
        raise ValueError("M5 approval receipt signature is invalid") from error
    return payload, _sha256(dict(envelope))


def _validate_artifact_bindings(
    raw_bytes: Mapping[str, bytes],
    hashes: Mapping[str, str],
    subject: Mapping[str, Any],
) -> None:
    bridge_payload = _json_value(raw_bytes["bridge_batches"], "bridge_batches")
    if not isinstance(bridge_payload, list):
        raise ValueError("M5 approval bridge_batches must be a JSON list")
    matches = [
        item
        for item in bridge_payload
        if isinstance(item, Mapping)
        and item.get("review_id") == subject["review_id"]
        and item.get("symbol") == subject["symbol"]
    ]
    if len(matches) != 1:
        raise ValueError("M5 approval receipt does not bind exactly one reviewed bridge batch")
    batch = dict(matches[0])
    if batch.get("namespace") != "ACTUAL" or batch.get("action") != "no_order":
        raise ValueError("M5 approval receipt requires one ACTUAL no_order bridge batch")
    event_ids, identity = _event_identity_from_batch(batch)
    if event_ids != subject["event_ids"]:
        raise ValueError("M5 approval receipt event identity changed")
    if identity != subject["event_identity_sha256"]:
        raise ValueError("M5 approval receipt event identity hash changed")
    if hashes["bridge_batches"] != subject["bridge_batches_sha256"]:
        raise ValueError("M5 approval receipt bridge bytes changed")
    if hashes["reviews"] != subject["review_sha256"]:
        raise ValueError("M5 approval receipt reviewed bytes changed")
    if hashes["current_queue"] != subject["current_queue_sha256"]:
        raise ValueError("M5 approval receipt current queue bytes changed")
    if hashes["graph_receipt"] != subject["graph_receipt_sha256"]:
        raise ValueError("M5 approval receipt graph receipt bytes changed")
    if hashes["reconciliation"] != subject["reconciliation_sha256"]:
        raise ValueError("M5 approval receipt reconciliation bytes changed")

    graph_receipt = _json_value(raw_bytes["graph_receipt"], "graph_receipt")
    if not isinstance(graph_receipt, Mapping) or graph_receipt.get("symbol") != subject["symbol"]:
        raise ValueError("M5 approval graph receipt scope differs")
    graph_payload = graph_receipt.get("graph")
    if not isinstance(graph_payload, Mapping) or _sha256(dict(graph_payload)) != subject["dependency_graph_sha256"]:
        raise ValueError("M5 approval graph receipt does not bind the signed graph")

    reconciliation = _json_value(raw_bytes["reconciliation"], "reconciliation")
    if not isinstance(reconciliation, Mapping) or reconciliation.get("action") != "no_order":
        raise ValueError("M5 approval reconciliation must remain no_order")
    prior_review_ids = reconciliation.get("prior_review_ids") or []
    if subject["review_id"] not in prior_review_ids:
        raise ValueError("M5 approval reconciliation does not bind the reviewed batch")


def verify_m5_actual_approval_receipt(
    bundle: Mapping[str, Any],
    trust_root: Mapping[str, Any],
    *,
    expected_subject: Mapping[str, Any] | None = None,
    expected_receipt_sha256: str | None = None,
    at: datetime | None = None,
) -> "M5ActualOfflineAuthorization":
    """Verify a receipt chain and return a sealed ACTUAL offline capability."""
    evaluation_time = _use_time(at)
    if not isinstance(bundle, Mapping) or set(bundle) != {
        "schema_version",
        "receipt_chain",
        "reviewed_artifacts",
    }:
        raise ValueError("M5 approval bundle schema differs")
    if bundle["schema_version"] != BUNDLE_VERSION or not isinstance(bundle["receipt_chain"], list):
        raise ValueError("M5 approval bundle version differs")
    if not isinstance(trust_root, Mapping) or set(trust_root) != {
        "schema_version",
        "approval_public_key",
        "approved_receipt_sha256",
        "approved_sequence",
        "approved_previous_receipt_sha256",
    }:
        raise ValueError("M5 approval trust root schema differs")
    if trust_root["schema_version"] != TRUST_ROOT_VERSION:
        raise ValueError("M5 approval trust root version differs")
    approved_hash = _required_sha256(trust_root["approved_receipt_sha256"], "approved_receipt_sha256")
    approved_sequence = trust_root["approved_sequence"]
    if isinstance(approved_sequence, bool) or not isinstance(approved_sequence, int) or approved_sequence < 1:
        raise ValueError("M5 approval approved_sequence must be positive")
    previous_root = trust_root["approved_previous_receipt_sha256"]
    if previous_root is not None:
        previous_root = _required_sha256(previous_root, "approved_previous_receipt_sha256")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(_required_text(trust_root["approval_public_key"], "approval_public_key"))
        )
    except (TypeError, ValueError) as error:
        raise ValueError("M5 approval public key is invalid") from error

    hashes, raw_bytes = _artifact_hashes(bundle["reviewed_artifacts"])
    chain = bundle["receipt_chain"]
    if len(chain) != approved_sequence:
        raise ValueError("M5 approval receipt chain length does not match its trust root")
    previous_hash: str | None = None
    seen_hashes: set[str] = set()
    seen_approvals: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    final_payload: dict[str, Any] | None = None
    derived_subject: dict[str, Any] | None = None
    for index, envelope in enumerate(chain, start=1):
        payload, receipt_hash = _parse_receipt(envelope, public_key)
        if payload["action"] != "no_order":
            raise ValueError("M5 approval receipt must remain no_order")
        if payload["review_provenance"] != USER_CONFIRMED_DELEGATED_REVIEW:
            raise ValueError("M5 approval receipt requires user-confirmed review provenance")
        if payload["sequence"] != index:
            raise ValueError("M5 approval receipt sequence is not contiguous")
        if payload["previous_receipt_sha256"] != previous_hash:
            raise ValueError("M5 approval receipt chain predecessor changed")
        if receipt_hash in seen_hashes:
            raise ValueError("M5 approval receipt chain contains a duplicate receipt")
        seen_hashes.add(receipt_hash)
        _validity_window(
            _timestamp(payload["authorized_at"], "authorized_at"),
            _timestamp(payload["valid_until"], "valid_until"),
        )
        if payload["reviewed_artifact_sha256"] != hashes:
            raise ValueError("M5 approval receipt does not bind the supplied reviewed bytes")
        subject = _decode_subject(payload["subject"])
        _required_text(payload["authorization_id"], "authorization_id")
        approval_identity = (
            _sha256(subject),
            tuple(sorted(hashes.items())),
        )
        if approval_identity in seen_approvals:
            raise ValueError("M5 approval receipt chain contains a replayed approval")
        seen_approvals.add(approval_identity)
        if expected_subject is not None and subject != _decode_subject(expected_subject):
            raise ValueError("M5 approval receipt subject does not match the requested event identity")
        derived_subject = subject
        final_payload = payload
        previous_hash = receipt_hash
    assert final_payload is not None and derived_subject is not None
    if previous_hash != approved_hash or final_payload["previous_receipt_sha256"] != previous_root:
        raise ValueError("M5 approval receipt is not the approved append-only head")
    if expected_receipt_sha256 is not None and previous_hash != _required_sha256(
        expected_receipt_sha256, "expected_receipt_sha256"
    ):
        raise ValueError("M5 approval receipt does not match the expected capability")
    _validate_artifact_bindings(raw_bytes, hashes, derived_subject)
    # A valid signature is not authorization on its own: the trust root that
    # issued it must appear in the pinned registry, otherwise any caller could
    # mint a fresh keypair and self-authorize an ACTUAL run.
    require_pinned_trust_root(trust_root)
    authorized_at, valid_until = _validity_window(
        _timestamp(final_payload["authorized_at"], "authorized_at"),
        _timestamp(final_payload["valid_until"], "valid_until"),
    )
    if evaluation_time < authorized_at:
        raise ValueError("M5 ACTUAL capability cannot be used before its approval")
    if evaluation_time > valid_until:
        raise ValueError("M5 ACTUAL capability has expired")
    capability_id = _sha256(
        {
            "receipt_sha256": previous_hash,
            "subject": derived_subject,
            "reviewed_artifact_sha256": hashes,
            "authorized_at": authorized_at.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
    )
    return _make_capability(
        authorization_id=_required_text(final_payload["authorization_id"], "authorization_id"),
        subject=derived_subject,
        authorized_at=authorized_at,
        valid_until=valid_until,
        receipt_sha256=previous_hash,
        receipt_sequence=approved_sequence,
        previous_receipt_sha256=previous_root,
        bundle=deepcopy(dict(bundle)),
        trust_root=deepcopy(dict(trust_root)),
        capability_id=capability_id,
    )


def _make_capability(
    *,
    authorization_id: str,
    subject: Mapping[str, Any],
    authorized_at: datetime,
    valid_until: datetime,
    receipt_sha256: str,
    receipt_sequence: int,
    previous_receipt_sha256: str | None,
    bundle: Mapping[str, Any],
    trust_root: Mapping[str, Any],
    capability_id: str,
) -> "M5ActualOfflineAuthorization":
    capability = object.__new__(M5ActualOfflineAuthorization)
    token = object()
    object.__setattr__(capability, "schema_version", AUTHORIZATION_SCHEMA_VERSION)
    object.__setattr__(capability, "authorization_id", _required_text(authorization_id, "authorization_id"))
    object.__setattr__(capability, "review_provenance", USER_CONFIRMED_DELEGATED_REVIEW)
    object.__setattr__(capability, "subject", dict(subject))
    object.__setattr__(capability, "authorized_at", authorized_at)
    object.__setattr__(capability, "valid_until", valid_until)
    object.__setattr__(capability, "receipt_sha256", _required_sha256(receipt_sha256, "receipt_sha256"))
    object.__setattr__(capability, "receipt_sequence", receipt_sequence)
    object.__setattr__(capability, "previous_receipt_sha256", previous_receipt_sha256)
    object.__setattr__(capability, "receipt_bundle", deepcopy(dict(bundle)))
    object.__setattr__(capability, "approval_trust_root", deepcopy(dict(trust_root)))
    object.__setattr__(capability, "capability_id", _required_sha256(capability_id, "capability_id"))
    object.__setattr__(capability, "_capability_token", token)
    object.__setattr__(capability, "scheduler_enabled", False)
    object.__setattr__(capability, "notification_enabled", False)
    object.__setattr__(capability, "production_database_write", False)
    object.__setattr__(capability, "action", "no_order")
    _TOKEN_REGISTRY[id(token)] = capability.capability_id
    capability._validate()
    return capability


@dataclass(frozen=True, init=False)
class M5ActualOfflineAuthorization:
    """Sealed, self-reverifying capability for one reviewed ACTUAL batch."""

    schema_version: str
    authorization_id: str
    review_provenance: str
    subject: dict[str, Any]
    authorized_at: datetime
    valid_until: datetime | None
    receipt_sha256: str
    receipt_sequence: int
    previous_receipt_sha256: str | None
    receipt_bundle: dict[str, Any]
    approval_trust_root: dict[str, Any]
    capability_id: str
    scheduler_enabled: bool = False
    notification_enabled: bool = False
    production_database_write: bool = False
    action: str = "no_order"
    _capability_token: object = field(compare=False, repr=False)
    read_only_legacy: bool = field(default=False, compare=False, repr=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("M5 ACTUAL capabilities must be issued by a verified approval receipt")

    @classmethod
    def _from_legacy_read_only(
        cls, payload: Mapping[str, Any]
    ) -> "M5ActualOfflineAuthorization":
        """Reconstruct an archived v1 capability for audit-only replay.

        The legacy payload has no signature and therefore cannot authorize a
        new run. The explicit read-only marker is consumed only by the bounded
        replay path, which must request legacy replay separately.
        """

        if set(payload) != LEGACY_AUTHORIZATION_FIELDS:
            raise ValueError("Legacy M5 ACTUAL authorization keys do not match the schema")
        legacy = object.__new__(cls)
        subject = {
            "review_sha256": _required_sha256(payload["review_sha256"], "review_sha256"),
            "queue_sha256": _required_sha256(payload["queue_sha256"], "queue_sha256"),
            "dependency_graph_sha256": _required_sha256(
                payload["dependency_graph_sha256"], "dependency_graph_sha256"
            ),
        }
        object.__setattr__(legacy, "schema_version", LEGACY_AUTHORIZATION_SCHEMA_VERSION)
        object.__setattr__(
            legacy,
            "authorization_id",
            _required_text(payload["authorization_id"], "authorization_id"),
        )
        object.__setattr__(
            legacy,
            "review_provenance",
            _required_text(payload["review_provenance"], "review_provenance"),
        )
        object.__setattr__(legacy, "subject", subject)
        object.__setattr__(
            legacy,
            "authorized_at",
            _timestamp(payload["authorized_at"], "authorized_at"),
        )
        object.__setattr__(legacy, "valid_until", None)
        object.__setattr__(legacy, "receipt_sha256", subject["review_sha256"])
        object.__setattr__(legacy, "receipt_sequence", 0)
        object.__setattr__(legacy, "previous_receipt_sha256", None)
        object.__setattr__(legacy, "receipt_bundle", {})
        object.__setattr__(legacy, "approval_trust_root", {})
        object.__setattr__(legacy, "capability_id", subject["review_sha256"])
        object.__setattr__(legacy, "scheduler_enabled", payload["scheduler_enabled"])
        object.__setattr__(legacy, "notification_enabled", payload["notification_enabled"])
        object.__setattr__(
            legacy,
            "production_database_write",
            payload["production_database_write"],
        )
        object.__setattr__(legacy, "action", payload["action"])
        object.__setattr__(legacy, "_capability_token", object())
        object.__setattr__(legacy, "read_only_legacy", True)
        legacy._validate()
        return legacy

    @property
    def is_legacy_read_only(self) -> bool:
        return bool(self.read_only_legacy)

    @property
    def review_sha256(self) -> str:
        return str(self.subject["review_sha256"])

    @property
    def queue_sha256(self) -> str:
        return str(self.subject["queue_sha256"])

    @property
    def dependency_graph_sha256(self) -> str:
        return str(self.subject["dependency_graph_sha256"])

    @property
    def event_identity_sha256(self) -> str:
        return str(self.subject["event_identity_sha256"])

    def _validate(self) -> None:
        if self.read_only_legacy:
            if self.schema_version != LEGACY_AUTHORIZATION_SCHEMA_VERSION:
                raise ValueError("unsupported legacy M5 ACTUAL authorization schema")
            if self.review_provenance != USER_CONFIRMED_DELEGATED_REVIEW:
                raise ValueError("Legacy M5 ACTUAL authorization review provenance is invalid")
            if self.authorized_at.tzinfo is None:
                raise ValueError("Legacy M5 ACTUAL authorization requires a timezone")
            if not isinstance(self.authorization_id, str) or not self.authorization_id.strip():
                raise ValueError("Legacy M5 ACTUAL authorization id is required")
            if self.action != "no_order":
                raise ValueError("Legacy M5 ACTUAL authorization must remain no_order")
            if self.scheduler_enabled or self.notification_enabled or self.production_database_write:
                raise ValueError("Legacy M5 ACTUAL authorization cannot enable production operations")
            for field_name in ("review_sha256", "queue_sha256", "dependency_graph_sha256"):
                if not _SHA256.fullmatch(str(self.subject[field_name])):
                    raise ValueError(f"Legacy M5 ACTUAL authorization {field_name} is invalid")
            return
        if self.schema_version != AUTHORIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported M5 ACTUAL authorization schema")
        if self.review_provenance != USER_CONFIRMED_DELEGATED_REVIEW:
            raise ValueError("M5 ACTUAL authorization requires user-confirmed review provenance")
        if self.action != "no_order":
            raise ValueError("M5 ACTUAL authorization must remain no_order")
        if self.scheduler_enabled or self.notification_enabled or self.production_database_write:
            raise ValueError("M5 ACTUAL authorization cannot enable production operations")
        if not isinstance(self.authorized_at, datetime) or not isinstance(
            self.valid_until, datetime
        ):
            raise ValueError("M5 ACTUAL authorization validity window is invalid")
        _validity_window(self.authorized_at, self.valid_until)
        if self.receipt_sequence < 1 or (
            self.previous_receipt_sha256 is not None
            and not _SHA256.fullmatch(self.previous_receipt_sha256)
        ):
            raise ValueError("M5 ACTUAL authorization receipt chain fields are invalid")
        if not _SHA256.fullmatch(self.receipt_sha256) or not _SHA256.fullmatch(self.capability_id):
            raise ValueError("M5 ACTUAL authorization receipt hashes are invalid")
        if _TOKEN_REGISTRY.get(id(self._capability_token)) != self.capability_id:
            raise ValueError("M5 ACTUAL authorization capability was not verified by a receipt verifier")
        if self.as_policy()["capability_id"] != self.capability_id:
            raise ValueError("M5 ACTUAL authorization capability payload changed")

    def verify(
        self,
        *,
        at: datetime | None = None,
        graph: object | None = None,
        events: Sequence[object] | None = None,
        observed_times: Sequence[datetime] | None = None,
        run_id: str | None = None,
        batch_id: str | None = None,
        stream_id: str | None = None,
        symbol: str | None = None,
    ) -> None:
        """Re-verify the signed receipt and all caller-visible subject bindings."""
        self._validate()
        if self.read_only_legacy:
            if graph is not None and graph_sha256(graph) != self.dependency_graph_sha256:
                raise ValueError("Legacy M5 ACTUAL authorization dependency graph hash does not match")
            return
        evaluation_time = _use_time(at)
        verified = verify_m5_actual_approval_receipt(
            self.receipt_bundle,
            self.approval_trust_root,
            expected_subject=self.subject,
            expected_receipt_sha256=self.receipt_sha256,
            at=evaluation_time,
        )
        if verified.capability_id != self.capability_id:
            raise ValueError("M5 ACTUAL authorization capability does not match its receipt")
        if graph is not None and graph_sha256(graph) != self.dependency_graph_sha256:
            raise ValueError("M5 ACTUAL authorization dependency graph hash does not match")
        if events is not None or observed_times is not None:
            if events is None or observed_times is None:
                raise ValueError("M5 ACTUAL authorization event identity requires both events and observed times")
            if event_identity_sha256(events, observed_times) != self.event_identity_sha256:
                raise ValueError("M5 ACTUAL authorization event identity does not match")
            expected_ids = [getattr(event, "source_event_id", None) for event in events]
            if expected_ids != self.subject["event_ids"]:
                raise ValueError("M5 ACTUAL authorization event ids do not match")
        for label, requested, bound in (
            ("run_id", run_id, self.subject["run_id"]),
            ("batch_id", batch_id, self.subject["batch_id"]),
            ("stream_id", stream_id, self.subject["stream_id"]),
            ("symbol", symbol, self.subject["symbol"]),
        ):
            if requested is not None and requested != bound:
                raise ValueError(f"M5 ACTUAL authorization {label} does not match")

    def as_policy(self) -> dict[str, Any]:
        if self.read_only_legacy:
            return {
                "authorization_id": self.authorization_id,
                "review_provenance": self.review_provenance,
                "review_sha256": self.review_sha256,
                "queue_sha256": self.queue_sha256,
                "dependency_graph_sha256": self.dependency_graph_sha256,
                "authorized_at": self.authorized_at.isoformat(),
                "scheduler_enabled": self.scheduler_enabled,
                "notification_enabled": self.notification_enabled,
                "production_database_write": self.production_database_write,
                "action": self.action,
            }
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "review_provenance": self.review_provenance,
            "subject": deepcopy(self.subject),
            "authorized_at": self.authorized_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "receipt_sha256": self.receipt_sha256,
            "receipt_sequence": self.receipt_sequence,
            "previous_receipt_sha256": self.previous_receipt_sha256,
            "receipt_bundle": deepcopy(self.receipt_bundle),
            "approval_trust_root": deepcopy(self.approval_trust_root),
            "capability_id": self.capability_id,
            "scheduler_enabled": self.scheduler_enabled,
            "notification_enabled": self.notification_enabled,
            "production_database_write": self.production_database_write,
            "action": self.action,
        }


def actual_offline_authorization_from_payload(
    payload: object,
    *,
    allow_legacy_read_only: bool = False,
    at: datetime | None = None,
) -> M5ActualOfflineAuthorization:
    if not isinstance(payload, Mapping):
        raise ValueError("Actual offline authorization must be an object")
    data = dict(payload)
    if set(data) == LEGACY_AUTHORIZATION_FIELDS:
        if not allow_legacy_read_only:
            raise ValueError(
                "Legacy M5 ACTUAL authorization is read-only and cannot authorize a new run"
            )
        return M5ActualOfflineAuthorization._from_legacy_read_only(data)
    if "schema_version" not in data:
        raise ValueError("Actual offline authorization schema differs")
    capability = verify_m5_actual_approval_receipt(
        data.get("receipt_bundle"),
        data.get("approval_trust_root"),
        expected_subject=data.get("subject"),
        expected_receipt_sha256=data.get("receipt_sha256"),
        at=at,
    )
    expected = capability.as_policy()
    if set(data) != set(expected):
        raise ValueError("Actual offline authorization keys do not match the schema")
    if data != expected:
        raise ValueError("Actual offline authorization does not round-trip to its receipt")
    return capability


def require_actual_offline_authorization(
    *,
    namespace: str,
    authorization: M5ActualOfflineAuthorization | None,
    graph: object,
    events: Sequence[object] | None = None,
    observed_times: Sequence[datetime] | None = None,
    run_id: str | None = None,
    batch_id: str | None = None,
    stream_id: str | None = None,
    symbol: str | None = None,
    allow_legacy_read_only: bool = False,
    at: datetime | None = None,
) -> None:
    if namespace == "SIMULATED":
        if authorization is not None:
            raise ValueError("Simulated M5 runs cannot carry actual authorization")
        return
    if namespace != "ACTUAL":
        raise ValueError("Unknown M5 run namespace")
    if authorization is None:
        raise ValueError("ACTUAL offline M5 runs require explicit authorization")
    if not isinstance(authorization, M5ActualOfflineAuthorization):
        raise ValueError("ACTUAL offline M5 runs require a verified approval capability")
    if authorization.is_legacy_read_only and not allow_legacy_read_only:
        raise ValueError(
            "Legacy M5 ACTUAL authorization is read-only and cannot authorize a new run"
        )
    authorization.verify(
        graph=graph,
        events=events,
        observed_times=observed_times,
        run_id=run_id,
        batch_id=batch_id,
        stream_id=stream_id,
        symbol=symbol,
        at=at,
    )


__all__ = [
    "ARTIFACT_NAMES",
    "AUTHORIZATION_SCHEMA_VERSION",
    "BUNDLE_VERSION",
    "M5ActualOfflineAuthorization",
    "RECEIPT_VERSION",
    "SUBJECT_FIELDS",
    "TRUST_ROOT_VERSION",
    "USER_CONFIRMED_DELEGATED_REVIEW",
    "actual_offline_authorization_from_payload",
    "build_subject",
    "event_identity_sha256",
    "graph_sha256",
    "require_actual_offline_authorization",
    "verify_m5_actual_approval_receipt",
]
