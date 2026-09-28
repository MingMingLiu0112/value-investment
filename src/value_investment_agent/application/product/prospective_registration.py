"""Create an immutable runtime receipt for a pre-registered public research plan."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...domain.research.prospective_registration import (
    canonical_registration_payload,
    prospective_registration_from_payload,
)
from .common import load_json_object, require_inside, sha256_file, write_new_json


def verify_prospective_registration_receipt(
    *, root: Path, receipt_path: str, receipt_sha256: str,
    plan_path: str, expected_registration_sha256: str | None = None,
) -> tuple[dict[str, Any], Any]:
    """Verify a receipt, its exact plan bytes, and the registration commit ancestry."""
    receipt_file = require_inside(root, root / receipt_path, "prospective registration receipt")
    receipt_bytes = receipt_file.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != receipt_sha256.lower():
        raise ValueError("registration receipt byte hash mismatch")
    receipt = json.loads(receipt_bytes)
    if receipt.get("schema_version") != "prospective-research-registration-receipt-v2" or receipt.get("action") != "no_order":
        raise ValueError("current no_order registration receipt required")
    if receipt.get("declared_time_independently_proven") is not False:
        raise ValueError("process-clock registration time must remain explicitly unattested")
    if receipt.get("pit_time_anchor") != "receipt_created_at":
        raise ValueError("receipt_created_at must remain the declared PIT time anchor")
    if any(receipt.get(field) is not False for field in (
        "outcomes_observed", "valuation_executed", "decision_signal_created", "portfolio_data_used",
    )):
        raise ValueError("registration receipt must precede outcomes and remain non-personalized")
    if expected_registration_sha256 is not None and receipt.get("registration_sha256") != expected_registration_sha256:
        raise ValueError("registration fingerprint differs from expected value")
    registration = prospective_registration_from_payload(
        {"schema_version": "prospective-research-registration-v2", **receipt["registration"]}
    )
    canonical_sha = hashlib.sha256(canonical_registration_payload(registration).encode("utf-8")).hexdigest()
    if canonical_sha != receipt.get("registration_sha256"):
        raise ValueError("registration receipt does not bind registration bytes")
    created = datetime.fromisoformat(receipt.get("receipt_created_at", ""))
    if created.tzinfo is None:
        raise ValueError("receipt_created_at must include a timezone")
    if created > datetime.now(timezone.utc):
        raise ValueError("receipt_created_at cannot be in the future")
    plan_file = require_inside(root, root / plan_path, "registered plan")
    plan_bytes = plan_file.read_bytes()
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    if plan_sha != receipt.get("plan_sha256"):
        raise ValueError("registered plan byte hash mismatch")
    commit = receipt.get("git_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("registration commit is invalid")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root,
        capture_output=True, check=False,
    )
    relative = plan_file.relative_to(root.resolve()).as_posix()
    committed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=root,
        capture_output=True, check=False,
    )
    if ancestry.returncode != 0 or committed.returncode != 0 or hashlib.sha256(committed.stdout).hexdigest() != plan_sha:
        raise ValueError("registration commit ancestry or committed plan bytes are not verified")
    plan_registration = prospective_registration_from_payload(load_json_object(plan_file, "registered plan"))
    if plan_registration.as_policy() != registration.as_policy():
        raise ValueError("registration receipt differs from the registered plan")
    if any(created > case.observation_start_at for case in registration.cases):
        raise ValueError("registration receipt was created after observation start")
    return receipt, registration


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    head = completed.stdout.strip()
    if completed.returncode != 0 or len(head) != 40:
        raise ValueError("cannot bind prospective registration to Git HEAD")
    return head


def register_prospective_research_plan(
    *, root: Path, plan_path: Path, output_path: Path,
) -> dict[str, Any]:
    """Bind a committed plan to the current revision without observing outcomes."""
    plan_file = require_inside(root, plan_path, "prospective registration plan")
    target = require_inside(root, output_path, "prospective registration output")
    runtime = (root / "runtime").resolve()
    if not target.is_relative_to(runtime):
        raise ValueError("prospective registration output must remain under runtime")
    if not plan_file.is_file():
        raise ValueError("prospective registration plan must be an existing file")
    try:
        plan_bytes = plan_file.read_bytes()
        plan_payload = json.loads(plan_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective registration plan must be valid UTF-8 JSON") from error
    if not isinstance(plan_payload, dict):
        raise ValueError("prospective registration plan must be a JSON object")
    registration = prospective_registration_from_payload(plan_payload)
    receipt_created_at = datetime.now(timezone.utc)
    if any(receipt_created_at > case.observation_start_at for case in registration.cases):
        raise ValueError("prospective receipt must be created on or before observation_start_at")
    git_commit = _git_head(root)
    relative = plan_file.relative_to(root.resolve()).as_posix()
    committed = subprocess.run(
        ["git", "show", f"{git_commit}:{relative}"], cwd=root,
        capture_output=True, check=False,
    )
    if committed.returncode != 0 or committed.stdout != plan_bytes:
        raise ValueError("prospective registration plan bytes must match the file committed at HEAD")
    canonical = canonical_registration_payload(registration).encode("utf-8")
    result: dict[str, Any] = {
        "schema_version": "prospective-research-registration-receipt-v2",
        "registration": registration.as_policy(),
        "registration_sha256": hashlib.sha256(canonical).hexdigest(),
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "git_commit": git_commit,
        "receipt_created_at": receipt_created_at.isoformat(),
        "declared_time_independently_proven": False,
        "pit_time_anchor": "receipt_created_at",
        "action": "no_order",
        "outcomes_observed": False,
        "valuation_executed": False,
        "decision_signal_created": False,
        "portfolio_data_used": False,
    }
    write_new_json(target, result)
    return result | {"output_path": str(target), "output_sha256": sha256_file(target)}


__all__ = ["register_prospective_research_plan"]
__all__.append("verify_prospective_registration_receipt")
