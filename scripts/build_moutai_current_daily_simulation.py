#!/usr/bin/env python3
"""Build one close-only, research-only 600519 daily paper-account input.

This producer deliberately separates an observed close from next-session
execution evidence.  It may create a paper proposal only when all registered
research gates are satisfied; it never grants formal valuation or live-trading
approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.paper_sizing import size_entry_or_add, size_one_third_reduce
from value_investment_agent.quote_session_collection import resolve_session_reference
from value_investment_agent.quote_sessions import next_sse_2026_session
from value_investment_agent.simulation_state import DecisionInput, evaluate
from value_investment_agent.virtual_account import ORDER_TERMS_VERSION, VirtualAccount


CURRENT_MODEL_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"
SCOPE_REVIEW_POINTER = ROOT / "runtime/company-research/600519-current-equity-scope-review-latest.json"
THESIS_POINTER = ROOT / "runtime/company-research/600519-current-thesis-latest.json"
ADMISSION_POINTER = ROOT / "runtime/company-research/600519-current-valuation-admission-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_evidence(path: Path | None, pointer_path: Path, label: str) -> tuple[dict, dict]:
    """Load a root-contained evidence file, preserving its exact content hash.

    The optional path exists for archived, date-consistent P2 replays.  It is
    deliberately an explicit ``evidence.json`` artifact rather than an
    unqualified directory or a mutable ``latest`` pointer.
    """
    if path is None:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        evidence = (ROOT / pointer["path"] / "evidence.json").resolve()
        expected = pointer.get("sha256")
    else:
        evidence = path.resolve()
        expected = None
    if (evidence.name != "evidence.json" or not evidence.is_file()
            or not evidence.is_relative_to(ROOT.resolve())):
        raise ValueError(f"{label} evidence must be an evidence.json file under the project root")
    actual = digest(evidence)
    if expected is not None and actual != expected:
        raise ValueError(f"Pinned {label} evidence changed")
    return json.loads(evidence.read_text(encoding="utf-8")), {
        "path": str(evidence.relative_to(ROOT)), "sha256": actual,
    }


def load_pinned_current_model(evidence_path: Path | None = None) -> tuple[dict, dict]:
    model, reference = load_evidence(evidence_path, CURRENT_MODEL_POINTER, "current valuation")
    if (model.get("symbol") != "600519"
            or model.get("model_version") != "moutai-current-parent-equity-residual-income-v1"
            or model.get("formal_fair_value") is not None
            or model.get("valuation_approved") is not False):
        raise ValueError("Unexpected current model scope")
    return model, reference


def load_scope_review(model_ref: dict, evidence_path: Path | None = None) -> dict:
    review, reference = load_evidence(evidence_path, SCOPE_REVIEW_POINTER, "current-model scope review")
    if (review.get("decision") != "admitted_for_bounded_same_date_paper_research_only"
            or review.get("current_model") != model_ref or review.get("trade_approved") is not False):
        raise ValueError("Unexpected current-model scope review")
    return reference


def load_thesis(observed_at: datetime, evidence_path: Path | None = None) -> dict:
    thesis, reference = load_evidence(evidence_path, THESIS_POINTER, "current thesis")
    if thesis.get("symbol") != "600519" or thesis.get("trade_approved") is not False:
        raise ValueError("Unexpected current thesis scope")
    if thesis.get("thesis_intact") not in {True, False}:
        raise ValueError("Current thesis has no determinate status")
    return {"thesis_intact": thesis["thesis_intact"],
            "as_of": thesis.get("as_of"),
            "compatible_with_quote_session": thesis.get("as_of") == observed_at.date().isoformat(),
            **reference}


def load_nested_reference(reference: object, label: str) -> tuple[dict, dict]:
    """Resolve a hash-pinned evidence reference stored by another artifact."""
    if not isinstance(reference, dict):
        raise ValueError(f"{label} must be a hash-pinned evidence reference")
    raw_path, expected = reference.get("path"), reference.get("sha256")
    if not isinstance(raw_path, str) or not isinstance(expected, str):
        raise ValueError(f"{label} must include path and sha256")
    path = (ROOT / raw_path.replace("\\", "/")).resolve()
    if (path.name != "evidence.json" or not path.is_file()
            or not path.is_relative_to(ROOT.resolve())):
        raise ValueError(f"{label} must resolve to project-contained evidence.json")
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"{label} hash does not match its pinned value")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.relative_to(ROOT)), "sha256": actual,
    }


def load_p1_admission(model_ref: dict, observed_at: datetime,
                      evidence_path: Path | None = None) -> dict:
    admission, reference = load_evidence(evidence_path, ADMISSION_POINTER, "current valuation-admission")
    assessment = admission.get("model_scope_assessment") or {}
    if (admission.get("symbol") != "600519"
            or not isinstance(admission.get("p1_current_model_admitted"), bool)
            or not isinstance(admission.get("blocking_gate_ids"), list)
            or assessment.get("conclusion") not in {
                "admitted_for_bounded_current_paper_research", "not_admitted_for_specified_simulation"}
            or admission.get("formal_fair_value") is not None
            or admission.get("trade_approved") is not False):
        raise ValueError("Unexpected current P1 admission scope")
    direct_model = admission.get("current_model_evidence")
    if direct_model is not None:
        if direct_model != model_ref:
            raise ValueError("Current P1 admission references a different valuation model")
    else:
        bridge, _ = load_nested_reference(
            admission.get("current_capital_bridge_evidence"),
            "Current P1 admission capital bridge")
        if (bridge.get("symbol") != "600519"
                or (bridge.get("evidence") or {}).get("current_model") != model_ref):
            raise ValueError("Current P1 admission capital bridge references a different valuation model")
    return {"p1_current_model_admitted": admission["p1_current_model_admitted"],
            "blocking_gate_ids": admission["blocking_gate_ids"], "as_of": observed_at.date().isoformat(),
            **reference}


def load_quote(report_path: Path) -> tuple[Decimal, datetime, dict, dict]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = [row for row in report.get("observations", []) if row.get("symbol") == "600519"]
    if len(rows) != 1:
        raise ValueError("Quote report requires one 600519 observation")
    result = rows[0].get("result") or {}
    times = result.get("provider_times")
    if result.get("passed") is not True or not isinstance(times, dict) or set(times) != {"tencent", "sina"}:
        raise ValueError("Quote report requires a verified dual-source session")
    observed_at = max(datetime.fromisoformat(value) for value in times.values())
    price = Decimal(str(rows[0].get("observed_price")))
    if not price.is_finite() or price <= 0:
        raise ValueError("Quote report requires a positive observed price")
    bundle_path = report_path.with_name("bundle.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    reference = (bundle.get("references") or {}).get("600519")
    resolved = resolve_session_reference(reference, bundle.get("documents"))
    calendar_checked_at = datetime.fromisoformat(bundle["finished_at"])
    if calendar_checked_at.tzinfo is None or calendar_checked_at < observed_at:
        raise ValueError("Quote-session bundle completion time is invalid")
    next_session, calendar_hashes = next_sse_2026_session(
        resolved["calendar_documents"], observed_at.date(), calendar_checked_at)
    return price, observed_at, result, {
        "date": next_session,
        "calendar_source_url": resolved["calendar_documents"][0]["source_url"],
        "calendar_source_hashes": calendar_hashes,
        "calendar_checked_at": calendar_checked_at.isoformat(),
        "status": "scheduled_by_official_calendar_open_evidence_pending",
    }


def model_value(model: dict) -> Decimal:
    rows = [row for row in model.get("results") or [] if row.get("scenario") == "base"]
    if len(rows) != 1:
        raise ValueError("Current model requires exactly one base scenario")
    value = Decimal(rows[0]["conditional_value_per_current_disclosed_share_cny"])
    if not value.is_finite() or value <= 0:
        raise ValueError("Current base value must be positive")
    return value


def bounded_execution_terms(*, decision: dict, observed_at: datetime, value: Decimal,
                            execution: dict, model_ref: dict, admission: dict) -> dict | None:
    """Freeze the terms required by the existing virtual-account ledger.

    A close-time proposal can only carry terms already supported by the dated
    execution contract.  The later opening session decides whether it fills;
    this function never supplies or infers that opening price.
    """
    state = decision.get("state")
    if state not in {"proposed_entry", "proposed_add", "proposed_reduce"}:
        return None
    if not execution["execution_ready"]:
        raise ValueError("A paper proposal requires an execution-ready dated contract")
    if not execution["path"] or not execution["sha256"]:
        raise ValueError("A paper proposal requires a pinned execution-contract file")
    quantity = decision.get("quantity")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("A paper proposal requires an explicit positive board-lot quantity")
    margin = Decimal("0.30")
    # Entry/add proposals use the registered 30% P2 experiment threshold. A
    # valuation-driven reduction requires net proceeds no lower than the same
    # dated conditional value used to create the proposal.
    limit = (value * (Decimal(1) - margin) if state in {"proposed_entry", "proposed_add"} else value)
    limit = limit.quantize(Decimal("0.01"))
    sizing = decision.get("sizing") or {}
    cash_budget = (Decimal(str(sizing.get("permitted_budget_cny", "0")))
                   if state in {"proposed_entry", "proposed_add"} else Decimal("0"))
    if cash_budget < 0:
        raise ValueError("Paper proposal cannot have a negative cash budget")
    return {
        "version": ORDER_TERMS_VERSION,
        "valid_session": execution["next_session"],
        "limit_price": str(limit),
        "cash_budget_cny": str(cash_budget),
        "liquidity_budget_cny": str(execution["liquidity_budget_cny"]),
        "liquidity_as_of": observed_at.date().isoformat(),
        "slippage_bps": str(execution["slippage_bps"]),
        "basis_id": (
            f"600519-p2-{observed_at.date().isoformat()}-"
            f"{model_ref['sha256'][:12]}-{admission['sha256'][:12]}-{execution['sha256'][:12]}"
        ),
    }


def load_execution_contract(contract_path: Path, observed_at: datetime, next_session: dict) -> dict:
    contract_path = contract_path.resolve()
    if not contract_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Execution contract must remain under the project root")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (contract.get("symbol") != "600519" or contract.get("observed_session") != observed_at.date().isoformat()
            or contract.get("valid_session") != next_session["date"]
            or contract.get("trade_approved") is not False or contract.get("live_eligible") is not False
            or type(contract.get("execution_ready")) is not bool):
        raise ValueError("Execution contract is incompatible with the quote session")
    return {"execution_ready": contract["execution_ready"], "blockers": contract.get("blockers", []),
            "path": str(contract_path.relative_to(ROOT)), "sha256": digest(contract_path),
            "next_session": contract["valid_session"], "slippage_bps": contract["slippage_bps"],
            "liquidity_budget_cny": contract.get("liquidity_budget_cny")}


def build(quote_report: Path, account: VirtualAccount | None = None,
          execution_contract: Path | None = None, model_evidence: Path | None = None,
          scope_review_evidence: Path | None = None, thesis_evidence: Path | None = None,
          admission_evidence: Path | None = None) -> dict:
    quote_report = quote_report.resolve()
    if not quote_report.is_relative_to(ROOT.resolve()):
        raise ValueError("Quote report must remain under the project root")
    model, model_ref = load_pinned_current_model(model_evidence)
    scope_review = load_scope_review(model_ref, scope_review_evidence)
    price, observed_at, quote, next_session = load_quote(quote_report)
    thesis = load_thesis(observed_at, thesis_evidence)
    admission = load_p1_admission(model_ref, observed_at, admission_evidence)
    account = account or VirtualAccount()
    execution = (load_execution_contract(execution_contract, observed_at, next_session)
                 if execution_contract else {"execution_ready": False,
                                              "blockers": ["execution_contract_missing"],
                                              "path": None, "sha256": None,
                                              "next_session": next_session["date"],
                                              "slippage_bps": None, "liquidity_budget_cny": None})
    model_at = datetime.fromisoformat(model["valuation_at"])
    blockers: list[str] = []
    # A dated model cannot be carried across later closes until the capital
    # event inventory and valuation package have been refreshed for that date.
    if model_at.date() != observed_at.date():
        blockers.append("current_model_stale_for_quote_session")
    if not thesis["compatible_with_quote_session"]:
        blockers.append("current_thesis_stale_for_quote_session")
    if not admission["p1_current_model_admitted"]:
        blockers.append("p1_current_model_not_admitted")
    if model.get("review_status") != "current_model_and_sensitivity_ready_for_scope_review":
        blockers.append("current_model_scope_not_review_ready")
    thesis_intact = thesis["thesis_intact"]
    state = evaluate(DecisionInput(
        price=price,
        value=model_value(model),
        holding_shares=account.shares,
        data_ready=not blockers,
        valuation_approved=False,
        research_model_ready=admission["p1_current_model_admitted"] and not blockers,
        account_ready=True,
        execution_ready=execution["execution_ready"],
        thesis_intact=thesis_intact,
        trade_session_open=True,
        blockers=tuple(blockers),
    ))
    decision = {**state, "decision_id": "600519-close-" + observed_at.date().isoformat(),
                "decision_scope": "current_close_research_only"}
    if state["state"] == "proposed_entry":
        sizing = size_entry_or_add(nav=account.marked_nav(), cash=account.cash,
                                   current_shares=account.shares, price=price, tranche_index=0)
        decision["quantity"] = sizing["quantity"]
        decision["sizing"] = sizing
    elif state["state"] == "proposed_reduce":
        sizing = size_one_third_reduce(sellable_shares=account.sellable_shares(observed_at.date()))
        decision["quantity"] = sizing["quantity"]
        decision["sizing"] = sizing
    terms = bounded_execution_terms(decision=decision, observed_at=observed_at,
                                    value=model_value(model), execution=execution,
                                    model_ref=model_ref, admission=admission)
    if terms is not None:
        decision["execution_terms"] = terms
    return {
        "symbol": "600519",
        "run_type": "current_close_paper_simulation_input",
        "quote_report_path": str(quote_report.relative_to(ROOT)),
        "quote_report_sha256": digest(quote_report),
        "current_model": model_ref,
        "scope_review": scope_review,
        "thesis": thesis,
        "p1_admission": admission,
        "execution_contract": execution,
        "observed_at": observed_at.isoformat(),
        "sessions": [{
            "date": observed_at.date().isoformat(), "open": None, "close": str(price),
            "execution_ready": False, "execution_status": "close_only_next_open_not_observed",
            "execution_reason": "This run has a verified close only; no next-session opening execution evidence is available.",
        }],
        "decisions": {observed_at.date().isoformat(): decision},
        "decision": decision,
        "quote_session": {"status": quote.get("status"), "expected_session": quote.get("expected_session"),
                          "provider_times": quote["provider_times"]},
        "next_session": next_session,
        "formal_fair_value": None, "valuation_approved": False,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "limitation": "A verified close may record a bounded paper-research decision but cannot imply a next-session fill. A later quote date requires refreshed current-model and P1-admission evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execution-contract", type=Path)
    parser.add_argument("--model-evidence", type=Path,
                        help="pinned historical/current model evidence.json for a date-consistent replay")
    parser.add_argument("--scope-review-evidence", type=Path,
                        help="scope review evidence.json matching --model-evidence")
    parser.add_argument("--thesis-evidence", type=Path,
                        help="dated thesis evidence.json matching the quote session")
    parser.add_argument("--admission-evidence", type=Path,
                        help="dated P1 admission evidence.json for the same paper-research scope")
    args = parser.parse_args()
    account = None
    if args.state_file and args.state_file.exists():
        account = VirtualAccount.from_dict(json.loads(args.state_file.read_text(encoding="utf-8")))
    payload = build(args.quote_report, account, args.execution_contract,
                    args.model_evidence, args.scope_review_evidence,
                    args.thesis_evidence, args.admission_evidence)
    if args.output_dir:
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        input_path = output / "input.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
            "input_sha256": digest(input_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        payload = {"output": str(output), **payload}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
