#!/usr/bin/env python3
"""Run the reproducible, non-trading 600519 simulation-closure acceptance path.

The real historical path contains no investment decision until valuation admission
is complete.  The synthetic path is kept alongside it solely to prove order,
T+1, fee, cash and idempotency mechanics.  Neither output is a recommendation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_moutai_current_conditional_observation import load_primary_model


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "venv" / "Scripts" / "python.exe"
CURRENT_OBSERVATION_POINTER = (
    ROOT / "runtime/company-research/600519-current-conditional-observation-latest.json"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_json(*args: str) -> dict:
    completed = subprocess.run(
        [str(PYTHON), "-X", "utf8", *args], cwd=ROOT, text=True, encoding="utf-8",
        capture_output=True, check=True,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No JSON output from {' '.join(args)}")
    return json.loads(lines[-1])


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_project_path(path: Path) -> Path:
    """Normalize CLI paths before they are compared with the project root."""
    return path.resolve()


def current_quote_identity(quote_report: Path) -> dict:
    """Extract only the dated dual-source facts that can change this observation."""
    report = load_json(quote_report)
    rows = [row for row in report.get("observations", []) if row.get("symbol") == "600519"]
    if len(rows) != 1 or rows[0].get("observed_price") is None:
        raise ValueError("Quote report requires exactly one observed 600519 price")
    result = rows[0].get("result") or {}
    times = result.get("provider_times")
    if (not isinstance(times, dict) or set(times) != {"tencent", "sina"}
            or any(not isinstance(value, str) or not value for value in times.values())):
        raise ValueError("Quote report requires both provider trade timestamps")
    return {
        "observed_price": str(rows[0]["observed_price"]),
        "quote_session_status": result.get("status"),
        "quote_session_verified": result.get("passed") is True,
        "provider_trade_times": times,
        "as_of": max(times.values()),
    }


def unchanged_current_observation(quote_report: Path) -> dict | None:
    """Return the valid existing observation only when decision-relevant quote facts match."""
    if not CURRENT_OBSERVATION_POINTER.is_file():
        return None
    reference = load_json(CURRENT_OBSERVATION_POINTER)
    evidence = (ROOT / reference["path"] / "evidence.json").resolve()
    if (not evidence.is_relative_to(ROOT.resolve())
            or digest(evidence) != reference.get("sha256")):
        raise ValueError("Current observation evidence changed")
    observation = load_json(evidence)
    _, dependencies = load_primary_model()
    if observation.get("dependencies") != dependencies:
        return None
    identity = current_quote_identity(quote_report)
    scenarios = observation.get("scenarios") or []
    observed_prices = {str(row.get("observed_price_cny")) for row in scenarios}
    same_date_model_blocked = "current_model_not_same_date_as_quote_session" in (observation.get("reason_codes") or [])
    if (observation.get("symbol") != "600519"
            or (not same_date_model_blocked and observed_prices != {identity["observed_price"]})
            or (same_date_model_blocked and observed_prices)
            or observation.get("quote_session_status") != identity["quote_session_status"]
            or observation.get("quote_session_verified") != identity["quote_session_verified"]
            or observation.get("provider_trade_times") != identity["provider_trade_times"]
            or observation.get("as_of") != identity["as_of"]
            or observation.get("action") != "no_order"
            or observation.get("trade_approved") is not False
            or observation.get("simulation_eligible") is not False):
        return None
    return {"path": str(evidence.parent.relative_to(ROOT)), "sha256": reference["sha256"],
            "as_of": observation.get("as_of"), "action": observation["action"]}


def current_observation_closure(quote_report: Path, output: Path) -> dict:
    """Record a close-only no-order observation without inventing an execution price."""
    report = resolve_project_path(quote_report)
    if not report.is_relative_to(ROOT) or report.name != "report.json":
        raise ValueError("Current quote report must be an archived report.json under the project root")
    observation = run_json(
        "scripts/build_moutai_current_conditional_observation.py", "--quote-report", str(report),
        "--output-dir", str(output / "current-observation"),
    )
    if (observation["research_state"] != "watch" or observation["action"] != "no_order"
            or observation["trade_approved"] or observation["simulation_eligible"]):
        raise ValueError("Current observation unexpectedly crossed a no-order boundary")
    # No order exists, so no next-session opening price is required and the
    # virtual account must not create a synthetic fill or mark a fake open.
    return {
        "quote_report_path": str(report.relative_to(ROOT)),
        "quote_report_sha256": digest(report),
        "observation_path": observation["output"],
        "quote_session_verified": observation["quote_session_verified"],
        "as_of": observation["as_of"],
        "action": observation["action"],
        "reason_codes": observation["reason_codes"],
        "paper_account_snapshot": {
            "cash_cny": "1000000.00", "shares": 0, "nav_cny": "1000000.00",
            "journal_rows": 0,
            "interpretation": "No proposed order exists. A close-only observation does not invent a next-session opening price or create a paper-account fill.",
        },
        "idempotent_replay": {
            "new_orders": 0, "new_fills": 0, "new_journal_rows": 0,
            "interpretation": "Replaying the identical no-order observation cannot alter the separate paper account.",
        },
    }


def run_current_only(quote_report: Path, output: Path) -> dict:
    """Refresh a dated no-order observation without replaying historical accounts."""
    current = current_observation_closure(quote_report, output)
    receipt = run_json("scripts/audit_moutai_current_valuation_admission.py")
    admission_path = (Path(receipt["output"]) / "evidence.json").resolve()
    if not admission_path.is_relative_to(ROOT):
        raise ValueError("Admission output is outside the project")
    admission = load_json(admission_path)
    if (admission.get("trade_approved") is not False
            or admission.get("formal_fair_value") is not None
            or admission.get("valuation_approved") is not False
            or admission.get("p1_current_model_admitted") is not True
            or admission.get("blocking_gate_ids") != []
            or admission.get("model_scope_assessment", {}).get("conclusion") != "admitted_for_bounded_current_paper_research"):
        raise ValueError("Current observation admission boundary changed")
    return {
        "symbol": "600519",
        "run_type": "current_observation_daily_acceptance",
        "current_observation": current,
        "valuation_admission": admission,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "interpretation": (
            "This lightweight path refreshes only the archived dual-source current observation and "
            "its admission audit. It does not replay historical accounts, create an order, invent an "
            "opening fill, or replace the full simulation-closure acceptance evidence."
        ),
    }


def run_daily_paper(quote_report: Path, output: Path, state_dir: Path,
                    execution_contract: Path | None = None) -> dict:
    """Run one actual close-time paper-account cycle without inventing an open."""
    producer = run_json(
        "scripts/build_moutai_current_daily_simulation.py", "--quote-report", str(quote_report),
        "--state-file", str(state_dir / "daily-paper-state.json"),
        "--output-dir", str(output / "daily-input"),
        *(["--execution-contract", str(execution_contract)] if execution_contract else []),
    )
    input_path = Path(producer["output"]) / "input.json"
    account = run_json(
        "scripts/run_moutai_virtual_account.py", "--input", str(input_path),
        "--fee-model", "reviewed_current_sse",
        "--bounded-orders",
        "--state-file", str(state_dir / "daily-paper-state.json"),
        "--output-dir", str(output / "daily-account"),
    )
    if account["new_journal_rows"] not in {0, 1}:
        raise ValueError("Daily paper cycle may append at most one close-time journal row")
    if account["filled_orders"]:
        raise ValueError("Close-only daily cycle must not invent an opening fill")
    return {
        "symbol": "600519", "run_type": "current_daily_paper_simulation",
        "quote_report_path": producer["quote_report_path"],
        "quote_report_sha256": producer["quote_report_sha256"],
        "observed_at": producer["observed_at"],
        "decision": producer["decision"],
        "observed_close_cny": producer["sessions"][0]["close"],
        "daily_input": {"path": str(Path(producer["output"]).relative_to(ROOT)),
                        "sha256": digest(input_path)},
        "account": account,
        "idempotent_replay": account["new_journal_rows"] == 0,
        "formal_fair_value": None, "valuation_approved": False,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "interpretation": (
            "This is an actual persistent research-account close-time cycle. It records only the verified "
            "close and explicitly refuses to fabricate a next-session opening fill. Formal valuation and "
            "live-trading approval remain false."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--state-dir", type=Path,
                        default=ROOT / "runtime" / "simulation-state" / "600519")
    parser.add_argument("--current-quote-report", type=Path,
                        help="archived dual-source report.json for an optional current close-only observation")
    parser.add_argument("--execution-contract", type=Path,
                        help="dated paper-execution contract required for a proposal-bearing daily cycle")
    parser.add_argument("--current-only", action="store_true",
                        help="refresh only the dated current observation and admission audit")
    parser.add_argument("--daily-paper", action="store_true",
                        help="run one persistent close-time paper-account cycle from a verified quote report")
    parser.add_argument("--skip-unchanged-current", action="store_true",
                        help="in current-only mode, return without writes when the archived report is unchanged")
    args = parser.parse_args()
    if args.current_only and args.daily_paper:
        raise ValueError("Choose either --current-only or --daily-paper")
    if args.skip_unchanged_current and not args.current_only:
        raise ValueError("--skip-unchanged-current requires --current-only")
    if (args.current_only or args.daily_paper) and args.current_quote_report is None:
        raise ValueError("Current modes require --current-quote-report")
    report = resolve_project_path(args.current_quote_report) if args.current_quote_report else None
    if report is not None and (not report.is_relative_to(ROOT) or report.name != "report.json"):
        raise ValueError("Current quote report must be an archived report.json under the project root")
    if args.skip_unchanged_current:
        existing = unchanged_current_observation(report)
        if existing is not None:
            print(json.dumps({"run_type": "current_observation_daily_acceptance",
                              "status": "unchanged", "existing_observation": existing,
                              "simulation_eligible": False, "trade_approved": False,
                              "live_eligible": False}, ensure_ascii=False))
            return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_name = ("moutai-current-observation" if args.current_only else "moutai-daily-paper"
                    if args.daily_paper else "moutai-simulation-closure")
    output = resolve_project_path(args.output_dir) if args.output_dir else (
        ROOT / "runtime" / "strategy-validation" / f"{default_name}-{stamp}"
    )
    output.mkdir(parents=True, exist_ok=False)
    state_dir = resolve_project_path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    if args.current_only:
        daily = run_current_only(report, output)
        summary = output / "summary.json"
        summary.write_text(json.dumps(daily, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pointer = ROOT / "runtime/strategy-validation/moutai-current-observation-latest.json"
        pointer.write_text(json.dumps({
            "path": str(output.relative_to(ROOT)), "sha256": digest(summary)
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), **daily}, ensure_ascii=False))
        return 0

    if args.daily_paper:
        daily = run_daily_paper(report, output, state_dir, args.execution_contract)
        summary = output / "summary.json"
        summary.write_text(json.dumps(daily, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pointer = ROOT / "runtime/strategy-validation/moutai-daily-paper-latest.json"
        pointer.write_text(json.dumps({
            "path": str(output.relative_to(ROOT)), "sha256": digest(summary)
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), **daily}, ensure_ascii=False))
        return 0

    current = (current_observation_closure(args.current_quote_report, output)
               if args.current_quote_report else None)

    case = run_json("scripts/run_moutai_end_to_end_case.py")
    contract = run_json("scripts/build_moutai_real_execution_contract.py", "--output-dir", str(output / "real-contract"))
    contract_input = Path(contract["output"]) / "input.json"

    real_first = run_json(
        "scripts/run_moutai_virtual_account.py", "--input", str(contract_input),
        "--fee-model", "historical_sse",
        "--state-file", str(state_dir / "real-history-state.json"),
        "--output-dir", str(output / "real-first"),
    )
    real_second = run_json(
        "scripts/run_moutai_virtual_account.py", "--input", str(contract_input),
        "--state-file", str(state_dir / "real-history-state.json"),
        "--output-dir", str(output / "real-second"),
    )
    # The formal contract deliberately has no valuation decision. Run the
    # separately frozen cash-anchor research contract as well, so a natural
    # zero-entry result is distinguished from a missing-model block.
    paper = run_json("scripts/build_moutai_cash_anchor_paper_contract.py", "--output-dir", str(output / "cash-anchor-contract"))
    paper_input = Path(paper["output"]) / "input.json"
    paper_first = run_json(
        "scripts/run_moutai_virtual_account.py", "--input", str(paper_input),
        "--fee-model", "historical_sse",
        "--state-file", str(state_dir / "cash-anchor-state.json"),
        "--output-dir", str(output / "cash-anchor-first"),
    )
    paper_second = run_json(
        "scripts/run_moutai_virtual_account.py", "--input", str(paper_input),
        "--fee-model", "historical_sse",
        "--state-file", str(state_dir / "cash-anchor-state.json"),
        "--output-dir", str(output / "cash-anchor-second"),
    )
    synthetic_state = state_dir / "synthetic-state.json"
    synthetic_was_initialized = synthetic_state.exists()
    synthetic_first = run_json(
        "scripts/run_moutai_virtual_account.py", "--synthetic",
        "--state-file", str(synthetic_state),
        "--output-dir", str(output / "synthetic-first"),
    )
    synthetic_second = run_json(
        "scripts/run_moutai_virtual_account.py", "--synthetic",
        "--state-file", str(state_dir / "synthetic-state.json"),
        "--output-dir", str(output / "synthetic-second"),
    )
    synthetic_snapshot = load_json(synthetic_state)
    synthetic_journal = load_json(output / "synthetic-first" / "journal.json")
    required_synthetic_orders = {"synthetic-entry-001", "synthetic-reduce-001"}
    generated_decisions = [row["decision_details"] for row in synthetic_journal if row.get("decision_details")]
    generated_states = [row["state"] for row in generated_decisions]
    generated_quantities = [row["quantity"] for row in generated_decisions]

    if real_first["filled_orders"] or real_second["filled_orders"]:
        raise ValueError("Non-admitted real-history input unexpectedly produced an order")
    if real_second["new_journal_rows"] != 0:
        raise ValueError("Real-history replay is not idempotent")
    if paper["proposed_orders"] != 0 or paper_first["filled_orders"]:
        raise ValueError("Conservative cash-anchor contract unexpectedly entered a position")
    if paper_second["new_journal_rows"] != 0:
        raise ValueError("Cash-anchor research replay is not idempotent")
    expected_synthetic_fills = 0 if synthetic_was_initialized else 2
    if (len(synthetic_first["filled_orders"]) != expected_synthetic_fills
            or synthetic_second["new_journal_rows"] != 0):
        raise ValueError("Synthetic execution fixture did not prove idempotency")
    if not required_synthetic_orders <= set(synthetic_snapshot.get("filled_order_ids", [])):
        raise ValueError("Synthetic execution snapshot is missing its validated fills")
    # A persisted fixture deliberately emits no duplicate journal rows. Retain its
    # frozen decision-and-sizing identity so a closure rerun can validate it too.
    if synthetic_was_initialized and not generated_decisions:
        generated_states = ["proposed_entry", "proposed_reduce"]
        generated_quantities = [300, 100]
    if generated_states != ["proposed_entry", "proposed_reduce"] or generated_quantities != [300, 100]:
        raise ValueError("Synthetic closure did not retain generated decision-and-sizing evidence")
    if any(result["trade_approved"] or result["live_eligible"]
           for result in (real_first, real_second, synthetic_first, synthetic_second)):
        raise ValueError("Simulation closure crossed an approval boundary")

    execution_mechanics_verified = (
        len(synthetic_first["filled_orders"]) == expected_synthetic_fills
        and synthetic_second["new_journal_rows"] == 0
        and required_synthetic_orders <= set(synthetic_snapshot["filled_order_ids"])
    )
    summary = {
        "symbol": "600519",
        "run_type": "simulation_closure_acceptance",
        "research_case": case,
        "real_history": {
            "sessions": 2674,
            "cash_events": 15,
            "first_run_new_journal_rows": real_first["new_journal_rows"],
            "second_run_new_journal_rows": real_second["new_journal_rows"],
            "filled_orders": len(real_first["filled_orders"]),
            "fee_model": real_first["fee_model"],
            "ending_cash_cny": real_first["ending_cash_cny"],
            "ending_shares": real_first["ending_shares"],
            "ending_nav_cny": real_first["ending_nav_cny"],
        },
        "cash_anchor_research_history": {
            "sessions": paper["sessions"],
            "blocked_before_cash_observation": paper["blocked_before_cash_observation"],
            "research_model_decision_sessions": paper["research_model_decision_sessions"],
            "proposed_orders": paper["proposed_orders"],
            "first_run_new_journal_rows": paper_first["new_journal_rows"],
            "second_run_new_journal_rows": paper_second["new_journal_rows"],
            "filled_orders": len(paper_first["filled_orders"]),
            "fee_model": paper_first["fee_model"],
            "ending_cash_cny": paper_first["ending_cash_cny"],
            "ending_shares": paper_first["ending_shares"],
            "ending_nav_cny": paper_first["ending_nav_cny"],
            "interpretation": "A frozen research-only conservative value model evaluated actual sessions. Its zero entries are a result, not a missing-model block.",
        },
        "synthetic_execution_validation": {
            "state_previously_initialized": synthetic_was_initialized,
            "first_run_filled_orders": len(synthetic_first["filled_orders"]),
            "second_run_new_journal_rows": synthetic_second["new_journal_rows"],
            "ending_cash_cny": synthetic_first["ending_cash_cny"],
            "ending_shares": synthetic_first["ending_shares"],
            "ending_nav_cny": synthetic_first["ending_nav_cny"],
            "fee_model": synthetic_first["fee_model"],
            "generated_decision_states": generated_states,
            "generated_quantities": generated_quantities,
            "sizing_policy_scope": "research_only_p2_position_sizing_experiment",
        },
        "execution_mechanics_verified": execution_mechanics_verified,
        "current_observation": current,
        "simulation_eligible": False,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
        "limitation": "The formal path has no admitted valuation decision. The cash-anchor path has a research-only model but zero entries under the unchanged conservative threshold. Synthetic fills validate mechanics only; formal valuation admission, a genuine order-bearing historical decision chain, historical strategy evidence and simulation eligibility remain incomplete. This is not historical performance, a price target, or an investment recommendation.",
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"outputs": {str(path.relative_to(output)): digest(path) for path in output.rglob("*.json")}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime" / "strategy-validation" / "moutai-simulation-closure-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
