"""Bounded V13 two-stage cash-policy input for conditional E2 research."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .operating_horizon_cash_policy_e2_v2 import _read_bound_cash_policy_e2_input
from .agent_review.operating_horizon_task_v13_live import (
    CONTRACT, OperatingHorizonTaskService,
)

VERSION = "operating-horizon-cash-policy-e2-input-v5"


def read_v13_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    return _read_bound_cash_policy_e2_input(
        root=root, task_id=task_id, now=now, contract=CONTRACT,
        task_service=OperatingHorizonTaskService, version=VERSION,
        label="V13", service=service)
