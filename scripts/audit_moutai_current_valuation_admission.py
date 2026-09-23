#!/usr/bin/env python3
"""Audit whether the current 600519 research can become a formal value."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_OBSERVATION_POINTER = ROOT / "runtime/company-research/600519-current-conditional-observation-latest.json"
SIMULATION_CLOSURE_POINTER = ROOT / "runtime/strategy-validation/moutai-simulation-closure-latest.json"
P1_MODEL_CONTRACT_POINTER = ROOT / "runtime/company-research/600519-p1-model-contract-latest.json"
CURRENT_CAPITAL_BRIDGE_POINTER = ROOT / "runtime/company-research/600519-current-capital-bridge-latest.json"
CURRENT_COST_POLICY_POINTER = ROOT / "runtime/company-research/600519-current-cost-of-equity-policy-latest.json"
CURRENT_FORWARD_ASSUMPTIONS_POINTER = ROOT / "runtime/company-research/600519-current-forward-assumptions-latest.json"
CURRENT_MODEL_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pointed_evidence(pointer: Path, evidence_name: str) -> tuple[dict, dict]:
    reference = json.loads(pointer.read_text(encoding="utf-8"))
    path = (ROOT / reference["path"] / evidence_name).resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError(f"Pinned {pointer.name} evidence changed")
    return json.loads(path.read_text(encoding="utf-8")), {"path": str(path.relative_to(ROOT)), "sha256": reference["sha256"]}


def load_pinned_reference(reference: dict) -> tuple[dict, dict]:
    path = (ROOT / reference["path"]).resolve()
    if path.is_dir():
        path = path / "evidence.json"
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned model dependency changed")
    return json.loads(path.read_text(encoding="utf-8")), {"path": str(path.relative_to(ROOT)), "sha256": reference["sha256"]}


def resolve_separate_execution_requirements(contract: dict) -> dict:
    """Derive the execution-policy fact from the pinned policy, not its stale flag.

    The v4 P1 contract moved its research date from 2026-09-21 to 2026-09-22.
    The separately dated paper-execution policy was observed on the prior session
    and is valid for the 2026-09-22 session. The audit must preserve that
    historical fact instead of letting an old boolean in the contract shadow the
    hash-bound policy that the contract itself references.
    """
    requirements = dict(contract.get("separate_execution_requirements") or {})
    if contract.get("contract_version") == "moutai-p1-model-contract-v4":
        policy_ref = requirements.get("daily_simulation_policy") or {}
        policy, _ = load_pinned_reference(policy_ref) if policy_ref else (None, {})
        implemented = bool(
            policy
            and policy.get("implementation_status")
            == "implemented_for_paper_execution_only"
            and policy.get("trade_approved") is False
            and policy.get("live_eligible") is False
            and contract.get("as_of") in {
                policy.get("observed_session"),
                policy.get("valid_session"),
            }
        )
        requirements["daily_simulation_policy_implemented"] = implemented
    return requirements


def audit() -> dict:
    observation, observation_ref = load_pointed_evidence(CURRENT_OBSERVATION_POINTER, "evidence.json")
    closure, closure_ref = load_pointed_evidence(SIMULATION_CLOSURE_POINTER, "summary.json")
    contract, contract_ref = load_pointed_evidence(P1_MODEL_CONTRACT_POINTER, "evidence.json")
    capital_bridge, capital_bridge_ref = load_pointed_evidence(CURRENT_CAPITAL_BRIDGE_POINTER, "evidence.json")
    cost_policy, cost_policy_ref = load_pointed_evidence(CURRENT_COST_POLICY_POINTER, "evidence.json")
    forward_assumptions, forward_assumptions_ref = load_pointed_evidence(CURRENT_FORWARD_ASSUMPTIONS_POINTER, "evidence.json")
    current_model, current_model_ref = load_pointed_evidence(CURRENT_MODEL_POINTER, "evidence.json")
    if (contract.get("contract_version") not in {"moutai-p1-model-contract-v2", "moutai-p1-model-contract-v3", "moutai-p1-model-contract-v4"}
            or contract.get("specified_simulation_eligible") is not False
            or contract.get("formal_fair_value") is not None
            or contract.get("trade_approved") is not False
            or contract.get("candidate_primary_model", {}).get("name") != "consolidated_parent_equity_residual_income_or_dividend_capacity"):
        raise ValueError("Unexpected P1 model contract scope")
    contract_gates = contract.get("admission_gates") or []
    if contract.get("contract_version") == "moutai-p1-model-contract-v4" and contract.get("inputs", {}).get("current_model") != current_model_ref:
        raise ValueError("Current P1 contract is not bound to the audited current model")
    separated = contract["contract_version"] in {"moutai-p1-model-contract-v3", "moutai-p1-model-contract-v4"}
    expected_gate_ids = ["parent_equity_scope", "model_arithmetic", "cost_of_equity_selection", "forward_assumptions", "current_share_capital_actions"]
    if not separated:
        expected_gate_ids.append("historical_execution")
    if [row.get("id") for row in contract_gates] != expected_gate_ids:
        raise ValueError("Unexpected P1 admission gates")
    market_session_passed = (observation.get("symbol") == "600519" and observation.get("quote_session_status") == "matched_close"
                             and observation.get("quote_session_verified") is True and observation.get("action") == "no_order"
                             and observation.get("trade_approved") is False)
    paper_execution_passed = (closure.get("symbol") == "600519" and closure.get("execution_mechanics_verified") is True
                              and closure.get("valuation_approved") is False and closure.get("trade_approved") is False
                              and closure.get("live_eligible") is False)
    context_checks = [
             {"id": "market_session", "passed": market_session_passed,
              "reason": "当前双源收盘价及上交所会话只验证本次研究观察，不构成历史逐日可成交性或交易批准。"},
             {"id": "paper_execution", "passed": paper_execution_passed,
              "reason": "既有虚拟账户机制证据；保守日线执行政策仍须实现和验证，模拟成交与实际可成交性分别判断。"}]
    capital_refresh_ref = current_model.get("inputs", {}).get("capital_refresh") or {}
    capital_refresh, _ = load_pinned_reference(capital_refresh_ref)
    current_model_at = datetime.fromisoformat(current_model["valuation_at"])
    current_model_date = current_model_at.date().isoformat()
    capital_refresh_timing_passed = (
        datetime.fromisoformat(capital_refresh["fetched_at"]) <= current_model_at
    )
    current_capital_passed = (
        capital_bridge.get("symbol") == "600519"
        and capital_bridge.get("as_of") == current_model_date
        and capital_bridge.get("passed") is True
        and capital_bridge.get("trade_approved") is False
        and capital_refresh_timing_passed
    )
    current_cost_policy_passed = (
        cost_policy.get("symbol") == "600519"
        and cost_policy.get("as_of") == current_model_date
        and cost_policy.get("passed") is True
        and cost_policy.get("trade_approved") is False
    )
    current_forward_assumptions_passed = (
        forward_assumptions.get("symbol") == "600519"
        and forward_assumptions.get("as_of") == current_model_date
        and forward_assumptions.get("passed") is True
        and forward_assumptions.get("trade_approved") is False
    )
    gates = []
    for gate in contract_gates:
        if gate["id"] == "cost_of_equity_selection":
            gates.append({
                "id": gate["id"], "passed": current_cost_policy_passed,
                "reason": "Current-model base/stress cost-of-equity selection is frozen before the " + current_model_date + " valuation date; it is a bounded policy, not a claim of a uniquely true rate.",
            })
        elif gate["id"] == "forward_assumptions":
            gates.append({
                "id": gate["id"], "passed": current_forward_assumptions_passed,
                "reason": "Current earnings, payout and franchise-fade assumptions are frozen with issuer facts, counterevidence and registered stresses; this is not proof of future outcomes.",
            })
        elif gate["id"] == "current_share_capital_actions":
            gates.append({
                "id": gate["id"], "passed": current_capital_passed,
                "reason": "Current-model share and capital-event bridge must be complete and available no later than the valuation time; it remains a bounded denominator assessment, not a registry certificate.",
            })
        else:
            gates.append(gate)
    if not separated:
        gates.extend(context_checks)
    p1_model_admitted = not any(not gate["passed"] for gate in gates)
    assessment = {
        "primary_model": {"name": "consolidated_parent_equity_residual_income_or_dividend_capacity", "role": "candidate_primary_model",
                          "facts_used": ["合并归母权益、归母利润和期末已发行股本为同一上市权益范围的已钉住事实链。"],
                          "assumptions_not_facts": ["资本成本为区间，ROE、留存、终值增长和衰减仍是条件假设。"]},
        "cross_check": {"name": "cash_distribution_anchored_equity_range", "role": "research_only_cross_check",
                        "limitation": "现金锚无法替代权益模型的前瞻假设或生成订单。"},
        "legacy_research_path": {"name": "industrial_operating_fcff_dcf_with_explicit_equity_bridge",
                                 "limitation": "旧 FCFF 的工业/金融范围与权益桥接问题被保留为反证，不再作为本契约主路径。"},
        "conclusion": ("admitted_for_bounded_current_paper_research" if p1_model_admitted
                       else "not_admitted_for_specified_simulation"),
        "allowed_output": ("A dated conditional research range and paper-account decision input; no formal fair value, safety-margin signal, order, historical strategy return, or live-trading admission."
                           if p1_model_admitted else
                           "research observations and counterevidence only; no formal fair value, safety-margin signal, order, historical strategy return, or simulation admission."),
            "next_evidence_path": [item for item in contract["next_evidence_path"]
                                   if not item.startswith("Bridge dividends")],
    }
    return {"symbol": "600519", "valuation_approved": False, "trade_approved": False, "formal_fair_value": None,
            "p1_current_model_admitted": p1_model_admitted,
            "admission_version": "current-valuation-admission-v3" if separated else "current-valuation-admission-v2",
            "gates": gates, "context_checks": context_checks,
            "market_session_evidence": observation_ref, "paper_execution_evidence": closure_ref,
            "p1_model_contract_evidence": contract_ref,
            "current_capital_bridge_evidence": capital_bridge_ref,
            "current_model_evidence": current_model_ref,
            "capital_refresh_timing_passed": capital_refresh_timing_passed,
            "current_cost_policy_evidence": cost_policy_ref,
            "current_forward_assumptions_evidence": forward_assumptions_ref,
            "blocking_gate_ids": [gate["id"] for gate in gates if not gate["passed"]],
            "model_scope_assessment": assessment,
             "separate_execution_requirements": resolve_separate_execution_requirements(contract),
            "interpretation": "Current valuation requires dated model facts, supported assumptions and accounting/capital-action bridges. P1 admission permits only the stated conditional paper-research scope; market observations and execution mechanics are separate context, not formal-value or trade approval. Historical and forward simulation retain their own execution requirements."}


def main() -> int:
    result = audit()
    output = ROOT / "runtime/company-research" / f"600519-current-valuation-admission-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/company-research/600519-current-valuation-admission-latest.json").write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "blocking_gate_ids": result["blocking_gate_ids"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
