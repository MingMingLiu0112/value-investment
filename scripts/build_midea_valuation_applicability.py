"""Pin Midea's formal model-applicability decision from retained scope evidence.

FCFF remains the mature-manufacturing default but is not applicable to Midea's
current consolidated public scope. The profile now permits explicit selection
of the shared residual-income model; dated ordinary-share inputs are still
required before that model can run.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


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

OUT = ROOT / "runtime/company-research/midea-valuation-applicability-20260930-v3"
POINTER = ROOT / "runtime/company-research/midea-valuation-applicability-latest.json"
H1_REPORT = ROOT / "runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf"
H1_REPORT_SHA256 = "576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8"
POST_PERIOD_SHARE_REPORT = ROOT / "runtime/company-research/midea-share-denominator-followup-20260930/2026092901149.pdf"
POST_PERIOD_SHARE_REPORT_SHA256 = "99063212c10151143deb2e86375a7cbbb7e668ffa921390cbd5ba0d5d17912cd"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "valuation_basis_ordinary_share_denominator": "A_BLOCKING_UNKNOWN_2026_06_30_NOT_BOUNDED",
        "clean_surplus_equity_rollforward": "VERIFIED_2026_06_30_REPORT",
    }
    required_next_evidence = ["Exact 2026-06-30 ordinary-share denominator excluding treasury and employee-plan shares; H1 weighted-average EPS shares are not a date-end count"]
    scenario_inputs_to_register = [
        "Bear/base/bull ROE paths and fade bounded by historical proxies and H1 counterevidence",
        "Dated cost-of-equity sensitivity with named basis",
        "Retention/payout and terminal ROE/growth sensitivity",
    ]

    return {
        "symbol": "000333",
        "package_version": "midea-valuation-applicability-v4",
        "assessment_date": "2026-09-30",
        "blocker_classification": {
            "A_BLOCKING_UNKNOWN": 1, "B_SCENARIO_RANGE_INPUT": 6,
            "C_NON_BLOCKING_UNCERTAINTY": 0, "D_EVIDENCE_STOP": 3,
            "A_blocker": "2026-06-30 ordinary-share denominator cannot be bounded from the retained dated disclosure",
        },
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
            "baseline_v13_rewritten": False, "valuation_run_status": "NOT_RUN_A_BLOCKING_SHARE_DENOMINATOR",
        },
        "scope_assessment": {
            "industrial_fcff_carve_out": "MODEL_NOT_APPLICABLE", "consolidated_enterprise_value_bridge": "VALUATION_NOT_READY",
            "fy2025_accounting_eps_denominator": "DISCLOSED_NOT_REGISTERED", "announcement_date_share_scope": "DISCLOSED_NOT_REGISTERED",
            "valuation_basis_2026_06_30_share_scope": "A_BLOCKING_UNKNOWN",
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
            {"id": "shared_residual_income_equity", "status": "VALUATION_NOT_READY", "reason": "The shared route is authorized, but the 2026-06-30 denominator is unbounded; no per-share scenarios are emitted."},
        ],
        "conclusion": "FCFF is not applicable; the profile permits shared residual income, but no valuation runs without a bounded 2026-06-30 denominator. Post-period shares are not backdated; v13 is unchanged.",
        "alternative_route_candidate": {
            "model_id": alternative_route["model_id"],
            "status": "PROFILE_AUTHORIZED_INPUTS_INCOMPLETE",
            "reason": "The shared model is authorized, but the 2026-06-30 per-share denominator is not bounded.",
            "required_next_evidence": required_next_evidence,
            "profile_authorization": equity_route.status,
            "evidence_status": equity_route_evidence,
            "scenario_inputs_to_register": scenario_inputs_to_register,
            "minimum_evidence_contract": {
                "start_book_equity": "Verified 2026-06-30 attributable equity with H1 equity-change table bound",
                "ordinary_shares": "Exact date-matched denominator; do not substitute 2026-09-29 or weighted-average EPS shares",
                "forecast_roes": "Bear/Base/Bull ROE paths and fade; historical proxies are bounds, not forecasts",
                "cost_of_equity": "Explicit dated sensitivity range", "payout_or_retention": "Scenario assumptions with capital-allocation context",
                "clean_surplus_reconciliation": "2026H1 equity-change table is hash-bound",
            },
            "decision": "AUTHORIZED_NOT_RUN_A_BLOCKING_SHARE_DENOMINATOR",
        },
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "valuation_status": "VALUATION_NOT_READY",
        "blockers": ["2026_06_30_ordinary_share_denominator_unresolved"],
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
        "registered_valuation_model": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
