#!/usr/bin/env python3
"""Audit the bounded R0 research-card acceptance for 600519.

R0 means that the research card has the required evidence-backed content and
states its decision boundary.  It is deliberately not a valuation, simulation,
or trading approval.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime" / "company-research"
POINTER = RESEARCH / "600519-research-card-evidence-latest.json"
VERSION = "moutai-r0-research-card-acceptance-v1"
REQUIRED_FLAGS = (
    "valuation_approved",
    "simulation_eligible",
    "trade_approved",
    "live_eligible",
)
CONTENT_REQUIREMENTS = {
    "business_engine": ("business_model", "earnings", "sales_realization"),
    "profit_cash_debt_capital_allocation": (
        "cash_distribution", "resilience", "liquidity_boundary", "capital_allocation", "governance",
    ),
    "support_and_counterevidence": (
        "counterevidence", "resilience_counterevidence", "governance_counterevidence",
    ),
    "model_and_assumption_scope": ("model_basis", "market_implied_expectation", "valuation"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned(pointer: Path) -> tuple[dict, Path, str]:
    reference = json.loads(pointer.read_text(encoding="utf-8"))
    target = (ROOT / reference["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Research-card pointer escapes the project root")
    expected = reference["sha256"]
    actual = sha256(target)
    if actual != expected:
        raise ValueError(f"Research-card evidence hash mismatch: {target}")
    return json.loads(target.read_text(encoding="utf-8")), target, actual


def dependency_result(reference: dict) -> dict:
    target = (ROOT / reference["path"]).resolve()
    expected = reference["sha256"]
    result = {
        "path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT.resolve()) else str(target),
        "expected_sha256": expected,
        "exists": target.exists(),
        "within_project": target.is_relative_to(ROOT.resolve()),
    }
    if result["exists"] and result["within_project"]:
        result["actual_sha256"] = sha256(target)
        result["passed"] = result["actual_sha256"] == expected
    else:
        result["actual_sha256"] = None
        result["passed"] = False
    return result


def content_check(conclusions: dict, fields: tuple[str, ...]) -> dict:
    missing = [field for field in fields if not isinstance(conclusions.get(field), str) or not conclusions[field].strip()]
    return {"required_fields": list(fields), "missing_fields": missing, "passed": not missing}


def audit() -> dict:
    card, evidence_path, card_sha256 = load_pinned(POINTER)
    if card.get("symbol") != "600519":
        raise ValueError("Research card is not for 600519")
    dependencies = {name: dependency_result(reference) for name, reference in card.get("evidence", {}).items()}
    content = {name: content_check(card.get("conclusions", {}), fields) for name, fields in CONTENT_REQUIREMENTS.items()}
    content["price_and_action_boundary"] = {
        "required_fields": ["not_holding", "holding"],
        "missing_fields": [
            name for name in ("not_holding", "holding")
            if not isinstance(card.get("conditional_actions", {}).get(name), str)
            or not card["conditional_actions"][name].strip()
        ],
    }
    content["price_and_action_boundary"]["passed"] = not content["price_and_action_boundary"]["missing_fields"]
    monitoring_missing = []
    if not isinstance(card.get("next_event"), str) or not card["next_event"].strip():
        monitoring_missing.append("next_event")
    gaps = card.get("gaps")
    if not isinstance(gaps, list) or not gaps or any(not isinstance(item, str) or not item.strip() for item in gaps):
        monitoring_missing.append("gaps")
    content["monitoring_and_decision_gaps"] = {
        "required_fields": ["next_event", "gaps"],
        "missing_fields": monitoring_missing,
        "decision_changing_gap_count": len(gaps) if isinstance(gaps, list) else None,
        "max_allowed": 3,
        "passed": not monitoring_missing and len(gaps) <= 3,
    }
    flags = {name: card.get(name) for name in REQUIRED_FLAGS}
    flags_passed = all(value is False for value in flags.values())
    dependencies_passed = bool(dependencies) and all(result["passed"] for result in dependencies.values())
    content_passed = all(result["passed"] for result in content.values())
    return {
        "acceptance_version": VERSION,
        "symbol": "600519",
        "scope": "R0 company research-card content and evidence acceptance only; not a fair-value, simulation, paper-order, or trading approval.",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "research_card": {
            "path": str(evidence_path.relative_to(ROOT)),
            "sha256": card_sha256,
            "version": card.get("research_card_version"),
            "as_of": card.get("as_of"),
        },
        "dependencies": dependencies,
        "content": content,
        "decision_flags": flags,
        "decision_flags_passed": flags_passed,
        "r0_research_card_accepted": dependencies_passed and content_passed and flags_passed,
        "formal_fair_value": card.get("formal_fair_value"),
        "valuation_approved": card.get("valuation_approved"),
        "simulation_eligible": card.get("simulation_eligible"),
        "trade_approved": card.get("trade_approved"),
        "live_eligible": card.get("live_eligible"),
        "next_step": "Rebuild the specified-date valuation admission with point-in-time inputs; R0 does not authorize simulation or trading.",
    }


def main() -> int:
    result = audit()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = RESEARCH / f"600519-r0-research-card-acceptance-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": sha256(Path(__file__)), "evidence_sha256": sha256(evidence)}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-r0-research-card-acceptance-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": manifest["evidence_sha256"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "r0_research_card_accepted": result["r0_research_card_accepted"]}, ensure_ascii=False))
    return 0 if result["r0_research_card_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
