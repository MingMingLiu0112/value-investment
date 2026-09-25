"""DEPRECATED_COMPATIBILITY_SHIM for the research run contract.

The implementation lives in
`value_investment_agent.domain.research.research_run_contract`. This module
keeps existing imports stable while consumers migrate.
"""

from .domain.research.research_run_contract import *  # noqa: F401,F403
