"""Compile a new, conditional 600519 first input from exact retained sources.

This case adapter reuses the existing E2 compiler. It never adopts a main
valuation, changes a current candidate, or grants an investment approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.research.company_profile import load_company_profile
from value_investment_agent.application.research.first_research_intake_v2 import (
    compile_first_research_from_intake, prepare_first_research_intake,
)
from value_investment_agent.application.product.common import encode_json_bytes, write_new_bytes

PROPOSAL = ROOT / "config/research-proposals/600519-joint-capital-cash-path-v4.json"
RATIONALE = ROOT / "config/research-assumptions/600519-joint-capital-cash-path-v4.json"
CASE_PACKAGE = ROOT / "runtime/joint-cash-v4-current/20261028T044953763337Z/600519/package.json"
PERIODS = ("2025-12-31", "2026-06-30", "2025-06-30")
FLOW_FIELDS = ("revenue", "cost", "surcharges", "selling", "admin", "research",
               "pre_tax_profit", "tax", "parent_profit")


def _binding(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT):
        raise ValueError("E2_BOUND_PATH_OUTSIDE_REPOSITORY")
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _unique_fact(facts: list[dict], field: str, period: str) -> str:
    rows = [row["id"] for row in facts if row["field"] == field and row["period_end"] == period]
    if len(rows) != 1:
        raise ValueError(f"E2_UNIQUE_NATIVE_FACT_REQUIRED:{field}:{period}")
    return rows[0]


def _ttm(facts: list[dict], field: str) -> dict:
    return {"operation": "TTM", "fact_ids": [_unique_fact(facts, field, period)
             for period in PERIODS]}


def _inputs(native: dict, native_path: Path, choice_id: str, now: datetime) -> tuple[dict, dict, dict]:
    if (native.get("symbol") != "600519" or native.get("financial_basis") != "2026-06-30"
            or native.get("action") != "no_order"):
        raise ValueError("E2_NATIVE_ISSUER_BASIS_OR_ACTION_INVALID")
    proposal = json.loads(PROPOSAL.read_bytes())
    rationale = json.loads(RATIONALE.read_bytes())
    package = json.loads(CASE_PACKAGE.read_bytes())
    if any(node.get("symbol") != "600519" for node in (proposal, rationale, package)):
        raise ValueError("E2_RESEARCH_ISSUER_INVALID")
    choices = [row for row in proposal["choices"] if row["id"] == choice_id]
    if len(choices) != 1:
        raise ValueError("E2_EXPLICIT_ECONOMIC_CHOICE_REQUIRED")
    choice = choices[0]
    refs = [_binding(path) for path in (native_path, PROPOSAL, RATIONALE, CASE_PACKAGE)]
    facts = native["facts"]
    historical = {field: _ttm(facts, field) for field in FLOW_FIELDS}
    historical["nonrecurring"] = {"operation": "DIFFERENCE", "operands": [
        _ttm(facts, "parent_profit"), _ttm(facts, "ex_parent_profit")]}
    amortization_labels = sorted({row["label"] for row in facts if row["field"] == "amortization"})
    if not amortization_labels or not all(any(row["field"] == "depreciation" and row["period_end"] == period
                                            for row in facts) for period in PERIODS):
        raise ValueError("E2_NATIVE_DEPRECIATION_AND_AMORTIZATION_REQUIRED")
    amortization_terms = []
    for label in amortization_labels:
        ids = []
        for period in PERIODS:
            rows = [row["id"] for row in facts if row["field"] == "amortization"
                    and row["label"] == label and row["period_end"] == period]
            if len(rows) != 1:
                raise ValueError(f"E2_NATIVE_AMORTIZATION_ROW_REQUIRED:{label}:{period}")
            ids.append(rows[0])
        amortization_terms.append({"operation": "TTM", "fact_ids": ids})
    historical["da"] = {"operation": "SUM", "operands": [
        _ttm(facts, "depreciation"), *amortization_terms]}
    for field in ("opening_cash", "opening_distribution_capacity", "cash_floor"):
        item = proposal["joint_historical"][field]
        historical[field] = {"assumption": {"value": item["value"], "unit": "CNY",
            "scope": "ordinary_owner_equivalent_cash_mapping", "rationale": item["rationale"],
            "source_bindings": refs}}
    assumptions = {"schema_version": "first-research-assumptions-v1", "action": "no_order",
        "symbol": "600519", "financial_basis": "2026-06-30", "generated_at": now.isoformat(),
        "assumption_scope": "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST",
        "source_bindings": refs,
        "choice": {key: choice[key] for key in ("id", "rationale", "countercase")},
        "historical_bindings": historical,
        "scenarios": {name: {"drivers": choice["joint_drivers"][name],
            "terminal_policy": choice["terminal_policy"][name],
            "cost_of_equity": choice["cost_of_equity"][name]}
            for name in ("bear", "base", "bull")}}
    profile = load_company_profile(root=ROOT, symbol="600519", now=now)
    if profile["status"] != "SOURCE_BOUND_PROFILE" or profile["profile"]["profile_id"] != "quality_compounder":
        raise ValueError("E2_SOURCE_BOUND_SUPPORTED_PROFILE_REQUIRED")
    original_case = package["research_case"]
    case_fields = ("industry", "investment_path", "thesis", "return_driver",
                   "mispricing_hypothesis", "positives", "counter_evidence",
                   "thesis_breakers", "next_events")
    research_case = {key: original_case[key] for key in case_fields}
    # Historical narrative citations belong to the old package's catalog.
    # Bind that immutable package as a research artifact; keep the original
    # granular IDs for audit without pretending they exist in the new catalog.
    old_ids = {row["id"] for row in package["sources"]}
    old_package_id = "first-input-" + refs[-1]["sha256"]
    official_ids = {row["id"] for row in native["sources"]}
    for field in ("positives", "counter_evidence", "thesis_breakers", "next_events"):
        revised = []
        for statement in research_case[field]:
            historical_refs = list(statement.get("evidence_refs", []))
            if any(ref not in old_ids for ref in historical_refs):
                raise ValueError("E2_HISTORICAL_RESEARCH_REFERENCE_UNBOUND")
            current_refs = list(dict.fromkeys(ref if ref in official_ids else old_package_id
                                               for ref in historical_refs))
            revised.append({**statement, "evidence_refs": current_refs,
                            "historical_evidence_refs": historical_refs})
        research_case[field] = revised
    research_case["investment_path"] += "；本次仅为未批准条件首编"
    return assumptions, profile, research_case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-facts", required=True, type=Path)
    parser.add_argument("--choice-id", required=True,
                        choices=("ADVANTAGE_CONTINUITY", "GRADUAL_EROSION", "FUNDING_PRESSURE"))
    args = parser.parse_args()
    native_path = (ROOT / args.native_facts).resolve()
    native_binding = _binding(native_path)
    native = json.loads(native_path.read_bytes())
    now = datetime.now(timezone.utc)
    assumptions, profile, case = _inputs(native, native_path, args.choice_id, now)
    run_id = "moutai-e2-" + now.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    output = ROOT / "runtime/e2-first-input-600519-20261117" / run_id
    output.mkdir(parents=True, exist_ok=False)
    assumption_path, profile_path = output / "assumptions.json", output / "profile.json"
    write_new_bytes(assumption_path, encode_json_bytes(assumptions))
    write_new_bytes(profile_path, encode_json_bytes(profile))
    facts = native["facts"]
    intake = {"schema_version": "first-research-intake-v2", "action": "no_order",
        "symbol": "600519", "name": "贵州茅台", "run_id": run_id,
        "point_in_time": {"report_period": "2026-06-30", "valuation_date": "2026-06-30",
            "research_as_of": now.date().isoformat(), "available_at": now.isoformat(),
            "computed_at": now.isoformat()},
        "source_binding": native_binding, "assumption_binding": _binding(assumption_path),
        "profile_binding": _binding(profile_path),
        "capital_bindings": {"start_book_equity": _unique_fact(facts, "start_book_equity", "2026-06-30"),
            "ordinary_shares": _unique_fact(facts, "ordinary_shares", "2026-06-30")},
        "share_basis": "issued_ordinary_shares", "research_case": case}
    prepared = prepare_first_research_intake(root=ROOT, intake=intake, now=now)
    compiled = compile_first_research_from_intake(root=ROOT, intake=intake,
        intake_output_dir=output / "intake", output_dir=output / "compilation", now=now,
        compiler_version="v2")
    print(json.dumps({"status": compiled["status"], "action": "no_order", "run_id": run_id,
        "choice_id": args.choice_id, "spec_sha256": prepared["input_manifest"]["spec_sha256"],
        "input_manifest_binding": compiled["input_manifest_binding"],
        "compilation": compiled["compilation"]}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
