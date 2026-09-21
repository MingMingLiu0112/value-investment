#!/usr/bin/env python3
"""Build annual point-in-time conditional FCFF research inputs for 600519.

The output is deliberately a finite research sensitivity package.  It is not a
fair-value model, does not provide a trade value and cannot approve a trade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
FILING_MANIFEST = ROOT / "runtime/historical-filing-index/20260909T061926130764Z/pdfs/manifest-20260909T062000269149Z.json"
CANDIDATE_DIR = ROOT / "runtime/historical-candidates-v26-20260908"
VERSION = "moutai-historical-conditional-inputs-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def value(row: dict, key: str) -> Decimal | None:
    raw = row.get(key)
    return Decimal(str(raw)) if raw is not None else None


def find_source_metadata(value: object, source_id: str) -> list[dict]:
    """Locate all matching source objects retained inside the frozen row."""
    matches = []
    if isinstance(value, dict):
        if value.get("source_id") == source_id and value.get("source_url"):
            matches.append(value)
        for nested in value.values():
            matches.extend(find_source_metadata(nested, source_id))
    elif isinstance(value, list):
        for nested in value:
            matches.extend(find_source_metadata(nested, source_id))
    return matches


def annual_rows(rows: list[dict]) -> list[dict]:
    """Select the first session where each annual report was actually available."""
    selected: dict[str, dict] = {}
    for row in rows:
        available_at = row["annual_available_at"]
        if row["decision_at"] < available_at:
            raise ValueError("Future annual report present before its availability bound")
        selected.setdefault(row["annual_source_id"], row)
    return [selected[key] for key in sorted(selected, key=lambda key: selected[key]["annual_available_at"])]


def filing_sources() -> dict[str, dict]:
    sources = {}
    for packet_path in sorted(CANDIDATE_DIR.glob("600519-*.json")):
        announcement = json.loads(packet_path.read_text(encoding="utf-8"))["announcement"]
        sources["cninfo:" + announcement["announcement_id"]] = announcement
    for announcement in json.loads(FILING_MANIFEST.read_text(encoding="utf-8")):
        sources.setdefault("cninfo:" + announcement["announcement_id"], announcement)
    return sources


def build_case(row: dict, filings: dict[str, dict]) -> dict:
    operating = row["annual_operating_lines_cny"]
    balance = row["annual_capital_balance_lines_cny"]
    subtotal = value(row, "annual_operating_subtotal_cny")
    capex_less_da = value(row, "annual_cash_capex_less_da_excluding_rou_cny")
    issued_shares = value(row, "bonus_adjusted_share_basis")
    revenue, cost = value(operating, "revenue"), value(operating, "cost")
    if subtotal is None or capex_less_da is None or issued_shares is None or revenue is None or cost is None:
        raise ValueError("Required source-backed annual field missing")
    direct_revenue_less_cost = revenue - cost
    shared_cost_proxy = direct_revenue_less_cost - subtotal
    if shared_cost_proxy < 0:
        raise ValueError("Operating subtotal exceeds source-backed revenue less cost")
    known_receivables = sum((value(balance, name) or Decimal("0")) for name in (
        "accounts_receivable", "notes_receivable", "receivables_financing", "contract_assets"))
    known_inventory = value(balance, "inventory") or Decimal("0")
    known_payables = sum((value(balance, name) or Decimal("0")) for name in (
        "accounts_payable", "notes_payable", "combined_notes_accounts_payable", "contract_liabilities", "advance_receipts"))
    unclassified_payables = sum((value(balance, name) or Decimal("0")) for name in (
        "other_payables", "payroll_payable", "other_current_liabilities"))
    prepayments = value(balance, "prepayments") or Decimal("0")
    # Each case is a transparent input convention, not an economic conclusion.
    nwc_cases = []
    for prepayment_treatment in ("exclude_unclassified", "include_prepayments"):
        for payable_treatment in ("exclude_unclassified", "include_unclassified_payables"):
            nwc = known_receivables + known_inventory - known_payables
            if prepayment_treatment == "include_prepayments":
                nwc += prepayments
            if payable_treatment == "include_unclassified_payables":
                nwc -= unclassified_payables
            nwc_cases.append({"prepayments": prepayment_treatment, "unclassified_payables": payable_treatment,
                              "conditional_operating_nwc_cny": str(nwc)})
    cash_tax_cases = [{"cash_tax_scope": "corporate_income_tax_payable_only",
                       "conditional_cash_tax_payable_cny": row.get("annual_corporate_income_tax_payable_cny")},
                      {"cash_tax_scope": "corporate_plus_other_taxes_payable",
                       "conditional_cash_tax_payable_cny": str((value(row, "annual_corporate_income_tax_payable_cny") or Decimal("0")) + (value(row, "annual_other_taxes_payable_cny") or Decimal("0")))}]
    shared_cost_cases = [{"industrial_share": share, "status": "experimental_shared_industrial_financial_cost_allocation"}
                         for share in ("0.80", "0.90", "1.00")]
    denominator_cases = [{"basis": "reported_issued_shares", "shares": str(issued_shares),
                          "status": "source_backed_issued_shares_only"},
                         {"basis": "treasury_share_treatment_unresolved", "shares": None,
                          "status": "blocked_no_treasury_or_cancellation_fact"}]
    filing = filings.get(row["annual_source_id"])
    if filing is None or not filing.get("url") or not filing.get("sha256") or not filing.get("path"):
        raise ValueError("Annual filing record missing from archive")
    filing_path = ROOT / Path(filing["path"])
    if digest(filing_path) != filing["sha256"]:
        raise ValueError("Archived annual filing hash mismatch")
    return {
        "symbol": "600519", "report_period": row["report_period"], "available_at": row["annual_available_at"],
        "source": {"source_id": row["annual_source_id"], "source_url": filing["url"],
                   "source_path": filing["path"], "annual_report_document_hash": filing["sha256"],
                   "capex_field_document_hash": row["capex_source_sha256"],
                   "operating_pages": row.get("operating_original_pages"), "capital_pages": row.get("capital_balance_original_pages"),
                   "parser_version": VERSION},
        "facts": {"operating_subtotal_cny": str(subtotal), "cash_capex_less_da_cny": str(capex_less_da),
                  "reported_issued_shares": str(issued_shares), "revenue_cny": operating.get("revenue"),
                  "cost_cny": operating.get("cost"), "direct_revenue_less_cost_cny": str(direct_revenue_less_cost),
                  "shared_cost_proxy_cny": str(shared_cost_proxy),
                  "known_receivables_cny": str(known_receivables), "inventory_cny": str(known_inventory),
                  "known_payables_cny": str(known_payables), "prepayments_cny": str(prepayments),
                  "unclassified_payables_cny": str(unclassified_payables)},
        "sensitivity_dimensions": {"operating_nwc": nwc_cases, "cash_tax": cash_tax_cases,
                                   "shared_cost": shared_cost_cases, "share_denominator": denominator_cases},
        "conditional_value": None, "formal_fair_value": None, "trade_value": None,
        "trade_approved": False, "valuation_approved": False,
        "blockers": ["historical_fcff_model_not_approved", "shared_industrial_financial_cost_unresolved",
                     "cash_tax_scope_incomplete", "treasury_and_distribution_denominator_unresolved",
                     "execution_and_benchmark_not_complete"],
    }


def build(rows: list[dict]) -> dict:
    filings = filing_sources()
    cases = [build_case(row, filings) for row in annual_rows(rows)]
    return {"version": VERSION, "symbol": "600519", "purpose": "point_in_time_conditional_fcff_research_inputs_only",
            "input_cases": cases, "case_count": len(cases), "formal_fair_value": None,
            "trade_approved": False, "strategy_backtest_complete": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_HASH:
        raise ValueError("Pinned daily research inputs changed")
    result = build(json.loads(INPUT.read_text(encoding="utf-8")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-conditional-inputs-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_bytes(encoded(result))
    manifest = {"input": str(INPUT.relative_to(ROOT)), "input_sha256": INPUT_HASH,
                "script_sha256": digest(Path(__file__)), "outputs": {"evidence.json": digest(evidence)}}
    (output / "manifest.json").write_bytes(encoded(manifest))
    latest = ROOT / "runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json"
    latest.write_bytes(encoded({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}))
    print(json.dumps({"output": str(output), "cases": result["case_count"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
