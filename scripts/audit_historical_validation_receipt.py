#!/usr/bin/env python3
"""Verify the historical-validation admission bundle without rerunning a strategy."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POINTER = ROOT / "runtime" / "historical-validation-600519-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _resolve_bundle(root: Path, pointer: Path | None) -> Path:
    if pointer is None:
        raise ValueError("A receipt directory or latest pointer is required")
    payload = _load_json(pointer)
    target = (root / str(payload.get("path", ""))).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_dir():
        raise ValueError("Latest pointer does not resolve to a project receipt directory")
    return target


def verify_bundle(root: Path, bundle: Path) -> dict[str, Any]:
    root = root.resolve()
    bundle = bundle.resolve()
    if not bundle.is_relative_to(root) or not bundle.is_dir():
        raise ValueError("Receipt bundle must be a project directory")
    receipt = _load_json(bundle / "receipt.json")
    admission = _load_json(bundle / "admission.json")
    manifest = _load_json(bundle / "input-manifest.json")
    walk = _load_json(bundle / "walk-forward-result.json")
    expected = {
        "admission_sha256": bundle / "admission.json",
        "input_manifest_sha256": bundle / "input-manifest.json",
        "walk_forward_result_sha256": bundle / "walk-forward-result.json",
        "user_report_sha256": bundle / "user-report.md",
    }
    if receipt.get("action") != "no_order" or admission.get("action") != "no_order":
        raise ValueError("Historical validation bundle must remain action=no_order")
    if manifest.get("action") != "no_order" or walk.get("action") != "no_order":
        raise ValueError("Historical validation supporting artifacts must remain action=no_order")
    for key, path in expected.items():
        if receipt.get(key) != digest(path):
            raise ValueError(f"Receipt hash mismatch: {key}")
    if receipt.get("classification") != admission.get("classification"):
        raise ValueError("Receipt classification does not match admission")
    if receipt.get("admission_status") != admission.get("admission_status"):
        raise ValueError("Receipt admission status does not match admission")
    if walk.get("status") == "NOT_RUN" and walk.get("performance", {}).get("strategy_backtest_complete") is not False:
        raise ValueError("NOT_RUN walk-forward result cannot claim a completed backtest")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Input manifest must contain files")
    seen: set[str] = set()
    for item in files:
        evidence_id = str(item.get("evidence_id", ""))
        if not evidence_id or evidence_id in seen:
            raise ValueError("Input manifest evidence ids must be present and unique")
        seen.add(evidence_id)
        path = (root / str(item.get("path", ""))).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Input evidence is missing or escapes root: {path}")
        if digest(path) != item.get("sha256"):
            raise ValueError(f"Input evidence hash changed: {path}")
    admission_ids = {item.get("evidence_id") for item in admission.get("evidence_refs", [])}
    if admission_ids != seen:
        raise ValueError("Admission evidence ids do not match the input manifest")
    policy_id = next((item["evidence_id"] for item in files if item.get("kind") == "policy"), None)
    builder_id = next(
        (item["evidence_id"] for item in files if item.get("kind") == "implementation"),
        None,
    )
    if not policy_id or not builder_id:
        raise ValueError("Policy and builder evidence are required")
    canonical = json.dumps(
        {
            "admission_id": admission.get("admission_id"),
            "action": "no_order",
            "files": files,
            "policy_evidence_id": policy_id,
            "builder_evidence_id": builder_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if manifest.get("canonical_sha256") != hashlib.sha256(canonical).hexdigest():
        raise ValueError("Input manifest canonical hash mismatch")
    return {
        "schema_version": "historical-validation-receipt-audit-v1",
        "status": "AUDIT_OK",
        "classification": admission.get("classification"),
        "admission_status": admission.get("admission_status"),
        "walk_forward_status": walk.get("status"),
        "evidence_files": len(files),
        "action": "no_order",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = args.receipt_dir or _resolve_bundle(root, args.pointer)
    result = verify_bundle(root, bundle)
    if args.output:
        output = args.output.resolve()
        if not output.is_relative_to(root):
            raise ValueError("Audit output must remain under the project root")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
