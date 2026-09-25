"""Historical validation domain boundary."""

from .admission import *  # noqa: F401,F403
from .admission import __all__ as _admission_all

__all__ = list(_admission_all)
