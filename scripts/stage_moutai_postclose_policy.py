#!/usr/bin/env python3
"""Stage, but do not activate, a dated current-model policy from a pre-close receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/moutai-current-equity-policy-v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ref(reference: dict) -> tuple[dict, Path]:
    path = (ROOT / reference["path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned pre-close evidence changed")
    return json.loads(path.read_text(encoding="utf-8")), path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--registered-at", required=True, help="Timezone-aware ISO timestamp after close")
    args = parser.parse_args()
    registered_at = datetime.fromisoformat(args.registered_at)
    if registered_at.tzinfo is None:
        raise ValueError("Registration time must be timezone-aware")
    receipt_path = args.receipt.resolve()
    if not receipt_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Receipt must remain under the project root")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("symbol") != "600519" or receipt.get("preclose_complete") is not True or receipt.get("trade_approved") is not False:
        raise ValueError("Receipt is not a bounded pre-close capital refresh")
    finished = datetime.fromisoformat(receipt["collection_finished_at"])
    if finished.tzinfo is None or finished.hour >= 15 or registered_at <= finished:
        raise ValueError("Receipt timing cannot support a later post-close policy")
    refresh, refresh_path = load_ref(receipt["capital_refresh"])
    if (refresh.get("complete") is not True or refresh.get("new_or_changed_announcements") != 0
            or refresh.get("query_window", "").split("~")[-1] != receipt["through"]):
        raise ValueError("Capital refresh needs specific review before policy staging")
    policy = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    policy["registered_at"] = registered_at.isoformat()
    policy["event_coverage_date"] = receipt["through"]
    policy["sources"]["capital_refresh"] = {"path": str(refresh_path.relative_to(ROOT)), "sha256": digest(refresh_path)}
    policy["preclose_receipt"] = {"path": str(receipt_path.relative_to(ROOT)), "sha256": digest(receipt_path)}
    policy["staged_only"] = True
    policy["activation_requirement"] = "Build a new dated model and complete its scope, capital, cost and assumption reviews. This policy is not active and grants no valuation, simulation or trade approval."
    output = ROOT / "runtime/company-research" / ("600519-current-equity-policy-staged-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    path = output / "policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "staged_only": True, "trade_approved": False}, ensure_ascii=False))

if __name__ == "__main__":
    raise SystemExit(main())
