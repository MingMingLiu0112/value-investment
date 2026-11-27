"""Versioned shape adapter and read-only diagnostic for flat Bear terminal replies."""
from dataclasses import replace
import json
from pathlib import PurePosixPath
import re

from .agent_review import parent_cash_task_v3 as native
from .agent_review.task_execution_v1 import _bytes, _hash


WIRE = "NOTE_GRID_FLAT_TERMINAL_V2"
_STAGE = "bear.terminal"
_TERM_METADATA = {"evidence_anchors", "mechanism", "counter_evidence", "reopen_condition"}
_DIGEST = re.compile(r"[a-f0-9]{64}")
_TASK_ID = re.compile(r"rt-[a-f0-9]{32}")


def _read_flat(text):
    if not isinstance(text, str) or len(text) > 100_000:
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_INVALID_JSON")
    try:
        packet = json.loads(text, object_pairs_hook=native._identical_prose_duplicate_only)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_INVALID_JSON") from error
    fields = {"cost_of_equity", "policy", "remaining_scheduled_events", "max_transition_years",
              "financing", "rationale", "counter_evidence", "reopen_condition"}
    if not isinstance(packet, dict) or set(packet) != fields or not isinstance(packet["policy"], dict):
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_FIELDS_INVALID")
    return packet


def _normalize_terms(packet):
    counts = {"value": 0, "values": 0}
    for term in (packet["cost_of_equity"], *packet["policy"].values()):
        if not isinstance(term, dict):
            raise ValueError("PARENT_DRAFT_TERM_SOURCE_INVALID")
        variant = set(term) - _TERM_METADATA
        if not _TERM_METADATA <= set(term) or variant not in ({"value"}, {"values"}):
            raise ValueError("PARENT_DRAFT_TERM_SOURCE_INVALID")
        key = next(iter(variant))
        value = [term[key]] if key == "value" else term[key]
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], str):
            raise ValueError("PARENT_DRAFT_TERM_SOURCE_INVALID")
        counts[key] += 1
        if key == "value":
            term["values"] = [term.pop("value")]
    return counts


def normalize_bear_terminal_response(response):
    """Return native nested wire for parsing; persist the original response separately."""
    if response.tool_calls:
        raise ValueError("PARENT_V3_TERMINAL_DRIVER_TOOL_CALL_FORBIDDEN")
    packet = _read_flat(response.text)
    _normalize_terms(packet)
    normalized = replace(response, text=json.dumps(packet, ensure_ascii=False, separators=(",", ":")))
    return native._unpack_flat_terminal_review_response(normalized)


def sealed_bear_terminal_diagnostic(service, task_id, *, wire_request):
    """Project only the failed stage and verified wire shape from a settled response."""
    if not _TASK_ID.fullmatch(task_id):
        return None
    directory = service._directory(task_id)
    with service._lock(directory):
        spec, state, _ = service._load(task_id)
        if (state["status"] != "FAILED" or not (state.get("error_code") or "").startswith("BEAR_TERMINAL_")
                or _STAGE in state["responses"] or "bear.policy" not in state["responses"]):
            return None
        settled = {key for key, row in state["reservations"].items()
                   if row.get("scenario") == _STAGE and row.get("status") == "SETTLED"}
        bindings = []
        for binding in state.get("returned_responses", ()):
            path = PurePosixPath(binding["path"])
            if path.parent.as_posix() != directory.relative_to(service.root).as_posix():
                continue
            reservation = path.name.removeprefix("response-").removesuffix(".json")
            if (_DIGEST.fullmatch(reservation) and reservation in settled
                    and path.name == f"response-{reservation}.json"):
                bindings.append(binding)
        if len(bindings) != 1:
            return None
        binding = bindings[0]
        try:
            packet = service._bound(binding)
        except (OSError, ValueError):
            return None
    if (not isinstance(packet, dict) or packet.get("action") != "no_order" or packet.get("scenario") != _STAGE
            or packet.get("source_fingerprint") != spec["source_fingerprint"]
            or packet.get("request_sha256") != _hash(_bytes(wire_request.__dict__))):
        return None
    response = packet.get("response")
    if not isinstance(response, dict):
        return None
    counts = None
    if response.get("tool_calls"):
        shape = "TOOL_CALL_FORBIDDEN"
    else:
        try:
            counts = _normalize_terms(_read_flat(response.get("text")))
        except ValueError as error:
            shape = str(error)
        else:
            shape = "FLAT_SINGLETON_TERMS"
    return dict(status="REJECTED_RESPONSE_DIAGNOSTIC_ONLY", stage=_STAGE, wire_shape=shape,
                term_shape_counts=counts, response_sha256=binding["sha256"], action="no_order",
                formal_eligibility=False)
