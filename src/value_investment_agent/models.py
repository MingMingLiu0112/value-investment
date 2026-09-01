from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    symbol: str
    field_name: str
    period_label: str
    value: Decimal
    unit: str
    source_name: str
    source_url: str
    published_at: datetime | None
    fetched_at: datetime
    parser_version: str
    raw_payload: bytes

    def audit_metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("raw_payload")
        result["value"] = str(result["value"])
        for key in ("published_at", "fetched_at"):
            if result[key] is not None:
                result[key] = result[key].isoformat()
        return result


@dataclass(frozen=True)
class QualityGateResult:
    symbol: str
    status: str
    reasons: list[str]
    current_price: Decimal | None
    fair_value: Decimal | None
    safety_margin: Decimal | None
    signal: str
    target_weight: Decimal
