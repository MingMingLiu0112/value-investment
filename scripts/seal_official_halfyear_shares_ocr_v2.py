"""Thin offline CLI for source-bound half-year share OCR sealing."""
import sys

from value_investment_agent.infrastructure.filings.official_halfyear_shares_ocr_sealer_v2 import seal


if __name__ == "__main__":
    seal(*sys.argv[1:4], source_url=sys.argv[4])
