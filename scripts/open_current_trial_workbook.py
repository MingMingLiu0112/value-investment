"""Resolve and optionally open the one configured canonical user workbook."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.infrastructure.evidence.workbook_publication import verify_workbook_publication
POINTER = ROOT / "config" / "current-trial-workbook.json"
CANONICAL_NAME = "A股价值投资_Agent前端智能跟踪模板.xlsx"
PRODUCT_UX_SOURCE = "PRODUCT_UX_RUNTIME"


def _canonical_workbook(contract: dict) -> Path:
    value = os.environ.get("WORKBOOK_PATH")
    env_file = ROOT / ".env"
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("WORKBOOK_PATH"):
                value = line.split("=", 1)[1].strip()
                break
    if not value:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    workbook = Path(value).expanduser().resolve()
    if not workbook.is_file() or workbook.suffix.lower() != ".xlsx" or workbook.name != CANONICAL_NAME:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    expected_sha = contract.get("canonical_workbook_sha256")
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None:
        raise ValueError("CANONICAL_WORKBOOK_POINTER_HASH_INVALID")
    actual_sha = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(
            f"CANONICAL_WORKBOOK_HASH_MISMATCH expected={expected_sha} actual={actual_sha}"
        )
    return workbook


def _product_ux_workbook(contract: dict) -> Path:
    relative = contract.get("workbook_path")
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("PRODUCT_UX_WORKBOOK_NOT_RESOLVED")
    workbook = (ROOT / relative).resolve()
    runtime_root = (ROOT / "runtime").resolve()
    if (
        not workbook.is_relative_to(runtime_root)
        or not workbook.is_file()
        or workbook.suffix.lower() != ".xlsx"
    ):
        raise ValueError("PRODUCT_UX_WORKBOOK_NOT_RESOLVED")
    expected_sha = contract.get("workbook_sha256")
    actual_sha = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if not isinstance(expected_sha, str) or actual_sha != expected_sha:
        raise ValueError("PRODUCT_UX_WORKBOOK_HASH_MISMATCH")
    manifest_value = contract.get("manifest_path")
    expected_manifest_sha = contract.get("manifest_sha256")
    if manifest_value is not None or expected_manifest_sha is not None:
        if not isinstance(manifest_value, str) or not isinstance(expected_manifest_sha, str):
            raise ValueError("PRODUCT_UX_MANIFEST_NOT_RESOLVED")
        manifest = (ROOT / manifest_value).resolve()
        if not manifest.is_relative_to(runtime_root) or not manifest.is_file():
            raise ValueError("PRODUCT_UX_MANIFEST_NOT_RESOLVED")
        actual_manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        if actual_manifest_sha != expected_manifest_sha:
            raise ValueError("PRODUCT_UX_MANIFEST_HASH_MISMATCH")
    return workbook


def _resolve_trial_workbook(contract: dict) -> Path:
    source = contract.get("workbook_source")
    if source == "WORKBOOK_PATH":
        verify_workbook_publication(ROOT, contract)
        return _canonical_workbook(contract)
    raise ValueError("CURRENT_TRIAL_WORKBOOK_SOURCE_NOT_RESOLVED")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the current read-only M7 trial workbook.")
    parser.add_argument("--open", action="store_true", help="Open the verified workbook with the default Windows application.")
    parser.add_argument('--historical-preview')
    parser.add_argument('--preview-sha256')
    args = parser.parse_args()
    contract = json.loads(POINTER.read_text(encoding="utf-8"))
    if contract.get("action") != "no_order":
        raise ValueError("current workbook pointer is not a no_order contract")
    historical = args.historical_preview is not None
    if historical != (args.preview_sha256 is not None):
        raise ValueError('historical preview requires explicit path and hash')
    workbook = (_product_ux_workbook(dict(workbook_path=args.historical_preview,
        workbook_sha256=args.preview_sha256)) if historical else _resolve_trial_workbook(contract))
    actual_sha = hashlib.sha256(workbook.read_bytes()).hexdigest()
    publication = {} if historical else contract.get("current_publication", {})
    result = {
        "status": 'HISTORICAL_PREVIEW_ONLY' if historical else contract["status"],
        "workbook": str(workbook),
        "sha256": actual_sha,
        "workbook_source": 'EXPLICIT_HISTORICAL_PREVIEW' if historical else contract.get("workbook_source"),
        "current_trial_pointer": 'NOT_CURRENT' if historical else contract.get("current_trial_pointer"),
        "simulation_only": contract.get("simulation_only", False),
        "data_as_of": publication.get("research_as_of", contract.get("as_of")),
        "quote_observation_as_of": publication.get("quote_observation_as_of"),
        "publication_status": publication.get("status"),
        "historical_pointer_as_of": contract.get("as_of"),
        "quote_coverage_status": contract.get("quote_coverage_status"),
        "m6_operational_status": contract.get("m6_operational_status"),
        "m7_final_user_acceptance": contract.get("m7_final_user_acceptance"),
        "initial_assisted_use": contract.get("initial_assisted_use"),
        "action": "no_order",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.open:
        if os.name != "nt":
            raise ValueError("--open is supported only on Windows")
        os.startfile(workbook)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
