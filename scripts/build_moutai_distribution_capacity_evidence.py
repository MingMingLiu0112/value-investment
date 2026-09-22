"""Build a reproducible Moutai distribution-capacity evidence package.

The package verifies primary-report payout history and parent-company cash
coverage. It is deliberately not a forecast payout policy, a cash-flow
certificate, a valuation approval, or a trading decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from value_investment_agent.pdf_text import extract_pages


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime" / "company-research"
ANNUAL_PDF = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf"
INTERIM_PDF = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf"
FACTS_PATH = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T115049Z/evidence.json"
TIMELINE_PATH = ROOT / "runtime/strategy-validation/moutai-historical-distribution-timeline-20260911T232129Z/observations.json"
REGISTRY_PATH = ROOT / "docs/reviewed-cash-distributions.json"
MODEL_POINTER = RESEARCH / "600519-consolidated-parent-equity-residual-income-current-latest.json"
RESILIENCE_POINTER = RESEARCH / "600519-resilience-review-latest.json"

ANNUAL_SHA256 = "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"
INTERIM_SHA256 = "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"
FACTS_SHA256 = "efc4dc37d81e9d4bf54930a5c2bf7cd50305b7b7ce808531ef4bc4138f80891b"
TIMELINE_SHA256 = "f21a2d26f2b48ba8ae84ace2aca2ecc5fa8d57e83bdbdbfcdee352cbcea2fc61"
REGISTRY_SHA256 = "ab15bdef761774593cd0a8ea96effe1cefa51424643673de492366c9c492312f"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(ref_id: str, path: Path, pages: list[int], description: str) -> dict:
    return {
        "id": ref_id,
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "pages": pages,
        "description": description,
    }


def pinned_json(path: Path, expected: str) -> tuple[dict, dict]:
    if digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(path.read_text(encoding="utf-8")), reference(
        path.name, path, [], "Hash-pinned evidence input"
    )


def pointer_json(pointer: Path) -> tuple[dict, dict]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Pointer escapes project root")
    return pinned_json(target, pin["sha256"])


def normalized(text: str) -> str:
    return re.sub(r"[\s,]+", "", text)


def verify_page(path: Path, page: int, expected: tuple[str, ...]) -> None:
    pypdf_text = PdfReader(str(path)).pages[page - 1].extract_text() or ""
    pdfium_text = extract_pages(path, limit=page)[page - 1]
    for backend, text in (("pypdf", pypdf_text), ("pdfium", pdfium_text)):
        compact = normalized(text)
        missing = [value for value in expected if normalized(value) not in compact]
        if missing:
            raise ValueError(f"{backend} page {page} is missing evidence: {missing}")


def verify_primary_sources() -> None:
    if digest(ANNUAL_PDF) != ANNUAL_SHA256 or digest(INTERIM_PDF) != INTERIM_SHA256:
        raise ValueError("Moutai primary-report source hash changed")
    verify_page(ANNUAL_PDF, 2, (
        "2025年年度利润分配拟向全体股东每股派发现金红利27.993元（含税）",
        "35,032,568,759.73",
        "1,251,476,039",
    ))
    verify_page(ANNUAL_PDF, 33, (
        "每10股派息数（元）（含税）",
        "279.93",
        "35,032,568,759.73",
        "82,320,067,101.68",
        "6,120,088,960.04",
        "71,153,295,260.53",
        "190,008,934,772.95",
        "84,055,509,712.46",
    ))
    verify_page(ANNUAL_PDF, 63, (
        "母公司利润表",
        "85,305,341,965.73",
        "76,370,303,842.59",
    ))
    verify_page(ANNUAL_PDF, 66, (
        "母公司现金流量表",
        "32,618,216,666.91",
        "110,369,954,530.92",
    ))
    verify_page(ANNUAL_PDF, 67, (
        "取得投资收益收到的现金",
        "49,653,138,761.40",
        "购建固定资产、无形资产和其他长期资产支付的现金",
        "3,104,346,428.46",
        "分配股利、利润或偿付利息支付的现金",
        "64,671,799,277.95",
        "76,517,140,680.50",
        "84,730,758,118.65",
    ))
    verify_page(INTERIM_PDF, 35, (
        "母公司现金流量表",
        "15,224,606,455.02",
        "101,052,220.78",
        "828,735,611.53",
        "35,032,574,305.20",
    ))
    verify_page(INTERIM_PDF, 36, (
        "84,730,758,118.65",
        "61,255,736,577.13",
    ))


def annual_history(observations: list[dict], facts: dict) -> list[dict]:
    ordinary = {
        int(row["annual_report_period"][:4]): row
        for row in observations
        if row.get("annual_report_period") and row.get("annual_profit_per_share_cny")
    }
    special = {}
    for row in observations:
        if row.get("annual_cycle_candidate") is False and row.get("ex_date"):
            special[int(row["ex_date"][:4])] = Decimal(str(row["cash_per_share_cny"]))
    rows = []
    for year in range(2015, 2025):
        row = ordinary[year]
        ordinary_cash = Decimal(str(row["cash_per_share_cny"]))
        extra_cash = special.get(year, Decimal("0"))
        eps = Decimal(str(row["annual_profit_per_share_cny"]))
        total_cash = ordinary_cash + extra_cash
        rows.append({
            "fiscal_year": year,
            "ordinary_cash_per_share_cny": format(ordinary_cash, ".3f"),
            "special_or_interim_cash_per_share_cny": format(extra_cash, ".3f"),
            "total_cash_per_share_cny": format(total_cash, ".3f"),
            "parent_eps_cny": format(eps, ".3f"),
            "total_cash_to_parent_eps": format(total_cash / eps, ".6f"),
            "distribution_type": "ordinary_plus_special_or_interim" if extra_cash else "ordinary_only",
        })
    annual_facts = next(row for row in facts["chain"] if row["period_end"] == "2025-12-31")
    fy2025_eps = Decimal(str(annual_facts["annual_parent_profit_per_issued_share_cny"]))
    proposed = Decimal("27.993")
    interim = Decimal("23.957")
    rows.append({
        "fiscal_year": 2025,
        "ordinary_cash_per_share_cny": "27.993",
        "special_or_interim_cash_per_share_cny": "23.957",
        "total_cash_per_share_cny": format(proposed + interim, ".3f"),
        "parent_eps_cny": format(fy2025_eps, ".3f"),
        "total_cash_to_parent_eps": format((proposed + interim) / fy2025_eps, ".6f"),
        "distribution_type": "proposed_annual_plus_implemented_interim",
    })
    return rows


def model_payout(policy: dict) -> dict:
    payout = Decimal(str(policy["payout_ratio"]))
    stress = [Decimal(str(value)) for value in policy["sensitivity"]["payout_ratios"]]
    if payout != Decimal("0.75") or stress != [Decimal("0.50"), Decimal("0.85")]:
        raise ValueError("Registered Moutai payout policy changed")
    latest_cash = Decimal("65033206300.49")
    latest_profit = Decimal("82320067101.68")
    three_year_cash = Decimal("190008934772.95")
    three_year_average_profit = Decimal("84055509712.46")
    return {
        "registered_payout_ratio": str(payout),
        "registered_stresses": [str(value) for value in stress],
        "latest_fy2025_cash_dividend_to_consolidated_profit": format(latest_cash / latest_profit, ".6f"),
        "latest_fy2025_cash_and_repurchase_to_consolidated_profit": format(
            Decimal("71153295260.53") / latest_profit, ".6f"
        ),
        "latest_three_year_cash_dividend_to_average_profit": format(
            three_year_cash / (three_year_average_profit * 3), ".6f"
        ),
        "comparison": (
            "The registered 75% payout is below the latest FY2025 cash-dividend ratio of about 79%, "
            "above the FY2025 annual-proposal-only ratio of 42.56%, and almost equal to the disclosed "
            "three-year cash-dividend-to-average-profit ratio of about 75.35%."
        ),
        "boundary": "This comparison is a historical observation, not a future payout commitment.",
    }


def cash_capacity() -> dict:
    fy2025 = {
        "parent_net_profit_cny": Decimal("85305341965.73"),
        "parent_cfo_cny": Decimal("32618216666.91"),
        "subsidiary_investment_income_received_cny": Decimal("49653138761.40"),
        "parent_capex_cny": Decimal("3104346428.46"),
        "distribution_and_interest_paid_cny": Decimal("64671799277.95"),
        "opening_cash_cny": Decimal("76517140680.50"),
        "closing_cash_cny": Decimal("84730758118.65"),
    }
    fy2025["coverage"] = format(
        (fy2025["parent_cfo_cny"] + fy2025["subsidiary_investment_income_received_cny"]
         - fy2025["parent_capex_cny"]) / fy2025["distribution_and_interest_paid_cny"],
        ".6f",
    )
    h1_2026 = {
        "parent_cfo_cny": Decimal("15224606455.02"),
        "subsidiary_investment_income_received_cny": Decimal("101052220.78"),
        "parent_capex_cny": Decimal("828735611.53"),
        "distribution_and_interest_paid_cny": Decimal("35032574305.20"),
        "opening_cash_cny": Decimal("84730758118.65"),
        "closing_cash_cny": Decimal("61255736577.13"),
    }
    h1_2026["cfo_after_capex_coverage"] = format(
        (h1_2026["parent_cfo_cny"] - h1_2026["parent_capex_cny"])
        / h1_2026["distribution_and_interest_paid_cny"],
        ".6f",
    )
    h1_2026["cfo_plus_investment_income_after_capex_coverage"] = format(
        (h1_2026["parent_cfo_cny"] + h1_2026["subsidiary_investment_income_received_cny"]
         - h1_2026["parent_capex_cny"]) / h1_2026["distribution_and_interest_paid_cny"],
        ".6f",
    )
    return {"fy2025": {key: str(value) for key, value in fy2025.items()},
            "h1_2026": {key: str(value) for key, value in h1_2026.items()},
            "interpretation": (
                "FY2025 parent operating cash plus received subsidiary investment income covered paid "
                "distributions and interest after capex by about 1.224x. H1 2026 received almost no "
                "subsidiary investment income, so its half-year coverage is only about 0.41x; remittance "
                "timing and future full-year disclosure remain required before forward cash capacity is approved."
            )}


def build() -> dict:
    verify_primary_sources()
    observations, _ = pinned_json(TIMELINE_PATH, TIMELINE_SHA256)
    facts, _ = pinned_json(FACTS_PATH, FACTS_SHA256)
    registry, _ = pinned_json(REGISTRY_PATH, REGISTRY_SHA256)
    model, model_ref = pointer_json(MODEL_POINTER)
    policy_ref = model["policy"]
    policy_path = (ROOT / policy_ref["path"]).resolve()
    if not policy_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Model policy path escapes project root")
    policy, _ = pinned_json(policy_path, policy_ref["sha256"])
    resilience, resilience_ref = pointer_json(RESILIENCE_POINTER)
    if registry.get("backtest_ready") is not False:
        raise ValueError("Distribution registry cannot be promoted to backtest-ready input")

    rows = annual_history(observations, facts)
    payout = model_payout(policy)
    capacity = cash_capacity()
    resilience_facts = resilience["facts"]
    return {
        "symbol": "600519",
        "package_version": "moutai-distribution-capacity-evidence-v1",
        "as_of": "2026-09-21",
        "scope": (
            "Primary-report payout history, parent-company legal profit and cash-flow coverage, and "
            "financial-subsidiary restrictions. Not a future payout policy, cash certificate, formal value, "
            "simulation order, or trading decision."
        ),
        "status": "distribution_history_verified_but_forward_cash_capacity_not_approved",
        "payout_history": rows,
        "model_payout_assumption": payout,
        "parent_cash_capacity": capacity,
        "financial_subsidiary_boundary": {
            "external_deposits_cny": resilience_facts["financial_subsidiary_external_deposits_cny"],
            "disclosed_restricted_cash_subset_cny": resilience_facts["disclosed_restricted_cash_subset_cny"],
            "rule": (
                "Consolidated finance-company deposits and restricted balances are not freely available "
                "parent-company cash and were not added to the parent cash-coverage arithmetic."
            ),
        },
        "assumption_effect": (
            "The registered 75% payout is now bounded by direct disclosure and historical observations, but "
            "this single package does not by itself increase valuation confidence or remove the remaining "
            "franchise-duration and discount-rate blockers."
        ),
        "blockers": [
            "future_parent_company_remittances_and_full_year_2026_cash_flow_not_yet_disclosed",
            "financial_subsidiary_cash_is_not_freely_distributable_parent_cash",
            "disclosed_payout_is_a_policy_and_historical_record_not_a_future_commitment",
            "dividend_tax_cash_timing_and_corporate_action_settlement_not_modeled",
        ],
        "evidence_refs": [
            reference("moutai_fy2025_annual_report", ANNUAL_PDF, [2, 33, 63, 66, 67],
                      "FY2025 distribution policy, parent profit and parent cash flow"),
            reference("moutai_2026_h1_report", INTERIM_PDF, [35, 36],
                      "H1 2026 parent cash flow and seasonal investment-income observation"),
            reference("moutai_historical_distribution_timeline", TIMELINE_PATH, [],
                      "Reviewed point-in-time annual and special distribution observations"),
            reference("moutai_parent_equity_inputs", FACTS_PATH, [],
                      "Reviewed 2014-2025 parent equity and profit chain"),
            reference("reviewed_cash_distributions", REGISTRY_PATH, [],
                      "Reviewed gross cash-entitlement registry"),
            model_ref,
            resilience_ref,
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    payload = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = RESEARCH / f"600519-distribution-capacity-evidence-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    target = output / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(target),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-distribution-capacity-evidence-latest.json"
    pointer.write_text(json.dumps({
        "path": str(output.relative_to(ROOT)),
        "sha256": digest(target),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": digest(target),
                      "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
