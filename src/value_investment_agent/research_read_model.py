"""DEPRECATED_COMPATIBILITY_SHIM: forward to the presentation read model."""

from .presentation.read_models import research_read_model as _implementation

__all__ = [
    name for name in dir(_implementation) if not name.startswith("_")
]
globals().update({name: getattr(_implementation, name) for name in __all__})
