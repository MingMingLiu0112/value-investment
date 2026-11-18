"""Typed materiality envelope for the v2 owner-distribution successor."""

from copy import deepcopy
import json

import pytest

from test_parent_owner_distribution_alignment_v2 import NOW, aligned_case, bound
from test_d2_conditional_shared_service import synthetic_chain
from value_investment_agent.application.product.research_materiality_reviews import (
    _direct_review_original,
    build_parent_owner_distribution_materiality_envelope,
    prepare_materiality_review_handoff,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research import parent_owner_distribution_alignment_v2
from value_investment_agent.application.research.direct_owner_cash_input_adapter_v2 import (
    build_direct_owner_cash_descriptor,
)
from value_investment_agent.application.research.direct_owner_cash_review_context_v2 import (
    build_direct_owner_cash_review_model_context,
)
from value_investment_agent.application.research.parent_owner_distribution_successor_v2 import (
    replay_parent_owner_distribution_successor,
)
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_run_contract import canonical_contract_payload
from value_investment_agent.valuation_models.direct_owner_cash_v2 import MODEL_ID, MODEL_VERSION


def _envelope(root, receipt):
    result = replay_parent_owner_distribution_successor(
        root=root, receipt_binding=receipt, now=NOW
    )
    output = root / "runtime/TEST_ONLY-owner-distribution-materiality-envelope.json"
    ref = build_parent_owner_distribution_materiality_envelope(
        root=root,
        receipt_path=root / receipt["path"],
        receipt_sha256=receipt["sha256"],
        model_validity_input={
            "model_id": MODEL_ID,
            "valid_from": result["compiled"]["valuation_date"],
            "events": [],
            "blockers": [],
        },
        output_path=output,
        now=NOW,
    )
    return result, ref


def test_v2_successor_envelope_cold_replays_exact_package_and_context(aligned_case):
    root, receipt, *_ = aligned_case
    result, envelope_ref = _envelope(root, receipt)
    envelope = json.loads((root / envelope_ref["path"]).read_text(encoding="utf-8"))
    package, validity = _direct_review_original(root=root, envelope=envelope, now=NOW)
    assert canonical_contract_payload(package) == canonical_contract_payload(result["package"])
    assert envelope["receipt_binding"] == receipt
    assert envelope["input_descriptor_sha256"] == result["input_descriptor_sha256"]
    assert validity["model_id"] == MODEL_ID

    descriptor = build_direct_owner_cash_descriptor(deepcopy(package), root=root)
    spec = build_research_run_spec(descriptor)
    context = build_direct_owner_cash_review_model_context(
        descriptor=descriptor, spec=spec
    )
    assert context["input_descriptor_sha256"] == result["input_descriptor_sha256"]
    assert context["model_version"] == MODEL_VERSION
    assert context["facts_sha256"]


def test_v2_successor_envelope_rejects_result_tampering(aligned_case):
    root, receipt, *_ = aligned_case
    _, envelope_ref = _envelope(root, receipt)
    envelope = json.loads((root / envelope_ref["path"]).read_text(encoding="utf-8"))
    result_path = root / envelope["result_binding"]["path"]
    result_path.write_bytes(result_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="hash mismatch|HASH_CHANGED"):
        _direct_review_original(root=root, envelope=envelope, now=NOW)


def test_alignment_binds_envelope_without_granting_materiality(aligned_case, monkeypatch):
    root, receipt, *_ = aligned_case
    result, envelope_ref = _envelope(root, receipt)
    config_path = root / "config/pending-candidate-alignments-v1" / (
        receipt["sha256"] + ".json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["materiality_envelope_binding"] = envelope_ref
    bound(root, config_path.relative_to(root).as_posix(), config)
    captured = {}

    def load_bound_alignment(**kwargs):
        captured.update(kwargs["analysis"])
        return {
            "status": "BLOCKED",
            "checks": [],
            "currentpricecomparison": False,
        }

    monkeypatch.setattr(
        parent_owner_distribution_alignment_v2,
        "_load_bound_alignment",
        load_bound_alignment,
    )
    projected = parent_owner_distribution_alignment_v2.read_parent_owner_distribution_alignment(
        root=root, receipt_binding=receipt, now=NOW
    )
    assert captured["review_binding"]["package_binding"] == envelope_ref
    assert projected["materiality_input_adapter"] == {
        "status": "EXACT_OWNER_DISTRIBUTION_REVIEW_ENVELOPE_BOUND",
        "envelope_binding": envelope_ref,
        "approval_granted": False,
        "reason": "Bound review inputs only; authenticated event decisions remain required.",
    }
    assert projected["formal_eligibility"] is False
    assert projected["action"] == "no_order"
    assert result["input_descriptor_sha256"] == captured["input_descriptor_sha256"]


def test_v2_successor_builds_unsigned_materiality_handoff(
    aligned_case, synthetic_chain, monkeypatch
):
    root, receipt, *_ = aligned_case
    source_root, *_ = synthetic_chain
    _, envelope_ref = _envelope(root, receipt)
    envelope_path = root / envelope_ref["path"]
    disclosure = source_root / "synthetic-disclosure.json"
    (root / disclosure.name).write_bytes(disclosure.read_bytes())
    scan = json.loads((source_root / "synthetic-scan.json").read_text(encoding="utf-8"))
    scan["symbol"] = "600887"
    scan["scan_from"] = "2025-12-31"
    scan["validity_from"] = "2025-12-31"
    scan_path = root / "synthetic-scan.json"
    scan_path.write_text(json.dumps(scan, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        "value_investment_agent.application.product.source_bound_inputs.verify_package_local_sources",
        lambda *_args, **_kwargs: None,
    )

    handoff = prepare_materiality_review_handoff(
        root=root,
        package_path=envelope_path,
        package_sha256=envelope_ref["sha256"],
        scan_path=scan_path,
        scan_sha256=sha256_file(scan_path),
        now=NOW,
    )
    assert handoff["schema_version"] == (
        "parent-owner-distribution-materiality-review-handoff-v1"
    )
    assert handoff["model_context"]["model_version"] == MODEL_VERSION
    assert handoff["unsigned_response"]["reviewer_id"] is None
    assert handoff["unsigned_response"]["event_materiality"]["decisions"][0][
        "human_decision"
    ] is None
