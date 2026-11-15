"""Admit a source-bound V25 native-transport task through the existing E2 gate."""
from datetime import datetime
from pathlib import Path

from .operating_horizon_cash_policy_e2_v11 import read_generic_cash_policy_e2_input
from .agent_review.operating_horizon_task_v25_canonical import (
    CONTRACT, OperatingHorizonTaskService,
)

from .agent_review.operating_horizon_sources_v2_return_plan import VERSION as RETURN_PLAN_LOADER

VERSION = "operating-horizon-cash-policy-e2-input-v17"


def read_v25_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    return read_generic_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, service_type=OperatingHorizonTaskService,
        version=VERSION, label="V25", service=service, staged_annual=True,
        additional_reported_fact_loaders=(RETURN_PLAN_LOADER,))



