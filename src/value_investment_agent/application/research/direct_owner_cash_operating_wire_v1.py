"""Wire contract for three separately positioned operating review statements."""
from dataclasses import replace
import json

from .direct_owner_cash_staged_v2 import parse_staged_parent_cash_response

REVIEW_FIELDS = ("rationale", "counter_evidence", "reopen_condition")


def operating_wire_request(request):
    if not set(REVIEW_FIELDS) <= set(request.output_schema["required"]):
        return request
    original = request.output_schema
    properties = {key: value for key, value in original["properties"].items()
                  if key not in REVIEW_FIELDS}
    properties["scenario_review"] = {
        "type": "array", "minItems": 3, "maxItems": 3,
        "items": {"type": "string", "minLength": 12},
    }
    schema = dict(original, properties=properties, required=sorted(properties))
    system = request.system.replace(
        "counter_evidence, rationale and reopen_condition",
        "Within each series term, counter_evidence, rationale and reopen_condition",
    )
    return replace(request, system=system, output_schema=schema, transport_output_contract=(
        "Return one JSON object with exactly these four unique top-level keys: "
        "years, series, annual_notes, scenario_review. "
        "Use the required ten consecutive years, ten annual notes and required series. "
        "Use exactly the series keys listed in required_fields. Each series term has "
        "values, evidence_anchors, mechanism, counter_evidence and reopen_condition. "
        "Values is an array of ten decimal strings in required_years order. "
        "The scenario_review array has exactly three "
        "strings in this order: scenario rationale, counter evidence, reopen condition. "
        "Never repeat any key or emit the three review statements as named top-level fields."
    ))


def parse_operating_wire(response, *, request, source_fingerprint):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("PARENT_V2_CONFLICTING_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(response.text, object_pairs_hook=unique,
                           parse_constant=lambda _: _reject_nonfinite())
    except json.JSONDecodeError as exc:
        raise ValueError("PARENT_V2_INVALID_JSON") from exc
    wire = operating_wire_request(request)
    if not isinstance(value, dict) or set(value) != set(wire.output_schema["required"]):
        raise ValueError("PARENT_V2_STAGE_OUTPUT_SCHEMA")
    review = value.pop("scenario_review")
    if (not isinstance(review, list) or len(review) != 3
            or any(not isinstance(item, str) or len(item.strip()) < 12 for item in review)):
        raise ValueError("PARENT_V2_OPERATING_REVIEW_SCHEMA")
    value.update(zip(REVIEW_FIELDS, review, strict=True))
    return parse_staged_parent_cash_response(
        replace(response, text=json.dumps(value, ensure_ascii=False)),
        request=request, source_fingerprint=source_fingerprint,
    )


def _reject_nonfinite():
    raise ValueError("PARENT_V2_NONFINITE_JSON")
