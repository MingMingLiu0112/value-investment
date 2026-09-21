"""Transparent, review-required PE/PB reference valuation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .models import SourceRecord


MODEL_VERSION = "pe-pb-reference-v2-explicit-components"
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
    if (point.get('metadata') or {}).get('evidence_quarantine') or point.get(
            'validation_status') in {'conflict', 'rejected', 'failed'}:
        return None
    try:
        value = Decimal(str(point['value']))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value.is_finite() and value > 0 else None


def build_reference_records(points: list[dict], symbols: list[str]) -> list[SourceRecord]:
    """Build auditable PE/PB reference values from true TTM EPS and BVPS."""
    latest: dict[str, dict[str, dict]] = {symbol: {} for symbol in symbols}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for point in points:
        if point['symbol'] in latest and point['field_name'] in {'eps_ttm', 'bvps'}:
            grouped.setdefault((point['symbol'], point['field_name']), []).append(point)
    for (symbol, field), candidates in grouped.items():
        if len(candidates) == 1:
            latest[symbol][field] = candidates[0]
            continue
        timed = []
        for candidate in candidates:
            stamp = candidate.get('created_at')
            try:
                stamp = datetime.fromisoformat(stamp) if isinstance(stamp, str) else stamp
                if not isinstance(stamp, datetime) or stamp.tzinfo is None:
                    break
                timed.append((stamp, candidate))
            except ValueError:
                break
        if len(timed) != len(candidates):
            continue
        newest_time = max(stamp for stamp, _ in timed)
        newest = [row for stamp, row in timed if stamp == newest_time]
        if all(row == newest[0] for row in newest):
            latest[symbol][field] = newest[0]

    fetched_at = datetime.now(timezone.utc)
    records: list[SourceRecord] = []
    for symbol in symbols:
        eps = _decimal(latest[symbol].get("eps_ttm"))
        bvps = _decimal(latest[symbol].get("bvps"))
        if eps is None and bvps is None:
            continue
        # A reference multiple is a sector/company-specific assumption. Do not
        # silently apply a sample company's profile to a newly screened issuer.
        profile_values = PROFILES.get(symbol)
        if profile_values is None:
            continue
        target_pe, target_pb, profile = profile_values
        pe_value = (eps * target_pe).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if eps else None
        pb_value = (bvps * target_pb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if bvps else None
        input_periods = {str(latest[symbol][field].get('period_label', ''))
                        for field in ('eps_ttm', 'bvps') if field in latest[symbol]}
        comparable = (pe_value is not None and pb_value is not None
                      and len(input_periods) == 1 and '' not in input_periods)
        fair_value = ((pe_value + pb_value) / 2).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP) if comparable else None
        inputs = {
            "model_version": MODEL_VERSION,
            "eps_ttm": str(eps) if eps else None,
            "bvps": str(bvps) if bvps else None,
            "target_pe": str(target_pe),
            "target_pb": str(target_pb),
            "pe_fair_value": str(pe_value) if pe_value else None,
            "pb_fair_value": str(pb_value) if pb_value else None,
            "formula": "mean(EPS_TTM * target_PE, BVPS * target_PB) only with both same-period components",
            "component_periods": {field: str(latest[symbol][field].get('period_label', ''))
                                  for field in ('eps_ttm', 'bvps') if field in latest[symbol]},
            "combined_reference_available": comparable,
            "model_validation_status": "unvalidated_reference_assumptions",
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
                    period_label=(str(latest[symbol]['eps_ttm'].get('period_label', ''))
                                  if field_name == 'model_pe_fair_value' else
                                  str(latest[symbol]['bvps'].get('period_label', ''))
                                  if field_name == 'model_pb_fair_value' else period_label),
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


def reference_matches_current_inputs(symbol: str, model: dict, points: list[dict]) -> bool:
    """Recompute lineage without falling back to an older eligible reference."""
    if _decimal(model) is None:
        return False
    current = [p for p in points if p.get('symbol') == symbol
               and p.get('field_name') in {'eps_ttm', 'bvps'}]
    expected = next((r for r in build_reference_records(current, [symbol])
                     if r.field_name == 'model_fair_value'), None)
    if expected is None:
        return False
    lineage = (model.get('metadata') or {}).get('valuation') or {}
    expected_lineage = expected.point_metadata['valuation']
    if not all(expected_lineage['input_source_ids'].values()):
        return False
    return (lineage == expected_lineage
            and str(model.get('period_label', '')) == expected.period_label
            and _decimal(model) == expected.value)
