"""Compare a valid intrinsic-value model with a quote without creating a trade signal."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import json
from typing import Any

from .model_validity import ModelValidity
from .valuation_models.base import ValuationResult


@dataclass(frozen=True)
class PriceBridgeResult:
    symbol: str
    valuation_date: date
    quote_date: date | None
    current_price: Decimal | None
    margin_to_bear: Decimal | None
    margin_to_base: Decimal | None
    model_validity_status: str
    quote_status: str
    bridge_status: str
    evidence_refs: list[dict[str, Any]]
    blockers: list[str]

    def __post_init__(self) -> None:
        if self.bridge_status not in {"READY", "PENDING_EXTERNAL_DATA", "STALE_MODEL", "INVALID"}:
            raise ValueError("Unknown price bridge status")
        margins = (self.margin_to_bear, self.margin_to_base)
        if self.current_price is None and any(value is not None for value in margins):
            raise ValueError("Price bridge margins require a quote")
        if self.current_price is not None and (self.current_price <= 0 or not self.current_price.is_finite()):
            raise ValueError("Price bridge quote must be positive and finite")
        if self.bridge_status == "READY" and (self.current_price is None or any(value is None for value in margins)):
            raise ValueError("READY price bridge requires quote and both margins")

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, (date, Decimal)):
                return value.isoformat() if isinstance(value, date) else str(value)
            raise TypeError(type(value).__name__)
        return json.dumps(asdict(self), ensure_ascii=False, default=encode, indent=2)


def bridge(valuation: ValuationResult, validity: ModelValidity, *, quote_date: date | None,
           current_price: Decimal | None, quote_status: str, evidence_refs: list[dict[str, Any]],
           blockers: list[str] | None = None) -> PriceBridgeResult:
    """Fail closed on price comparison while preserving an independent valuation."""
    blockers = list(blockers or [])
    if quote_date is not None and quote_date < validity.valid_from:
        return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, None, None, None,
                                 validity.status, quote_status, "INVALID", evidence_refs,
                                 blockers + ["quote date precedes model validity window"])
    if (quote_date is not None and validity.status == "VALID"
            and validity.last_material_event_check is not None
            and quote_date > validity.last_material_event_check):
        return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, None, None, None,
                                 validity.status, quote_status, "INVALID", evidence_refs,
                                 blockers + ["model validity has not been checked through the quote date"])
    if validity.status != "VALID":
        return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, None, None, None,
                                 validity.status, quote_status, "STALE_MODEL" if validity.status == "STALE" else "INVALID",
                                 evidence_refs, blockers + validity.blockers)
    if quote_date is None or current_price is None or quote_status != "verified_close":
        return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, None, None, None,
                                 validity.status, quote_status, "PENDING_EXTERNAL_DATA", evidence_refs,
                                 blockers + ["等待已验证收盘行情"])
    if valuation.bear_value is None or valuation.base_value is None:
        return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, None, None, None,
                                 validity.status, quote_status, "INVALID", evidence_refs,
                                 blockers + ["估值情景不完整"])
    return PriceBridgeResult(valuation.symbol, valuation.valuation_date, quote_date, current_price,
                             (valuation.bear_value - current_price) / valuation.bear_value,
                             (valuation.base_value - current_price) / valuation.base_value,
                             validity.status, quote_status, "READY", evidence_refs, blockers)


def pending_price_bridge_for_incomplete_valuation(
    valuation: ValuationResult,
    *,
    evidence_refs: list[dict[str, Any]],
    blockers: list[str] | None = None,
) -> PriceBridgeResult:
    """Represent a missing market comparison without inventing model validity.

    A not-ready valuation has no verified model window to compare with a quote.
    PENDING_EXTERNAL_DATA preserves the retained research result and prevents a
    market-price conclusion from being derived before the valuation exists.
    """
    if any(value is not None for value in (
            valuation.bear_value, valuation.base_value, valuation.bull_value)):
        raise ValueError("This adapter is only valid when no scenario value exists")
    return PriceBridgeResult(
        valuation.symbol,
        valuation.valuation_date,
        None,
        None,
        None,
        None,
        "UNKNOWN",
        "PENDING_EXTERNAL_DATA",
        "PENDING_EXTERNAL_DATA",
        evidence_refs,
        list(dict.fromkeys(["正式估值未形成，价格桥接不启用", *(blockers or [])])),
    )
