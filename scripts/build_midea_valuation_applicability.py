"""Pin Midea's formal model-applicability decision from retained scope evidence.

The mature-manufacturing profile authorizes the shared FCFF contract. The
retained 2025 filing still lacks the financial-business carve-out and
enterprise-value bridge required by that contract. This package separates the
economic route from the fact-level applicability decision.
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
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ROUTE_UNSUPPORTED, ValuationRouter


EBIT = ROOT / "runtime/company-research/midea-ebit-scope-20260921/evidence.json"
EBIT_SHA256 = "e9527b6c824be83366eaef9f7ffb95288c3befbfc1ac1f8811c56441c5248566"
SHARE_POINTER = ROOT / "runtime/company-research/midea-2025-share-basis-latest.json"
EQUITY_SCOPE_POINTER = ROOT / "runtime/company-research/midea-consolidated-equity-scope-latest.json"
HISTORICAL_EQUITY_RETURN_POINTER = ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-latest.json"
FINANCE_COMPANY_POINTER = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"

OUT = ROOT / "runtime/company-research/midea-valuation-applicability-20260922"
POINTER = ROOT / "runtime/company-research/midea-valuation-applicability-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    route = ValuationRouter().route(PROFILES["mature_manufacturing"], "fcff")
    if route.status != ROUTE_SUPPORTED or route.model_type != "FCFF":
        raise ValueError("Mature-manufacturing profile no longer routes to the shared FCFF contract")
    equity_route = ValuationRouter().route(
        PROFILES["mature_manufacturing"], "residual_income_or_equity_value"
    )
    if equity_route.status != ROUTE_UNSUPPORTED:
        raise ValueError("Mature-manufacturing profile unexpectedly authorizes the equity route as primary")

    equity_route_evidence = {
        "historical_equity_income_and_cash_return_series": "COMPILED_CANDIDATE",
        "forward_roe_or_earning_power": "NOT_EVIDENCED",
        "dated_cost_of_equity_range": "NOT_EVIDENCED",
        "registered_payout_or_retention": "NOT_EVIDENCED",
        "current_ordinary_share_denominator": "NOT_REGISTERED",
        "clean_surplus_equity_rollforward": "NOT_RECONCILED",
    }
    required_next_evidence = [
        "Forward bear/base/bull ROE assumptions with a named economic basis and franchise fade",
        "Dated cost-of-equity range with a named source and sensitivity evidence",
        "Registered payout or retention policy with capital-allocation evidence",
        "Dated current ordinary-share denominator excluding treasury shares",
        "Start-of-period attributable ordinary equity bridged to the valuation date after dividends, buybacks and other company actions",
        "Clean-surplus equity rollforward separating attributable income, OCI, dividends and buybacks",
    ]

    return {
        "symbol": "000333",
        "package_version": "midea-valuation-applicability-v3",
        "assessment_date": "2026-09-22",
        "profile_route": route.as_policy(),
        "equity_route_profile_routing": equity_route.as_policy(),
        "scope_assessment": {
            "industrial_fcff_carve_out": "MODEL_NOT_APPLICABLE",
            "consolidated_enterprise_value_bridge": "VALUATION_NOT_READY",
            "fy2025_accounting_eps_denominator": "DISCLOSED_NOT_REGISTERED",
            "current_valuation_share_scope": "NOT_REGISTERED",
        },
        "finance_company_size_observation": {
            "status": finance_company["status"],
            "audited_fy2025_net_profit_cny": finance_company["observations"][1]["values"]["net_profit_cny"],
            "audited_fy2025_net_assets_cny": finance_company["observations"][1]["values"]["net_assets_cny"],
            "does_not_unblock_industrial_fcff": True,
            "reason": (
                "A finance-company size disclosure is not a standalone financial-business "
                "profit statement, balance sheet, tax, debt, cash, or working-capital split."
            ),
        },
        "paths": [
            {
                "id": "industrial_fcff_carve_out",
                "status": "MODEL_NOT_APPLICABLE",
                "reason": (
                    "The annual report does not separately disclose the financial-business "
                    "profit statement, balance sheet, tax, debt, cash or working capital."
                ),
            },
            {
                "id": "consolidated_enterprise_value_bridge",
                "status": "VALUATION_NOT_READY",
                "reason": (
                    "A bridge requires separately evidenced financial-business and "
                    "non-operating-asset value before consolidated FCFF can be converted "
                    "to the listed-equity claim."
                ),
            },
        ],
        "conclusion": (
            "The economic profile supports the shared FCFF route, but no applicable FCFF "
            "scope is available from the retained 2025 facts. Therefore no arithmetic "
            "model is registered and no bear/base/bull value is produced."
        ),
        "alternative_route_candidate": {
            "model_id": alternative_route["model_id"],
            "status": alternative_route["status"],
            "reason": alternative_route["reason"],
            "required_next_evidence": required_next_evidence,
            "profile_authorization": equity_route.status,
            "profile_authorization_blocker": equity_route.blockers[0],
            "evidence_status": equity_route_evidence,
            "minimum_evidence_contract": {
                "start_book_equity": "latest verified attributable ordinary equity bridged to a dated valuation point after dividends, buybacks and other company actions",
                "ordinary_shares": "dated current ordinary-share denominator excluding treasury shares, with source URL and hash",
                "forecast_roes": "bear/base/bull forward ROE assumptions with named economic basis and franchise fade",
                "cost_of_equity": "dated cost-of-equity range from named source and sensitivity evidence",
                "payout_or_retention": "registered payout/retention policy or explicit assumption with capital-allocation evidence",
                "clean_surplus_reconciliation": "equity rollforward separating attributable income, OCI, dividends and buybacks",
            },
            "decision": "CANDIDATE_NOT_REGISTERED",
        },
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "blockers": [
            "financial_business_standalone_scope_not_disclosed",
            "industrial_invested_capital_not_allocated",
            "enterprise_value_bridge_not_evidenced",
            "current_valuation_ordinary_share_scope_not_registered",
            "formal_valuation_not_approved",
        ],
        "evidence_refs": [
            {
                "id": "midea_ebit_scope",
                "path": str(EBIT.relative_to(ROOT)),
                "sha256": EBIT_SHA256,
                "description": "2025 annual-report EBIT and financial-business scope audit",
            },
            {
                "id": "midea_share_basis",
                "path": str((ROOT / json.loads(SHARE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": share_sha256,
                "description": "2025 accounting EPS scope, year-end A/H totals and treasury-stock boundary",
            },
            {
                "id": "midea_consolidated_equity_scope",
                "path": str((ROOT / json.loads(EQUITY_SCOPE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": equity_scope_sha256,
                "description": "2025 consolidated ordinary/minority equity, attributable income, visible financial-business items and unregistered alternative equity route",
            },
            {
                "id": "midea_equity_return_history",
                "path": str((ROOT / json.loads(HISTORICAL_EQUITY_RETURN_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": historical_sha256,
                "description": "2014-2024 attributable equity, attributable profit and cash-return candidate series (not registered model inputs)",
            },
            {
                "id": "midea_finance_company_size_observation",
                "path": str((ROOT / json.loads(FINANCE_COMPANY_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": finance_company_sha256,
                "description": "Issuer-linked 2025 Midea Group Finance Co. size observation (not a model input)",
            },
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
