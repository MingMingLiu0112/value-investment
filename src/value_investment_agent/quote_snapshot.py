"""Minimal verified-quote input contract for the shared price bridge."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
import re
from typing import Any


QUOTE_STATUS_VERIFIED_CLOSE = "verified_close"
QUOTE_STATUS_PENDING_EXTERNAL_DATA = "PENDING_EXTERNAL_DATA"
QUOTE_STATUS_UNVERIFIED = "unverified"

QUOTE_STATUSES = {
    QUOTE_STATUS_VERIFIED_CLOSE,
    QUOTE_STATUS_PENDING_EXTERNAL_DATA,
    QUOTE_STATUS_UNVERIFIED,
}


@dataclass(frozen=True)
class QuoteSnapshot:
    """A quote observation bound to one security, session, price and evidence set."""

    symbol: str
    quote_date: date | None
    current_price: Decimal | None
    status: str
    evidence_refs: list[dict[str, Any]]
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Quote symbol must contain six digits")
        if self.status not in QUOTE_STATUSES:
            raise ValueError("Unknown quote snapshot status")
        if any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("Quote evidence requires named references")
        if self.current_price is not None and (
            self.current_price <= 0 or not self.current_price.is_finite()
        ):
            raise ValueError("Quote price must be positive and finite")
        if self.status == QUOTE_STATUS_VERIFIED_CLOSE:
            if self.quote_date is None or self.current_price is None:
                raise ValueError("Verified close requires a quote date and price")
            if not any(ref.get("sha256") for ref in self.evidence_refs):
                raise ValueError("Verified close requires hash-addressed evidence")
        if self.status == QUOTE_STATUS_PENDING_EXTERNAL_DATA and (
            self.quote_date is not None or self.current_price is not None
        ):
            raise ValueError("A pending quote must not contain a market observation")

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, Decimal):
                return str(value)
            raise TypeError(type(value).__name__)

        return json.dumps(
            {
                "symbol": self.symbol,
                "quote_date": self.quote_date,
                "current_price": self.current_price,
                "status": self.status,
                "evidence_refs": self.evidence_refs,
                "blockers": self.blockers,
            },
            ensure_ascii=False,
            allow_nan=False,
            default=encode,
            indent=2,
        )
