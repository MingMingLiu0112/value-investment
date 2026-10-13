"""Pin Midea's formal model-applicability decision from retained scope evidence.

FCFF remains the mature-manufacturing default but is not applicable to Midea's
current consolidated public scope. The profile permits explicit selection of
the shared residual-income model. As of the 2026-10-13 re-check the
2026-06-30 ordinary-share denominator is verified from issuer HKEX monthly
returns; only B-class scenario inputs remain before that model can run.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ValuationRouter


EBIT = ROOT / "runtime/company-research/midea-ebit-scope-20260921/evidence.json"
EBIT_SHA256 = "e9527b6c824be83366eaef9f7ffb95288c3befbfc1ac1f8811c56441c5248566"
SHARE_POINTER = ROOT / "runtime/company-research/midea-2025-share-basis-latest.json"
EQUITY_SCOPE_POINTER = ROOT / "runtime/company-research/midea-consolidated-equity-scope-latest.json"
HISTORICAL_EQUITY_RETURN_POINTER = ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-latest.json"
FINANCE_COMPANY_POINTER = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"
HKEX_SHARE_POINTER = ROOT / "runtime/company-research/midea-20260330-hkex-share-basis-latest.json"

OUT = ROOT / "runtime/company-research/midea-valuation-applicability-20261013-v5"
POINTER = ROOT / "runtime/company-research/midea-valuation-applicability-latest.json"
H1_REPORT = ROOT / "runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf"
H1_REPORT_SHA256 = "576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8"
POST_PERIOD_SHARE_REPORT = ROOT / "runtime/company-research/midea-share-denominator-followup-20260930/2026092901149.pdf"
POST_PERIOD_SHARE_REPORT_SHA256 = "99063212c10151143deb2e86375a7cbbb7e668ffa921390cbd5ba0d5d17912cd"

# 2026-10-13 bounded re-check: the issuer-stated 2026-06-30 share scope comes
# from the June and July HKEX monthly returns; the September roll-forward is
# reconciled from the September monthly return and two repurchase-progress
# announcements. All bytes are pinned; the enumeration values are re-checked
# against the retained PDFs before any payload is emitted.
JUNE_MONTHLY_RETURN = ROOT / "runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260701-20260807/originals/12235688-2026070700419_c.pdf"
JUNE_MONTHLY_RETURN_SHA256 = "fab9be2f0349dcda9880b178e45e4dd65474b98635bf454adeeb19ed7bc3ecfd"
JULY_MONTHLY_RETURN = ROOT / "runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260701-20260807/originals/12275468-2026080601118_c.pdf"
JULY_MONTHLY_RETURN_SHA256 = "2b44a2f088e59c6fcae197da299e1f98a365bd35084bd06333d815c897dbaba9"
SEPTEMBER_MONTHLY_RETURN = ROOT / "runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260930-20261013/originals/12365201-2026100700897_c.pdf"
SEPTEMBER_MONTHLY_RETURN_SHA256 = "c56a8370659ec85aa0812060cd6511184bb0ac29b304dd3c1c575367f64f378e"
REPURCHASE_PROGRESS_20261009 = ROOT / "runtime/company-research/midea-denominator-recheck-20261013/cninfo-originals/1225596587.PDF"
REPURCHASE_PROGRESS_20261009_SHA256 = "ecf88af046574b4a780c8fca23b4b5a4968648c2a70142cda0056753532a7073"
REPURCHASE_PROGRESS_20260903 = ROOT / "runtime/company-research/midea-share-denominator-followup-20260930/1225544342.pdf"
REPURCHASE_PROGRESS_20260903_SHA256 = "24900692f953f24bff8464e27e3383e91b2a272984e38bff21ca628b3d7cc50b"
PLAN_TRANSFER_NOTICE_20260903 = ROOT / "runtime/company-research/midea-share-denominator-followup-20260930/1225544482.pdf"
PLAN_TRANSFER_NOTICE_20260903_SHA256 = "d93bfd07da79f6b5e11b1c7bbdb151a4fe021690a2a307c0fc3c1047b4716365"
HKEX_RECHECK_WINDOW_INDEX = ROOT / "runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260701-20260807/window-index.json"
HKEX_RECHECK_WINDOW_INDEX_SHA256 = "e94a4cd424e3d37037577e7b5466888f6e65c9b827ecdaa469411efa38ae2679"
CNINFO_RECHECK_SCAN_INDEX = ROOT / "runtime/prospective-public-event-2026-10-13/gapfill-000333-20261013T061406981606Z/index.json"
CNINFO_RECHECK_SCAN_INDEX_SHA256 = "e69aac04f458b2a57e138943a7131dc61ba97ac8abfc616cacc0fe562022c462"

VERIFIED_2026_06_30_ORDINARY_SHARES = 7_464_347_335


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_page(path: Path, page_number: int, expected: tuple[str, ...]) -> None:
    pdf = pdfium.PdfDocument(str(path))
    try:
        text = pdf[page_number - 1].get_textpage().get_text_bounded() or ""
    finally:
        pdf.close()
    normalized = re.sub(r"\s+", "", text)
    missing = [value for value in expected if value.replace(",", "") not in normalized.replace(",", "")]
    if missing:
        raise ValueError(f"{path.name} page {page_number} is missing expected evidence {missing!r}")


def verify_share_denominator_evidence() -> None:
    pins = (
        (JUNE_MONTHLY_RETURN, JUNE_MONTHLY_RETURN_SHA256),
        (JULY_MONTHLY_RETURN, JULY_MONTHLY_RETURN_SHA256),
        (SEPTEMBER_MONTHLY_RETURN, SEPTEMBER_MONTHLY_RETURN_SHA256),
        (REPURCHASE_PROGRESS_20261009, REPURCHASE_PROGRESS_20261009_SHA256),
        (REPURCHASE_PROGRESS_20260903, REPURCHASE_PROGRESS_20260903_SHA256),
        (PLAN_TRANSFER_NOTICE_20260903, PLAN_TRANSFER_NOTICE_20260903_SHA256),
        (HKEX_RECHECK_WINDOW_INDEX, HKEX_RECHECK_WINDOW_INDEX_SHA256),
        (CNINFO_RECHECK_SCAN_INDEX, CNINFO_RECHECK_SCAN_INDEX_SHA256),
    )
    for path, expected in pins:
        if digest(path) != expected:
            raise ValueError(f"Midea 2026-10-13 denominator evidence changed: {path.name}")

    require_page(JUNE_MONTHLY_RETURN, 1, ("2026年6月30日", "6,962,590,407", "650,848,500", "7,613,438,907"))
    require_page(JUNE_MONTHLY_RETURN, 2, ("6,813,498,835", "149,091,572", "6,962,590,407"))
    require_page(JULY_MONTHLY_RETURN, 2, ("6,813,498,835", "149,091,572"))
    require_page(SEPTEMBER_MONTHLY_RETURN, 2, ("6,791,434,907", "187,650,463", "6,979,085,370"))
    require_page(REPURCHASE_PROGRESS_20261009, 1, ("123,010,307", "9,940,207,657"))
    require_page(REPURCHASE_PROGRESS_20260903, 1, ("99,797,967",))
    require_page(PLAN_TRANSFER_NOTICE_20260903, 2, ("15,772,385",))
    require_page(H1_REPORT, 88, ("68,679,031", "5,476,158,082"))

    if 6_962_590_407 + 650_848_500 != 7_613_438_907:
        raise ValueError("2026-06-30 A/H issued shares do not reconcile")
    if 6_813_498_835 + 650_848_500 != VERIFIED_2026_06_30_ORDINARY_SHARES:
        raise ValueError("2026-06-30 treasury-excluding denominator does not reconcile")
    if 149_091_572 - 68_679_031 != 80_412_541:
        raise ValueError("2026-06-30 treasury use split does not reconcile")
    september_buybacks = 123_010_307 - 99_797_967
    if september_buybacks - 15_772_385 != 187_650_463 - 180_210_508:
        raise ValueError("September 2026 treasury roll-forward does not reconcile")


def pointer_evidence_path(pointer: Path) -> Path:
    return ROOT / json.loads(pointer.read_text(encoding="utf-8"))["path"] / "evidence.json"


def load_pinned_share_basis() -> tuple[dict, str]:
    pin = json.loads(SHARE_POINTER.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Midea share-basis pointer escapes the project root")
    if digest(target) != pin["sha256"].lower():
        raise ValueError("Midea share-basis evidence changed")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"].lower()


def load_pinned_equity_scope() -> tuple[dict, str]:
    pin = json.loads(EQUITY_SCOPE_POINTER.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Midea equity-scope pointer escapes the project root")
    if digest(target) != pin["sha256"].lower():
        raise ValueError("Midea equity-scope evidence changed")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"].lower()


def load_pinned_historical_equity_return() -> tuple[dict, str]:
    pin = json.loads(HISTORICAL_EQUITY_RETURN_POINTER.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Midea historical equity-return pointer escapes the project root")
    if digest(target) != pin["sha256"].lower():
        raise ValueError("Midea historical equity-return evidence changed")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"].lower()


def load_pinned_finance_company_observation() -> tuple[dict, str]:
    pin = json.loads(FINANCE_COMPANY_POINTER.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Midea finance-company pointer escapes the project root")
    if digest(target) != pin["sha256"].lower():
        raise ValueError("Midea finance-company observation changed")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"].lower()


def load_pinned_hkex_share_basis() -> tuple[dict, str]:
    pin = json.loads(HKEX_SHARE_POINTER.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Midea HKEX share-basis pointer escapes the project root")
    if digest(target) != pin["sha256"].lower():
        raise ValueError("Midea HKEX share-basis evidence changed")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"].lower()


def build_payload() -> dict:
    if digest(EBIT) != EBIT_SHA256:
        raise ValueError("Midea EBIT scope evidence changed")
    ebit = json.loads(EBIT.read_text(encoding="utf-8"))
    if (ebit.get("symbol") != "000333"
            or ebit.get("valuation_status") != "VALUATION_NOT_READY"
            or ebit.get("financial_scope_approved") is not False):
        raise ValueError("Midea EBIT scope payload changed its fail-closed contract")

    share, share_sha256 = load_pinned_share_basis()
    if (share.get("symbol") != "000333"
            or share.get("share_basis_approved") is not False
            or share.get("registered_valuation_inputs", {}).get("ordinary_shares") is not None):
        raise ValueError("Midea share-basis payload changed its fail-closed contract")

    equity_scope, equity_scope_sha256 = load_pinned_equity_scope()
    alternative_route = equity_scope.get("alternative_route_candidate", {})
    if (equity_scope.get("symbol") != "000333"
            or equity_scope.get("financial_scope_approved") is not False
            or equity_scope.get("valuation_status") != "VALUATION_NOT_READY"
            or equity_scope.get("registered_valuation_inputs") != {}
            or alternative_route.get("status") != "CANDIDATE_NOT_REGISTERED"):
        raise ValueError("Midea equity-scope payload changed its fail-closed contract")

    historical_equity_return, historical_sha256 = load_pinned_historical_equity_return()
    if (historical_equity_return.get("symbol") != "000333"
            or historical_equity_return.get("status") != "equity_return_candidate_series_compiled_not_reviewed_or_registered"
            or historical_equity_return.get("valuation_status") != "VALUATION_NOT_READY"
            or historical_equity_return.get("registered_valuation_inputs") != {}
            or [row["year"] for row in historical_equity_return.get("series", [])] != list(range(2014, 2025))
            or any(row.get("model_input") is not None for row in historical_equity_return.get("series", []))):
        raise ValueError("Midea historical equity-return payload changed its fail-closed contract")

    finance_company, finance_company_sha256 = load_pinned_finance_company_observation()
    if (finance_company.get("symbol") != "000333"
            or finance_company.get("status") != "OBSERVATION_NOT_MODEL_INPUT"
            or finance_company.get("valuation_status") != "VALUATION_NOT_READY"
            or finance_company.get("registered_valuation_inputs") != {}
            or finance_company.get("registered_valuation_model") is not None):
        raise ValueError("Midea finance-company observation changed its fail-closed contract")

    hkex_share, hkex_share_sha256 = load_pinned_hkex_share_basis()
    if (hkex_share.get("symbol") != "000333"
            or hkex_share.get("status") != "announcement_date_share_basis_disclosed_not_registered"
            or hkex_share.get("share_basis_registered_for_current_valuation") is not False
            or hkex_share.get("valuation_status") != "VALUATION_NOT_READY"
            or hkex_share.get("registered_valuation_inputs") != {}):
        raise ValueError("Midea HKEX share-basis payload changed its fail-closed contract")

    if (digest(H1_REPORT) != H1_REPORT_SHA256
            or digest(POST_PERIOD_SHARE_REPORT) != POST_PERIOD_SHARE_REPORT_SHA256):
        raise ValueError("Midea share/equity source hashes changed")
    verify_share_denominator_evidence()

    route = ValuationRouter().route(PROFILES["mature_manufacturing"], "fcff")
    if route.status != ROUTE_SUPPORTED or route.model_type != "FCFF":
        raise ValueError("Mature-manufacturing profile no longer routes to the shared FCFF contract")
    equity_route = ValuationRouter().route(
        PROFILES["mature_manufacturing"], "residual_income_or_equity_value"
    )
    if (equity_route.status != ROUTE_SUPPORTED
            or equity_route.model_type != "residual_income_or_equity_value"):
        raise ValueError("Mature-manufacturing profile must expose the explicit shared equity alternative")

    equity_route_evidence = {
        "historical_equity_income_and_cash_return_series": "COMPILED_CANDIDATE_NOT_REGISTERED",
        "forward_roe_or_earning_power": "SCENARIO_RANGE_INPUT_NOT_REGISTERED",
        "dated_cost_of_equity_range": "SCENARIO_RANGE_INPUT_NOT_REGISTERED",
        "registered_payout_or_retention": "SCENARIO_RANGE_INPUT_NOT_REGISTERED",
        "announcement_date_share_scope": "DISCLOSED_NOT_REGISTERED",
        "post_period_ordinary_share_denominator": "VERIFIED_2026_09_29_NOT_BACKDATED",
        "valuation_basis_ordinary_share_denominator": "VERIFIED_2026_06_30_ISSUED_EXCLUDING_TREASURY",
        "clean_surplus_equity_rollforward": "VERIFIED_2026_06_30_REPORT",
    }
    required_next_evidence: list[str] = []
    scenario_inputs_to_register = [
        "Bear/base/bull ROE paths and fade bounded by historical proxies and H1 counterevidence",
        "Dated cost-of-equity sensitivity with named basis",
        "Retention/payout and terminal ROE/growth sensitivity",
    ]

    verified_share_scope = {
        "as_of": "2026-06-30",
        "basis": "Issuer HKEX monthly returns: issued shares excluding treasury shares, by class",
        "issued_total": 7_613_438_907,
        "a_issued": 6_962_590_407,
        "h_issued": 650_848_500,
        "a_treasury": 149_091_572,
        "h_treasury": 0,
        "ordinary_shares_excluding_treasury": VERIFIED_2026_06_30_ORDINARY_SHARES,
        "treasury_use_split": {
            "cancellation_designated_2026_program_at_2026_06_30": 68_679_031,
            "share_incentive_or_plan_designated": 80_412_541,
            "basis": "2026 program count from the H1 report; remainder of the monthly-return treasury count",
        },
        "cross_checks": [
            "A+H issued shares reconcile exactly with the 2026H1 interim report total 7,613,438,907",
            "The July monthly return repeats the same June 30 balances as its previous-month carry-in",
            "September 2026 roll-forward: 23,212,340 buybacks minus 15,772,385 employee-plan transfer out equals the +7,439,955 monthly-return treasury delta",
        ],
        "alternative_denominator_considered_not_selected": {
            "ordinary_shares_excluding_only_cancellation_designated": 7_544_759_876,
            "reason": "Parent equity is stated net of the full treasury-stock deduction, so the consistent denominator excludes every repurchase-account share; the alternative is recorded, not used.",
        },
        "not_a_substitute": [
            "H1 weighted-average basic/diluted EPS denominators are period averages, not date-end counts",
            "The 2026-09-29 post-period count is a different date and is not backdated to 2026-06-30",
        ],
    }

    return {
        "symbol": "000333",
        "package_version": "midea-valuation-applicability-v5",
        "assessment_date": "2026-10-13",
        "blocker_classification": {
            "A_BLOCKING_UNKNOWN": 0, "B_SCENARIO_RANGE_INPUT": 6,
            "C_NON_BLOCKING_UNCERTAINTY": 0, "D_EVIDENCE_STOP": 3,
            "resolved_A_blocker": "2026-06-30 ordinary-share denominator verified on 2026-10-13 from issuer HKEX monthly returns",
        },
        "verified_2026_06_30_share_scope": verified_share_scope,
        "profile_route": route.as_policy(),
        "equity_route_profile_routing": equity_route.as_policy(),
        "model_change": {
            "effective_date": "2026-09-30", "prior_primary_model": "fcff",
            "prior_alternative_route_status": "UNSUPPORTED",
            "selected_model": "residual_income_or_equity_value",
            "new_route_status": "SUPPORTED_BY_EXPLICIT_PROFILE_AUTHORIZATION",
            "why_fcff_failed": "Public consolidated filings do not separate financial-business cash/debt and invested capital for a defensible FCFF bridge.",
            "new_model_rationale": "Residual income values common equity from dated attributable book equity and explicit ROE/cost-of-equity scenarios without inventing an EV bridge.",
            "scenario_inputs_to_register": scenario_inputs_to_register,
            "baseline_v13_rewritten": False, "valuation_run_status": "NOT_RUN_B_SCENARIO_INPUTS_NOT_REGISTERED",
        },
        "scope_assessment": {
            "industrial_fcff_carve_out": "MODEL_NOT_APPLICABLE", "consolidated_enterprise_value_bridge": "VALUATION_NOT_READY",
            "fy2025_accounting_eps_denominator": "DISCLOSED_NOT_REGISTERED", "announcement_date_share_scope": "DISCLOSED_NOT_REGISTERED",
            "valuation_basis_2026_06_30_share_scope": "VERIFIED_2026_06_30_ISSUED_EXCLUDING_TREASURY",
            "valuation_basis_2026_06_30_ordinary_shares": VERIFIED_2026_06_30_ORDINARY_SHARES,
            "post_period_2026_09_29_share_scope": "VERIFIED_NOT_BACKDATED",
        },
        "finance_company_size_observation": {
            "status": finance_company["status"],
            "audited_fy2025_net_profit_cny": finance_company["observations"][1]["values"]["net_profit_cny"],
            "audited_fy2025_net_assets_cny": finance_company["observations"][1]["values"]["net_assets_cny"],
            "does_not_unblock_industrial_fcff": True,
            "reason": "Finance-company size is not a standalone profit, balance-sheet, tax, debt, cash, or working-capital split.",
        },
        "paths": [
            {"id": "industrial_fcff_carve_out", "status": "MODEL_NOT_APPLICABLE", "reason": "Public filings do not disclose a standalone financial-business profit statement, balance sheet, tax, debt, cash or working capital."},
            {"id": "consolidated_enterprise_value_bridge", "status": "VALUATION_NOT_READY", "reason": "Financial-business and non-operating-asset values are not separable for an FCFF-to-equity bridge."},
            {"id": "shared_residual_income_equity", "status": "VALUATION_NOT_READY", "reason": "The shared route is authorized and the 2026-06-30 denominator is verified; no per-share scenarios are emitted until B-class scenario inputs are registered."},
        ],
        "conclusion": "FCFF is not applicable; the shared residual-income route is authorized and the 2026-06-30 ordinary-share denominator is verified. No per-share scenarios are emitted until B-class scenario inputs are registered. Post-period shares are not backdated; v13 is unchanged.",
        "alternative_route_candidate": {
            "model_id": alternative_route["model_id"],
            "status": "PROFILE_AUTHORIZED_INPUTS_INCOMPLETE",
            "reason": "The shared model is authorized and the 2026-06-30 per-share denominator is verified; only B-class scenario inputs remain before a run.",
            "required_next_evidence": required_next_evidence,
            "profile_authorization": equity_route.status,
            "evidence_status": equity_route_evidence,
            "scenario_inputs_to_register": scenario_inputs_to_register,
            "minimum_evidence_contract": {
                "start_book_equity": "Verified 2026-06-30 attributable equity with H1 equity-change table bound",
                "ordinary_shares": "Verified 2026-06-30 issued shares excluding treasury, by class, from issuer HKEX monthly returns; do not substitute 2026-09-29 or weighted-average EPS shares",
                "forecast_roes": "Bear/Base/Bull ROE paths and fade; historical proxies are bounds, not forecasts",
                "cost_of_equity": "Explicit dated sensitivity range", "payout_or_retention": "Scenario assumptions with capital-allocation context",
                "clean_surplus_reconciliation": "2026H1 equity-change table is hash-bound",
            },
            "decision": "AUTHORIZED_DENOMINATOR_VERIFIED_PENDING_B_SCENARIO_INPUTS",
        },
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "valuation_status": "VALUATION_NOT_READY",
        "blockers": [],
        "evidence_stops": [
            "financial_business_standalone_scope_not_disclosed_for_FCFF", "internal_eliminations_not_disclosed_for_FCFF",
            "project_level_maintenance_growth_capex_not_disclosed_for_FCFF",
        ],
        "evidence_refs": [
            {"id": "midea_ebit_scope", "path": str(EBIT.relative_to(ROOT)), "sha256": EBIT_SHA256, "description": "2025 annual-report EBIT and financial-business scope audit"},
            {"id": "midea_share_basis", "path": str(pointer_evidence_path(SHARE_POINTER).relative_to(ROOT)), "sha256": share_sha256, "description": "2025 accounting EPS scope, year-end A/H totals and treasury-stock boundary"},
            {"id": "midea_consolidated_equity_scope", "path": str(pointer_evidence_path(EQUITY_SCOPE_POINTER).relative_to(ROOT)), "sha256": equity_scope_sha256, "description": "2025 attributable/minority equity and consolidated scope; alternative model candidate"},
            {"id": "midea_equity_return_history", "path": str(pointer_evidence_path(HISTORICAL_EQUITY_RETURN_POINTER).relative_to(ROOT)), "sha256": historical_sha256, "description": "2014-2024 equity, profit and cash-return candidate series; not registered inputs"},
            {"id": "midea_finance_company_size_observation", "path": str(pointer_evidence_path(FINANCE_COMPANY_POINTER).relative_to(ROOT)), "sha256": finance_company_sha256, "description": "Issuer-linked 2025 finance-company size observation; not a model input"},
            {"id": "midea_hkex_20260330_share_basis", "path": str(pointer_evidence_path(HKEX_SHARE_POINTER).relative_to(ROOT)), "sha256": hkex_share_sha256, "description": "2026-03-30 HKEX share basis and treasury count; not registered"},
            {"id": "midea_2026h1_equity_change_report", "path": str(H1_REPORT.relative_to(ROOT)), "sha256": H1_REPORT_SHA256, "description": "2026H1 attributable equity and equity-change report; available 2026-08-30"},
            {"id": "midea_2026_09_29_hkex_share_report", "path": str(POST_PERIOD_SHARE_REPORT.relative_to(ROOT)), "sha256": POST_PERIOD_SHARE_REPORT_SHA256, "description": "Verified 2026-09-29 A/H shares; post-period, not backdated"},
            {"id": "midea_202606_hkex_monthly_return", "path": str(JUNE_MONTHLY_RETURN.relative_to(ROOT)), "sha256": JUNE_MONTHLY_RETURN_SHA256, "description": "June 2026 monthly return: 2026-06-30 issued, treasury and treasury-excluding shares by class"},
            {"id": "midea_202607_hkex_monthly_return", "path": str(JULY_MONTHLY_RETURN.relative_to(ROOT)), "sha256": JULY_MONTHLY_RETURN_SHA256, "description": "July 2026 monthly return: repeats the 2026-06-30 carry-in balances"},
            {"id": "midea_202609_hkex_monthly_return", "path": str(SEPTEMBER_MONTHLY_RETURN.relative_to(ROOT)), "sha256": SEPTEMBER_MONTHLY_RETURN_SHA256, "description": "September 2026 monthly return: 2026-09-30 balances used for the treasury roll-forward check"},
            {"id": "midea_2026_10_09_repurchase_progress", "path": str(REPURCHASE_PROGRESS_20261009.relative_to(ROOT)), "sha256": REPURCHASE_PROGRESS_20261009_SHA256, "description": "2026 program cumulative 123,010,307 shares at 2026-09-30"},
            {"id": "midea_2026_09_03_repurchase_progress", "path": str(REPURCHASE_PROGRESS_20260903.relative_to(ROOT)), "sha256": REPURCHASE_PROGRESS_20260903_SHA256, "description": "2026 program cumulative 99,797,967 shares at 2026-08-31"},
            {"id": "midea_2026_09_03_plan_transfer_notice", "path": str(PLAN_TRANSFER_NOTICE_20260903.relative_to(ROOT)), "sha256": PLAN_TRANSFER_NOTICE_20260903_SHA256, "description": "15,772,385 shares transferred from the repurchase account to the 2026 employee holding plan"},
            {"id": "midea_denominator_recheck_hkex_window", "path": str(HKEX_RECHECK_WINDOW_INDEX.relative_to(ROOT)), "sha256": HKEX_RECHECK_WINDOW_INDEX_SHA256, "description": "Bounded HKEX issuer window index for the 2026-10-13 re-check"},
            {"id": "midea_denominator_recheck_cninfo_scan", "path": str(CNINFO_RECHECK_SCAN_INDEX.relative_to(ROOT)), "sha256": CNINFO_RECHECK_SCAN_INDEX_SHA256, "description": "Bounded CNINFO issuer scan index for the 2026-10-13 re-check"},
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> None:
    payload = build_payload()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_digest = digest(target)
    manifest = {
        "script_sha256": digest(Path(__file__).resolve()),
        "evidence_sha256": evidence_digest,
        "ebit_scope_sha256": EBIT_SHA256,
        "share_basis_sha256": load_pinned_share_basis()[1],
        "equity_scope_sha256": load_pinned_equity_scope()[1],
        "equity_return_history_sha256": load_pinned_historical_equity_return()[1],
        "finance_company_observation_sha256": load_pinned_finance_company_observation()[1],
        "hkex_share_basis_sha256": load_pinned_hkex_share_basis()[1],
        "june_monthly_return_sha256": JUNE_MONTHLY_RETURN_SHA256,
        "july_monthly_return_sha256": JULY_MONTHLY_RETURN_SHA256,
        "september_monthly_return_sha256": SEPTEMBER_MONTHLY_RETURN_SHA256,
        "repurchase_progress_20261009_sha256": REPURCHASE_PROGRESS_20261009_SHA256,
        "repurchase_progress_20260903_sha256": REPURCHASE_PROGRESS_20260903_SHA256,
        "plan_transfer_notice_sha256": PLAN_TRANSFER_NOTICE_20260903_SHA256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    POINTER.write_text(
        json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": evidence_digest},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": evidence_digest,
        "route_status": payload["profile_route"]["status"],
        "industrial_fcff_carve_out": payload["scope_assessment"]["industrial_fcff_carve_out"],
        "equity_route_profile_status": payload["equity_route_profile_routing"]["status"],
        "valuation_basis_2026_06_30_ordinary_shares": payload["scope_assessment"]["valuation_basis_2026_06_30_ordinary_shares"],
        "registered_valuation_model": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
