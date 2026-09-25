"""DEPRECATED_COMPATIBILITY_SHIM for gap classification.

The implementation lives in
``value_investment_agent.domain.research.gap_classification``. This module
keeps existing imports stable while consumers migrate.
"""

from .domain.research.gap_classification import *  # noqa: F401,F403
from .domain.research.gap_classification import __all__ as _domain_all


__all__ = list(_domain_all)
