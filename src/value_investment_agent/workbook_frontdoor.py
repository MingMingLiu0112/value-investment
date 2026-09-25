"""DEPRECATED_COMPATIBILITY_SHIM: forward to the Excel presentation adapter."""

from .presentation.excel.workbook_frontdoor import (
    GREEN,
    GREY,
    HOME,
    INK,
    PRIMARY,
    STAGE_FRONTEND,
    VERSION,
    _band,
    _link,
    _rows,
    apply_frontdoor,
    primary_sheet_names,
    repair_internal_links,
)

__all__ = [
    "GREEN",
    "GREY",
    "HOME",
    "INK",
    "PRIMARY",
    "STAGE_FRONTEND",
    "VERSION",
    "_band",
    "_link",
    "_rows",
    "apply_frontdoor",
    "primary_sheet_names",
    "repair_internal_links",
]
