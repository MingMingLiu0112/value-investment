"""Admit a source-bound V22 native-transport task through the existing E2 gate."""
from datetime import datetime
from pathlib import Path

from .operating_horizon_cash_policy_e2_v11 import read_generic_cash_policy_e2_input
from .agent_review.operating_horizon_task_v22_native import (
    CONTRACT, OperatingHorizonTaskService,
)

VERSION = "operating-horizon-cash-policy-e2-input-v14"


def read_v22_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    return read_generic_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, service_type=OperatingHorizonTaskService,
        version=VERSION, label="V22", service=service, staged_annual=True)
