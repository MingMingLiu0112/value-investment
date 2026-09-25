"""DEPRECATED_COMPATIBILITY_SHIM for the research case contract.

The implementation lives in
`value_investment_agent.domain.research.research_case`. This module keeps
existing imports stable while consumers migrate.
"""

from .domain.research.research_case import *  # noqa: F401,F403
from .domain.research.research_case import __all__ as _domain_all


__all__ = list(_domain_all)
