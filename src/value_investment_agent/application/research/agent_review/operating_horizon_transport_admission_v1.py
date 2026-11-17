"""Admit one narrowly repairable provider transport artifact without altering it.

The provider occasionally appends one closing brace to an otherwise complete JSON
object.  This module never changes the stored response: it creates a derived,
hash-bound normalized view only after proving that the suffix is exactly one
closing brace and that JSON parsing consumes the whole retained object.
"""
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path

from . import operating_horizon_task_v2 as v2
from . import operating_horizon_task_v3 as v3
from .task_execution_v1 import _bytes, _hash
from ....infrastructure.agent_runtime.provider import LLMResponse

VERSION = "operating-horizon-transport-admission-v1"


def _decoder():
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("TRANSPORT_DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    def constant(value):
        raise ValueError("TRANSPORT_NONFINITE_JSON_NUMBER")

    return json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant)


def normalize_one_extra_closing_brace(text):
    """Return a valid byte-identical object span, never a rewritten object."""
    if not isinstance(text, str) or not 1 <= len(text) <= 65536:
        raise ValueError("TRANSPORT_RESPONSE_BOUNDS_INVALID")
    leading = len(text) - len(text.lstrip(" \t\r\n"))
    raw = text[leading:]
    if not raw.startswith("{"):
        raise ValueError("TRANSPORT_JSON_PREFIX_INVALID")
    _, end = _decoder().raw_decode(raw)
    if raw[end:].strip(" \t\r\n") != "}":
        raise ValueError("TRANSPORT_NOT_EXACT_ONE_EXTRA_CLOSING_BRACE")
    normalized = text[:leading] + raw[:end]
    # Full parse is deliberately separate from raw_decode; it rejects trailing
    # bytes, duplicate keys and non-finite constants in the derived payload.
    _decoder().decode(normalized)
    return normalized


def _bound(service, binding):
    return service._bound(binding)


def admit(*, root, original_task_id, repair_task_id, now):
    """Return a source- and budget-verified, still-unapproved research result."""
    original_service = v2.OperatingHorizonTaskService(root)
    repair_service = v3.OperatingHorizonTaskService(root)
    with original_service._lock(original_service._directory(original_task_id)):
        original_spec, original_state, original_pin = original_service._load(original_task_id)
    with repair_service._lock(repair_service._directory(repair_task_id)):
        repair_spec, repair_state, repair_pin = repair_service._load(repair_task_id)
    if (original_state["status"] != "FAILED" or repair_state["status"] != "FAILED"
            or not original_state.get("response_binding") or not repair_state.get("response_binding")):
        raise ValueError("TRANSPORT_ADMISSION_REQUIRES_RETAINED_FAILED_RESPONSES")
    if repair_spec["repair_of"]["task_id"] != original_task_id:
        raise ValueError("TRANSPORT_REPAIR_ORIGINAL_MISMATCH")
    original_packet = _bound(original_service, original_state["response_binding"])
    repair_packet = _bound(repair_service, repair_state["response_binding"])
    original_response = LLMResponse(**original_packet["response"])
    repair_response = LLMResponse(**repair_packet["response"])
    normalized_original = normalize_one_extra_closing_brace(original_response.text)
    normalized_repair = normalize_one_extra_closing_brace(repair_response.text)
    # The paid repair request cannot introduce any semantic change.
    if _decoder().decode(normalized_original) != _decoder().decode(normalized_repair):
        raise ValueError("TRANSPORT_REPAIR_SEMANTICS_CHANGED")
    context = original_service._context(original_spec)
    original_service._usage(original_response, original_service._request(original_spec, context),
                            original_spec["config"]["model_id"])
    original_service._verify_settlement(original_spec, original_state, original_response)
    repair_service._usage(repair_response, repair_service._request(repair_spec, context),
                          repair_spec["config"]["model_id"])
    repair_service._verify_settlement(repair_spec, repair_state, repair_response)
    generated_at = datetime.fromisoformat(original_packet["generated_at"])
    if generated_at.utcoffset() is None or generated_at > now:
        raise ValueError("TRANSPORT_RESPONSE_AFTER_CONSUMPTION_CUTOFF")
    normalized_response = replace(original_response, text=normalized_original)
    result = v2.draft.validate_response(normalized_response, context,
                                        original_spec["years"], generated_at)
    if result.get("action") != "no_order" or result.get("formal_eligibility") is not False:
        raise ValueError("TRANSPORT_ADMISSION_BOUNDARY_INVALID")
    binding = dict(
        original_task_id=original_task_id,
        original_record_binding=original_pin,
        original_response_binding=original_state["response_binding"],
        repair_task_id=repair_task_id,
        repair_record_binding=repair_pin,
        repair_response_binding=repair_state["response_binding"],
        original_response_sha256=_hash(original_response.text.encode("utf-8")),
        normalized_response_sha256=_hash(normalized_original.encode("utf-8")),
        repair_response_sha256=_hash(repair_response.text.encode("utf-8")),
        implementation_sha256=_hash(Path(__file__).read_bytes()),
    )
    result.update(
        schema_version=VERSION,
        status="TRANSPORT_NORMALIZED_UNAPPROVED_ECONOMIC_REVIEW_REQUIRED",
        transport_status="EXACT_ONE_EXTRA_CLOSING_BRACE_NORMALIZED",
        transport_binding=binding,
        raw_response_preserved=True,
        formal_eligibility=False,
        main_range_adopted=False,
        valuation_produced=False,
        condition_price=None,
    )
    return result
