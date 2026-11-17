"""Review-context projector for the complete v3 descriptor payload."""
from __future__ import annotations

from ...research_artifact_codecs import artifact_payload
from ...research_input import build_research_run_spec, descriptor_sha256
from .v3_input_adapter import facts_to_payload_v3
from ...research_run_contract import canonical_contract_payload
from ..product.common import sha256_bytes


def _payload_sha256(payload):
    return sha256_bytes(canonical_contract_payload(payload).encode("utf-8"))


def build_v3_research_review_model_context(*, descriptor, spec):
    digest = descriptor_sha256(descriptor)
    if descriptor.input_sha256 != digest or spec.input_descriptor_sha256 != digest:
        raise ValueError("v3 review context descriptor hash mismatch")
    expected = build_research_run_spec(descriptor)
    for field in (
        "symbol", "profile_id", "requested_model", "as_of", "available_at",
        "report_period", "valuation_date", "computed_at", "input_sources",
        "assumption_bindings", "rule_version", "model_version", "parser_version",
        "scan_watermark", "quote", "model_validity_input", "valuation_approval",
        "distribution_result",
    ):
        if getattr(spec, field) != getattr(expected, field):
            raise ValueError(f"v3 review context spec mismatch: {field}")
    if spec.model_version != "residual-income-equity-path-v3" or spec.assumptions is None:
        raise ValueError("v3 review context requires exact model and assumptions")
    canonical = descriptor.as_policy()
    actual = {
        "research_case": artifact_payload(spec.research_case)[1],
        "facts": facts_to_payload_v3(spec.facts),
        "assumptions": artifact_payload(spec.assumptions)[1],
    }
    for role, payload in actual.items():
        if _payload_sha256(payload) != _payload_sha256(canonical[role]):
            raise ValueError(f"v3 review context spec mismatch: {role}")
    return {
        "input_descriptor_sha256": digest,
        "research_case_sha256": _payload_sha256(actual["research_case"]),
        "facts_sha256": _payload_sha256(actual["facts"]),
        "assumptions_sha256": _payload_sha256(actual["assumptions"]),
        "model_id": descriptor.dependencies.model_id,
        "model_version": spec.model_version,
        "terminal_contract_version": "terminal-economic-contract-v1",
        "profile_id": spec.profile_id,
        "research_as_of": spec.as_of.isoformat(),
    }
