import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "historical_validation_receipt_audit",
    ROOT / "scripts" / "audit_historical_validation_receipt.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def synthetic_bundle(tmp_path):
    root = tmp_path / "repo"
    bundle = root / "runtime" / "historical-validation-test"
    bundle.mkdir(parents=True)
    policy = root / "config" / "policy.json"
    builder = root / "scripts" / "build.py"
    policy.parent.mkdir(parents=True)
    builder.parent.mkdir(parents=True)
    policy.write_text("{}\n", encoding="utf-8")
    builder.write_text("# builder\n", encoding="utf-8")
    files = [
        {"evidence_id": "policy", "kind": "policy", "path": "config/policy.json", "sha256": digest(policy)},
        {"evidence_id": "admission_builder", "kind": "implementation", "path": "scripts/build.py", "sha256": digest(builder)},
    ]
    canonical = json.dumps(
        {
            "admission_id": "synthetic-admission",
            "action": "no_order",
            "files": files,
            "policy_evidence_id": "policy",
            "builder_evidence_id": "admission_builder",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "schema_version": "historical-validation-input-manifest-v1",
        "admission_id": "synthetic-admission",
        "action": "no_order",
        "files": files,
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    admission = {
        "admission_id": "synthetic-admission",
        "classification": "NOT_PIT_SAFE",
        "admission_status": "NOT_ADMITTED",
        "evidence_refs": files,
        "action": "no_order",
    }
    walk = {
        "status": "NOT_RUN",
        "performance": {"strategy_backtest_complete": False},
        "action": "no_order",
    }
    write_json(bundle / "input-manifest.json", manifest)
    write_json(bundle / "admission.json", admission)
    write_json(bundle / "walk-forward-result.json", walk)
    (bundle / "user-report.md").write_text("# test\n", encoding="utf-8")
    receipt = {
        "classification": admission["classification"],
        "admission_status": admission["admission_status"],
        "action": "no_order",
        "admission_sha256": digest(bundle / "admission.json"),
        "input_manifest_sha256": digest(bundle / "input-manifest.json"),
        "walk_forward_result_sha256": digest(bundle / "walk-forward-result.json"),
        "user_report_sha256": digest(bundle / "user-report.md"),
    }
    write_json(bundle / "receipt.json", receipt)
    return root, bundle


def test_receipt_audit_verifies_hashes_and_keeps_not_pit_safe(tmp_path):
    root, bundle = synthetic_bundle(tmp_path)
    result = MODULE.verify_bundle(root, bundle)
    assert result["status"] == "AUDIT_OK"
    assert result["classification"] == "NOT_PIT_SAFE"
    assert result["action"] == "no_order"


def test_receipt_audit_detects_tampering(tmp_path):
    root, bundle = synthetic_bundle(tmp_path)
    (bundle / "user-report.md").write_text("# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.verify_bundle(root, bundle)
