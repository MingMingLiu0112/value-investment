"""Fail-closed registry for pipelines that write decision-shaped state.

Data collectors may coexist. What must not coexist is two writers publishing
the same authoritative current state. This module validates the declared
registry and compares it with the scheduled tasks observed on the host.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "decision-writers-registry-v1"
ACTION_NO_ORDER = "no_order"
VALID_STATUSES = {
    "KEEP_READONLY",
    "MIGRATE",
    "ARCHIVE",
    "RETIRE_PENDING_APPROVAL",
    "RETIRED_AUTHORIZED",
}
OBSERVED_TASK_PREFIX = "ValueInvestmentAgent-"


class WriterRegistryError(ValueError):
    """Raised when the registry itself is malformed."""


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WriterRegistryError("writer registry must be an object")
    return payload


def validate_registry(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return deterministic error codes; an empty tuple means PASS."""
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION_MISMATCH")
    if payload.get("action") != ACTION_NO_ORDER:
        errors.append("ACTION_NOT_NO_ORDER")
    scopes = payload.get("authority_scopes")
    pipelines = payload.get("pipelines")
    if not isinstance(scopes, Mapping) or not scopes:
        errors.append("AUTHORITY_SCOPES_MISSING")
        scopes = {}
    if not isinstance(pipelines, list) or not pipelines:
        errors.append("PIPELINES_MISSING")
        pipelines = []

    declared_authority: dict[str, list[str]] = {scope: [] for scope in scopes}
    seen_ids: set[str] = set()
    for pipeline in pipelines:
        if not isinstance(pipeline, Mapping):
            errors.append("PIPELINE_NOT_OBJECT")
            continue
        pipeline_id = str(pipeline.get("id") or "")
        if not pipeline_id:
            errors.append("PIPELINE_ID_MISSING")
            continue
        if pipeline_id in seen_ids:
            errors.append(f"DUPLICATE_PIPELINE:{pipeline_id}")
        seen_ids.add(pipeline_id)
        if pipeline.get("status") not in VALID_STATUSES:
            errors.append(f"INVALID_STATUS:{pipeline_id}")
        writes = pipeline.get("writes_scopes")
        if not isinstance(writes, list):
            errors.append(f"WRITES_SCOPES_MISSING:{pipeline_id}")
            writes = []
        effective = pipeline.get("effective_authority")
        if not isinstance(effective, bool):
            errors.append(f"EFFECTIVE_AUTHORITY_MISSING:{pipeline_id}")
            effective = False
        consumed = pipeline.get("consumed_by_current_product")
        if not isinstance(consumed, bool):
            errors.append(f"CONSUMED_FLAG_MISSING:{pipeline_id}")
            consumed = False
        if effective:
            for scope in writes:
                if scope not in scopes:
                    errors.append(f"UNKNOWN_AUTHORITY_SCOPE:{pipeline_id}:{scope}")
                declared_authority.setdefault(scope, []).append(pipeline_id)
            if not pipeline.get("recovery"):
                errors.append(f"AUTHORITY_WITHOUT_RECOVERY:{pipeline_id}")
        elif consumed:
            errors.append(f"OBSERVER_MARKED_AS_CURRENT_CONSUMER:{pipeline_id}")
        if pipeline.get("kind") == "LEGACY" and not pipeline.get("legacy_label"):
            errors.append(f"LEGACY_WITHOUT_LABEL:{pipeline_id}")

    for scope, scope_policy in scopes.items():
        expected = (scope_policy or {}).get("authoritative_pipeline")
        actual = declared_authority.get(scope, [])
        if len(actual) > 1:
            errors.append(f"MULTIPLE_AUTHORITATIVE_WRITERS:{scope}:{','.join(sorted(actual))}")
        if expected and expected not in actual:
            errors.append(f"SCOPE_AUTHORITY_UNDECLARED:{scope}:{expected}")
    return tuple(dict.fromkeys(errors))


def compare_observed_tasks(
    payload: Mapping[str, Any], observed: Mapping[str, str]
) -> tuple[str, ...]:
    """Check that every observed ValueInvestmentAgent task is declared."""
    errors: list[str] = []
    declared = {
        str(pipeline.get("scheduled_task"))
        for pipeline in payload.get("pipelines", [])
        if isinstance(pipeline, Mapping) and pipeline.get("scheduled_task")
    }
    for task_name in sorted(observed):
        if task_name.startswith(OBSERVED_TASK_PREFIX) and task_name not in declared:
            errors.append(f"UNDECLARED_WRITER_TASK:{task_name}")
    for missing in sorted(declared - set(observed)):
        errors.append(f"DECLARED_TASK_NOT_OBSERVED:{missing}")
    return tuple(dict.fromkeys(errors))


def audit(
    payload: Mapping[str, Any], *, observed: Mapping[str, str] | None = None
) -> dict[str, Any]:
    errors = list(validate_registry(payload))
    if observed is not None:
        errors.extend(compare_observed_tasks(payload, observed))
    return {
        "schema_version": "decision-writers-audit-v1",
        "action": ACTION_NO_ORDER,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "pipeline_count": len(payload.get("pipelines") or []),
        "authority_scopes": sorted((payload.get("authority_scopes") or {}).keys()),
    }