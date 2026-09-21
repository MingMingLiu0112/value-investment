#!/usr/bin/env python3
"""Map, without waiving, the blockers for the pre-registered 600519 window."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOW_REGISTRATION = ROOT / "runtime/strategy-validation/moutai-historical-window-registration-20260918T121703Z/evidence.json"
CONDITIONAL_INPUTS = ROOT / "runtime/strategy-validation/moutai-historical-conditional-inputs-20260910-v2/evidence.json"
DAILY_INPUTS = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
DISTRIBUTIONS = ROOT / "docs/reviewed-cash-distributions.json"
COMPARATIVE_NWC = ROOT / "runtime/strategy-validation/moutai-2012-comparative-nwc-20260918T122931Z/evidence.json"
COMPARATIVE_NWC_SHA256 = "51a60d11a358d292f4d67cf5177c238c483e5c67db3bd2c0dd44f49476f2fb75"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def build() -> dict:
    registration = load(WINDOW_REGISTRATION)
    package = load(CONDITIONAL_INPUTS)
    daily_inputs = load(DAILY_INPUTS)
    distributions = load(DISTRIBUTIONS)["events"]
    comparative_nwc = load(COMPARATIVE_NWC)
    if digest(COMPARATIVE_NWC) != COMPARATIVE_NWC_SHA256:
        raise ValueError("Comparative NWC evidence changed; review mapping before reuse")
    window = registration["window"]
    selected_rows = [
        row for row in daily_inputs
        if window["start"] <= row["date"] <= window["end"]
    ]
    if len(selected_rows) != window["sessions"]:
        raise ValueError("Registered window does not have the expected daily-input sessions")
    if any(row["annual_source_id"] != window["annual_source_id"] for row in selected_rows):
        raise ValueError("Registered window has more than one annual source")
    case = next(
        (item for item in package["input_cases"] if item["source"]["source_id"] == window["annual_source_id"]),
        None,
    )
    if case is None or case["report_period"] != window["report_period"]:
        raise ValueError("Registered annual source does not match conditional-input package")
    if case["available_at"] > selected_rows[0]["decision_at"]:
        raise ValueError("Registered annual input was not available by the first decision time")
    if package["formal_fair_value"] is not None or package["trade_approved"]:
        raise ValueError("Research-only conditional input package unexpectedly promoted")
    action_dates = {
        event_date
        for event in distributions
        if event["symbol"] == "600519"
        for event_date in (event["record_date"], event["ex_date"], event["cash_payment_date"])
    }
    window_action_dates = sorted(
        action_date for action_date in action_dates if window["start"] <= action_date <= window["end"]
    )
    if window_action_dates:
        raise ValueError("Registered no-cash-action window contains a reviewed cash-action date")
    required = set(case["blockers"])
    expected = {
        "historical_fcff_model_not_approved",
        "shared_industrial_financial_cost_unresolved",
        "cash_tax_scope_incomplete",
        "treasury_and_distribution_denominator_unresolved",
        "execution_and_benchmark_not_complete",
    }
    if required != expected:
        raise ValueError("Conditional input blockers changed; review mapping before reuse")
    mapping = [
        {
            "blocker": "historical_fcff_model_not_approved",
            "material_to_window": True,
            "waived": False,
            "reason": "The selected annual source is the first case in the conditional package; it has no prior annual operating-NWC input, so the experimental FCFF replay also cannot generate a range for this window.",
        },
        {
            "blocker": "shared_industrial_financial_cost_unresolved",
            "material_to_window": True,
            "waived": False,
            "reason": "The 2013 annual source labels the allocation only as an experimental sensitivity. A single annual source in the window does not establish the operating/financial allocation.",
        },
        {
            "blocker": "cash_tax_scope_incomplete",
            "material_to_window": True,
            "waived": False,
            "reason": "The source retains two tax-payable scopes; selecting either one for a tradeable value would be an unapproved assumption.",
        },
        {
            "blocker": "treasury_and_distribution_denominator_unresolved",
            "material_to_window": True,
            "waived": False,
            "reason": "No reviewed cash action occurs inside this 20-session window, but that does not establish the equity-recognition bridge or the issued-versus-treasury per-share denominator at the decision date.",
        },
        {
            "blocker": "execution_and_benchmark_not_complete",
            "material_to_window": True,
            "waived": False,
            "reason": "A replay still needs period-dated fees, next-open rules, liquidity, corporate-action treatment and accepted same-period benchmark data; none is supplied by window selection.",
        },
    ]
    return {
        "symbol": "600519",
        "mapping_version": "moutai-historical-window-blocker-map-v1",
        "window": window,
        "registered_status": registration["status"],
        "input_scope": {
            "annual_source_id": case["source"]["source_id"],
            "report_period": case["report_period"],
            "available_at": case["available_at"],
            "first_decision_at": selected_rows[0]["decision_at"],
            "last_decision_at": selected_rows[-1]["decision_at"],
        },
        "no_cash_action_within_window": {
            "verified": True,
            "reviewed_action_dates": window_action_dates,
            "scope_limit": "This only removes an in-window reviewed cash-action date. It does not resolve equity recognition, share denominator or prior-report capital treatment.",
        },
        "blocker_mapping": mapping,
        "additional_model_fact": {
            "blocker": "prior_annual_operating_nwc_incomplete",
            "material_to_window": True,
            "waived": False,
            "reason": "Eight 2012 comparative balance rows are dual-decoded from the 2013 annual report, but the notes-payable row is blank and remains unknown. The experimental model cannot silently substitute zero for it.",
            "comparative_evidence_complete": comparative_nwc["comparative_nwc_input_complete"],
            "unresolved_fields": comparative_nwc["unresolved_fields"],
        },
        "status": "mapped_not_replay_eligible",
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "trade_approved": False,
        "live_eligible": False,
        "conclusion": "The narrow window reduces scope but waives no value, execution, denominator or benchmark requirement. It cannot be replayed as a strategy backtest.",
        "inputs": {
            relative(path): digest(path)
            for path in (WINDOW_REGISTRATION, CONDITIONAL_INPUTS, DAILY_INPUTS, DISTRIBUTIONS, COMPARATIVE_NWC)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-window-blocker-map-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "script": relative(Path(__file__)),
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "window": result["window"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
