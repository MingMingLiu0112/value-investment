"""Execution-domain contracts that never place real orders."""

from .simulation_only import (
    SIMULATION_EXECUTION_SCHEMA,
    SIMULATION_ONLY,
    SIMULATION_ONLY_EXECUTION_SCOPE,
    assert_simulation_execution,
    simulation_execution_marker,
)

__all__ = [
    "SIMULATION_EXECUTION_SCHEMA",
    "SIMULATION_ONLY",
    "SIMULATION_ONLY_EXECUTION_SCOPE",
    "assert_simulation_execution",
    "simulation_execution_marker",
]
