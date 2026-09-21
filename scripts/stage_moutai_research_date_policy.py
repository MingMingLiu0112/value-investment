#!/usr/bin/env python3
"""Build a dated 600519 policy after a complete official capital refresh.

This policy is usable only for a research-date valuation package.  It does not
claim that the last market close knew the same information and never opens a
simulation, paper-order, or trading gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "moutai-current-equity-policy-v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital-refresh", type=Path, required=True)
    parser.add_argument("--registered-at", required=True)
    args = parser.parse_args()
    refresh_path = args.capital_refresh.resolve()
    registered_at = datetime.fromisoformat(args.registered_at)
    if not refresh_path.is_relative_to(ROOT.resolve()) or registered_at.tzinfo is None:
        raise ValueError("Capital refresh must be project-local and registered time timezone-aware")
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    fetched_at = datetime.fromisoformat(refresh["fetched_at"])
    through = refresh.get("query_window", "").split("~")[-1]
    if (refresh.get("symbol") != "600519" or refresh.get("complete") is not True
            or refresh.get("new_or_changed_announcements") != 0 or not through
            or fetched_at.tzinfo is None or registered_at < fetched_at):
        raise ValueError("Capital refresh is not complete or was unavailable at policy registration")
    policy = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    policy["registered_at"] = registered_at.isoformat()
    policy["event_coverage_date"] = through
    policy["sources"]["capital_refresh"] = {
        "path": str(refresh_path.relative_to(ROOT)), "sha256": digest(refresh_path),
    }
    policy["research_date_only"] = True
    policy["research_date_boundary"] = (
        "This policy is registered after a complete official index through its stated date. "
        "It may support a same-date research valuation only; it is not information available at the prior market close "
        "and cannot create a market-session action, simulation approval, or order."
    )
    output = ROOT / "runtime/company-research" / (
        "600519-current-equity-policy-research-date-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    path = output / "policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": digest(Path(__file__)), "policy_sha256": digest(path)}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "research_date_only": True, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
