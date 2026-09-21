#!/usr/bin/env python3
"""Produce a dated, hash-bound operating-thesis status for 600519.

The output answers a deliberately narrow question: whether the registered
current evidence contains a direct falsifier of continued profitable operation.
It is not a competitive-moat score, a forecast, or trading approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_json(reference: dict) -> tuple[dict, dict]:
    path = (ROOT / reference["path"]).resolve()
    if path.is_dir():
        path = path / "evidence.json"
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned evidence changed")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.relative_to(ROOT)), "sha256": reference["sha256"],
    }


def build(as_of: date | None = None) -> dict:
    pointer = json.loads(MODEL_POINTER.read_text(encoding="utf-8"))
    model, model_ref = pinned_json(pointer)
    valuation_date = datetime.fromisoformat(model["valuation_at"]).date()
    as_of = as_of or valuation_date
    if as_of != valuation_date:
        raise ValueError("Thesis assessment is limited to the current model valuation date")

    policy, policy_ref = pinned_json(model["policy"])
    facts_ref = model["inputs"]["facts"]
    facts, facts_ref = pinned_json(facts_ref)
    peer, peer_ref = pinned_json(model["inputs"]["peer_counterevidence"])
    refresh, refresh_ref = pinned_json(model["inputs"]["capital_refresh"])
    current = facts.get("current_disclosed_basis")
    if not isinstance(current, dict):
        raise ValueError("Current disclosure basis is absent")
    available = datetime.fromisoformat(current["available_at"]).date()
    if available > as_of or (as_of - available).days > 90:
        raise ValueError("Current issuer disclosure is unavailable or stale")
    if policy.get("event_coverage_date") != as_of.isoformat():
        raise ValueError("Capital-event coverage does not reach the assessment date")
    if refresh.get("complete") is not True or refresh.get("new_or_changed_announcements") != 0:
        raise ValueError("Capital refresh is incomplete or contains unassessed events")
    if not refresh.get("query_window", "").endswith(as_of.isoformat()):
        raise ValueError("Capital-refresh window does not end on the assessment date")

    profit = Decimal(current["parent_profit_h1_cny"])
    ttm_profit = Decimal(current["ttm_ex_nonrecurring_parent_profit_cny"])
    roe_proxy = Decimal(current["ttm_ending_equity_profit_ratio"])
    direct_falsifiers: list[str] = []
    if profit <= 0:
        direct_falsifiers.append("latest_h1_parent_profit_nonpositive")
    if ttm_profit <= 0:
        direct_falsifiers.append("ttm_ex_nonrecurring_parent_profit_nonpositive")
    if roe_proxy <= 0:
        direct_falsifiers.append("ttm_parent_equity_profit_ratio_nonpositive")

    # The declining profit trend and peer evidence are deliberately retained as
    # counterevidence. They do not become a false "all clear" merely because
    # the issuer remains profitable.
    counterevidence = [
        "FY2025 and H1 2026 parent profit declined; the base case assumes no recovery.",
        "Peer interim evidence rejects automatic industry recovery.",
        "75% payout, future growth and fade remain model assumptions, not issuer commitments.",
    ]
    thesis_intact = not direct_falsifiers
    return {
        "symbol": "600519",
        "assessment_version": "moutai-current-thesis-v1",
        "as_of": as_of.isoformat(),
        "assessment_scope": "continued profitable operation only; not a moat, target price, or investment recommendation",
        "thesis_intact": thesis_intact,
        "status": "confirmed_with_counterevidence" if thesis_intact else "broken_by_direct_falsifier",
        "evidence": {
            "current_model": model_ref,
            "model_policy": policy_ref,
            "issuer_interim_basis": {
                "source_id": current["source_id"], "source_url": current["source_url"],
                "raw_file_hash": current["raw_file_hash"], "published_date": current["published_date"],
                "available_at": current["available_at"], "period_end": current["period_end"],
                "facts_package": facts_ref,
            },
            "capital_event_refresh": refresh_ref,
            "peer_counterevidence": peer_ref,
        },
        "observations": {
            "parent_profit_h1_cny": str(profit),
            "ttm_ex_nonrecurring_parent_profit_cny": str(ttm_profit),
            "ttm_ending_equity_profit_ratio": str(roe_proxy),
            "capital_refresh_complete": True,
            "capital_refresh_new_or_changed_announcements": 0,
            "peer_evidence_present": bool(peer),
        },
        "direct_falsifiers": direct_falsifiers,
        "counterevidence": counterevidence,
        "limitations": [
            "This does not establish durable competitive advantage or forecast future earnings.",
            "A positive thesis status cannot override valuation, execution, account, or live-trading gates.",
            "Any new announcement, later assessment date, or stale issuer filing requires a new assessment.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = build(as_of)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/company-research" / f"600519-current-thesis-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-current-thesis-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "thesis_intact": result["thesis_intact"],
                      "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
