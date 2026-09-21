#!/usr/bin/env python3
"""Build a point-in-time, primary-source timeline of Moutai cash distributions.

This is an evidence input for later equity research, not a payout forecast.  An
annual-cycle implementation can be paired with the most recent available
annual EPS only when the implementation contains no bonus shares.  December
special distributions stay separate, because dividing them by a prior annual
EPS would misrepresent their economic period as a financial-year payout ratio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
DAILY_INPUT_SHA256 = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
DISTRIBUTIONS = ROOT / "docs/reviewed-cash-distributions.json"
VERSION = "moutai-historical-distribution-timeline-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_events() -> list[dict]:
    packet = json.loads(DISTRIBUTIONS.read_text(encoding="utf-8"))
    result = []
    seen = set()
    for event in packet["events"]:
        if event["symbol"] != "600519":
            continue
        key = (event["symbol"], event["record_date"])
        if key in seen:
            raise ValueError("Duplicate Moutai cash-distribution record date")
        seen.add(key)
        if Decimal(event["cash_per_share"]) <= 0:
            raise ValueError("Cash distribution must be positive")
        for evidence in event["evidence"]:
            source = ROOT / evidence["path"]
            if not source.is_file() or digest(source) != evidence["sha256"]:
                raise ValueError("Distribution evidence hash mismatch")
        result.append(event)
    return sorted(result, key=lambda event: event["cash_payment_date"])


def latest_annual_before(rows: list[dict], as_of: date) -> dict | None:
    candidates = [row for row in rows if parse_date(row["date"]) <= as_of]
    if not candidates:
        return None
    selected = candidates[-1]
    if selected["decision_at"] < selected["annual_available_at"]:
        raise ValueError("Future annual result leaked into distribution timeline")
    return selected


def annual_cycle_candidate(event: dict) -> bool:
    """Only June/July implementations are annual-cycle candidates in this archive.

    The December events are individually retained as special distributions.  The
    date rule prevents their cash amount from being labelled as a financial-year
    payout ratio; it does not assert that all June/July events are ordinary
    dividends.
    """
    return parse_date(event["cash_payment_date"]).month in (6, 7)


def build(rows: list[dict], events: list[dict]) -> tuple[list[dict], list[dict]]:
    observations = []
    for event in events:
        payment = parse_date(event["cash_payment_date"])
        annual = latest_annual_before(rows, payment)
        base = {
            "event_id": f"600519:{event['record_date']}",
            "record_date": event["record_date"],
            "ex_date": event["ex_date"],
            "cash_payment_date": event["cash_payment_date"],
            "available_for_research_at": f"{event['cash_payment_date']}T00:00:00+08:00",
            "cash_per_share_cny": event["cash_per_share"],
            "source_evidence": event["evidence"],
            "tax_treatment_verified": event.get("tax_treatment_verified", False),
            "annual_cycle_candidate": annual_cycle_candidate(event),
            "formal_fair_value": None,
            "valuation_approved": False,
            "trade_approved": False,
        }
        if not annual_cycle_candidate(event):
            observations.append({**base, "status": "special_distribution_not_annual_payout_ratio",
                                 "annual_source_id": None, "annual_profit_per_share_cny": None,
                                 "cash_to_prior_annual_eps_ratio": None})
            continue
        if event.get("bonus_shares_per_share") not in (None, "0", "0.0", "0.00"):
            observations.append({**base, "status": "blocked_bonus_share_denominator_ambiguous",
                                 "annual_source_id": annual["annual_source_id"] if annual else None,
                                 "annual_profit_per_share_cny": None,
                                 "cash_to_prior_annual_eps_ratio": None})
            continue
        if annual is None:
            observations.append({**base, "status": "blocked_no_available_annual_eps",
                                 "annual_source_id": None, "annual_profit_per_share_cny": None,
                                 "cash_to_prior_annual_eps_ratio": None})
            continue
        eps = Decimal(annual["annual_profit_per_bonus_adjusted_share"])
        if eps <= 0:
            raise ValueError("Annual EPS must be positive for a payout observation")
        observations.append({**base, "status": "annual_cycle_cash_to_available_annual_eps",
                             "annual_source_id": annual["annual_source_id"],
                             "annual_report_period": annual["report_period"],
                             "annual_available_at": annual["annual_available_at"],
                             "annual_profit_per_share_cny": str(eps),
                             "cash_to_prior_annual_eps_ratio": str(Decimal(event["cash_per_share"]) / eps)})

    timeline = []
    known = []
    for row in rows:
        current_date = parse_date(row["date"])
        known.extend(item for item in observations
                     if parse_date(item["cash_payment_date"]) == current_date)
        accepted = [item for item in known if item["status"] == "annual_cycle_cash_to_available_annual_eps"]
        latest = accepted[-1] if accepted else None
        timeline.append({"date": row["date"], "annual_source_id": row["annual_source_id"],
                         "latest_annual_cycle_distribution_event_id": latest["event_id"] if latest else None,
                         "latest_cash_to_prior_annual_eps_ratio": latest["cash_to_prior_annual_eps_ratio"] if latest else None,
                         "status": "prior_annual_cycle_cash_observation_available" if latest else "no_prior_annual_cycle_cash_observation",
                         "formal_fair_value": None, "valuation_approved": False, "trade_approved": False})
    return observations, timeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(DAILY_INPUT) != DAILY_INPUT_SHA256:
        raise ValueError("Pinned daily research input changed")
    rows = json.loads(DAILY_INPUT.read_text(encoding="utf-8"))
    observations, timeline = build(rows, load_events())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-distribution-timeline-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    observations_path = output / "observations.json"
    timeline_path = output / "daily-timeline.json"
    observations_path.write_text(json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": VERSION, "events": len(observations),
               "annual_cycle_cash_to_available_annual_eps": sum(item["status"] == "annual_cycle_cash_to_available_annual_eps" for item in observations),
               "special_distributions_kept_separate": sum(item["status"] == "special_distribution_not_annual_payout_ratio" for item in observations),
               "bonus_share_denominator_blocked": sum(item["status"] == "blocked_bonus_share_denominator_ambiguous" for item in observations),
               "sessions_with_prior_annual_cycle_cash_observation": sum(item["status"] == "prior_annual_cycle_cash_observation_available" for item in timeline),
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "interpretation": "This is a point-in-time record of implemented cash entitlements. A cash-to-prior-annual-EPS ratio is a historical observation, not a forecast payout ratio, dividend policy, fair value, or order signal."}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"inputs": {str(DAILY_INPUT.relative_to(ROOT)): DAILY_INPUT_SHA256,
                            str(DISTRIBUTIONS.relative_to(ROOT)): digest(DISTRIBUTIONS),
                            "script_sha256": digest(Path(__file__))},
                "outputs": {path.name: digest(path) for path in (observations_path, timeline_path, summary_path)}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-distribution-timeline-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(summary_path),
                    "observations_sha256": digest(observations_path), "timeline_sha256": digest(timeline_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
