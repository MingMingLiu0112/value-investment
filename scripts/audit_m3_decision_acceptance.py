"""Recompute the non-personal M3 decision-card acceptance evidence."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from value_investment_agent.m3_decision_acceptance_audit import (
    EXPECTED_CANDIDATE_SHA256,
    EXPECTED_CANONICAL_WORKBOOK_SHA256,
    EXPECTED_INPUT_SHA256,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_PREREGISTRATION_SHA256,
    EXPECTED_WPS_RECEIPT_SHA256,
    M3DecisionAcceptanceSpec,
    _run_pytest,
    audit,
    write_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "runtime" / "m1-post-review-20260923T114228Z" / "integrated-runs.json"
)
DEFAULT_PREREGISTRATION = ROOT / "config" / "m1-fixed-sample-preregistration-v1.json"
DEFAULT_CANDIDATE = ROOT / "A股价值投资_M3决策卡候选_20260924.xlsx"
DEFAULT_MANIFEST = ROOT / "A股价值投资_M3决策卡候选_20260924.manifest.json"
DEFAULT_WPS_CANDIDATE = (
    Path(r"C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪")
    / "A股价值投资_M3决策卡候选_20260924.xlsx"
)
DEFAULT_WPS_RECEIPT = (
    ROOT / "runtime" / "m3-decision-card-wps-20260924" / "receipt.json"
)
DEFAULT_CANONICAL = (
    Path(r"C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪")
    / "A股价值投资_Agent前端智能跟踪模板.xlsx"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--wps-candidate", type=Path, default=DEFAULT_WPS_CANDIDATE)
    parser.add_argument("--wps-receipt", type=Path, default=DEFAULT_WPS_RECEIPT)
    parser.add_argument("--canonical-workbook", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--ci-status", choices=("success", "failure", "pending"))
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    manifest = json.loads(args.manifest.resolve().read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(str(manifest["generated_at"]))
    spec = M3DecisionAcceptanceSpec(
        input_path=args.input,
        input_sha256=EXPECTED_INPUT_SHA256,
        preregistration_path=args.preregistration,
        preregistration_sha256=EXPECTED_PREREGISTRATION_SHA256,
        candidate_path=args.candidate,
        candidate_sha256=EXPECTED_CANDIDATE_SHA256,
        manifest_path=args.manifest,
        manifest_sha256=EXPECTED_MANIFEST_SHA256,
        generated_at=generated_at,
        wps_candidate_path=args.wps_candidate,
        wps_receipt_path=args.wps_receipt,
        wps_receipt_sha256=EXPECTED_WPS_RECEIPT_SHA256,
        canonical_workbook_path=args.canonical_workbook,
        canonical_sha256=EXPECTED_CANONICAL_WORKBOOK_SHA256,
    )
    test_evidence = _run_pytest(root) if args.run_tests else None
    receipt = audit(
        root,
        spec,
        ci_evidence={"status": args.ci_status} if args.ci_status else None,
        test_evidence=test_evidence,
    )
    output = write_receipt(receipt, root=root)
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    print(f"M3 decision-card acceptance status: {receipt['status']}")
    print(f"done: {', '.join(receipt['summary']['done'])}")
    print(f"partial: {', '.join(receipt['summary']['partial'])}")
    print(f"pending_ci: {', '.join(receipt['summary']['pending_ci'])}")
    print(
        "pending_human_review: "
        + ", ".join(receipt["summary"]["pending_human_review"])
    )
    print(f"next_action: {receipt['summary']['next_action']}")
    print(f"receipt: {output['receipt_path']}")
    print(f"receipt sha256: {output['receipt_sha256']}")
    print("action: no_order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
