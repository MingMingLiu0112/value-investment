"""DEPRECATED_COMPATIBILITY_SHIM for human research approval contracts.

The implementation lives in
`value_investment_agent.domain.research.human_research_approval`. This module
keeps existing imports stable while consumers migrate.
"""

from .domain.research.human_research_approval import *  # noqa: F401,F403
