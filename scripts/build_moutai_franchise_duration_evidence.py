"""Build a reproducible audit of Moutai's franchise-duration model policy.

The audit establishes that the current five-year fade is a bounded conditional
central policy and that 0/10 years are explicit stress bounds. It does not
measure the company's future competitive-advantage period and does not approve
a fair value, a target price, or a trading decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from value_investment_agent.pdf_text import extract_pages


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime/company-research"
ANNUAL_PDF = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf"
INTERIM_PDF = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf"
MODEL_PATH = RESEARCH / "600519-consolidated-parent-equity-residual-income-current-20260921T124252Z/evidence.json"
POLICY_PATH = RESEARCH / "600519-current-equity-policy-staged-20260921T124252Z/policy.json"
FORWARD_PATH = RESEARCH / "600519-current-forward-assumptions-20260921T124252Z/evidence.json"
COST_PATH = RESEARCH / "600519-current-cost-of-equity-policy-20260921T124252Z/evidence.json"
VOLUME_PATH = RESEARCH / "600519-volume-constraints-20260909T092256548331Z/evidence.json"
DIAGNOSTIC_PATH = RESEARCH / "600519-current-assumption-diagnostic-20260917T014020Z/evidence.json"
PEER_PATH = RESEARCH / "000858-peer-interim-20260909T125304973619Z/evidence.json"
PEER_PDF = RESEARCH / "000858-peer-interim-20260909T125304973619Z/000858-1225531252.pdf"

ANNUAL_SHA256 = "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"
INTERIM_SHA256 = "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"
MODEL_SHA256 = "8ffe43ccf6acba184496eec12d7ed65082ec91d4ba38f7cfd5604a32fe648f30"
POLICY_SHA256 = "f79b027e21649c65df68cdef08c8776846379c51284f0ec51c9a47a571426d80"
FORWARD_SHA256 = "373ee3a900ecfcf51b7abacc8500cad47ead5446dc23846ac349eab1d25ac1a4"
COST_SHA256 = "f78a23609648a2ffd920f01d8708ad3affcd966571a0bc0065eebd3a33ec1b36"
VOLUME_SHA256 = "f33a903584df8b556024716c18746e5a1f0967269b1477ed2cfc044fb5a42f31"
DIAGNOSTIC_SHA256 = "452c3f71fc4f950ff2fe58025d8fb52082174b0efd49961d3b93e0099451ae72"
PEER_SHA256 = "1e5a3d030881678d7e3b63ae03718df3312dac4a17a44c64fb79436516a7a00c"
PEER_PDF_SHA256 = "15153679faee48d1b1b00c50557a88bdcbdf8cb4cbc49b8762e10f70210dfb5b"


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


def pinned_json(path: Path, expected: str, ref_id: str, description: str,
                pages: list[int] | None = None) -> tuple[dict, dict]:
    if digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(path.read_text(encoding="utf-8")), reference(
        ref_id, path, list(pages or []), description
    )


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


def verify_primary_volume_and_policy_text() -> None:
    if digest(ANNUAL_PDF) != ANNUAL_SHA256 or digest(INTERIM_PDF) != INTERIM_SHA256:
        raise ValueError("Moutai primary-report source hash changed")
    verify_page(ANNUAL_PDF, 10, (
        "酒类168,774,585,187.6514,805,900,139.5991.23-1.088.63",
        "酒类吨116,123.7385,104.14339,977.8611.252.139.67",
    ))
    verify_page(ANNUAL_PDF, 15, (
        "茅台酒制酒车间46,395.0058,473.16",
        "系列酒制酒车间59,400.0057,650.57",
        "实际产能按报告期实际基酒产量计算",
    ))
    verify_page(ANNUAL_PDF, 22, (
        "贮足陈酿、不卖新酒",
        "零售价格动态调整机制",
    ))
    verify_page(INTERIM_PDF, 7, (
        "贮足陈酿、不卖新酒",
        "随行就市、相对平稳、供需适配、量价平衡",
        "动态价格调整机制",
    ))


def verify_peer_counterevidence() -> None:
    if digest(PEER_PDF) != PEER_PDF_SHA256:
        raise ValueError("Wuliangye peer PDF hash changed")
    verify_page(PEER_PDF, 6, (
        "28,416,674,541.7723,509,972,048.6520.87%",
        "8,752,942,991.314,623,850,715.1389.30%",
    ))
    verify_page(PEER_PDF, 7, (
        "-2,153,568,792.3231,136,736,628.58-106.92%",
    ))
    verify_page(PEER_PDF, 11, (
        "销售费用6,322,231,378.533,499,723,307.9580.65%",
    ))


def central_policy(model: dict, policy: dict, forward: dict) -> dict:
    registered = model["model_policy"]
    for name in ("forecast_years", "fade_years"):
        if registered.get(name) != policy.get(name):
            raise ValueError(f"Model and policy disagree on {name}")
    if registered["forecast_years"] != 5 or registered["fade_years"] != 5:
        raise ValueError("Five-year forecast and fade central policy changed")
    if registered.get("terminal_roe_policy") != "cost_of_equity_no_permanent_excess_return":
        raise ValueError("Terminal no-permanent-excess-return policy changed")
    if policy["sensitivity"]["fade_years"] != [0, 10]:
        raise ValueError("Registered 0/10 fade stresses changed")
    if forward["capital_and_fade_policy"]["fade_stresses"] != [0, 10]:
        raise ValueError("Forward review no longer registers 0/10 fade stresses")
    if "Five-year horizons are bounded research choices" not in policy["rationale"]["capital_and_fade"]:
        raise ValueError("Policy no longer states that the horizons are bounded choices")
    if "no perpetual excess franchise value" not in policy["rationale"]["capital_and_fade"]:
        raise ValueError("Policy no longer excludes a perpetual excess franchise tail")
    return {
        "forecast_years": registered["forecast_years"],
        "fade_years": registered["fade_years"],
        "fade_stresses": policy["sensitivity"]["fade_years"],
        "terminal_roe_policy": registered["terminal_roe_policy"],
        "classification": "conditional_central_policy",
        "why_five_years_is_the_central_policy": (
            "Five years is not an empirical competitive-advantage measurement. It is a "
            "bounded neutral research horizon chosen after FY2025 revenue fell while "
            "sales volume rose, H1 2026 parent profit fell, and peer interim evidence did "
            "not support automatic industry recovery. It lets retained capital earn a "
            "linearly fading excess return before terminal ROE reaches the scenario cost "
            "of equity, without granting an indefinite franchise tail."
        ),
        "why_0_and_10_are_stresses": (
            "Immediate fade removes the assumed five-year excess-return window and acts "
            "as a lower-bound/absence-of-franchise test. Ten-year fade permits a materially "
            "longer excess-return window and acts as a longer-duration stress, while still "
            "converging to no permanent excess return."
        ),
        "boundary": (
            "The audit verifies that the geometry is bounded, explicit, internally consistent "
            "and counterevidence-aware. It does not establish how long Moutai's actual "
            "competitive advantage will last."
        ),
    }


def build() -> dict:
    verify_primary_volume_and_policy_text()
    verify_peer_counterevidence()
    model, model_ref = pinned_json(MODEL_PATH, MODEL_SHA256, "moutai_current_model",
                                   "Current frozen residual-income model")
    policy, policy_ref = pinned_json(POLICY_PATH, POLICY_SHA256, "moutai_current_policy",
                                     "Current staged valuation policy")
    forward, forward_ref = pinned_json(FORWARD_PATH, FORWARD_SHA256, "moutai_forward_review",
                                       "Dated forward-assumption review")
    cost, cost_ref = pinned_json(COST_PATH, COST_SHA256, "moutai_cost_policy_review",
                                 "Dated cost-of-equity selection review")
    volume, volume_ref = pinned_json(VOLUME_PATH, VOLUME_SHA256, "moutai_volume_constraints",
                                     "FY2025 volume-price realization constraints")
    diagnostic, diagnostic_ref = pinned_json(DIAGNOSTIC_PATH, DIAGNOSTIC_SHA256,
                                             "moutai_reverse_valuation",
                                             "Reverse valuation across registered horizons")
    peer, peer_ref = pinned_json(PEER_PATH, PEER_SHA256, "wuliangye_peer_counterevidence",
                                 "Wuliangye H1 2026 operating counterevidence")

    if forward.get("passed") is not True:
        raise ValueError("Franchise-duration policy is no longer accepted by the forward review")
    if cost.get("passed") is not True:
        raise ValueError("Cost-of-equity policy review no longer passes")
    if peer.get("peer_support_approved") is not False:
        raise ValueError("Peer evidence cannot become supporting evidence automatically")
    reverse_rows = diagnostic["reverse_valuation"]
    if not reverse_rows or any(row["status"] != "above_registered_envelope" for row in reverse_rows):
        raise ValueError("Reverse valuation diagnostic scope changed")
    horizons = {row.get("fade_years") for row in reverse_rows}
    if horizons != {0, 5, 10}:
        raise ValueError("Reverse valuation no longer covers 0/5/10 year fade horizons")
    sensitivity = {row["case"]: row for row in model["sensitivity"]}
    if sensitivity["base_fade_0"]["fade_years"] != 0 or sensitivity["base_fade_10"]["fade_years"] != 10:
        raise ValueError("Model no longer contains immediate and ten-year fade stresses")
    if any(row["fade_years"] != 5 for row in model["results"]):
        raise ValueError("Primary scenarios no longer use the five-year fade")

    return {
        "symbol": "600519",
        "package_version": "moutai-franchise-duration-evidence-v1",
        "as_of": "2026-09-21",
        "scope": (
            "Independent audit of the bounded franchise-fade geometry in the current Moutai "
            "valuation policy. Not a measurement of future competitive-advantage duration, "
            "a formal fair value, a target price, or a trading decision."
        ),
        "status": "bounded_conditional_policy_audited_not_empirical_franchise_duration",
        "central_policy": central_policy(model, policy, forward),
        "stress_design": {
            "immediate_fade": {
                "fade_years": 0,
                "role": "absence_of_franchise_lower_bound",
                "conditional_base_value_cny": str(sensitivity["base_fade_0"]["conditional_value_per_current_disclosed_share_cny"]),
            },
            "central_fade": {
                "fade_years": 5,
                "role": "bounded_conditional_central_policy",
                "conditional_base_value_cny": str(next(
                    row["conditional_value_per_current_disclosed_share_cny"]
                    for row in model["results"] if row["scenario"] == "base"
                )),
            },
            "extended_fade": {
                "fade_years": 10,
                "role": "materially_longer_duration_upper_bound_stress",
                "conditional_base_value_cny": str(sensitivity["base_fade_10"]["conditional_value_per_current_disclosed_share_cny"]),
            },
            "interpretation": (
                "The three values are conditional arithmetic, not lower/central/upper "
                "evidence about how long the franchise will persist."
            ),
        },
        "issuer_evidence": {
            "fy2025_volume_price": {
                "liquor_revenue_growth_pct": volume["reported_revenue_growth_pct"],
                "liquor_sales_volume_growth_pct": volume["reported_sales_volume_growth_pct"],
                "approximate_revenue_per_tonne_change_pct": str(
                    round(float(volume["approximate_revenue_per_tonne_change"]) * 100, 4)
                ),
                "interpretation": volume["scenario_constraints"][0],
            },
            "capacity_and_inventory_constraints": [
                volume["scenario_constraints"][2],
                volume["scenario_constraints"][3],
                volume["scenario_constraints"][5],
            ],
            "h1_2026_dynamic_pricing": (
                "H1 2026 describes a dynamic price-adjustment mechanism as management policy, "
                "not an observed whole-company price uplift or a future guarantee."
            ),
        },
        "peer_counterevidence": {
            "symbol": peer["symbol"],
            "status": "retained_as_counterevidence_not_transferred_to_moutai",
            "observations": [
                "H1 2026 revenue rose 20.87% but reported profit comparisons were restated.",
                "H1 2026 operating cash flow was negative at about -2.154 billion CNY.",
                "H1 2026 selling expenses rose about 80.65%.",
            ],
            "limitations": peer["limitations"],
        },
        "policy_consistency": {
            "forward_assumption_review_passed": forward["passed"],
            "cost_of_equity_review_passed": cost["passed"],
            "primary_scenarios_use_five_year_fade": True,
            "immediate_and_ten_year_fade_stresses_present": True,
            "terminal_regime_has_no_permanent_excess_return": True,
            "reverse_valuation_covers_0_5_10_year_horizons": True,
            "reverse_valuation_result": "all_horizons_above_registered_envelope",
            "no_quote_fit_to_create_a_buy_point": (
                "The archived quote lies above every registered profit and fade combination; "
                "therefore the five-year fade was not selected to manufacture a positive margin."
            ),
        },
        "conclusion": {
            "policy_boundary": (
                "The current five-year fade is a defensible bounded central research policy: "
                "it is explicit, counterevidence-aware, stress-tested at zero and ten years, "
                "and ends with no permanent excess return. The 0/10 stress choices are correctly "
                "bounded absence-of-franchise and longer-duration alternatives."
            ),
            "not_proven": (
                "No historical econometric evidence in the pinned inputs measures the length "
                "of Moutai's competitive-advantage period. Brand, production and management "
                "statements can support a research hypothesis but cannot prove future duration."
            ),
            "effect": (
                "The franchise-duration policy is now audited as bounded, but confidence remains "
                "low and this package grants no valuation, simulation, or trade approval."
            ),
        },
        "blockers": [
            "five_year_fade_is_a_policy_not_an_empirically_measured_franchise_duration",
            "future_competitive_advantage_duration_requires_long_term_evidence_and_events",
            "full_year_2026_parent_remittances_and_cash_flow_not_yet_disclosed",
            "formal_valuation_approval_requires_a_separate_gate",
        ],
        "evidence_refs": [
            model_ref,
            policy_ref,
            forward_ref,
            cost_ref,
            volume_ref,
            diagnostic_ref,
            peer_ref,
            reference("moutai_fy2025_annual_report", ANNUAL_PDF, [10, 15, 22],
                      "FY2025 volume-price, capacity and aged-product disclosures"),
            reference("moutai_2026_h1_report", INTERIM_PDF, [7],
                      "H1 2026 aged-product and dynamic-price policy disclosures"),
            reference("wuliangye_peer_interim_pdf", PEER_PDF, [6, 7, 11],
                      "Wuliangye H1 2026 financial and selling-expense observations"),
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
    output = RESEARCH / f"600519-franchise-duration-evidence-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    target = output / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(target),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-franchise-duration-evidence-latest.json"
    pointer.write_text(json.dumps({
        "path": str(output.relative_to(ROOT)),
        "sha256": digest(target),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": digest(target),
                      "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
