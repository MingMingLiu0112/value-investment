"""Offline, source-bound citation-only repair for a sealed failed V7 annual stage.

This contract prepares a bounded request but never invokes a provider or mutates
the original task. A separate authorized runner may account for a later call.
"""
from copy import deepcopy
from datetime import datetime
import hashlib

from . import operating_draft_v1 as common
from . import operating_horizon_draft_v2 as annual
from . import operating_horizon_split_v7 as v7
from . import operating_driver_draft_v2 as drivers
from .operating_driver_draft_v2 import _payload, _exact
from ....infrastructure.agent_runtime.provider import LLMRequest, LLMResponse

VERSION = "operating-horizon-citation-repair-v1"
MAX_REPLACEMENTS = 3


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slots(node, prefix=()):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_ids":
                if not isinstance(value, list):
                    raise ValueError("REPAIR_CITATIONS_NOT_LIST")
                for index, ref in enumerate(value):
                    yield prefix + (key, index), ref, node.get("rationale")
            else:
                yield from _slots(value, prefix + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _slots(value, prefix + (index,))


def _sealed(service, task_id):
    """Reopen original files through V7's source, hash, PIT and budget checks."""
    spec, state, _ = service._load(task_id)
    if (spec.get("task_contract") != "operating-horizon-task-v7-split"
            or spec.get("action") != "no_order" or state.get("status") != "FAILED"
            or state.get("stage_validated") or state.get("stage_responses", {}).keys() != {"annual"}
            or state.get("stage_intents", {}).keys() != {"annual"}):
        raise ValueError("REPAIR_FAILED_V7_ANNUAL_ONLY")
    context = service._context(spec)
    packet = service._packet(spec, state, "annual")
    request = v7.build_annual_request(context, spec["years"],
        source_binding=service._source_binding(spec),
        max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
    from .task_execution_v1 import _bytes, _hash as bytes_hash
    if bytes_hash(_bytes(request.__dict__)) != packet["request_sha256"]:
        raise ValueError("REPAIR_ORIGINAL_REQUEST_CHANGED")
    response = LLMResponse(**packet["response"])
    service._usage(response, request, spec["config"]["model_id"])
    service._verify_stage_settlement(spec, state, "annual", packet)
    generated = datetime.fromisoformat(packet["generated_at"])
    if generated.utcoffset() is None or response.model_id != spec["config"]["model_id"]:
        raise ValueError("REPAIR_ORIGINAL_RESPONSE_INVALID")
    # The old validator supplies the source/PIT check even though the citation
    # error prevents the complete annual result from being accepted.
    common._context(drivers.legacy_context(context))
    if any(datetime.fromisoformat(row["available_at"]) > generated for row in context["evidence"]):
        raise ValueError("REPAIR_FUTURE_SOURCE")
    original = _payload(response.text)
    _exact(original, ("years",))
    _exact(original["years"], (str(spec["years"][0]),))
    admissible = {row["id"] for row in context["evidence"]}
    invalid = [(path, ref, rationale) for path, ref, rationale in _slots(original)
               if type(ref) is not str or ref not in admissible]
    if not 1 <= len(invalid) <= MAX_REPLACEMENTS or any(
            not isinstance(reason, str) or not reason.strip() for _, _, reason in invalid):
        raise ValueError("REPAIR_INVALID_CITATION_BOUNDS")
    return spec, context, response, generated, original, admissible, invalid


def build_request(service, task_id, *, max_completion_tokens=512):
    spec, context, response, _, _, admissible, invalid = _sealed(service, task_id)
    if not 1 <= max_completion_tokens <= min(512, spec["config"]["max_completion_tokens_cap"]):
        raise ValueError("REPAIR_TOKEN_CAP")
    problems = [{"path": list(path), "invalid_id": ref, "original_rationale": rationale}
                for path, ref, rationale in invalid]
    source = {row["id"]: {key: row[key] for key in
        ("text", "period", "scope", "unit", "source_id", "pdf_sha256", "available_at")}
              for row in context["evidence"]}
    user = common._canonical({"original_task_id": task_id,
        "original_response_sha256": _hash(response.text), "problems": problems,
        "admissible_evidence": source})
    if len(user) > 64000:
        raise ValueError("REPAIR_CONTEXT_OVER_BUDGET")
    schema = {"type": "object", "additionalProperties": False,
        "required": ["version", "original_response_sha256", "replacements"],
        "properties": {"version": {"const": VERSION, "type": "string"},
            "original_response_sha256": {"const": _hash(response.text), "type": "string"},
            "replacements": {"type": "array", "minItems": len(invalid),
                "maxItems": len(invalid), "items": {"type": "object",
                    "additionalProperties": False,
                    "required": ["path", "invalid_id", "replacement_id", "support_quote"],
                    "properties": {"path": {"type": "array"},
                        "invalid_id": {"type": "string"},
                        "replacement_id": {"type": "string", "enum": sorted(admissible)},
                        "support_quote": {"type": "string", "minLength": 8,
                            "maxLength": 240}}}}}}
    return LLMRequest(role="FUNDAMENTAL", system=(VERSION +
        ": Replace only the listed invalid evidence IDs. Preserve every numeric bound, "
        "classification, unit, rationale and all other original response fields byte-for-byte "
        "in the reconstructed object. Give an exact relevant quote from the selected source. "
        "If no admissible source supports the original rationale, "
        "do not invent an ID; the repair must fail. Return only the replacement mapping. "
        "This is unapproved research; action=no_order."),
        user=user, output_schema=schema, max_completion_tokens=max_completion_tokens)


def validate_repair(service, task_id, proposal_text, *, repair_generated_at):
    spec, context, response, original_generated, original, admissible, invalid = _sealed(service, task_id)
    if (repair_generated_at.utcoffset() is None or repair_generated_at < original_generated
            or any(datetime.fromisoformat(row["available_at"]) > repair_generated_at
                   for row in context["evidence"])):
        raise ValueError("REPAIR_TIME_INVALID")
    proposal = _payload(proposal_text)
    _exact(proposal, ("version", "original_response_sha256", "replacements"))
    if proposal["version"] != VERSION or proposal["original_response_sha256"] != _hash(response.text):
        raise ValueError("REPAIR_ORIGINAL_BINDING_CHANGED")
    rows = proposal["replacements"]
    if not isinstance(rows, list) or len(rows) != len(invalid):
        raise ValueError("REPAIR_REPLACEMENT_COUNT")
    fixed = deepcopy(original)
    for row, (path, old, _) in zip(rows, invalid):
        _exact(row, ("path", "invalid_id", "replacement_id", "support_quote"))
        if (row["path"] != list(path) or row["invalid_id"] != old
                or row["replacement_id"] not in admissible):
            raise ValueError("REPAIR_UNAUTHORIZED_CHANGE")
        quote = row["support_quote"]
        source_text = next(item["text"] for item in context["evidence"]
                           if item["id"] == row["replacement_id"])
        if (not isinstance(quote, str) or not 8 <= len(quote) <= 240
                or quote not in source_text):
            raise ValueError("REPAIR_SOURCE_QUOTE_NOT_VERIFIED")
        target = fixed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = row["replacement_id"]
    corrected = common._canonical(fixed)
    result = annual.validate_response(corrected, context, spec["years"], repair_generated_at)
    return {"version": VERSION, "original_task_id": task_id,
        "original_response_sha256": _hash(response.text),
        "repair_proposal_sha256": _hash(proposal_text),
        "corrected_response_sha256": _hash(corrected),
        "corrected_annual_response": corrected,
        "annual_result": result, "research_admission": False,
        "requires_semantic_evidence_review": True,
        "formal_eligibility": False, "action": "no_order"}
