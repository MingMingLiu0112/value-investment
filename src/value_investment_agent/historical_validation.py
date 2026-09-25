"""DEPRECATED_COMPATIBILITY_SHIM for historical_validation.

The implementation moved to
``value_investment_agent.domain.historical_validation.admission``.
This module keeps old imports stable while consumers migrate.
"""

from .domain.historical_validation import *  # noqa: F401,F403
from .domain.historical_validation import __all__ as _domain_all

__all__ = list(_domain_all)
