"""Byte-level verification for M6 Shadow authorization artifacts."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping


ARTIFACT_KEYS = frozenset({"scope_manifest", "deployment_manifest", "runtime_config"})


def _object(raw: bytes, label: str) -> dict[str, Any]:
    pairs: list[tuple[str, Any]] = json.loads(raw, object_pairs_hook=list)
    if not isinstance(pairs, list) or any(not isinstance(item, tuple) for item in pairs):
        raise ValueError(f"{label} must be a JSON object")
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"{label} contains duplicate JSON keys")
        result[key] = value
    return result


def verify_authorization_artifacts(
    authorization: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    *,
    expected_target_mode: str | None = None,
    expected_operator_id: str | None = None,
) -> dict[str, str]:
    """Hash actual bytes and verify their signed authorization relationships."""
    if set(artifacts) != ARTIFACT_KEYS:
        raise ValueError("Shadow authorization artifact set is incomplete")
    decoded: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for name in sorted(ARTIFACT_KEYS):
        envelope = artifacts[name]
        if not isinstance(envelope, Mapping) or set(envelope) != {"raw_base64", "sha256"}:
            raise ValueError(f"Shadow {name} envelope differs")
        try:
            raw = base64.b64decode(envelope["raw_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Shadow {name} bytes are invalid") from error
        digest = hashlib.sha256(raw).hexdigest()
        if not raw or digest != envelope["sha256"]:
            raise ValueError(f"Shadow {name} hash differs from actual bytes")
        decoded[name] = raw
        digests[name] = digest
    if (
        digests["scope_manifest"] != authorization.get("scope_manifest_sha256")
        or digests["deployment_manifest"] != authorization.get("deployment_sha256")
        or digests["runtime_config"] != authorization.get("config_sha256")
    ):
        raise ValueError("Shadow authorization does not bind the supplied artifact bytes")
    scope = _object(decoded["scope_manifest"], "scope manifest")
    deployment = _object(decoded["deployment_manifest"], "deployment manifest")
    config = _object(decoded["runtime_config"], "runtime config")
    expected_scope = {
        "action": "no_order",
        "authorization_id": authorization.get("authorization_id"),
        "mode": authorization.get("mode"),
        "venue": authorization.get("venue"),
        "valid_from": authorization.get("valid_from"),
        "valid_until": authorization.get("valid_until"),
        "deployment_sha256": digests["deployment_manifest"],
        "config_sha256": digests["runtime_config"],
    }
    if any(scope.get(key) != value for key, value in expected_scope.items()):
        raise ValueError("Shadow scope manifest differs from signed authorization")
    if expected_target_mode is not None:
        if scope.get("target_mode") != expected_target_mode:
            raise ValueError("Shadow scope manifest target mode differs from the control transition")
    elif "target_mode" in scope and (
        not isinstance(scope.get("target_mode"), str)
        or not scope["target_mode"].strip()
    ):
        raise ValueError("Shadow scope manifest target mode is invalid")
    if expected_operator_id is not None:
        if scope.get("operator_id") != expected_operator_id:
            raise ValueError("Shadow scope manifest operator differs from the control operator")
    elif "operator_id" in scope and (
        not isinstance(scope.get("operator_id"), str)
        or not scope["operator_id"].strip()
    ):
        raise ValueError("Shadow scope manifest operator is invalid")
    if deployment.get("action") != "no_order" or config.get("action") != "no_order":
        raise ValueError("Shadow deployment and config artifacts must remain no_order")
    if not deployment.get("deployment_id") or not config.get("config_id"):
        raise ValueError("Shadow deployment and config identities are required")
    return digests
