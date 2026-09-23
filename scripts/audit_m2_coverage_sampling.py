"""Run the pre-registered M2 coverage audit against one pinned receipt.

The command is read-only with respect to the receipt, WPS workbook, production
database and server projects. It writes one new audit report under runtime/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_coverage_sampling import (  # noqa: E402
    DEFAULT_SAMPLING_PATH,
    load_m2_coverage_sampling,
    load_pinned_receipt,
    run_m2_coverage_audit,
)


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _write(output_dir: Path, name: str, payload: dict) -> Path:
    target = output_dir / name
    target.write_bytes(_json_bytes(payload))
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_SAMPLING_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runtime" / "m2-ac9-coverage-audit-20260923-v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("M2 audit output escapes project root")
    if (output_dir / "report.json").exists():
        raise ValueError(f"M2 audit output already exists: {output_dir / 'report.json'}")
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = load_m2_coverage_sampling(args.config)
    receipt = load_pinned_receipt(policy, root=ROOT)
    audit = run_m2_coverage_audit(policy, receipt)
    report_path = _write(output_dir, "report.json", audit.as_policy())
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "m2-coverage-audit-manifest-v1",
        "action": "no_order",
        "sampling_config": str(Path(args.config).resolve().relative_to(ROOT)),
        "receipt": policy.receipt_path,
        "receipt_sha256": policy.receipt_sha256,
        "report_sha256": report_sha256,
        "audit_status": audit.audit_status,
        "acceptance_status": audit.acceptance_status,
    }
    _write(output_dir, "manifest.json", manifest)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
