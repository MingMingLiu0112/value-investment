#!/usr/bin/env python3
"""Stress the Moutai conditional model against a disclosed finance-cost scale.

This is deliberately narrower than a cost-allocation model.  The finance
company's reported revenue less pretax profit is *not* a disclosed allocation
of consolidated shared costs.  It is used only as a transparent scale for a
counterfactual sensitivity: if that recurring amount had already been charged
to the finance company but also remained in the industrial proxy, how much
would the existing conditional result move?  The output is research-only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_moutai_ttm_comparability import ROOT, texts


SCOPE = ROOT / "runtime/company-research/600519-operating-profit-scope-20260909T143825138457Z/evidence.json"
SCOPE_SHA256 = "d2006397c8cc92bb7bf69c4afd4507907245d355ec24657cc25f2ad51bcc6629"
DCF = ROOT / "runtime/company-research/600519-conditional-operating-dcf-20260909T123857151905Z/evidence.json"
DCF_SHA256 = "931d9234f3e473b50ec30f4c65fb4e08deb263f9a34fd9babc780d9f5037372b"
INTEGRATED = ROOT / "runtime/company-research/600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json"
INTEGRATED_SHA256 = "67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc"
FINANCE_PDF = ROOT / "runtime/company-research/600519-finance-current-20260909T073502376364Z/600519-1225475863.pdf"
FINANCE_PDF_SHA256 = "cf2d50aa028fcf11ce9eb04746932b7a9be25c3e31d443295f77add844b1121b"
OBSERVATION = ROOT / "runtime/strategy-validation/moutai-current-observation-20260912T235130Z/current-observation/evidence.json"
OBSERVATION_SHA256 = "c353fc2b99c725cc9e5b4d295b90e6fbc1a52d7d5108c34d9bfe820da8e7e2bd"
OPERATING = ROOT / "runtime/company-research/600519-dated-operating-20260909T121512582335Z/evidence.json"
OPERATING_SHA256 = "8d4dc2ae6970fd3f3f71731961fa167e3875045ac1fef15840f5e26a30fd6fec"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_json(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Pinned input changed: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def one(rows: list[dict], **criteria: str) -> dict:
    matches = [row for row in rows if all(str(row[key]) == value for key, value in criteria.items())]
    if len(matches) != 1:
        raise ValueError(f"Expected one matching row: {criteria}")
    return matches[0]


def finance_scale() -> dict:
    if digest(FINANCE_PDF) != FINANCE_PDF_SHA256:
        raise ValueError("Pinned finance-company report changed")
    page = "\n".join(texts(FINANCE_PDF, 7))
    phrase = "2026年1-6月，财务公司实现营业收入15.76亿元，实现利润总额8.02亿元，净利润4.68亿元"
    if phrase not in page:
        raise ValueError("Finance-company H1 disclosure phrase changed")
    revenue_h1 = Decimal("15.76") * Decimal("1e8")
    pretax_h1 = Decimal("8.02") * Decimal("1e8")
    difference_h1 = revenue_h1 - pretax_h1
    if difference_h1 <= 0:
        raise ValueError("Finance-company reference scale must be positive")
    return {
        "source_period": "2026H1",
        "revenue_h1_cny": str(revenue_h1),
        "pretax_profit_h1_cny": str(pretax_h1),
        "revenue_less_pretax_h1_cny": str(difference_h1),
        "annualized_reference_scale_cny": format(difference_h1 * 2, "f"),
        "interpretation": (
            "Revenue less pretax profit contains standalone expenses and may also contain non-operating items. "
            "It is a disclosed sensitivity scale, not a reported allocation of consolidated shared costs or a hard bound."
        ),
    }


def load_verified_observation() -> tuple[Decimal, dict]:
    path = OBSERVATION.resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != OBSERVATION_SHA256:
        raise ValueError("Pinned dated observation changed")
    observation = json.loads(path.read_text(encoding="utf-8"))
    prices = {Decimal(row["observed_price_cny"]) for row in observation.get("scenarios", [])}
    if (observation.get("quote_session_verified") is not True or observation.get("quote_session_status") != "matched_close"
            or len(prices) != 1):
        raise ValueError("Dated observation lacks one verified price")
    return prices.pop(), {"path": str(path.relative_to(ROOT)), "sha256": OBSERVATION_SHA256}


def analyze() -> dict:
    scope = pinned_json(SCOPE, SCOPE_SHA256)
    dcf = pinned_json(DCF, DCF_SHA256)
    integrated = pinned_json(INTEGRATED, INTEGRATED_SHA256)
    if (scope.get("industrial_financial_scope_approved") is not False
            or dcf.get("valuation_approved") is not False
            or integrated.get("valuation_approved") is not False):
        raise ValueError("Unexpected input approval scope")
    shared_h1 = sum(Decimal(row["reported_value"]) for row in scope["ledger"]
                    if row["scope"] == "included_shared_scope")
    if shared_h1 != Decimal("21638749278.42"):
        raise ValueError("Unexpected consolidated shared-scope subtotal")
    scale = finance_scale()
    price, observation_ref = load_verified_observation()
    annual_scale = Decimal(scale["annualized_reference_scale_cny"])
    dcf_by_key = {
        (row["scenario"], row["capital_anchor"], row["nwc_case"], row["discount_rate"]): row
        for row in dcf["results"]
    }
    if len(dcf_by_key) != 54:
        raise ValueError("Incomplete operating DCF grid")
    results = []
    with localcontext() as context:
        context.prec = 45
        for source in integrated["results"]:
            key = (source["scenario"], source["capital_anchor"], source["nwc_case"], source["discount_rate"])
            operating = dcf_by_key.get(key)
            if operating is None:
                raise ValueError("Integrated row has no matching operating DCF")
            annual_rows = operating["annual_calculations"]
            tax_rates = {Decimal(row["cash_tax_rate"]) for row in annual_rows}
            if len(tax_rates) != 1:
                raise ValueError("Sensitivity requires one explicit operating cash-tax rate")
            tax_rate = tax_rates.pop()
            rate = Decimal(source["discount_rate"])
            next_nopat = Decimal(operating["terminal_calculation"]["next_year_nopat"])
            terminal_pv = Decimal(operating["terminal_calculation"]["present_value"])
            terminal_discount = terminal_pv / (next_nopat / rate)
            annual_discount_sum = sum(Decimal(row["discount_factor"]) for row in annual_rows)
            for multiplier in (Decimal("0"), Decimal("1")):
                after_tax_annual = annual_scale * multiplier * (Decimal("1") - tax_rate)
                delta = after_tax_annual * annual_discount_sum + (after_tax_annual / rate) * terminal_discount
                original = Decimal(source["conditional_equity_value"])
                adjusted = original + delta
                if multiplier == 0 and adjusted != original:
                    raise ValueError("Zero sensitivity must reproduce original conditional equity")
                if adjusted < original:
                    raise ValueError("Reattribution sensitivity must not reduce the conditional equity value")
                results.append({
                    "scenario": source["scenario"], "discount_rate": source["discount_rate"],
                    "capital_anchor": source["capital_anchor"], "nwc_case": source["nwc_case"],
                    "reserve_days": source["reserve_days"], "payment_basis": source["payment_basis"],
                    "tax_case": source["tax_case"], "reference_scale_multiplier": str(multiplier),
                    "cash_tax_rate": str(tax_rate), "annual_discount_sum": str(annual_discount_sum),
                    "terminal_discount_factor": str(terminal_discount),
                    "incremental_conditional_equity_cny": str(delta),
                    "original_conditional_equity_cny": str(original),
                    "adjusted_conditional_equity_cny": str(adjusted),
                    "disclosed_share_assumption": source["disclosed_share_assumption"],
                    "adjusted_conditional_value_per_share_cny": str(adjusted / Decimal(source["disclosed_share_assumption"])),
                    "observed_price_cny": str(price),
                    "safety_margin": str((adjusted / Decimal(source["disclosed_share_assumption"]) - price)
                                         / (adjusted / Decimal(source["disclosed_share_assumption"]))),
                    "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
                })
    if len(results) != len(integrated["results"]) * 2:
        raise ValueError("Incomplete sensitivity grid")
    representatives = []
    for scenario in ("bear", "base", "bull"):
        rows = [row for row in results if row["scenario"] == scenario and row["discount_rate"] == "0.08"
                and row["capital_anchor"] == "fy2025_spending" and row["nwc_case"] == "exclude_unclassified_payables"
                and row["reserve_days"] == 60 and row["payment_basis"] == "latest_half_year_average"
                and row["tax_case"] == "intercompany_tax_asset_only"]
        if len(rows) != 2:
            raise ValueError("Representative sensitivity rows missing")
        representatives.append({"scenario": scenario, "rows": sorted(rows, key=lambda row: row["reference_scale_multiplier"])})
    if digest(OPERATING) != OPERATING_SHA256:
        raise ValueError("Pinned operating expense forecast changed")
    forecast = json.loads(OPERATING.read_text(encoding="utf-8"))
    expense_ceiling = []
    for source in integrated["results"]:
        key = (source["scenario"], source["capital_anchor"], source["nwc_case"], source["discount_rate"])
        annuals = dcf_by_key[key]["annual_calculations"]
        periods = forecast["results"][source["scenario"]]
        if len(annuals) != len(periods):
            raise ValueError("Expense ceiling forecast length mismatch")
        delta = Decimal(0)
        for annual, period in zip(annuals, periods):
            if annual["cash_flow_date"] != period["period_end"]:
                raise ValueError("Expense ceiling period mismatch")
            costs = [Decimal(period["future_operating_amounts"][field])
                     for field in ("surcharges", "selling", "admin", "research")]
            if any(cost < 0 for cost in costs):
                raise ValueError("Nonnegative shared costs required for removal ceiling")
            after_tax = sum(costs) * (1 - Decimal(annual["cash_tax_rate"]))
            delta += after_tax * Decimal(annual["discount_factor"])
        delta += after_tax / Decimal(source["discount_rate"]) * Decimal(annuals[-1]["discount_factor"])
        ceiling_value = (Decimal(source["conditional_equity_value"]) + delta) / Decimal(source["disclosed_share_assumption"])
        expense_ceiling.append({
            **{key: source[key] for key in ("scenario", "discount_rate", "capital_anchor", "nwc_case", "reserve_days", "payment_basis", "tax_case")},
            "all_shared_expenses_removed_value_cny": str(ceiling_value),
            "crosses_30pct_entry": ceiling_value * Decimal("0.70") >= price,
        })
    entry_break_even = []
    # Invert the existing linear sensitivity; do not fit a new valuation or threshold.
    for group in representatives:
        zero, unit = group["rows"]
        shares = Decimal(zero["disclosed_share_assumption"])
        original = Decimal(zero["original_conditional_equity_cny"])
        pv_per_annual_cny = Decimal(unit["incremental_conditional_equity_cny"]) / annual_scale
        if pv_per_annual_cny <= 0:
            raise ValueError("Positive marginal expense sensitivity required")
        target = price * shares / Decimal("0.70")
        required = max(Decimal(0), (target - original) / pv_per_annual_cny)
        reconstructed = (original + required * pv_per_annual_cny) / shares
        if original < target and abs(reconstructed * Decimal("0.70") - price) > Decimal("0.000001"):
            raise ValueError("Entry break-even does not independently reconcile to observed price")
        entry_break_even.append({
            "scenario": group["scenario"], "entry_margin": "0.30",
            "required_recurring_pretax_adjustment_cny": str(required),
            "reference_scale_multiple": str(required / annual_scale),
            "target_conditional_value_per_share_cny": str(target / shares),
            "scope": "same fixed annual and terminal sensitivity; not a disclosed allocation bound",
        })
    robust_no_entry = all(Decimal(row["adjusted_conditional_value_per_share_cny"]) < price
                          for group in representatives for row in group["rows"])
    return {
        "symbol": "600519", "valuation_date": integrated["valuation_date"], "observed_price_cny": str(price),
        "inputs": {
            "operating_scope": {"path": str(SCOPE.relative_to(ROOT)), "sha256": SCOPE_SHA256,
                                "shared_scope_h1_cny": str(shared_h1)},
            "conditional_dcf": {"path": str(DCF.relative_to(ROOT)), "sha256": DCF_SHA256},
            "integrated_conditional_equity": {"path": str(INTEGRATED.relative_to(ROOT)), "sha256": INTEGRATED_SHA256},
            "finance_report": {"path": str(FINANCE_PDF.relative_to(ROOT)), "sha256": FINANCE_PDF_SHA256},
            "current_observation": observation_ref,
        },
        "finance_reference_scale": scale,
        "results": results, "representative_scenarios": representatives,
        "entry_break_even": entry_break_even,
        "expense_removal_ceiling": {
            "input_path": str(OPERATING.relative_to(ROOT)), "input_sha256": OPERATING_SHA256,
            "scope": "All included forecast shared costs removed, fixed tax rates and all other assumptions including equity bridge; not a company-value bound",
            "cases": expense_ceiling,
            "crossing_cases": sum(row["crosses_30pct_entry"] for row in expense_ceiling),
        },
        "robust_no_entry_under_this_sensitivity": robust_no_entry,
        "scope_approved": False, "valuation_approved": False, "formal_fair_value": None,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "limitations": [
            "The finance-company revenue-less-pretax figure is not a shared-cost allocation, a hard upper bound, or a finance-company FCFF adjustment.",
            "The sensitivity assumes the annualized reference amount recurs unchanged in each forecast year and terminal period, and that the reported finance earnings already bear that amount. Neither statement is established by the disclosure.",
            "Cash reserve, tax-capital, finance equity, minority claims, asset bridge and share-denominator limitations from the integrated conditional model remain unchanged.",
            "A price remains above every representative result under this limited sensitivity. That is not proof about all possible allocations and does not admit a fair value or order.",
        ],
    }


def main() -> int:
    result = analyze()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/company-research" / f"600519-finance-cost-sensitivity-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    representatives = result["representative_scenarios"]
    lines = ["# 茅台财务公司成本尺度敏感性", "", "这不是费用分摊模型或正式合理价。", "",
             "| 情景 | 尺度倍数 | 条件每股值（元） | 相对观察价安全边际 |", "| --- | ---: | ---: | ---: |"]
    for group in representatives:
        for row in group["rows"]:
            lines.append("| " + group["scenario"] + " | " + row["reference_scale_multiplier"] + " | "
                         + f"{Decimal(row['adjusted_conditional_value_per_share_cny']):.2f} | "
                         + f"{Decimal(row['safety_margin']):.2%} |")
    lines += ["", "## 保留30%门槛的反向检验", "",
              "在其他假设不变时，需要下列每年及终值期持续税前调整；这不是实际费用或可靠上界。", "",
              "| 情景 | 所需年度调整（亿元） | 参考尺度倍数 |", "| --- | ---: | ---: |"]
    for row in result["entry_break_even"]:
        lines.append(f"| {row['scenario']} | {Decimal(row['required_recurring_pretax_adjustment_cny']) / Decimal('1e8'):.2f} | {Decimal(row['reference_scale_multiple']):.2f} |")
    ceiling = result["expense_removal_ceiling"]
    lines += ["", "## 共享费用全额移除的条件上界", "",
              f"固定其他假设，{len(ceiling['cases'])}组原情景中有{ceiling['crossing_cases']}组跨越30%门槛。",
              "逐期移除预测税金附加、销售、管理和研发费用；终值移除最后一期相同费用。",
              "该极端上界仅约束冻结模型内费用归属的影响，不是现实公司价值上界，也不批准买入。"]
    lines += ["", "## 限制", ""] + ["- " + item for item in result["limitations"]]
    (output / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/company-research/600519-finance-cost-sensitivity-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "robust_no_entry_under_this_sensitivity": result["robust_no_entry_under_this_sensitivity"],
                      "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
