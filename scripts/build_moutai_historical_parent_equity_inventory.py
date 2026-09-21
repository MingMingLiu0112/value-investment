#!/usr/bin/env python3
"""Verify the point-in-time parent-equity facts for the registered 2015 window.

This is a source inventory, not a historical valuation or strategy replay.  It
keeps the reported 2013 balance-sheet claim distinct from the subsequently
effective 2014 share/distribution event so a model cannot silently divide an
old equity figure by a newer share count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "runtime/strategy-validation/moutai-historical-window-registration-20260918T121703Z/evidence.json"
WARMUP = ROOT / "runtime/strategy-validation/moutai-warmup-20260909T062823719664Z"
EXPECTED_SOURCE_ID = "cninfo:63720184"
FIRST_DECISION_AT = "2015-01-05T15:00:00+08:00"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def build() -> dict:
    registration = load(REGISTRATION)
    annual_inputs = load(WARMUP / "annual-inputs.json")
    bridge = load(WARMUP / "share-bridge.json")
    window = registration["window"]
    if window["annual_source_id"] != EXPECTED_SOURCE_ID or window["report_period"] != "2013-12-31":
        raise ValueError("Registered window no longer binds the reviewed 2013 annual source")
    row = next((item for item in annual_inputs if item["source_id"] == EXPECTED_SOURCE_ID), None)
    if row is None:
        raise ValueError("Pinned annual source absent from warmup inventory")
    if row["available_at"] > FIRST_DECISION_AT:
        raise ValueError("Annual report was not available before the first registered decision")
    expected_inputs = {
        "parent_equity_cny": "42622216487.81",
        "parent_profit_cny": "15136639784.35",
        "ending_issued_shares": "1038180000",
        "reported_basic_eps": "14.58",
    }
    if row["inputs"] != expected_inputs:
        raise ValueError("Reviewed annual parent-equity inputs changed")
    evidence_by_field = {item["literal"]: item["page"] for item in row["evidence"]}
    required_pages = {
        "归属于上市公司股东的净资产42,622,216,487.81": 7,
        "归属于母公司所有者权益合计42,622,216,487.81": 45,
        "归属于上市公司股东的净利润15,136,639,784.35": 7,
        "归属于母公司所有者的净利润15,136,639,784.35": 49,
        "以2013年年末总股本103,818万股为基数": 2,
    }
    if any(evidence_by_field.get(literal) != page for literal, page in required_pages.items()):
        raise ValueError("Annual source page evidence is incomplete or changed")
    if bridge["pre_event_issued_shares"] != expected_inputs["ending_issued_shares"]:
        raise ValueError("Pre-event issued-share bridge does not match annual source")
    if Decimal(bridge["post_event_issued_shares"]) != Decimal("1141998000") or bridge["share_scale_effective_on"] > window["start"]:
        raise ValueError("Registered window does not follow the reviewed 2014 share event")
    if bridge["cash_distributed_gross_cny"] != "4540999320.00000":
        raise ValueError("Reviewed 2014 gross cash distribution changed")
    if row["trade_input_approved"] or registration["trade_approved"]:
        raise ValueError("Research-only historical evidence unexpectedly promoted")
    return {
        "inventory_version": "moutai-historical-parent-equity-inventory-v1",
        "symbol": "600519",
        "window": window,
        "decision_information_cutoff": FIRST_DECISION_AT,
        "status": "historical_parent_equity_input_inventory_verified_not_valuation_admitted",
        "annual_parent_equity_fact": {
            "report_period": row["period_label"],
            "available_at": row["available_at"],
            "source_id": row["source_id"],
            "source_url": row["source_url"],
            "source_path": row["source_path"],
            "raw_file_hash": row["raw_file_hash"],
            "parent_equity_cny": row["inputs"]["parent_equity_cny"],
            "parent_profit_cny": row["inputs"]["parent_profit_cny"],
            "reported_ending_issued_shares": row["inputs"]["ending_issued_shares"],
            "reported_basic_eps": row["inputs"]["reported_basic_eps"],
            "cross_statement_pages": {
                "parent_equity_summary": 7,
                "parent_equity_balance_sheet": 45,
                "parent_profit_summary": 7,
                "parent_profit_income_statement": 49,
                "issued_share_disclosure": 2,
            },
            "availability_verified_before_first_decision": True,
        },
        "intervening_capital_and_distribution_context": {
            "event_effective_before_window": True,
            "issued_shares_after_2014_bonus_event": bridge["post_event_issued_shares"],
            "gross_cash_distribution_cny": bridge["cash_distributed_gross_cny"],
            "treatment": "Recorded as a separate event. It is not netted against the 2013 parent equity or used to create a per-share residual-income input.",
        },
        "model_readiness": {
            "parent_equity_scope_verified": True,
            "parent_profit_scope_verified": True,
            "issued_share_event_identified": True,
            "post_distribution_equity_recognition_verified": False,
            "historical_forward_assumptions_registered": False,
            "historical_residual_income_contract_frozen": False,
            "historical_execution_contract_complete": False,
            "benchmark_accepted": False,
        },
        "material_gaps": [
            "The annual parent-equity amount predates the reviewed 2014 cash distribution; its post-distribution recognition cannot be inferred by subtraction.",
            "No historical residual-income forecast, cost-of-equity policy, or assumption freeze exists for this decision window.",
            "Dated fees, next-open execution, liquidity, corporate-action treatment and a same-period accepted benchmark remain incomplete.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "inputs": {
            relative(REGISTRATION): digest(REGISTRATION),
            relative(WARMUP / "annual-inputs.json"): digest(WARMUP / "annual-inputs.json"),
            relative(WARMUP / "share-bridge.json"): digest(WARMUP / "share-bridge.json"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-parent-equity-inventory-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "script": relative(Path(__file__)),
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "source_id": EXPECTED_SOURCE_ID}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
