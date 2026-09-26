"""Versioned marker for virtual-account executions.

The marker is deliberately explicit in every fill, journal row, and account
snapshot. A simulated execution is never an approved trade or a live order.
"""
from __future__ import annotations

from typing import Any, Mapping


SIMULATION_EXECUTION_SCHEMA = "simulation-only-execution-v1"
SIMULATION_ONLY = "SIMULATION_ONLY"
SIMULATION_ONLY_EXECUTION_SCOPE = "daily_simulation_assumption_not_real_fill"


def simulation_execution_marker() -> dict[str, Any]:
    """Return a fresh copy of the immutable simulation-only execution marker."""
    return {
        "schema_version": SIMULATION_EXECUTION_SCHEMA,
        "order_scope": SIMULATION_ONLY,
        "simulation_only": True,
        "trade_approved": False,
        "live_eligible": False,
        "execution_scope": SIMULATION_ONLY_EXECUTION_SCOPE,
        "action": "no_order",
    }


def assert_simulation_execution(value: object) -> None:
    """Reject any payload that could be mistaken for a real execution."""
    if not isinstance(value, Mapping):
        raise ValueError("Simulation execution marker requires an object")
    expected = simulation_execution_marker()
    for key, required in expected.items():
        if value.get(key) != required:
            raise ValueError(f"Simulation execution marker differs: {key}")
