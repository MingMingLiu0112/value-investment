"""DEPRECATED_COMPATIBILITY_SHIM: forward to the filings PDF adapter."""

from .infrastructure.filings.pdf_text import extract_pages

__all__ = ["extract_pages"]
