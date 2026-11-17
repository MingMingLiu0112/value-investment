"""TEST_ONLY direct materiality handoff; no reviewer identity or signature created."""
import json

import pytest

from test_direct_owner_cash_alignment_v1 import _bound
from test_direct_owner_cash_compilation_v1 import NOW, sample
from test_d2_conditional_shared_service import synthetic_chain
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_materiality_reviews import (
    build_direct_owner_cash_materiality_envelope, prepare_materiality_review_handoff,
)
from value_investment_agent.application.research import direct_owner_cash_research_v1 as runner
from value_investment_agent.valuation_models.direct_owner_cash_v1 import MODEL_ID, MODEL_VERSION


def _write(root, name, value):
    path = root / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path, {"path": name, "sha256": sha256_file(path)}


def _receipt_with_local_originals(monkeypatch, root):
    """Use the alignment fixture's real receipt builder with hashable TEST_ONLY bytes."""
    spec = sample(monkeypatch)
    source = _bound(root / "runtime/TEST_ONLY.json", root, {})
    spec["operating_sources"][0]["sha256"] = source["sha256"]
    pdf_path = root / "runtime/TEST_ONLY.pdf"
    pdf_path.write_bytes(b"TEST_ONLY source bytes")
    pdf_hash = sha256_file(pdf_path)
    spec["owner_sources"][0]["sha256"] = pdf_hash
    spec["source_descriptors"][0]["sha256"] = pdf_hash
    spec_binding = _bound(root / "runtime/spec.json", root, spec)
    return runner.build_direct_owner_cash_receipt(
        root=root, spec_binding=spec_binding,
        output_dir=root / "runtime/output", now=NOW)["receipt_binding"]


def test_direct_envelope_unsigned_exact_context_and_drift(synthetic_chain, monkeypatch):
    root, _, *_ = synthetic_chain
    receipt_ref = _receipt_with_local_originals(monkeypatch, root)
    receipt_path = root / receipt_ref["path"]
    receipt = runner._read(root, receipt_ref)
    result = runner._read(root, receipt["result_binding"])
    package = result["package"]
    package_path = root / "runtime/direct-package.json"
    package_ref = _bound(package_path, root, package)
    original_package_bytes = package_path.read_bytes()
    scan_path = root / "synthetic-scan.json"
    original_scan_bytes = scan_path.read_bytes()
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan_hash = sha256_file(scan_path)
    valid_from = scan["validity_from"]
    envelope_path = root / "runtime/direct-materiality-envelope.json"
    envelope_ref = build_direct_owner_cash_materiality_envelope(
        root=root, package_path=package_path, package_sha256=package_ref["sha256"],
        receipt_path=receipt_path, receipt_sha256=receipt_ref["sha256"],
        model_validity_input={"model_id": MODEL_ID, "valid_from": valid_from,
                              "events": [], "blockers": []}, output_path=envelope_path)
    assert json.loads(envelope_path.read_text(encoding="utf-8"))["receipt_binding"] == receipt_ref
    assert json.loads(envelope_path.read_text(encoding="utf-8"))["result_binding"] == receipt["result_binding"]
    assert sha256_file(package_path) == package_ref["sha256"]

    def prepare():
        return prepare_materiality_review_handoff(
            root=root, package_path=envelope_path, package_sha256=envelope_ref["sha256"],
            scan_path=scan_path, scan_sha256=scan_hash)

    handoff = prepare()
    assert handoff["schema_version"] == "direct-owner-cash-materiality-review-handoff-v1"
    assert handoff["package_binding"] == envelope_ref
    assert handoff["model_context"]["model_version"] == MODEL_VERSION
    assert handoff["model_context"]["facts_sha256"]
    assert handoff["unsigned_response"]["event_materiality"]["decisions"]
    assert handoff["unsigned_response"]["reviewer_id"] is None
    assert handoff["unsigned_response"]["event_materiality"]["decisions"][0]["human_decision"] is None

    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["result_binding"] = dict(envelope["result_binding"], sha256="0" * 64)
    wrong_path = root / "runtime/wrong-result-envelope.json"
    wrong_ref = _bound(wrong_path, root, envelope)
    with pytest.raises(ValueError, match="result binding differs from receipt"):
        prepare_materiality_review_handoff(root=root, package_path=wrong_path,
            package_sha256=wrong_ref["sha256"], scan_path=scan_path, scan_sha256=scan_hash)

    package["facts"]["blockers"].append("TEST_ONLY_TAMPER")
    package_path.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare()
    package_path.write_bytes(original_package_bytes)
    scan["blockers"] = ["TEST_ONLY_TAMPER"]
    scan_path.write_text(json.dumps(scan), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare()
    scan_path.write_bytes(original_scan_bytes)
    result_path = root / receipt["result_binding"]["path"]
    result_path.write_bytes(result_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare()


def test_direct_original_without_explicit_validity_rejected(synthetic_chain, monkeypatch):
    root, _, *_ = synthetic_chain
    receipt_ref = _receipt_with_local_originals(monkeypatch, root)
    receipt = runner._read(root, receipt_ref)
    result = runner._read(root, receipt["result_binding"])
    package_path = root / "runtime/direct-package.json"
    package_ref = _bound(package_path, root, result["package"])
    envelope_path, envelope_ref = _write(root, "direct-envelope.json", {
        "schema_version": "direct-owner-cash-materiality-envelope-v1", "action": "no_order",
        "package_binding": package_ref, "receipt_binding": receipt_ref,
        "result_binding": receipt["result_binding"],
        "model_validity_input": None})
    scan_path = root / "synthetic-scan.json"
    with pytest.raises(ValueError, match="explicit non-conflicting validity"):
        prepare_materiality_review_handoff(
            root=root, package_path=envelope_path, package_sha256=envelope_ref["sha256"],
            scan_path=scan_path, scan_sha256=sha256_file(scan_path))
