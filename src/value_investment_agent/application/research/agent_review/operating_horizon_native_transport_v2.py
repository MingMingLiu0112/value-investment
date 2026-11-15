"""Bounded canonicalization for a duplicate native driver with identical value.

This is a transport repair only.  It cannot choose between conflicting
numeric assumptions: those remain rejected by V1.  When a provider repeats
one driver with the exact same value, all cited anchors and explanations are
retained in one bounded canonical row before the V1 economic validator runs.
"""
import json
from decimal import Decimal

from .operating_driver_draft_v2 import _exact
from .operating_horizon_native_transport_v1 import _payload, normalize_scenario as _v1
from ....domain.research.operating_driver_bridge_v1 import DRIVERS


def _json(value):
    """Encode V1-parsed Decimals as JSON numbers without float rounding."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_json(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(_json(str(key)) + ":" + _json(item)
                              for key, item in value.items()) + "}"
    raise ValueError("V25_NATIVE_JSON_VALUE_INVALID")


def normalize_scenario(text, scenario, *, period_start, period_end):
    payload = _payload(text)
    _exact(payload, ("scenario", "drivers", "capital_assumptions",
                     "unit_cost_mechanism", "unit_cost_case",
                     "counter_evidence", "reopen_condition"))
    rows = payload["drivers"]
    if not isinstance(rows, list) or len(rows) not in (len(DRIVERS), len(DRIVERS) + 1):
        raise ValueError("V25_NATIVE_DRIVER_COUNT_INVALID")
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("V25_NATIVE_DRIVER_ROW_INVALID")
        identifier = row.get("driver_id")
        grouped.setdefault(identifier, []).append(row)
    if set(grouped) != {"revenue_activity_volume", "realization_mix_change", "unit_cost_change",
                        "fixed_cogs_share", "opex_change", "surcharge_ratio", "other_pretax_cny"}:
        raise ValueError("V25_NATIVE_DRIVER_IDS_INVALID")
    result = []
    for identifier, values in grouped.items():
        if len(values) == 1:
            result.append(values[0])
            continue
        if len(values) != 2:
            raise ValueError("V25_NATIVE_DUPLICATE_MULTIPLICITY_INVALID")
        first, second = values
        _exact(first, ("driver_id", "value", "baseline_anchor_ids", "rationale"))
        _exact(second, ("driver_id", "value", "baseline_anchor_ids", "rationale"))
        if first["value"] != second["value"]:
            raise ValueError("V25_NATIVE_DUPLICATE_VALUE_CONFLICT")
        anchors = []
        for anchor in [*first["baseline_anchor_ids"], *second["baseline_anchor_ids"]]:
            if anchor not in anchors:
                anchors.append(anchor)
        rationale = first["rationale"] + "\n" + second["rationale"]
        if len(anchors) > 8 or len(rationale) > 600:
            raise ValueError("V25_NATIVE_DUPLICATE_MERGE_BOUNDS_INVALID")
        result.append(dict(driver_id=identifier, value=first["value"],
                           baseline_anchor_ids=anchors, rationale=rationale))
    payload["drivers"] = result
    return _v1(_json(payload), scenario,
               period_start=period_start, period_end=period_end)
