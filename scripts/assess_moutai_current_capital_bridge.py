#!/usr/bin/env python3
"""Assess the dated ordinary-share and capital-event bridge for current 600519 research.

The assessment establishes a bounded per-share denominator only.  It does not
claim a shareholder-register extract, current net assets, a fair value, or a
trading recommendation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
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


def consecutive_windows(first: str, second: str, through: date) -> bool:
    first_start, first_end = (date.fromisoformat(value) for value in first.split("~"))
    second_start, second_end = (date.fromisoformat(value) for value in second.split("~"))
    return first_start <= date(2026, 6, 1) and first_end >= second_start and second_end == through


def build() -> dict:
    pointer = json.loads(MODEL_POINTER.read_text(encoding="utf-8"))
    model, model_ref = pinned_json(pointer)
    valuation_at = datetime.fromisoformat(model["valuation_at"])
    if model.get("symbol") != "600519" or model.get("trade_approved") is not False:
        raise ValueError("Unexpected current model scope")
    facts, facts_ref = pinned_json(model["inputs"]["facts"])
    refresh, refresh_ref = pinned_json(model["inputs"]["capital_refresh"])
    policy, policy_ref = pinned_json(model["policy"])
    current = facts.get("current_disclosed_basis")
    if not isinstance(current, dict):
        raise ValueError("Current disclosure basis is missing")
    issued = int(current["issued_shares"])
    share_values = current.get("share_evidence", {}).get("values", {})
    event_query = current.get("event_query", {})
    if (issued <= 0 or share_values.get("ending_issued_shares") != str(issued)
            or current.get("period_end") != "2026-06-30"
            or current.get("share_evidence", {}).get("unit") != "shares"
            or event_query.get("complete") is not True
            or event_query.get("new_or_changed_announcements") != 0
            or refresh.get("complete") is not True
            or refresh.get("new_or_changed_announcements") != 0):
        raise ValueError("Share or capital-event evidence is incomplete")
    if policy.get("event_coverage_date") != valuation_at.date().isoformat():
        raise ValueError("Current model policy does not reach valuation date")
    if not consecutive_windows(event_query["window"], refresh["query_window"], valuation_at.date()):
        raise ValueError("Capital-event query windows are not continuous through valuation date")
    equity_bridge = current.get("equity_bridge", {})
    if equity_bridge.get("deduct_reported_distributions_again") is not False:
        raise ValueError("Reported distributions would be double counted")
    return {
        "symbol": "600519",
        "assessment_version": "moutai-current-capital-bridge-v1",
        "as_of": valuation_at.date().isoformat(),
        "assessment_scope": "current per-share denominator and known capital-event bridge only",
        "passed": True,
        "ordinary_share_basis": {
            "reported_period_end": current["period_end"],
            "issued_shares": str(issued),
            "source_id": current["source_id"],
            "source_url": current["source_url"],
            "raw_file_hash": current["raw_file_hash"],
            "physical_page": current["share_evidence"]["physical_page"],
            "share_change": share_values["share_change"],
        },
        "capital_event_coverage": {
            "first_complete_window": event_query["window"],
            "first_query": {"path": event_query["path"], "sha256": event_query["sha256"]},
            "second_complete_window": refresh["query_window"],
            "second_query": refresh_ref,
            "new_or_changed_announcements": 0,
            "coverage_reaches_as_of": True,
        },
        "equity_treatment": {
            "reported_distribution_not_deducted_again": True,
            "repurchase_equity_change_cny": equity_bridge["repurchase_equity_change_cny"],
            "distribution_equity_change_cny": equity_bridge["distribution_equity_change_cny"],
        },
        "evidence": {"current_model": model_ref, "facts": facts_ref, "policy": policy_ref},
        "limitations": [
            "This carries forward the latest disclosed ordinary-share count; it is not an as-of shareholder-register certificate.",
            "It does not observe daily net assets, post-report earnings or future distributions.",
            "Any later valuation date requires a new complete capital-event query and a new bridge assessment.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = build()
    output = ROOT / "runtime/company-research" / (
        "600519-current-capital-bridge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-current-capital-bridge-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": True, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
