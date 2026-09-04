"""Transparent, review-required PE/PB reference valuation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from .models import SourceRecord


MODEL_VERSION = "pe-pb-reference-v1"
MODEL_SOURCE = "Value Investment Agent PE/PB reference model"
MODEL_URL = "internal://value-investment-agent/pe-pb-reference-v1"

# Conservative, reviewable assumptions. The model output is never an approved
# recommendation and the assumptions are retained in every derived record.
PROFILES: dict[str, tuple[Decimal, Decimal, str]] = {
    "600941": (Decimal("12"), Decimal("1.50"), "telecom cash-flow"),
    "600900": (Decimal("12"), Decimal("1.50"), "regulated utility"),
    "600519": (Decimal("18"), Decimal("4.00"), "premium consumer"),
    "000333": (Decimal("15"), Decimal("2.50"), "quality appliance"),
    "600036": (Decimal("8"), Decimal("0.90"), "bank"),
    "601288": (Decimal("7"), Decimal("0.75"), "bank"),
    "601088": (Decimal("10"), Decimal("1.40"), "cyclical energy"),
    "600690": (Decimal("14"), Decimal("2.00"), "quality appliance"),
    "300750": (Decimal("20"), Decimal("3.00"), "growth manufacturing"),
    "600887": (Decimal("15"), Decimal("2.50"), "staple consumer"),
}


def _decimal(point: dict | None) -> Decimal | None:
    if not point or point.get("value") is None:
        return None
    value = Decimal(str(point["value"]))
    return value if value > 0 else None


def build_reference_records(points: list[dict], symbols: list[str]) -> list[SourceRecord]:
    """Build auditable PE/PB reference values from true TTM EPS and BVPS."""
    latest: dict[str, dict[str, dict]] = {symbol: {} for symbol in symbols}
    for point in points:
        if point["symbol"] in latest:
            latest[point["symbol"]][point["field_name"]] = point

    fetched_at = datetime.now(timezone.utc)
    records: list[SourceRecord] = []
    for symbol in symbols:
        eps = _decimal(latest[symbol].get("eps_ttm"))
        bvps = _decimal(latest[symbol].get("bvps"))
        if eps is None and bvps is None:
            continue
        target_pe, target_pb, profile = PROFILES[symbol]
        pe_value = (eps * target_pe).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if eps else None
        pb_value = (bvps * target_pb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if bvps else None
        components = [value for value in (pe_value, pb_value) if value is not None]
        fair_value = (sum(components) / len(components)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        inputs = {
            "eps_ttm": str(eps) if eps else None,
            "bvps": str(bvps) if bvps else None,
            "target_pe": str(target_pe),
            "target_pb": str(target_pb),
            "pe_fair_value": str(pe_value) if pe_value else None,
            "pb_fair_value": str(pb_value) if pb_value else None,
            "formula": "mean(EPS_TTM * target_PE, BVPS * target_PB) using available components",
            "profile": profile,
            "input_source_ids": {
                field: str(latest[symbol][field].get("source_id", ""))
                for field in ("eps_ttm", "bvps") if field in latest[symbol]
            },
        }
        raw_payload = json.dumps(inputs, sort_keys=True, ensure_ascii=True).encode("utf-8")
        period_label = max(
            str(point.get("period_label", ""))
            for point in (latest[symbol].get("eps_ttm"), latest[symbol].get("bvps")) if point
        )
        for field_name, value in (
            ("model_target_pe", target_pe),
            ("model_target_pb", target_pb),
            ("model_pe_fair_value", pe_value),
            ("model_pb_fair_value", pb_value),
            ("model_fair_value", fair_value),
        ):
            if value is None:
                continue
            records.append(
                SourceRecord(
                    symbol=symbol,
                    field_name=field_name,
                    period_label=period_label,
                    value=value,
                    unit="multiple" if field_name.startswith("model_target") else "CNY/share",
                    source_name=MODEL_SOURCE,
                    source_url=MODEL_URL,
                    published_at=None,
                    fetched_at=fetched_at,
                    parser_version=MODEL_VERSION,
                    raw_payload=raw_payload,
                    point_metadata={"valuation": inputs, "review_required": True},
                )
            )
    return records
