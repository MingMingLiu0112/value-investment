#!/usr/bin/env python3
"""Freeze the evidence boundary between Moutai operating and finance scope.

This is an admission audit.  It does not allocate unreported shared costs or
turn a sensitivity into a valuation conclusion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "operating_profit_scope": (
        "runtime/company-research/600519-operating-profit-scope-20260909T143825138457Z/evidence.json",
        "d2006397c8cc92bb7bf69c4afd4507907245d355ec24657cc25f2ad51bcc6629",
    ),
    "finance_scope": (
        "runtime/company-research/600519-finance-scope-current-20260909T073652934406Z/evidence.json",
        "26009565a69a84029d6fd8a6db6ce8b3a46685d37a59eb62137c83859dc93baf",
    ),
    "equity_bridge": (
        "runtime/company-research/600519-equity-bridge-control-20260909T132548421808Z/evidence.json",
        "1c5137422eeb75ba62ed39d244256c304b7e46bd77a9257a7e1c5929fe6212cd",
    ),
    "shared_cost_sensitivity": (
        "runtime/company-research/600519-finance-cost-sensitivity-20260912T123118Z/evidence.json",
        "e4dc21bb4d553fec4d334210cac9601eab902586a31b83f82255208d57539930",
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit() -> dict:
    data, references = {}, {}
    for name, (relative, expected) in INPUTS.items():
        path = ROOT / relative
        if digest(path) != expected:
            raise ValueError(f"Pinned input changed: {name}")
        data[name] = json.loads(path.read_text(encoding="utf-8"))
        references[name] = {"path": relative, "sha256": expected}

    operating = data["operating_profit_scope"]
    finance = data["finance_scope"]
    bridge = data["equity_bridge"]
    sensitivity = data["shared_cost_sensitivity"]
    explicit_finance_rows = [
        row["field"] for row in operating["ledger"] if row["scope"].startswith("excluded_separate_finance")
        or row["scope"] == "excluded_financing_and_cash_income"
    ]
    ceiling = sensitivity["expense_removal_ceiling"]
    total_cases = len(ceiling["cases"])
    crossing_cases = ceiling["crossing_cases"]
    if total_cases != 648 or crossing_cases != 72:
        raise ValueError("Unexpected shared-cost sensitivity coverage")
    if operating["industrial_financial_scope_approved"] or finance["industrial_financial_eliminations_approved"]:
        raise ValueError("Unexpectedly approved scope input")
    if bridge["pending_value_adjustments"]["industrial_financial_scope"] is not None:
        raise ValueError("Unexpectedly resolved bridge scope")

    gates = [
        {
            "id": "explicit_finance_profit_rows_excluded",
            "passed": True,
            "evidence": explicit_finance_rows,
            "interpretation": "已从经营利润代理中剔除明确披露的金融利息、手续费与财务费用项目。",
        },
        {
            "id": "financial_company_equity_scope",
            "passed": False,
            "reason": "财务公司公允价值、工业金融抵销和金融资本释放均未获批准。",
        },
        {
            "id": "shared_cost_and_asset_boundary",
            "passed": False,
            "reason": "合并报表中的共享费用及嵌入经营资产的金融公司资产尚未形成经审计的分配或替代边界。",
        },
        {
            "id": "materiality_test",
            "passed": False,
            "reason": "将全部已纳入预测的共享费用移除的敏感性在 72/648 个条件案例中跨越30%入场试验，不能视为非实质事项。",
        },
    ]
    return {
        "symbol": "600519",
        "audit_type": "operating_finance_scope_admission_gate",
        "inputs": references,
        "explicitly_excluded_finance_rows": explicit_finance_rows,
        "shared_scope_h1_cny": sensitivity["inputs"]["operating_scope"]["shared_scope_h1_cny"],
        "shared_cost_sensitivity": {
            "total_cases": total_cases,
            "crossing_30pct_entry_cases": crossing_cases,
            "scope": ceiling["scope"],
            "not_a_bound": True,
        },
        "gates": gates,
        "approved": False,
        "valuation_approved": False,
        "trade_approved": False,
        "conclusion": "Operating FCFF plus an explicit equity bridge remains a candidate research structure, but its operating/financial boundary is not admitted for a formal value or simulation decision.",
        "required_evidence": [
            "A reproducible treatment for financial-company assets, internal deposits and eliminations that avoids double counting with the equity bridge.",
            "An auditable allocation or conservative bounded treatment for shared industrial/financial costs and embedded financial assets.",
            "A re-run of the operating DCF and equity bridge after the boundary contract is frozen.",
        ],
    }


def main() -> int:
    result = audit()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/company-research" / f"600519-operating-finance-scope-audit-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence), "inputs": result["inputs"]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-operating-finance-scope-audit-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "approved": False, "blocking_gates": [g["id"] for g in result["gates"] if not g["passed"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
