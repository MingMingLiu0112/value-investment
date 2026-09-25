"""DEPRECATED_COMPATIBILITY_SHIM for research profiles.

The implementation lives in
`value_investment_agent.domain.research.research_profile`. This module keeps
existing imports stable while consumers migrate.
"""

from .domain.research.research_profile import *  # noqa: F401,F403
from .domain.research.research_profile import __all__ as _domain_all


__all__ = list(_domain_all)
