"""Versioned company research, independent of orders and account state."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any


@dataclass(frozen=True)
class ResearchCase:
    symbol: str
    name: str
    as_of: date
    run_id: str
    generated_at: datetime
    research_version: str
    industry: str
    investment_path: str
    thesis: str
    return_driver: str
    mispricing_hypothesis: str
    financial_summary: dict[str, Any]
    positives: list[dict[str, Any]]
    counter_evidence: list[dict[str, Any]]
    thesis_breakers: list[dict[str, Any]]
    next_events: list[dict[str, Any]]
    evidence_status: str
    valuation_status: str
    research_status: str
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]
    quote_date: date | None
    financial_period: date | None
    missing_date_reasons: dict[str, str]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Research symbol must contain six digits")
        if not all(isinstance(x, str) and x.strip() for x in (
                self.name, self.run_id, self.research_version)):
            raise ValueError("Research identity and version are required")
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError("Research as_of must be a date")
        if self.generated_at.utcoffset() is None:
            raise ValueError("Research generation timestamp must include timezone")
        for field in ("quote_date", "financial_period"):
            value = getattr(self, field)
            if value is None and not self.missing_date_reasons.get(field):
                raise ValueError(f"Missing date needs an explanation: {field}")
            if value is not None and value > self.as_of:
                raise ValueError(f"Date exceeds research as_of: {field}")
        ids = [ref.get("id") for ref in self.evidence_refs]
        if any(not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("Evidence ids must be nonempty and unique")
        for items in (self.positives, self.counter_evidence,
                      self.thesis_breakers, self.next_events):
            for item in items:
                if item.get("kind") not in {"fact", "interpretation", "hypothesis", "gap"}:
                    raise ValueError("Research statements require an explicit kind")
                refs = item.get("evidence_refs", [])
                if not set(refs).issubset(ids):
                    raise ValueError("Research statement references unknown evidence")
                if item["kind"] in {"fact", "interpretation"} and not refs:
                    raise ValueError("Facts and interpretations require evidence")

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, Decimal):
                if not value.is_finite():
                    raise ValueError("Research numbers must be finite")
                return str(value)
            raise TypeError(f"Unsupported research value: {type(value).__name__}")

        return json.dumps(asdict(self), default=encode, ensure_ascii=False,
                          allow_nan=False, indent=2)
