"""DEPRECATED_COMPATIBILITY_SHIM for valuation confidence.

The implementation lives in
``value_investment_agent.domain.valuation.confidence``. This module keeps
existing imports stable while consumers migrate.
"""

from .domain.valuation.confidence import *  # noqa: F401,F403
from .domain.valuation.confidence import __all__ as _domain_all


__all__ = list(_domain_all)
