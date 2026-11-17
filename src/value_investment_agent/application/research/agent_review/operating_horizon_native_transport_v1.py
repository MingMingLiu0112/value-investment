"""Strictly normalize the provider-native annual scenario transport.

The provider-native form is not an economic shortcut.  It has a different
container shape only; every value, citation and unknown remains explicit and
the established annual validator still owns economic admission.
"""
from decimal import Decimal
import json

from .operating_driver_draft_v2 import _exact
from ....domain.research.operating_driver_bridge_v1 import DRIVERS

NATIVE_DRIVER_IDS = {
    "revenue_activity_volume": "volume_change",
    "realization_mix_change": "realization_mix_change",
    "unit_cost_change": "unit_cost_change",
    "fixed_cogs_share": "fixed_cogs_share",
    "opex_change": "opex_change",
    "surcharge_ratio": "surcharge_ratio",
    "other_pretax_cny": "other_pretax_cny",
}
NATIVE_CAPITAL_IDS = {
    "capital_investment": "investment",
    "funding_access": "funding_access",
    "terminal": "terminal",
}
_RATIO_DRIVERS = set(DRIVERS) - {"other_pretax_cny"}


def _payload(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 64000:
        raise ValueError("V22_NATIVE_RESPONSE_BOUNDED_JSON_REQUIRED")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("V22_NATIVE_RESPONSE_DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("V22_NATIVE_RESPONSE_NONFINITE")

    return json.loads(text, object_pairs_hook=pairs, parse_float=Decimal,
                      parse_int=Decimal, parse_constant=constant)


def _decimal_text(value):
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("V22_NATIVE_RANGE_INVALID")
    return format(value, "f")


def _refs(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 8
            or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value)):
        raise ValueError("V22_NATIVE_CITATIONS_INVALID")
    return value


def _text(value, code):
    if not isinstance(value, str) or not value.strip() or len(value) > 600:
        raise ValueError(code)
    return value


def normalize_scenario(text, scenario, *, period_start, period_end):
    """Return the exact V21 flat scenario shape, or reject without repair."""
    if scenario not in {"bear", "base", "bull"}:
        raise ValueError("V22_NATIVE_SCENARIO_INVALID")
    if not isinstance(period_start, str) or not isinstance(period_end, str):
        raise ValueError("V22_NATIVE_PERIOD_INVALID")
    payload = _payload(text)
    _exact(payload, ("scenario", "drivers", "capital_assumptions",
                     "unit_cost_mechanism", "unit_cost_case",
                     "counter_evidence", "reopen_condition"))
    if payload["scenario"] != scenario:
        raise ValueError("V22_NATIVE_SCENARIO_MISMATCH")
    if not isinstance(payload["drivers"], list) or len(payload["drivers"]) != len(DRIVERS):
        raise ValueError("V22_NATIVE_SEVEN_DRIVERS_REQUIRED")

    drivers = {}
    for row in payload["drivers"]:
        _exact(row, ("driver_id", "value", "baseline_anchor_ids", "rationale"))
        native = row["driver_id"]
        if native not in NATIVE_DRIVER_IDS or native in drivers:
            raise ValueError("V22_NATIVE_DRIVER_ID_INVALID")
        name = NATIVE_DRIVER_IDS[native]
        _exact(row["value"], ("type", "lower", "upper", "unit"))
        if row["value"]["type"] != "range":
            raise ValueError("V22_NATIVE_DRIVER_RANGE_REQUIRED")
        expected_unit = "ratio" if name in _RATIO_DRIVERS else "CNY"
        if row["value"]["unit"] != expected_unit:
            raise ValueError("V22_NATIVE_DRIVER_UNIT_INVALID")
        drivers[name] = dict(lower=_decimal_text(row["value"]["lower"]),
                             upper=_decimal_text(row["value"]["upper"]),
                             rationale=_text(row["rationale"], "V22_NATIVE_DRIVER_RATIONALE_INVALID"),
                             evidence_ids=_refs(row["baseline_anchor_ids"]))
    if set(drivers) != set(DRIVERS):
        raise ValueError("V22_NATIVE_SEVEN_DRIVERS_REQUIRED")

    if not isinstance(payload["capital_assumptions"], list) or len(payload["capital_assumptions"]) != 3:
        raise ValueError("V22_NATIVE_CAPITAL_REQUIRED")
    capital = []
    seen = set()
    for row in payload["capital_assumptions"]:
        _exact(row, ("assumption_id", "value", "baseline_anchor_ids", "rationale"))
        native = row["assumption_id"]
        if native not in NATIVE_CAPITAL_IDS or native in seen:
            raise ValueError("V22_NATIVE_CAPITAL_ID_INVALID")
        seen.add(native)
        _exact(row["value"], ("type", "lower", "upper", "unit"))
        kind = row["value"]["type"]
        if kind == "unknown":
            if row["value"]["lower"] is not None or row["value"]["upper"] is not None:
                raise ValueError("V22_NATIVE_UNKNOWN_BOUNDS_INVALID")
            classification, lower, upper = "UNKNOWN", None, None
        elif kind == "range":
            if row["value"]["unit"] == "not_quantified":
                raise ValueError("V22_NATIVE_FORECAST_UNIT_INVALID")
            classification = "FORECAST"
            lower, upper = _decimal_text(row["value"]["lower"]), _decimal_text(row["value"]["upper"])
        else:
            raise ValueError("V22_NATIVE_CAPITAL_TYPE_INVALID")
        capital.append(dict(dimension=NATIVE_CAPITAL_IDS[native],
                            period_start=period_start, period_end=period_end,
                            classification=classification, lower=lower, upper=upper,
                            unit=row["value"]["unit"],
                            rationale=_text(row["rationale"], "V22_NATIVE_CAPITAL_RATIONALE_INVALID"),
                            evidence_ids=_refs(row["baseline_anchor_ids"])))
    if {item["dimension"] for item in capital} != {"investment", "funding_access", "terminal"}:
        raise ValueError("V22_NATIVE_CAPITAL_REQUIRED")

    _exact(payload["unit_cost_case"], ("conditional_mechanism", "mechanism_source_ids",
                                       "contrary_evidence_ids"))
    case = dict(mechanism=_text(payload["unit_cost_case"]["conditional_mechanism"],
                                "V22_NATIVE_COST_MECHANISM_INVALID"),
                source_anchor_ids=_refs(payload["unit_cost_case"]["mechanism_source_ids"]),
                contrary_evidence_ids=_refs(payload["unit_cost_case"]["contrary_evidence_ids"]),
                reopen_condition=_text(payload["reopen_condition"],
                                       "V22_NATIVE_REOPEN_CONDITION_INVALID"))
    counter = payload["counter_evidence"]
    if (not isinstance(counter, list) or not 1 <= len(counter) <= 5
            or any(not isinstance(item, str) or not item.strip() for item in counter)):
        raise ValueError("V22_NATIVE_COUNTER_EVIDENCE_INVALID")
    return dict(scenario=scenario, drivers=drivers, capital_assumptions=capital,
                unit_cost_mechanism=_text(payload["unit_cost_mechanism"],
                                          "V22_NATIVE_COST_LABEL_INVALID"),
                unit_cost_case=case, counter_evidence="; ".join(counter),
                reopen_condition=case["reopen_condition"])
