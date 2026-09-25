"""DEPRECATED_COMPATIBILITY_SHIM: forward to infrastructure backup snapshot."""

from .infrastructure.backup.backup_snapshot import compare_checks, table_checks

__all__ = ["compare_checks", "table_checks"]
