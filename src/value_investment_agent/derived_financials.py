"""Derived financial facts backed by retained verified statutory inputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from .models import SourceRecord


DERIVATION_VERSION = "verified-financial-derivations-v5-explicit-profit-scope"
DERIVATION_SOURCE = "Value Investment Agent verified financial derivations"
DERIVATION_URL = "internal://value-investment-agent/verified-financial-derivations-v1"
MONEY_UNITS = {'CNY': Decimal('1'), 'CNY 10K': Decimal('10000'), 'CNY 100M': Decimal('100000000')}
RATIO_SCOPES = {
    'net_margin': 'parent_attributable_net_income / operating_revenue',
    'operating_cash_flow_to_net_income': 'consolidated_operating_cash_flow / parent_attributable_net_income',
}


def _input_facts(inputs: dict[str, dict]) -> dict:
    return {name: {'source_id': str(p.get('source_id', '')), 'value': str(p['value']),
                   'unit': p.get('unit'), 'period': str(p['period_label']),
                   **({'data_point_id': str(p['data_point_id'])} if p.get('data_point_id') else {})}
            for name, p in inputs.items()}


def _accepted(point: dict | None) -> bool:
    return bool(
        point
        and point.get("validation_status") == "verified"
        and not (point.get("metadata") or {}).get("evidence_quarantine")
        and (point.get("metadata") or {}).get("automatic_cross_source_verification") is True
    )


def _record(symbol: str, field_name: str, value: Decimal, unit: str, period: str, inputs: dict[str, dict], formula: str) -> SourceRecord:
    source_ids = {name: str(point.get("source_id", "")) for name, point in inputs.items()}
    ratio_scope = RATIO_SCOPES.get(field_name)
    payload = {
        "field_name": field_name,
        "value": str(value),
        "unit": unit,
        "period": period,
        "formula": formula,
        "input_source_ids": source_ids,
        "input_facts": _input_facts(inputs),
        "ratio_scope": ratio_scope,
    }
    return SourceRecord(
        symbol=symbol,
        field_name=field_name,
        period_label=period,
        value=value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        unit=unit,
        source_name=DERIVATION_SOURCE,
        source_url=DERIVATION_URL,
        published_at=None,
        fetched_at=datetime.now(timezone.utc),
        parser_version=DERIVATION_VERSION,
        raw_payload=json.dumps(payload, ensure_ascii=True, sort_keys=True).encode(),
        point_metadata={
            "automatic_cross_source_verification": True,
            "derivation_formula": formula,
            "input_source_ids": source_ids,
            "input_facts": _input_facts(inputs),
            "ratio_scope": ratio_scope,
            "verification_method": "derived_from_official_pdf_facts_with_independent_cross_source_matches",
        },
    )


def build_verified_derivations(points: list[dict], symbols: list[str]) -> list[SourceRecord]:
    """Create ratio and total facts only from same-period verified input facts."""
    by_symbol: dict[str, dict[str, dict]] = {symbol: {} for symbol in symbols}
    for point in points:
        if point["symbol"] in by_symbol:
            previous = by_symbol[point['symbol']].get(point['field_name'])
            if previous is not None and previous != point:
                raise ValueError('Resolve financial input versions before derivation: '
                                 + point['symbol'] + '/' + point['field_name'])
            by_symbol[point["symbol"]][point["field_name"]] = point

    records: list[SourceRecord] = []
    formulas = (
        ("gross_margin", ("revenue", "operating_cost"), "percent", "(revenue - operating_cost) / revenue * 100"),
        ("net_margin", ("net_income", "revenue"), "percent", "net_income / revenue * 100"),
        ("operating_cash_flow_to_net_income", ("operating_cash_flow", "net_income"), "percent", "operating_cash_flow / net_income * 100"),
        ("debt_ratio", ("total_liabilities", "total_assets"), "percent", "total_liabilities / total_assets * 100"),
        ("borrowings_bonds_subtotal", ("short_term_borrowings", "current_portion_long_term_debt", "long_term_borrowings", "bonds_payable"), "CNY", "short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable"),
    )
    for symbol, fields in by_symbol.items():
        for output_field, input_fields, unit, formula in formulas:
            inputs = {name: fields.get(name) for name in input_fields}
            if not all(_accepted(point) for point in inputs.values()):
                continue
            periods = {str(point["period_label"]) for point in inputs.values()}
            if len(periods) != 1:
                continue
            existing = fields.get(output_field)
            if (existing and _accepted(existing) and str(existing.get("period_label")) in periods
                and (existing.get("metadata") or {}).get("derivation_formula") == formula
                and (existing.get("metadata") or {}).get("ratio_scope") == RATIO_SCOPES.get(output_field)
                and (existing.get("metadata") or {}).get("input_facts") == _input_facts(inputs)):
                continue
            if any(point.get('unit') not in MONEY_UNITS for point in inputs.values()):
                continue
            values = {name: Decimal(str(point["value"])) * MONEY_UNITS[point['unit']] for name, point in inputs.items()}
            if not all(value.is_finite() for value in values.values()):
                continue
            if output_field == "gross_margin":
                if values["revenue"] <= 0:
                    continue
                value = (values["revenue"] - values["operating_cost"]) / values["revenue"] * Decimal("100")
            elif output_field == "net_margin":
                if values["revenue"] <= 0:
                    continue
                value = values["net_income"] / values["revenue"] * Decimal("100")
            elif output_field == "operating_cash_flow_to_net_income":
                if values["net_income"] <= 0:
                    continue
                value = values["operating_cash_flow"] / values["net_income"] * Decimal("100")
            elif output_field == "debt_ratio":
                if values["total_assets"] <= 0:
                    continue
                value = values["total_liabilities"] / values["total_assets"] * Decimal("100")
            else:
                value = sum(values.values())
            records.append(_record(symbol, output_field, value, unit, periods.pop(), inputs, formula))
    return records
