"""DEPRECATED_COMPATIBILITY_SHIM: forward to the presentation Excel adapter."""

from .presentation.excel.workbook_compat import load_wps_workbook

__all__ = ["load_wps_workbook"]
