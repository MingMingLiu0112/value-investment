"""DEPRECATED_COMPATIBILITY_SHIM: use infrastructure.market_data.provider_scope."""

from .infrastructure.market_data.provider_scope import (
    REPLACEMENTS,
    snapshot_proves_provider_field,
)

__all__ = ["REPLACEMENTS", "snapshot_proves_provider_field"]
