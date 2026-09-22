"""Compare a valid intrinsic-value model with a quote without creating a trade signal."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from .model_validity import (
    ModelValidity,
    model_validity_from_payload,
    model_validity_identity_blockers,
)
from .quote_snapshot import (
    QUOTE_STATUS_PENDING_EXTERNAL_DATA,
    QUOTE_STATUS_VERIFIED_CLOSE,
    QuoteSnapshot,
)
from .valuation_models.base import ValuationResult


BRIDGE_SCHEMA_VERSION = "c0-v1"
BRIDGE_STATUSES = {"READY", "PENDING_EXTERNAL_DATA", "STALE_MODEL", "INVALID"}


def _validate_refs(refs: list[dict[str, Any]]) -> None:
    if any(not ref.get("id") for ref in refs):
        raise ValueError("Price-bridge evidence requires named references")


def _merge_refs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for refs in groups:
        for ref in refs:
            ref_id = ref.get("id")
            if ref_id in merged and merged[ref_id] != ref:
                raise ValueError(
                    f"Evidence references with the same id must match: {ref_id}"
                )
            merged[ref_id] = dict(ref)
    return list(merged.values())


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
    quote_evidence_refs: list[dict[str, Any]]
    blockers: list[str]
    schema_version: str = BRIDGE_SCHEMA_VERSION
    model_id: str | None = None
    model_version: str | None = None
    model_as_of: date | None = None
    quote_symbol: str | None = None
    valuation_bear_value: Decimal | None = None
    valuation_base_value: Decimal | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Price-bridge symbol must contain six digits")
        if self.quote_symbol is not None and not re.fullmatch(r"[0-9]{6}", self.quote_symbol):
            raise ValueError("Price-bridge quote symbol must contain six digits")
        if self.schema_version != BRIDGE_SCHEMA_VERSION:
            raise ValueError("Unknown price-bridge schema version")
        if self.bridge_status not in BRIDGE_STATUSES:
            raise ValueError("Unknown price bridge status")
        _validate_refs(self.evidence_refs)
        _validate_refs(self.quote_evidence_refs)
        margins = (self.margin_to_bear, self.margin_to_base)
        if self.current_price is None and any(value is not None for value in margins):
            raise ValueError("Price bridge margins require a quote")
        if self.current_price is not None and (
            self.current_price <= 0 or not self.current_price.is_finite()
        ):
            raise ValueError("Price bridge quote must be positive and finite")
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("Price bridge requires a nonempty model id")
        if self.model_version is not None and not self.model_version.strip():
            raise ValueError("Price bridge requires a nonempty model version")
        if self.model_as_of is not None and not isinstance(self.model_as_of, date):
            raise ValueError("Price bridge model as-of must be a date")

        if self.bridge_status == "READY":
            if self.current_price is None or any(value is None for value in margins):
                raise ValueError("READY price bridge requires quote and both margins")
            if self.model_validity_status != "VALID":
                raise ValueError("READY price bridge requires VALID model validity")
            if self.quote_status != QUOTE_STATUS_VERIFIED_CLOSE:
                raise ValueError("READY price bridge requires a verified close")
            if self.quote_date is None or self.quote_symbol != self.symbol:
                raise ValueError("READY price bridge requires the quote identity")
            if self.model_as_of != self.valuation_date:
                raise ValueError("READY price bridge model as-of must match the valuation date")
            if not self.model_id or not self.model_version or self.model_as_of is None:
                raise ValueError("READY price bridge requires bound model identity")
            if not self.quote_evidence_refs or not any(
                ref.get("sha256") for ref in self.quote_evidence_refs
            ):
                raise ValueError("READY price bridge requires verified quote evidence")
            if self.valuation_bear_value is None or self.valuation_base_value is None:
                raise ValueError("READY price bridge requires bound valuation scenarios")
            expected_bear = (
                self.valuation_bear_value - self.current_price
            ) / self.valuation_bear_value
            expected_base = (
                self.valuation_base_value - self.current_price
            ) / self.valuation_base_value
            if (
                self.margin_to_bear != expected_bear
                or self.margin_to_base != expected_base
            ):
                raise ValueError("Price bridge margins must be recomputed from bound inputs")

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, Decimal):
                return str(value)
            raise TypeError(type(value).__name__)

        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            allow_nan=False,
            default=encode,
            indent=2,
        )


def _rejected_bridge(
    valuation: ValuationResult,
    validity: ModelValidity,
    quote: QuoteSnapshot,
    bridge_status: str,
    blockers: list[str],
) -> PriceBridgeResult:
    return PriceBridgeResult(
        symbol=valuation.symbol,
        valuation_date=valuation.valuation_date,
        quote_date=quote.quote_date if bridge_status == "READY" else None,
        current_price=None,
        margin_to_bear=None,
        margin_to_base=None,
        model_validity_status=validity.status,
        quote_status=quote.status,
        bridge_status=bridge_status,
        evidence_refs=_merge_refs(validity.evidence_refs, quote.evidence_refs),
        quote_evidence_refs=list(quote.evidence_refs),
        blockers=list(dict.fromkeys(blockers)),
        model_id=validity.model_id,
        model_version=valuation.model_version,
        model_as_of=validity.model_as_of,
        quote_symbol=quote.symbol,
        valuation_bear_value=valuation.bear_value,
        valuation_base_value=valuation.base_value,
    )


def bridge_with_quote(
    valuation: ValuationResult,
    validity: ModelValidity,
    quote: QuoteSnapshot,
    *,
    blockers: list[str] | None = None,
) -> PriceBridgeResult:
    """Fail closed on price comparison while preserving an independent valuation."""
    if not isinstance(valuation, ValuationResult):
        raise ValueError("Price bridge requires a ValuationResult")
    if not isinstance(validity, ModelValidity):
        raise ValueError("Price bridge requires a ModelValidity")
    if not isinstance(quote, QuoteSnapshot):
        raise ValueError("Price bridge requires a QuoteSnapshot")

    base_blockers = list(blockers or [])
    identity_blockers = model_validity_identity_blockers(validity, valuation)
    if quote.symbol != valuation.symbol:
        identity_blockers.append("valuation and quote symbols differ")
    if identity_blockers:
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "INVALID",
            [*base_blockers, *identity_blockers],
        )

    if quote.status == QUOTE_STATUS_PENDING_EXTERNAL_DATA:
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "PENDING_EXTERNAL_DATA",
            [*base_blockers, "等待已验证收盘行情"],
        )

    if quote.status != QUOTE_STATUS_VERIFIED_CLOSE:
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "INVALID",
            [*base_blockers, "报价未通过核验"],
        )

    if quote.quote_date is not None and quote.quote_date < validity.valid_from:
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "INVALID",
            [*base_blockers, "quote date precedes model validity window"],
        )
    if (
        quote.quote_date is not None
        and validity.status == "VALID"
        and validity.last_material_event_check is not None
        and quote.quote_date > validity.last_material_event_check
    ):
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "INVALID",
            [
                *base_blockers,
                "model validity has not been checked through the quote date",
            ],
        )

    if validity.status != "VALID":
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "STALE_MODEL" if validity.status == "STALE" else "INVALID",
            [*base_blockers, *validity.blockers],
        )

    if (
        quote.quote_date is None
        or quote.current_price is None
        or valuation.bear_value is None
        or valuation.base_value is None
    ):
        return _rejected_bridge(
            valuation,
            validity,
            quote,
            "INVALID",
            [*base_blockers, "估值情景或已验证报价不完整"],
        )

    return PriceBridgeResult(
        symbol=valuation.symbol,
        valuation_date=valuation.valuation_date,
        quote_date=quote.quote_date,
        current_price=quote.current_price,
        margin_to_bear=(
            valuation.bear_value - quote.current_price
        ) / valuation.bear_value,
        margin_to_base=(
            valuation.base_value - quote.current_price
        ) / valuation.base_value,
        model_validity_status=validity.status,
        quote_status=quote.status,
        bridge_status="READY",
        evidence_refs=_merge_refs(validity.evidence_refs, quote.evidence_refs),
        quote_evidence_refs=list(quote.evidence_refs),
        blockers=list(dict.fromkeys(base_blockers)),
        model_id=validity.model_id,
        model_version=valuation.model_version,
        model_as_of=validity.model_as_of,
        quote_symbol=quote.symbol,
        valuation_bear_value=valuation.bear_value,
        valuation_base_value=valuation.base_value,
    )


def bridge(
    valuation: ValuationResult,
    validity: ModelValidity,
    *,
    quote_date: date | None,
    current_price: Decimal | None,
    quote_status: str,
    evidence_refs: list[dict[str, Any]],
    blockers: list[str] | None = None,
) -> PriceBridgeResult:
    """Compatibility adapter that builds a QuoteSnapshot before applying C0 checks."""
    if quote_status != QUOTE_STATUS_PENDING_EXTERNAL_DATA:
        try:
            quote = QuoteSnapshot(
                symbol=valuation.symbol,
                quote_date=quote_date,
                current_price=current_price,
                status=quote_status,
                evidence_refs=list(evidence_refs),
            )
        except ValueError as error:
            return _rejected_bridge(
                valuation,
                validity,
                QuoteSnapshot(
                    symbol=valuation.symbol,
                    quote_date=quote_date,
                    current_price=current_price,
                    status=QUOTE_STATUS_PENDING_EXTERNAL_DATA
                    if quote_date is None and current_price is None
                    else "unverified",
                    evidence_refs=list(evidence_refs),
                ),
                "INVALID",
                [*(blockers or []), str(error)],
            )
    else:
        quote = QuoteSnapshot(
            symbol=valuation.symbol,
            quote_date=None,
            current_price=None,
            status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
            evidence_refs=list(evidence_refs),
        )
    return bridge_with_quote(valuation, validity, quote, blockers=blockers)


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
    if any(
        value is not None
        for value in (valuation.bear_value, valuation.base_value, valuation.bull_value)
    ):
        raise ValueError("This adapter is only valid when no scenario value exists")
    return PriceBridgeResult(
        symbol=valuation.symbol,
        valuation_date=valuation.valuation_date,
        quote_date=None,
        current_price=None,
        margin_to_bear=None,
        margin_to_base=None,
        model_validity_status="UNKNOWN",
        quote_status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
        bridge_status="PENDING_EXTERNAL_DATA",
        evidence_refs=list(evidence_refs),
        quote_evidence_refs=[],
        blockers=list(
            dict.fromkeys(["正式估值未形成，价格桥接不启用", *(blockers or [])])
        ),
        model_id=None,
        model_version=valuation.model_version,
        model_as_of=valuation.valuation_date,
        quote_symbol=valuation.symbol,
        valuation_bear_value=None,
        valuation_base_value=None,
    )


def price_bridge_binding_blockers(
    valuation: ValuationResult,
    price_bridge: PriceBridgeResult,
) -> list[str]:
    """Check that a serialized or directly constructed bridge still matches the valuation."""
    blockers: list[str] = []
    if price_bridge.symbol != valuation.symbol:
        blockers.append("price bridge and valuation symbols differ")
    if price_bridge.valuation_date != valuation.valuation_date:
        blockers.append("price bridge valuation date does not match the valuation")
    if price_bridge.quote_symbol not in (None, valuation.symbol):
        blockers.append("price bridge quote is bound to another security")
    if price_bridge.model_version not in (None, valuation.model_version):
        blockers.append("price bridge model version does not match the valuation")
    if (
        price_bridge.model_as_of is not None
        and price_bridge.model_as_of != valuation.valuation_date
    ):
        blockers.append("price bridge model as-of does not match the valuation date")
    known_model_ids = {
        str(ref.get("sha256"))
        for ref in valuation.evidence_refs
        if ref.get("sha256")
    }
    known_model_ids.add(valuation.model_version)
    if price_bridge.model_id is not None and price_bridge.model_id not in known_model_ids:
        blockers.append("price bridge model id does not match the valuation snapshot")
    if price_bridge.bridge_status == "READY":
        if price_bridge.valuation_bear_value is None or price_bridge.valuation_base_value is None:
            blockers.append("READY bridge has no bound valuation scenarios")
        elif price_bridge.current_price is None:
            blockers.append("READY bridge has no bound quote price")
        else:
            expected_bear = (
                price_bridge.valuation_bear_value - price_bridge.current_price
            ) / price_bridge.valuation_bear_value
            expected_base = (
                price_bridge.valuation_base_value - price_bridge.current_price
            ) / price_bridge.valuation_base_value
            if (
                price_bridge.margin_to_bear != expected_bear
                or price_bridge.margin_to_base != expected_base
            ):
                blockers.append("READY bridge margins do not recompute from bound inputs")
    return blockers


def validate_price_bridge_binding(
    valuation: ValuationResult,
    price_bridge: PriceBridgeResult,
) -> None:
    blockers = price_bridge_binding_blockers(valuation, price_bridge)
    if blockers:
        raise ValueError(
            "Price bridge is not bound to the valuation: " + "; ".join(blockers)
        )


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date string") from exc


def _required_date(value: object, field: str) -> date:
    parsed = _optional_date(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal string") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal string")
    return number


def price_bridge_from_payload(
    valuation: ValuationResult,
    payload: dict[str, Any],
    *,
    model_validity_payload: dict[str, Any] | None = None,
) -> PriceBridgeResult:
    """Restore a bridge while validating its binding to the supplied valuation."""
    legacy = payload.get("schema_version") is None
    schema = payload.get("schema_version", BRIDGE_SCHEMA_VERSION)
    if schema != BRIDGE_SCHEMA_VERSION:
        raise ValueError(f"Unknown price-bridge schema: {schema}")

    validity = (
        model_validity_from_payload(model_validity_payload)
        if model_validity_payload is not None
        else None
    )
    bridge_status = str(payload["bridge_status"])
    if legacy and bridge_status == "READY" and validity is None:
        raise ValueError("Legacy READY bridge requires its model-validity payload")

    base_blockers = list(payload.get("blockers", []))
    if legacy:
        base_blockers.append("legacy_price_bridge_contract_revalidated")
        model_id = validity.model_id if validity is not None else None
        model_as_of = (
            validity.model_as_of
            if validity is not None
            else valuation.valuation_date
        )
        quote_symbol = str(payload.get("symbol", valuation.symbol))
        quote_evidence_refs = list(payload.get("evidence_refs", []))
        evidence_refs = _merge_refs(
            payload.get("evidence_refs", []),
            validity.evidence_refs if validity is not None else [],
        )
    else:
        model_id = payload.get("model_id")
        model_as_of = _optional_date(payload.get("model_as_of"), "model_as_of")
        quote_symbol = payload.get("quote_symbol")
        quote_evidence_refs = list(payload.get("quote_evidence_refs", []))
        evidence_refs = list(payload.get("evidence_refs", []))

    price_bridge = PriceBridgeResult(
        symbol=str(payload["symbol"]),
        valuation_date=_required_date(payload["valuation_date"], "valuation_date"),
        quote_date=_optional_date(payload.get("quote_date"), "quote_date"),
        current_price=_optional_decimal(payload.get("current_price"), "current_price"),
        margin_to_bear=_optional_decimal(payload.get("margin_to_bear"), "margin_to_bear"),
        margin_to_base=_optional_decimal(payload.get("margin_to_base"), "margin_to_base"),
        model_validity_status=str(payload["model_validity_status"]),
        quote_status=str(payload["quote_status"]),
        bridge_status=bridge_status,
        evidence_refs=evidence_refs,
        quote_evidence_refs=quote_evidence_refs,
        blockers=base_blockers,
        model_id=model_id,
        model_version=(
            valuation.model_version if legacy else payload.get("model_version")
        ),
        model_as_of=model_as_of,
        quote_symbol=quote_symbol,
        valuation_bear_value=(
            valuation.bear_value
            if legacy
            else _optional_decimal(payload.get("valuation_bear_value"), "valuation_bear_value")
        ),
        valuation_base_value=(
            valuation.base_value
            if legacy
            else _optional_decimal(payload.get("valuation_base_value"), "valuation_base_value")
        ),
    )

    binding_blockers = price_bridge_binding_blockers(valuation, price_bridge)
    if validity is not None:
        binding_blockers.extend(model_validity_identity_blockers(validity, valuation))
    if binding_blockers:
        raise ValueError(
            "Price-bridge payload is not bound to the valuation: "
            + "; ".join(dict.fromkeys(binding_blockers))
        )
    return price_bridge
