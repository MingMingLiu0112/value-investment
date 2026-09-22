"""A serializable intrinsic-value result; market prices belong to PriceBridge."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import json
import re
from typing import Any


@dataclass(frozen=True)
class ValuationResult:
    symbol: str
    model_type: str
    valuation_date: date
    bear_value: Decimal | None
    base_value: Decimal | None
    bull_value: Decimal | None
    confidence: str
    assumptions: dict[str, Any]
    sensitivities: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    blockers: list[str]
    status: str
    model_version: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Valuation symbol must contain six digits")
        if not self.model_type.strip() or self.confidence not in {"高", "中", "低"}:
            raise ValueError("Valuation model type and confidence are required")
        values = (self.bear_value, self.base_value, self.bull_value)
        if any(value is not None and (not value.is_finite() or value <= 0) for value in values):
            raise ValueError("Scenario values must be positive finite Decimals when supplied")
        if all(value is not None for value in values) and not self.bear_value <= self.base_value <= self.bull_value:
            raise ValueError("Scenario values must be bear <= base <= bull")
        if not self.evidence_refs or any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("Valuation requires named evidence references")
        if not self.model_version.strip():
            raise ValueError("Valuation model version is required")
        if self.status not in {"not_ready", "conditional_research_only", "approved_research_only", "ready"}:
            raise ValueError("Unknown valuation status")

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, (date, Decimal)):
                return value.isoformat() if isinstance(value, date) else str(value)
            raise TypeError(type(value).__name__)
        return json.dumps(asdict(self), ensure_ascii=False, allow_nan=False, default=encode, indent=2)
