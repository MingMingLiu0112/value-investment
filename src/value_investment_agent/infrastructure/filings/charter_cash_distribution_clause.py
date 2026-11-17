"""Extract a conditional annual cash distribution floor from an issuer charter."""

from hashlib import sha256
from pathlib import Path
import re

from .pdf_text import extract_pages
from .statutory_reserve_clause import _compact


def read_annual_cash_floor(path: Path, *, issuer: str, expected_sha256: str) -> dict:
    """Verify the exact operative layout and preserve the policy denominator."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("CASH_FLOOR_CHARTER_HASH_REQUIRED")
    if sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("CASH_FLOOR_CHARTER_HASH_CHANGED")
    pages = extract_pages(path)
    if not pages or not issuer or not re.match(
        r"^(?:—\d+—)?" + re.escape(_compact(issuer)) + "章程", _compact(pages[0])
    ):
        raise ValueError("CASH_FLOOR_CHARTER_ISSUER_MISMATCH")
    pattern = re.compile(
        r"公司在年度报告期内盈利且累计未分配利润为正时,应当进行现金分红。"
        r"\(2\)如实施现金分红,其比例为:每年以现金方式分配的利润"
        r"不少于当年实现可分配利润的([1-9][0-9]?)%。"
    )
    matches = [(i, m) for i, page in enumerate(pages, 1)
               for m in pattern.finditer(_compact(page))]
    if len(matches) != 1:
        raise ValueError("CASH_FLOOR_CHARTER_UNIQUE_OPERATIVE_CLAUSE_REQUIRED")
    if sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("CASH_FLOOR_CHARTER_HASH_CHANGED")
    page, clause = matches[0]
    return dict(
        issuer=issuer, physical_page=page, source_sha256=expected_sha256,
        clause_sha256=sha256(clause[0].encode("utf-8")).hexdigest(),
        cash_floor_percent=clause[1], denominator="ANNUAL_DISTRIBUTABLE_PROFIT",
        conditions=["PROFITABLE_REPORTING_YEAR", "POSITIVE_ACCUMULATED_UNDISTRIBUTED_PROFIT"],
        payout_target=None, projected_cash_cny=None, action="no_order",
    )
