"""Exact direct-owner-cash context for an unsigned materiality handoff."""
from ...research_artifact_codecs import artifact_payload
from ...research_input import build_research_run_spec, descriptor_sha256
from ...research_run_contract import canonical_contract_payload
from ...valuation_models.direct_owner_cash_v1 import MODEL_ID, MODEL_VERSION, facts_to_payload
from ..product.common import sha256_bytes


def _hash(value):
    return sha256_bytes(canonical_contract_payload(value).encode("utf-8"))


def build_direct_owner_cash_review_model_context(*, descriptor, spec):
    digest = descriptor_sha256(descriptor)
    if descriptor.input_sha256 != digest or spec.input_descriptor_sha256 != digest:
        raise ValueError("direct review descriptor hash mismatch")
    if (descriptor.descriptor_version != "direct-owner-cash-input-v1"
            or descriptor.dependencies.model_id != MODEL_ID
            or spec.model_version != MODEL_VERSION or spec.assumptions is not None):
        raise ValueError("direct review requires exact direct model")
    expected = build_research_run_spec(descriptor)
    for field in ("symbol", "profile_id", "requested_model", "as_of", "available_at",
                  "report_period", "valuation_date", "computed_at", "input_sources",
                  "assumption_bindings", "rule_version", "model_version", "parser_version",
                  "scan_watermark", "quote", "model_validity_input", "valuation_approval",
                  "distribution_result"):
        if getattr(spec, field) != getattr(expected, field):
            raise ValueError("direct review spec mismatch: " + field)
    actual = {"research_case": artifact_payload(spec.research_case)[1],
              "facts": facts_to_payload(spec.facts)}
    policy = descriptor.as_policy()
    for role, payload in actual.items():
        if _hash(payload) != _hash(policy[role]):
            raise ValueError("direct review payload mismatch: " + role)
        declared = getattr(spec, role + "_payload")
        if declared is not None and _hash(declared) != _hash(payload):
            raise ValueError("direct review declared payload mismatch: " + role)
    return {"input_descriptor_sha256": digest,
            "research_case_sha256": _hash(actual["research_case"]),
            "facts_sha256": _hash(actual["facts"]),
            "model_id": MODEL_ID, "model_version": MODEL_VERSION,
            "profile_id": spec.profile_id, "research_as_of": spec.as_of.isoformat()}
