"""Bounded V11 two-stage cash-policy input for conditional E2 research."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import FunctionType

from . import operating_horizon_cash_policy_e2_v2 as prior
from .agent_review.operating_horizon_task_v11_live import (
    CONTRACT, OperatingHorizonTaskService,
)

VERSION = "operating-horizon-cash-policy-e2-input-v3"


def read_v11_cash_policy_e2_input(*, root: Path, task_id: str, now, service=None) -> dict:
    """Replay V10's fail-closed checks against the V11 contract and service."""
    # Function globals are private to this adapter: no module mutation or V10 byte changes.
    bindings = dict(prior.read_v10_cash_policy_e2_input.__globals__)
    bindings.update(CONTRACT=CONTRACT, OperatingHorizonTaskService=OperatingHorizonTaskService,
                    VERSION=VERSION)
    reader = FunctionType(prior.read_v10_cash_policy_e2_input.__code__, bindings)
    result = reader(root=root, task_id=task_id, now=now, service=service)
    result = deepcopy(result)
    mode = result["execution_mode"]
    result["status"] = ("SOURCE_BOUND_D2_V11_CASH_POLICY_READY_FOR_E2"
                        if mode == "LIVE_OPERATING" else "TEST_ONLY_E2_CONTRACT_REPLAY")
    result["scope"] = ("CONDITIONAL_UNAPPROVED_D2_V11_POLICY_NOT_VALUATION_OR_PRICE"
                       if mode == "LIVE_OPERATING" else "TEST_ONLY_NOT_REAL_RESEARCH_OR_VALUATION")
    return result
