#!/usr/bin/env python3
"""Freeze authenticated Moutai OHLC and cash events for the virtual ledger.

This creates a data/execution contract, not a value signal.  Decisions remain
blocked until a separate point-in-time valuation admission is satisfied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from replay_moutai_distributions import load_inputs


PRICE_LIMIT_RULE_PATH = (
    "runtime/exchange-rules/sse-limit-rule-2012/source.html"
)
PRICE_LIMIT_RULE_SHA256 = (
    "ba1178daccbe886e979161c9b60f30635108096e80dc950a753ea9a08fa3ad73"
)
PEER_DATE_AUDIT_PATH = (
    "runtime/historical-prices/20260908T061418761988Z/peer-date-audit.json"
)
PEER_DATE_AUDIT_SHA256 = (
    "77ab9523b4bab14027fbfb48b4ba708eb23debca387e2d0cd0cec03171bde65b"
)
SSE_CALENDAR_AUDIT_PATH = (
    "runtime/exchange-calendar-probes/moutai-sse-calendar-audit-20260913T093954Z/evidence.json"
)
SSE_CALENDAR_AUDIT_SHA256 = (
    "ad5e6eca1515a57a199058d82a7a12d903e2aeb3cae17c51f3f973a6dac8c3b3"
)
SSE_SUSPENSION_AUDIT_PATH = (
    "runtime/exchange-suspension-probes/moutai-sse-suspension-audit-20260913T095625Z/evidence.json"
)
SSE_SUSPENSION_AUDIT_SHA256 = (
    "fc350ba01bd9abea5901962907b31c865fe6f8a88aef29fd5881ba4f8449734b"
)
PRICE_TICK = Decimal("0.01")
MAIN_BOARD_LIMIT = Decimal("0.10")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def round_to_tick(value: Decimal) -> Decimal:
    return value.quantize(PRICE_TICK, rounding=ROUND_HALF_UP)


def classify_open(row: dict, previous: dict | None) -> dict:
    """Classify only what daily bars and the archived rule can establish.

    A daily bar cannot prove queue position, order-book depth, or a market-order
    fill.  Every result is deliberately non-executable until separate evidence
    admits the relevant session.
    """
    if previous is None:
        return {
            "execution_status": "first_archived_bar_no_prior_close",
            "open_limit_classification": "not_computable_without_prior_close",
            "price_limit_up": None,
            "price_limit_down": None,
            "execution_limitation": (
                "The archive begins on this session, so its exchange limit cannot be "
                "computed from an authenticated prior close. No fill is permitted."
            ),
            "next_open_fill_eligible": False,
        }

    prior_close = Decimal(str(previous["close"]))
    observed_open = Decimal(str(row["open"]))
    upper = round_to_tick(prior_close * (Decimal("1") + MAIN_BOARD_LIMIT))
    lower = round_to_tick(prior_close * (Decimal("1") - MAIN_BOARD_LIMIT))
    if observed_open == upper:
        classification = "open_at_upper_limit_queue_unknown"
        limitation = (
            "Observed open equals the rule-derived upper price limit. Daily OHLC/volume "
            "does not establish buy-side queue position or a fill."
        )
    elif observed_open == lower:
        classification = "open_at_lower_limit_queue_unknown"
        limitation = (
            "Observed open equals the rule-derived lower price limit. Daily OHLC/volume "
            "does not establish sell-side queue position or a fill."
        )
    else:
        classification = "open_not_at_derived_limit_no_orderbook"
        limitation = (
            "Observed open is not at the rule-derived daily limit, but daily OHLC/volume "
            "does not establish order-book depth, queue priority, suspension state, or a fill."
        )
    return {
        "execution_status": "daily_bar_execution_not_admitted",
        "open_limit_classification": classification,
        "price_limit_up": str(upper),
        "price_limit_down": str(lower),
        "execution_limitation": limitation,
        "next_open_fill_eligible": False,
    }


def load_secondary_date_crosscheck() -> dict:
    audit_path = ROOT / PEER_DATE_AUDIT_PATH
    if digest(audit_path) != PEER_DATE_AUDIT_SHA256:
        raise ValueError("Pinned secondary peer-date audit changed")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["reference"] != "Union of three secondary-provider series, not exchange calendar":
        raise ValueError("Unexpected peer-date audit scope")
    rows = [row for row in audit["companies"] if row["symbol"] == "sh600519"]
    if len(rows) != 1 or rows[0]["observed_dates"] != 2674 or rows[0]["unexplained_peer_dates"] != 0:
        raise ValueError("Unexpected Moutai secondary date crosscheck")
    return {
        "path": PEER_DATE_AUDIT_PATH,
        "sha256": PEER_DATE_AUDIT_SHA256,
        "observed_dates": rows[0]["observed_dates"],
        "unexplained_peer_dates": rows[0]["unexplained_peer_dates"],
        "status": "no_secondary_peer_gap_not_official_calendar",
        "limitation": (
            "The peer union can detect a symbol-specific secondary-provider gap, but cannot "
            "prove an official exchange session or suspension state."
        ),
    }


def load_sse_calendar_audit() -> dict:
    audit_path = ROOT / SSE_CALENDAR_AUDIT_PATH
    if digest(audit_path) != SSE_CALENDAR_AUDIT_SHA256:
        raise ValueError("Pinned SSE calendar audit changed")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if not audit["calendar_approved"] or audit["execution_approved"]:
        raise ValueError("Unexpected SSE calendar audit status")
    if audit["sse_open_dates"] != 2674 or audit["missing_from_moutai"] or audit["extra_moutai_dates"]:
        raise ValueError("Unexpected SSE calendar date coverage")
    return {
        "path": SSE_CALENDAR_AUDIT_PATH,
        "sha256": SSE_CALENDAR_AUDIT_SHA256,
        "sse_open_dates": audit["sse_open_dates"],
        "calendar_approved": True,
        "execution_approved": False,
        "limitation": audit["limitation"],
    }


def load_sse_suspension_audit() -> dict:
    audit_path = ROOT / SSE_SUSPENSION_AUDIT_PATH
    if digest(audit_path) != SSE_SUSPENSION_AUDIT_SHA256:
        raise ValueError("Pinned SSE suspension audit changed")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit["symbol"] != "600519" or audit["period"] != "2015-01-01..2025-12-31"
            or audit["suspension_status_evidence"] != "no_official_listed_stop_resume_records_returned"
            or audit["official_returned_record_count"] != 0):
        raise ValueError("Unexpected SSE suspension audit result")
    if len(audit["queries"]) != 4 or any(row["records"] != 0 for row in audit["queries"]):
        raise ValueError("Incomplete SSE suspension-query coverage")
    return {
        "path": SSE_SUSPENSION_AUDIT_PATH,
        "sha256": SSE_SUSPENSION_AUDIT_SHA256,
        "queried_windows": len(audit["queries"]),
        "official_returned_record_count": 0,
        "status": audit["suspension_status_evidence"],
        "execution_approved": False,
        "limitation": audit["limitation"],
    }


def build_contract() -> dict:
    bars, events, annual, references = load_inputs(ROOT)
    rule_path = ROOT / PRICE_LIMIT_RULE_PATH
    if digest(rule_path) != PRICE_LIMIT_RULE_SHA256:
        raise ValueError("Archived SSE price-limit rule changed")
    rule_text = rule_path.read_text(encoding="utf-8", errors="replace")
    if "涨跌幅比例为10%" not in rule_text or "四舍五入" not in rule_text:
        raise ValueError("Archived SSE price-limit rule text is incomplete")
    secondary_date_crosscheck = load_secondary_date_crosscheck()
    sse_calendar_audit = load_sse_calendar_audit()
    sse_suspension_audit = load_sse_suspension_audit()

    sessions = []
    for index, row in enumerate(bars):
        session = {
            "date": row["date"],
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume_raw": str(row["volume_raw"]),
        }
        session.update(classify_open(row, bars[index - 1] if index else None))
        sessions.append(session)
    cash_events = [{"event_id": f"600519:{row['record_date']}", "record_date": row["record_date"],
                    "ex_date": row["ex_date"], "payment_date": row["cash_payment_date"],
                    "cash_per_share": str(row["cash_per_share"]),
                    "bonus_shares_per_share": row.get("bonus_shares_per_share"),
                    "bonus_listing_date": row.get("bonus_listing_date")} for row in events]
    if len(sessions) != 2674 or sessions[0]["date"] != "2015-01-05" or sessions[-1]["date"] != "2025-12-31":
        raise ValueError("Unexpected authenticated Moutai session coverage")
    if len(cash_events) != 15:
        raise ValueError("Unexpected reviewed cash-event coverage")
    references.append({
        "kind": "sse_main_board_price_limit_rule",
        "path": PRICE_LIMIT_RULE_PATH,
        "sha256": PRICE_LIMIT_RULE_SHA256,
        "url": "https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20150912_3988628.shtml",
        "scope": "2015-2025 ordinary main-board 10 percent price-limit arithmetic only",
    })
    return {"symbol": "600519", "contract_version": "moutai-real-execution-input-v5",
            "input_scope": "authenticated_historical_daily_OHLC_volume_reviewed_cash_distributions_archived_sse_limit_rule_official_sse_calendar_and_suspension_audits_and_secondary_date_crosscheck",
            "sessions": sessions, "cash_events": cash_events, "decisions": {},
            "annual_source_count": len(annual), "references": references,
            "secondary_date_crosscheck": secondary_date_crosscheck,
            "sse_calendar_audit": sse_calendar_audit,
            "sse_suspension_audit": sse_suspension_audit,
            "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
            "interpretation": "This permits chronological valuation, income-accounting and conservative "
                              "daily price-limit screening research only. The official SSE calendar audit confirms date "
                              "membership and the official suspension query returned no listed stop/resume events; the secondary date crosscheck finds no Moutai-specific provider date gap. "
                              "Every daily session remains non-executable because these sources do not prove intraday order-book "
                              "liquidity, queue position, costs or a next-open fill."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-real-execution-contract-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    contract = build_contract()
    input_path = output / "input.json"
    input_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: contract[key] for key in ("symbol", "contract_version", "input_scope", "formal_fair_value", "valuation_approved", "trade_approved", "interpretation")}
    summary.update({"sessions": len(contract["sessions"]), "cash_events": len(contract["cash_events"]), "input_sha256": digest(input_path)})
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "outputs": {p.name: digest(p) for p in output.iterdir()}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
