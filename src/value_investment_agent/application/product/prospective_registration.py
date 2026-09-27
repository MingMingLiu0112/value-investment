"""Create an immutable runtime receipt for a pre-registered public research plan."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...domain.research.prospective_registration import (
    canonical_registration_payload,
    prospective_registration_from_payload,
)
from .common import load_json_object, require_inside, sha256_file, write_new_json


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
    registration = prospective_registration_from_payload(
        load_json_object(plan_file, "prospective registration plan")
    )
    receipt_created_at = datetime.now(timezone.utc)
    if any(receipt_created_at > case.observation_start_at for case in registration.cases):
        raise ValueError("prospective receipt must be created on or before observation_start_at")
    canonical = canonical_registration_payload(registration).encode("utf-8")
    result: dict[str, Any] = {
        "schema_version": "prospective-research-registration-receipt-v2",
        "registration": registration.as_policy(),
        "registration_sha256": hashlib.sha256(canonical).hexdigest(),
        "plan_sha256": sha256_file(plan_file),
        "git_commit": _git_head(root),
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
