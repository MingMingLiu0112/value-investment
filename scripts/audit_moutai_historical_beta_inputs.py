#!/usr/bin/env python3
"""Audit beta inputs without estimating or admitting a historical beta."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.collect_historical_prices import parse_bars
except ModuleNotFoundError:  # Direct execution keeps the script directory on sys.path.
    from collect_historical_prices import parse_bars


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
PRICE_AUDIT = ROOT / "runtime/historical-prices/20260908T061418761988Z/peer-date-audit.json"
BENCHMARK = ROOT / "runtime/strategy-validation/moutai-historical-window-benchmark-20260918T123302Z/evidence.json"
PREDECISION_DIRECTORY = ROOT / "runtime/historical-prices/20260920T074631172611Z"
PREDECISION_CROSSCHECK = ROOT / "runtime/strategy-validation/moutai-2014-price-crosscheck-20260920T084412Z/comparison.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    rows = json.loads(DAILY.read_text(encoding="utf-8"))
    price_audit = json.loads(PRICE_AUDIT.read_text(encoding="utf-8"))
    if len(rows) != 2674 or any(not row.get("date") or not row.get("close") for row in rows):
        raise ValueError("Historical decision inputs do not contain a complete Moutai close series")
    moutai = next((row for row in price_audit["companies"] if row["symbol"] == "sh600519"), None)
    if moutai is None or moutai["observed_dates"] != 2674 or moutai["unexplained_peer_dates"] != 0:
        raise ValueError("Archived unadjusted Moutai price coverage changed")
    pre_manifest = json.loads((PREDECISION_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    pre_entry = next((entry for entry in pre_manifest["requests"]
                      if entry["symbol"] == "sh600519" and entry["year"] == 2014), None)
    if pre_entry is None:
        raise ValueError("Pre-decision Moutai request is missing")
    pre_raw = PREDECISION_DIRECTORY / pre_entry["raw_file"]
    if digest(pre_raw) != pre_entry["sha256"]:
        raise ValueError("Pre-decision Moutai raw evidence changed")
    pre_bars = parse_bars(pre_raw.read_bytes(), "sh600519", 2014)
    if len(pre_bars) != 245 or pre_bars[0]["date"] != "2014-01-02" or pre_bars[-1]["date"] != "2014-12-31":
        raise ValueError("Pre-decision Moutai return candidate coverage changed")
    crosscheck = json.loads(PREDECISION_CROSSCHECK.read_text(encoding="utf-8"))
    if (crosscheck.get("symbol") != "600519" or crosscheck.get("year") != 2014
            or crosscheck.get("common_dates") != 245 or crosscheck.get("ohlc_mismatch_days") != 0
            or crosscheck.get("backtest_ready") is not False):
        raise ValueError("Pre-decision Moutai crosscheck changed")
    benchmark_exists = BENCHMARK.is_file()
    benchmark_status = "missing"
    if benchmark_exists:
        benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        benchmark_status = (
            "rejected_total_return_not_point_in_time"
            if benchmark.get("coverage_verified") and not benchmark.get("historical_version_verified")
            else "unexpected_benchmark_contract_state"
        )
    return {
        "contract_version": "moutai-historical-beta-input-audit-v1",
        "symbol": "600519",
        "company_close_input": {
            "sessions": len(rows),
            "first_date": rows[0]["date"],
            "last_date": rows[-1]["date"],
            "decision_input_sha256": digest(DAILY),
            "unadjusted_secondary_coverage_sessions": moutai["observed_dates"],
            "unexplained_peer_dates": moutai["unexplained_peer_dates"],
        },
        "benchmark_input_status": benchmark_status,
        "predecision_company_return_window": {
            "status": "secondary_unadjusted_candidate_crosschecked_research_only",
            "sessions": len(pre_bars), "first_date": pre_bars[0]["date"], "last_date": pre_bars[-1]["date"],
            "raw_sha256": pre_entry["sha256"],
            "crosscheck_path": str(PREDECISION_CROSSCHECK.relative_to(ROOT)),
            "crosscheck_sha256": digest(PREDECISION_CROSSCHECK),
        },
        "beta_policy_status": "blocked_missing_frozen_beta_policy_and_matched_point_in_time_benchmark",
        "beta_estimated": False,
        "historical_replay_eligible": False,
        "trade_approved": False,
        "limitations": [
            "The 2014 company series is a cross-checked secondary unadjusted candidate; it remains later-fetched, not point-in-time archived, and has no frozen corporate-action policy.",
            "A pre-decision company close candidate does not establish an ex-ante beta without a frozen minimum-observation policy and matched benchmark return definition.",
            "A 2026-fetched total-return index response cannot prove the version available at a 2015 decision and can embed later dividend treatment.",
            "No beta, equity risk premium, cost of equity, fair value, order, fill, strategy return or live approval is produced.",
        ],
    }


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-historical-beta-input-audit-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "beta_policy_status": json.loads(evidence.read_text(encoding="utf-8"))["beta_policy_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
