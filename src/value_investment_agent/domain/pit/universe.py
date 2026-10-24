"""Which securities belong in an A-share research sample.

The public bulk-disclosure endpoints do not distinguish exchanges. They return
Shanghai, Shenzhen, the Beijing Stock Exchange (4xx / 8xx / 920) and NEEQ
(83x / 87x) in one payload, which roughly doubles the row count and silently
changes the universe mid-sample. Liquidity, disclosure cadence and index
membership differ enough across those boards that mixing them corrupts any
cross-sectional comparison, so the boundary is explicit here rather than being
rediscovered inside every caller.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

SCHEMA_VERSION = "pit-universe-v1"

# Shanghai / Shenzhen main board, ChiNext and STAR Market.
A_SHARE_PREFIXES: tuple[str, ...] = (
    "600", "601", "603", "605",   # Shanghai main board
    "000", "001", "002", "003",   # Shenzhen main board
    "300", "301",                 # ChiNext
    "688", "689",                 # STAR Market
)

# Explicitly excluded, recorded so the exclusion is auditable rather than implied.
EXCLUDED_BOARDS: dict[str, tuple[str, ...]] = {
    "bse": ("43", "83", "87", "88", "920"),   # Beijing Stock Exchange
    "neeq": ("83", "87"),                      # NEEQ overlaps the BSE prefix space
}

# ST / *ST / delisting-transition markers appear in the security name, not the code.
_SPECIAL_TREATMENT = re.compile(r"(ST|\*ST|退)", re.IGNORECASE)


def is_a_share(code: str) -> bool:
    code = str(code).strip()
    return code[:3] in A_SHARE_PREFIXES


def is_special_treatment(name: str) -> bool:
    """True for ST / *ST / delisting-transition names.

    These are not filtered out automatically — survivorship and distress effects
    are real and excluding them flatters any strategy. The predicate exists so a
    caller that does exclude them records *that it did*, and a caller that keeps
    them can flag the affected rows.
    """
    return bool(_SPECIAL_TREATMENT.search(str(name or "")))


def restrict(codes: Iterable[str]) -> list[str]:
    """Order-preserving filter of an iterable of codes to the A-share set."""
    return [c for c in codes if is_a_share(c)]


def partition(codes: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split into (kept, dropped) so a caller can report what it discarded."""
    kept: list[str] = []
    dropped: list[str] = []
    for code in codes:
        (kept if is_a_share(code) else dropped).append(code)
    return kept, dropped


def coverage(codes: Sequence[str]) -> dict[str, int]:
    total = len(codes)
    kept, dropped = partition(codes)
    return {
        "total": total,
        "a_share": len(kept),
        "dropped": len(dropped),
        "dropped_pct": round(100.0 * len(dropped) / total, 2) if total else 0,
    }
