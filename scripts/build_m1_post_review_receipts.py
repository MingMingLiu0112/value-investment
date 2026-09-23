"""Build append-only M1 post-review receipts from the frozen M1 baseline.

This script reads the frozen valuation packages, the existing event-scan PDFs
and the existing M1 application output. It emits a new timestamped runtime
bundle. It never edits config/m1-valuation-packages-v1, the production
database, the scheduler, the WPS workbook or the server PTA project.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_DUPLICATE,
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    DECISION_SUPPORTING,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.human_research_approval import (
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_REJECTED_NEEDS_REWORK,
    HumanResearchApprovalReceipt,
    artifact_fingerprint,
    resolve_human_research_approval,
)
from value_investment_agent.interim_report_policy import (
    classify_unaudited_interim_report,
)
from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_profile import PROFILES
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_bridge_review import (
    KIND_DEBT,
    KIND_MINORITY_INTEREST,
    KIND_NON_OPERATING_ASSET,
    RECOVERABILITY_CONSERVATIVE_ASSUMPTION,
    RECOVERABILITY_CONTRACTUAL,
    RECOVERABILITY_PARTIALLY_SUPPORTED,
    BridgeComponentAssessment,
    build_bridge_contribution,
)
from value_investment_agent.valuation_models.residual_income import scenario_value


SCHEMA_VERSION = "m1-post-review-receipts-v1"
ACTION_NO_ORDER = "no_order"
REVIEWED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
REVIEW_AS_OF = REVIEWED_AT.date()
SCAN_DIR = ROOT / "runtime" / "company-research" / "m1-event-scans" / "20260923T051018Z"

# SHA-256 of the committed files. The script fails if the frozen baseline has
# been edited, which prevents a later receipt from silently rebinding to it.
FROZEN_PACKAGE_SHA256 = {
    "000651": "38472b97dea937a665a7ddf0cbdc16676760ed98c98b44af192ee4d0aa8431ba",
    "600741": "58f006de38c8f827b974e9801920809a844d74bac3e0948fbc697c3312a02e24",
    "600887": "e0387d58d45e728d6576a3e44bce66b14c03253491bcf733ce8e6942f492e803",
}


def _decision_spec(
    *,
    decision: str,
    domains: tuple[str, ...] = (),
    fact_fields: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    notes: tuple[str, ...],
    cluster_id: str | None = None,
    supersedes_event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "affected_domains": list(domains),
        "affected_fact_fields": list(fact_fields),
        "affected_assumptions": list(assumptions),
        "affected_artifacts": list(artifacts),
        "review_notes": list(notes),
        "event_cluster_id": cluster_id,
        "supersedes_event_id": supersedes_event_id,
    }


DECISION_SPECS: dict[str, dict[str, dict[str, Any]]] = {
    "000651": {
        "1225542476": _decision_spec(
            decision=DECISION_RISK_MONITOR,
            domains=("capital_allocation", "ordinary_shares", "cash"),
            artifacts=("capital_allocation_assessment", "buyback_monitor"),
            notes=(
                "Buyback progress is capital allocation monitoring; do not reduce shares until an actual cancellation is evidenced.",
            ),
            cluster_id="GREE_BUYBACK_2026",
        ),
        "1225515009": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            notes=("Procedural strategy progress; no quantified new commitment was identified in the reviewed packet.",),
        ),
        "1225515008": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            domains=("accounting_policy",),
            notes=("Policy change is retained as source evidence and does not materially alter the reviewed financial facts.",),
        ),
        "1225515007": _decision_spec(
            decision=DECISION_RISK_MONITOR,
            domains=("balance_sheet_risk", "capital_allocation"),
            artifacts=("balance_sheet_risk_monitor",),
            notes=("Inter-subsidiary guarantee is monitored; a default, subrogation or material new exposure would require recalculation.",),
        ),
        "1225515005": _decision_spec(
            decision=DECISION_REQUIRES_RECALCULATION,
            domains=("cash_recoverability", "legal_entity_cash_availability", "related_party_receivables", "non_operating_asset_bridge"),
            fact_fields=("restricted_cash", "related_party_receivables", "finance_company_scope", "non_operating_assets"),
            assumptions=("financial_asset_recoverability", "bridge_contribution"),
            artifacts=("facts", "bridge_review", "assumptions"),
            notes=("Funds-occupation and related-party flow evidence directly affects the legal-entity bridge; G3 remains rejected until this is resolved.",),
        ),
        "1225515004": _decision_spec(
            decision=DECISION_ALREADY_INCORPORATED,
            domains=("financial_facts",),
            fact_fields=("revenue", "parent_profit", "operating_cash_flow", "equity"),
            artifacts=("facts",),
            notes=("The H1 filing is already the latest facts source and must not trigger a redundant model stale state.",),
        ),
        "1225515003": _decision_spec(
            decision=DECISION_DUPLICATE,
            notes=("H1 summary is derived from the full H1 report.",),
            supersedes_event_id="1225515004",
        ),
    },
    "600741": {
        "1225516580": _decision_spec(
            decision=DECISION_SUPPORTING,
            domains=("financial_company_risk", "bridge_evidence"),
            fact_fields=("saic_finance_deposits",),
            artifacts=("bridge_review",),
            notes=("This supports the corresponding SAIC Finance deposit item only; it does not make all non-operating assets 100% recoverable.",),
        ),
        "1225516573": _decision_spec(
            decision=DECISION_ALREADY_INCORPORATED,
            domains=("financial_facts",),
            artifacts=("facts",),
            notes=("H1 report is already the current facts basis.",),
        ),
        "1225516560": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            notes=("Internal reporting procedure does not change economic rights or capital structure.",),
        ),
        "1225516550": _decision_spec(
            decision=DECISION_DUPLICATE,
            notes=("H1 summary is derived from the full H1 report.",),
            supersedes_event_id="1225516573",
        ),
    },
    "600887": {
        "1225568022": _decision_spec(
            decision=DECISION_RISK_MONITOR,
            domains=("capital_allocation", "ordinary_shares", "cash"),
            artifacts=("capital_allocation_assessment", "buyback_monitor"),
            notes=("Formal buyback report is monitored. Shares and cash consumption update only after actual repurchase and cancellation.",),
            cluster_id="YILI_BUYBACK_2026",
        ),
        "1225568017": _decision_spec(
            decision=DECISION_DUPLICATE,
            domains=("capital_allocation",),
            artifacts=("buyback_monitor",),
            notes=("Creditor notice is a procedural derivative of the 2026 buyback.",),
            cluster_id="YILI_BUYBACK_2026",
        ),
        "1225559652": _decision_spec(
            decision=DECISION_RISK_MONITOR,
            domains=("balance_sheet_risk", "distribution_sustainability"),
            artifacts=("balance_sheet_risk_monitor",),
            notes=("Subsidiary guarantee is monitored; default, subrogation or a large new exposure upgrades the review.",),
        ),
        "1225559649": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            domains=("buyback_disclosure",),
            notes=("Top-ten shareholder disclosure is procedural buyback reporting.",),
        ),
        "1225547701": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            domains=("share_plan",),
            notes=("Shareholder-meeting procedure; no material new issuance or dilution was identified.",),
        ),
        "1225547678": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            domains=("share_plan",),
            notes=("Long-service-plan meeting procedure; no material dilution was identified.",),
        ),
        "1225536213": _decision_spec(
            decision=DECISION_NOT_MATERIAL,
            domains=("buyback_disclosure",),
            notes=("Top-ten shareholder disclosure is procedural buyback reporting.",),
        ),
        "1225511505": _decision_spec(
            decision=DECISION_DUPLICATE,
            notes=("H1 summary is derived from the full H1 report.",),
            supersedes_event_id="1225511409",
        ),
        "1225511493": _decision_spec(
            decision=DECISION_REQUIRES_RECALCULATION,
            domains=("reported_roe", "normalized_roe", "capital_allocation", "counter_evidence"),
            fact_fields=("impairment_expense", "reported_roe", "normalized_roe"),
            assumptions=("forecast_roes", "capital_allocation_quality"),
            artifacts=("facts", "assumptions", "normalized_roe_review", "thesis"),
            notes=("Impairment must distinguish one-off cleanup from recurring capital-allocation failure before the ROE path can be approved.",),
        ),
        "1225511474": _decision_spec(
            decision=DECISION_REQUIRES_DECOMPOSITION,
            domains=("raised_funds", "capital_allocation"),
            fact_fields=("unused_funds", "project_schedule", "changed_use", "return_on_reinvestment"),
            artifacts=("capital_allocation_assessment",),
            notes=("Fund usage requires decomposition; a material project delay or changed use could require recalc or risk monitoring.",),
        ),
        "1225511473": _decision_spec(
            decision=DECISION_DUPLICATE,
            domains=("capital_allocation",),
            artifacts=("buyback_monitor",),
            notes=("Early buyback scheme is a prior version in the same buyback event set.",),
            cluster_id="YILI_BUYBACK_2026",
        ),
        "1225511470": _decision_spec(
            decision=DECISION_ALREADY_INCORPORATED,
            domains=("business_quality", "thesis", "product_channel_mix"),
            artifacts=("facts", "research_case"),
            notes=("Operating data is already used by BusinessQuality and Thesis evidence.",),
        ),
        "1225511409": _decision_spec(
            decision=DECISION_ALREADY_INCORPORATED,
            domains=("financial_facts",),
            artifacts=("facts",),
            notes=("H1 report is already the current facts basis.",),
        ),
    },
}


APPROVAL_SPECS: dict[str, dict[str, Any]] = {
    "000651": {
        "decision": DECISION_REJECTED_NEEDS_REWORK,
        "review_priority": "NORMAL",
        "remaining_blockers": (
            "treasury_finance_company_scope_not_split",
            "restricted_cash_legal_entity_distribution_not_verified",
            "related_party_and_subsidiary_receivables_not_mapped",
            "financial_asset_recoverability_haircuts_required",
            "non_operating_bridge_dominates_valuation",
            "issuer_specific_wacc_and_roic_not_verified",
        ),
        "required_followups": (
            "finance_company_and_restricted_cash_split",
            "related_party_cash_flow_mapping",
            "bridge_recoverability_review",
            "wacc_and_roic_sensitivity",
        ),
        "reopen_triggers": (
            "finance_company_and_restricted_cash_split_available",
            "related_party_cash_flow_mapping_available",
            "bridge_no_longer_dominates_conclusion",
        ),
    },
    "600741": {
        "decision": DECISION_REJECTED_NEEDS_REWORK,
        "review_priority": "HIGH",
        "remaining_blockers": (
            "saic_finance_evidence_supports_only_deposit_item",
            "remaining_non_operating_assets_require_recoverability_review",
            "customer_concentration_and_oem_price_pressure_not_quantified",
            "issuer_specific_wacc_and_roic_not_verified",
            "h1_profit_decline_normalization_pending",
        ),
        "required_followups": (
            "bridge_recoverability_review",
            "customer_oem_price_pressure_operating_mapping",
            "wacc_and_roic_sensitivity",
            "h1_profit_normalization",
        ),
        "reopen_triggers": (
            "bridge_review_isolated_and_no_longer_dominates",
            "operating_risk_mapped_to_bear_base_bull",
            "remaining_assumptions_explicitly_low_confidence",
        ),
    },
    "600887": {
        "decision": DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        "review_priority": "NORMAL",
        "remaining_blockers": (),
        "conditions": (
            "cost_of_equity_sensitivity",
            "retention_dividend_consistency",
            "impairment_normalized_roe_review",
            "buyback_cash_and_share_count_monitoring",
        ),
        "required_followups": (
            "cost_of_equity_sensitivity",
            "retention_dividend_consistency",
            "impairment_normalized_roe_review",
            "buyback_cash_and_share_count_monitoring",
        ),
        "reopen_triggers": (
            "valuation_artifact_changes",
            "facts_or_assumptions_change",
            "material_event_requires_recalculation",
            "actual_buyback_cancellation_changes_shares",
        ),
    },
}


BRIDGE_SPECS: dict[str, dict[str, Any]] = {
    "000651": {
        "cash_and_liquid_financial_assets": ("153186167311.92", "0.45", "0.30", "0.20"),
        "longer_term_financial_assets": ("84752161911.55", "0.60", "0.40", "0.25"),
        "investment_property": ("360503333.85", "0.20", "0.10", "0.05"),
        "debt": "71744407416.55",
        "minority": "3861982870.68",
    },
    "600741": {
        "cash_and_debt_investments": ("42248491420.70", "0.30", "0.20", "0.10"),
        "long_term_equity_and_other_financial_assets": ("17211651633.02", "0.55", "0.40", "0.25"),
        "investment_property": ("509614893.86", "0.20", "0.10", "0.05"),
        "debt": "17643806194.84",
        "minority": "3993209722.41",
    },
}


def _json_text(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object expected: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ref(path: Path, ref_id: str) -> dict[str, str]:
    return {
        "id": ref_id,
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
    }


def _decision_flags(decision: str) -> tuple[bool, bool, bool]:
    if decision == DECISION_REQUIRES_RECALCULATION:
        return True, True, False
    if decision in {DECISION_RISK_MONITOR, DECISION_REQUIRES_DECOMPOSITION}:
        return False, False, True
    return False, False, False


def _load_scan(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    symbol = str(payload["symbol"])
    scan_path = SCAN_DIR / symbol / "evidence.json"
    scan_payload = _json_text(scan_path)
    scan_reference = dict(payload["model_validity_input"]["event_scan_ref"])
    if scan_reference.get("path") != scan_path.relative_to(ROOT).as_posix():
        raise ValueError(f"Event scan path mismatch for {symbol}")
    actual_scan_hash = _sha256(scan_path)
    if scan_reference.get("sha256") != actual_scan_hash:
        raise ValueError(f"Event scan hash changed for {symbol}")
    announcements = {
        str(item["announcement_id"]): item
        for item in scan_payload.get("announcements") or []
    }
    return scan_payload, scan_reference, announcements


def _build_event_review(
    payload: Mapping[str, Any],
    scan_payload: Mapping[str, Any],
    scan_reference: Mapping[str, Any],
    announcements: Mapping[str, Any],
) -> EventMaterialityReview:
    symbol = str(payload["symbol"])
    specs = DECISION_SPECS[symbol]
    decisions: list[EventMaterialityDecision] = []
    for announcement_id, spec in specs.items():
        announcement = announcements.get(announcement_id)
        if announcement is None:
            raise ValueError(f"Missing announcement {announcement_id} for {symbol}")
        source_ref = announcement["evidence_refs"][0]
        source_path = ROOT / str(source_ref["path"])
        if not source_path.is_file():
            raise ValueError(f"Announcement PDF missing for {announcement_id}: {source_path}")
        actual_hash = _sha256(source_path)
        if source_ref.get("sha256") != actual_hash:
            raise ValueError(f"Announcement PDF hash changed: {announcement_id}")
        recalc, stale, followup = _decision_flags(spec["decision"])
        decisions.append(
            EventMaterialityDecision(
                event_decision_id=f"{symbol}-event-decision-{announcement_id}-20260923.1",
                symbol=symbol,
                announcement_id=announcement_id,
                title=str(announcement["title"]),
                published_at=datetime.fromisoformat(str(announcement["published_at"])),
                source_ref=dict(source_ref),
                source_sha256=actual_hash,
                machine_candidate_reason=(
                    f"title-based machine candidate; rule_kind={announcement.get('rule_kind')}"
                ),
                human_decision=str(spec["decision"]),
                affected_domains=tuple(str(item) for item in spec["affected_domains"]),
                affected_fact_fields=tuple(str(item) for item in spec["affected_fact_fields"]),
                affected_assumptions=tuple(str(item) for item in spec["affected_assumptions"]),
                affected_artifacts=tuple(str(item) for item in spec["affected_artifacts"]),
                requires_recalculation=recalc,
                requires_model_stale=stale,
                requires_followup=followup,
                supersedes_event_id=spec["supersedes_event_id"],
                event_cluster_id=spec["event_cluster_id"],
                reviewed_at=REVIEWED_AT,
                review_notes=tuple(str(item) for item in spec["review_notes"]),
            )
        )

    expected_counts = {"000651": 7, "600741": 4, "600887": 13}
    if len(decisions) != expected_counts[symbol]:
        raise ValueError(f"Unexpected decision count for {symbol}: {len(decisions)}")
    return EventMaterialityReview(
        review_id=f"{symbol}-event-materiality-review-20260923",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol=symbol,
        scan_id=str(scan_reference["id"]),
        scan_sha256=str(scan_reference["sha256"]),
        scan_from=date.fromisoformat(str(scan_payload["scan_from"])),
        scan_to=date.fromisoformat(str(scan_payload["scan_to"])),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEW_AS_OF,
        reviewer_type="human_research_lead",
        decisions=tuple(decisions),
        evidence_refs=(dict(scan_reference),),
    )


def _build_receipt(
    *,
    symbol: str,
    payload: Mapping[str, Any],
    valuation: Any,
    model_id: str,
    package_ref: Mapping[str, str],
    scan_reference: Mapping[str, str],
) -> HumanResearchApprovalReceipt:
    approval_spec = APPROVAL_SPECS[symbol]
    research_version = str(payload["research_case"]["research_version"])
    return HumanResearchApprovalReceipt(
        approval_id=f"{symbol}-g3-human-approval-20260923.1",
        symbol=symbol,
        security_id=symbol,
        profile_id=str(payload["profile_id"]),
        valuation_artifact_id=f"{symbol}-m1-valuation-result-v1",
        valuation_artifact_sha256=valuation_result_sha256(valuation),
        valuation_model_id=model_id,
        valuation_model_version=str(payload["dependencies"]["model_version"]),
        research_case_id=research_version,
        research_case_sha256=artifact_fingerprint(payload["research_case"]),
        assumption_set_id=f"{symbol}-assumptions-{research_version}",
        assumption_set_sha256=artifact_fingerprint(payload["assumptions"]),
        facts_artifact_id=f"{symbol}-facts-{research_version}",
        facts_artifact_sha256=artifact_fingerprint(payload["facts"]),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEW_AS_OF,
        reviewer_type="human_research_lead",
        decision=str(approval_spec["decision"]),
        price_assessment_eligible=False,
        review_priority=str(approval_spec["review_priority"]),
        conditions=tuple(str(item) for item in approval_spec.get("conditions") or ()),
        remaining_blockers=tuple(
            str(item) for item in approval_spec.get("remaining_blockers") or ()
        ),
        required_followups=tuple(
            str(item) for item in approval_spec.get("required_followups") or ()
        ),
        reopen_triggers=tuple(
            str(item) for item in approval_spec.get("reopen_triggers") or ()
        ),
        evidence_refs=(dict(package_ref), dict(scan_reference)),
        decision_version="20260923.1",
        created_at=REVIEWED_AT,
    )


def _interim_policy(
    symbol: str,
    package: Mapping[str, Any],
    announcements: Mapping[str, Any],
) -> Any:
    interim_id = {"000651": "1225515004", "600741": "1225516573", "600887": "1225511409"}[symbol]
    announcement = announcements[interim_id]
    source_ref = announcement["evidence_refs"][0]
    package_sources = {str(item["id"]): item for item in package["sources"]}
    filing_ref = next(
        item for item in package_sources.values()
        if "2026h1" in str(item["id"])
    )
    return classify_unaudited_interim_report(
        symbol=symbol,
        report_period=date(2026, 6, 30),
        source_verified=True,
        evidence_refs=(dict(source_ref), dict(filing_ref)),
    )


def _asset(
    *,
    symbol: str,
    name: str,
    book_value: str,
    kind: str,
    recoverability: str,
    legal_availability: str,
    liquidity: str,
    haircuts: tuple[str, str, str] | None,
    basis: str,
    evidence_refs: tuple[Mapping[str, Any], ...],
    blockers: tuple[str, ...] = (),
) -> BridgeComponentAssessment:
    bear, base, bull = haircuts or ("0", "0", "0")
    bear_value = Decimal(bear)
    base_value = Decimal(base)
    bull_value = Decimal(bull)
    return BridgeComponentAssessment(
        symbol=symbol,
        name=name,
        kind=kind,
        book_value=Decimal(book_value),
        legal_availability=legal_availability,
        liquidity=liquidity,
        recoverability=recoverability,
        bear_haircut=bear_value,
        base_haircut=base_value,
        bull_haircut=bull_value,
        bear_recoverable_value=Decimal(book_value) * (Decimal(1) - bear_value),
        base_recoverable_value=Decimal(book_value) * (Decimal(1) - base_value),
        bull_recoverable_value=Decimal(book_value) * (Decimal(1) - bull_value),
        basis=basis,
        confidence="低",
        evidence_refs=tuple(dict(ref) for ref in evidence_refs),
        blockers=blockers,
    )


def _claim(
    *,
    symbol: str,
    name: str,
    book_value: str,
    kind: str,
    evidence_refs: tuple[Mapping[str, Any], ...],
) -> BridgeComponentAssessment:
    return _asset(
        symbol=symbol,
        name=name,
        book_value=book_value,
        kind=kind,
        recoverability=RECOVERABILITY_CONTRACTUAL,
        legal_availability="VERIFIED",
        liquidity="HIGH",
        haircuts=("0", "0", "0"),
        basis="contractual claim at reviewed book value",
        evidence_refs=evidence_refs,
    )


def _scenario_bridge_components(
    symbol: str,
    specs: Mapping[str, Any],
    evidence_refs: tuple[Mapping[str, Any], ...],
) -> tuple[BridgeComponentAssessment, ...]:
    blockers = {
        "000651": (
            "gree_finance_company_and_restricted_cash_split_not_established",
            "gree_related_party_receivables_not_mapped",
        ),
        "600741": (
            "huayu_saic_finance_deposit_item_not_split_from_other_assets",
            "huayu_long_term_equity_recoverability_not_verified",
        ),
    }[symbol]
    components: list[BridgeComponentAssessment] = []
    for name, value in specs.items():
        if name == "debt":
            components.append(_claim(symbol=symbol, name="interest_bearing_debt", book_value=value, kind=KIND_DEBT, evidence_refs=evidence_refs))
        elif name == "minority":
            components.append(_claim(symbol=symbol, name="minority_interest", book_value=value, kind=KIND_MINORITY_INTEREST, evidence_refs=evidence_refs))
        elif name == "investment_property":
            book, bear, base, bull = value
            components.append(
                _asset(
                    symbol=symbol,
                    name="investment_property",
                    book_value=book,
                    kind=KIND_NON_OPERATING_ASSET,
                    recoverability=RECOVERABILITY_PARTIALLY_SUPPORTED,
                    legal_availability="VERIFIED",
                    liquidity="LOW",
                    haircuts=(bear, base, bull),
                    basis="reviewed book value with explicit illiquidity haircut",
                    evidence_refs=evidence_refs,
                )
            )
        else:
            book, bear, base, bull = value
            components.append(
                _asset(
                    symbol=symbol,
                    name=name,
                    book_value=book,
                    kind=KIND_NON_OPERATING_ASSET,
                    recoverability=RECOVERABILITY_CONSERVATIVE_ASSUMPTION,
                    legal_availability="UNKNOWN",
                    liquidity="UNKNOWN",
                    haircuts=(bear, base, bull),
                    basis="explicit conservative assumption; legal-entity split is not established",
                    evidence_refs=evidence_refs,
                    blockers=blockers,
                )
            )
    return tuple(components)


def _frozen_net_bridge(facts: Mapping[str, Any], scenario: str) -> Decimal:
    total = Decimal("0")
    for item in facts["scenario_inputs"][scenario]["bridge"]:
        signed = Decimal(str(item["value"]))
        if item["kind"] != "nonoperating_asset":
            signed = -signed
        total += signed
    return total


def _build_bridge_reviews(
    symbol: str,
    package: Mapping[str, Any],
    valuation: Any,
    package_ref: Mapping[str, str],
) -> list[dict[str, Any]]:
    facts = package["facts"]
    shares = Decimal(str(facts["operating_inputs"]["shares"]))
    frozen_values = {
        "bear": valuation.bear_value,
        "base": valuation.base_value,
        "bull": valuation.bull_value,
    }
    source_refs = tuple(dict(item) for item in package["sources"] if item["id"].startswith(symbol or ""))
    if not source_refs:
        source_refs = tuple(dict(item) for item in package["sources"])
    components = _scenario_bridge_components(symbol, BRIDGE_SPECS[symbol], source_refs)
    reviews: list[dict[str, Any]] = []
    for scenario in ("bear", "base", "bull"):
        net_bridge = _frozen_net_bridge(facts, scenario)
        operating_enterprise_value = (
            Decimal(str(frozen_values[scenario])) * shares - net_bridge
        )
        review = build_bridge_contribution(
            symbol=symbol,
            valuation_scenario=scenario,
            currency="CNY",
            ordinary_shares=shares,
            operating_enterprise_value=operating_enterprise_value,
            components=components,
            confidence="低",
            evidence_refs=(dict(package_ref),),
            blockers=(
                "review_is_research_arithmetic_only",
                "frozen_m1_valuation_numbers_were_not_changed",
            ),
        )
        reviews.append(review.as_policy())
    return reviews


def _wacc_sensitivity(symbol: str, descriptor: Any) -> dict[str, Any]:
    base = descriptor.facts.scenario_inputs["base"]
    rows = []
    for rate in ("0.075", "0.080", "0.085", "0.090", "0.095"):
        adjusted = replace(
            base,
            forecast=tuple(
                replace(row, wacc=Decimal(rate)) for row in base.forecast
            ),
            terminal=replace(base.terminal, wacc=Decimal(rate)),
        )
        result = adjusted.calculate("base")
        rows.append(
            {
                "wacc": rate,
                "per_share_value": str(result["per_share_value"]),
                "operating_value": str(result["operating_value"]),
                "status": "research_arithmetic_only",
            }
        )
    return {
        "symbol": symbol,
        "scenario": "base",
        "issuer_beta_status": "NOT_VERIFIED",
        "rows": rows,
        "blockers": (
            "issuer_specific_beta_not_verified",
            "credit_spread_not_verified",
            "market_derived_wacc_not_verified",
        ),
    }


def _yili_condition_review(package: Mapping[str, Any]) -> dict[str, Any]:
    facts = package["facts"]
    start_book = Decimal(str(facts["operating_inputs"]["start_book_equity"]))
    shares = Decimal(str(facts["operating_inputs"]["ordinary_shares"]))
    base = facts["scenario_inputs"]["base"]
    base_config = {
        "terminal_roe": base["terminal_roe"],
        "terminal_growth": base["terminal_growth"],
        "forecast_roe": base["forecast_roes"],
        "retention": base["retention"],
    }

    cost_rows = []
    for cost in ("0.070", "0.075", "0.080", "0.085", "0.090"):
        calculation = scenario_value(start_book, shares, Decimal(cost), base_config)
        cost_rows.append(
            {
                "cost_of_equity": cost,
                "per_share_value": calculation["conditional_value_per_2025_issued_share_cny"],
                "dividend_crosscheck_difference": calculation["dividend_crosscheck_difference_cny"],
                "status": "research_arithmetic_only",
            }
        )

    retention_rows = []
    for retention in ("0.20", "0.30", "0.40"):
        config = dict(base_config)
        config["retention"] = retention
        calculation = scenario_value(start_book, shares, Decimal("0.080"), config)
        closing_book = calculation["forecast_years"][-1]["closing_book_equity_cny"]
        retention_rows.append(
            {
                "retention": retention,
                "implied_payout_ratio": str(Decimal(1) - Decimal(retention)),
                "per_share_value": calculation["conditional_value_per_2025_issued_share_cny"],
                "closing_book_equity": closing_book,
                "dividend_crosscheck_difference": calculation["dividend_crosscheck_difference_cny"],
                "status": "arithmetic_consistency_only",
            }
        )

    scenario_roes = {
        name: list(facts["scenario_inputs"][name]["forecast_roes"])
        for name in ("bear", "base", "bull")
    }
    return {
        "symbol": "600887",
        "cost_of_equity_sensitivity": cost_rows,
        "retention_dividend_consistency": retention_rows,
        "normalized_roe_review": {
            "reported_fy2025_weighted_roe": "0.2087",
            "reported_h1_2026_weighted_roe": "0.1009",
            "forecast_roe_ranges": scenario_roes,
            "normalized_roe_status": "NOT_VERIFIED",
            "one_off_vs_recurring_impairment_status": "UNRESOLVED",
            "blockers": (
                "normalized_roe_review_pending",
                "impairment_classification_pending",
                "recurring_capital_allocation_quality_not_assessed",
            ),
        },
        "status": "CONDITIONAL_REVIEW_PENDING",
        "action": ACTION_NO_ORDER,
    }


def _unresolved_split(symbol: str) -> dict[str, Any]:
    if symbol == "000651":
        items = [
            "unrestricted_cash",
            "restricted_cash",
            "finance_company_assets",
            "related_party_or_subsidiary_receivables",
            "long_term_equity_investments",
            "other_financial_assets",
            "investment_property",
            "interest_bearing_debt",
            "minority_interest",
        ]
    else:
        items = [
            "cash",
            "saic_finance_deposits",
            "debt_investments",
            "long_term_equity_investments",
            "other_financial_assets",
            "investment_property",
            "debt",
            "minority_interest",
        ]
    return {
        "symbol": symbol,
        "status": "UNRESOLVED",
        "reason": "Existing M1 filings do not establish every legal-entity component at a verified book value.",
        "components": [
            {"name": name, "verified_book_value": None, "recoverability": "UNKNOWN"}
            for name in items
        ],
    }


def _outcome_payload(
    *,
    spec: Any,
    outcome: Any,
    receipt: HumanResearchApprovalReceipt,
    valuation: Any,
    model_id: str,
    package: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = resolve_human_research_approval(
        receipt,
        valuation,
        model_id=model_id,
        research_case_payload=package["research_case"],
        facts_payload=package["facts"],
        assumptions_payload=package["assumptions"],
    )
    return {
        "run_id": spec.run_id,
        "symbol": spec.symbol,
        "status": outcome.status,
        "gate": {
            "conclusion": outcome.gate.conclusion,
            "blockers": list(outcome.gate.blockers),
        },
        "human_approval": resolved.as_policy(),
        "valuation": json.loads(outcome.valuation.to_json()),
        "model_validity": (
            json.loads(outcome.model_validity.to_json())
            if outcome.model_validity is not None else None
        ),
        "price_bridge": (
            json.loads(outcome.price_bridge.to_json())
            if outcome.price_bridge is not None else None
        ),
        "price_attractiveness": (
            outcome.price_attractiveness.as_policy()
            if outcome.price_attractiveness is not None else None
        ),
        "current_research_status": (
            outcome.current_status.as_policy()
            if outcome.current_status is not None else None
        ),
        "pre_decision_eligibility": (
            outcome.pre_decision_eligibility.as_policy()
            if outcome.pre_decision_eligibility is not None else None
        ),
        "interim_report_policy": (
            outcome.interim_report_policy.as_policy()
            if outcome.interim_report_policy is not None else None
        ),
        "blockers": list(outcome.blockers),
        "action": ACTION_NO_ORDER,
    }


def build_bundle(root: Path) -> dict[str, Any]:
    payloads = load_descriptor_payloads(root)
    service = ResearchApplicationService(InMemoryResearchArtifactRepository())
    approvals: list[dict[str, Any]] = []
    event_reviews: list[dict[str, Any]] = []
    interim_policies: list[dict[str, Any]] = []
    bridge_reviews: list[dict[str, Any]] = []
    unresolved_splits: list[dict[str, Any]] = []
    wacc_sensitivities: list[dict[str, Any]] = []
    integrated_runs: list[dict[str, Any]] = []
    yili_condition_review: dict[str, Any] | None = None
    frozen_integrity: list[dict[str, str]] = []

    for symbol in ("000651", "600741", "600887"):
        package_path = root / "config" / "m1-valuation-packages-v1" / (
            f"{symbol}-fcff.json" if symbol != "600887" else f"{symbol}-quality-compounder.json"
        )
        package = _json_text(package_path)
        actual_package_hash = _sha256(package_path)
        if actual_package_hash != FROZEN_PACKAGE_SHA256[symbol]:
            raise ValueError(f"Frozen M1 package hash changed: {symbol}")
        frozen_integrity.append(
            {
                "symbol": symbol,
                "path": str(package_path.relative_to(root)),
                "sha256": actual_package_hash,
                "status": "UNCHANGED",
            }
        )
        descriptor = build_descriptor(package, root=root)
        base_spec = build_research_run_spec(descriptor)
        profile = PROFILES[descriptor.profile_id]
        route = service.router.route(profile, descriptor.requested_model)
        model = route.build_model()
        valuation = model.value(descriptor.facts, descriptor.research_case)

        scan_payload, scan_reference, announcements = _load_scan(package)
        event_review = _build_event_review(
            package,
            scan_payload,
            scan_reference,
            announcements,
        )
        package_ref = _ref(package_path, f"{symbol}-m1-valuation-package-v1")
        receipt = _build_receipt(
            symbol=symbol,
            payload=package,
            valuation=valuation,
            model_id=route.selected_model,
            package_ref=package_ref,
            scan_reference=scan_reference,
        )
        interim = _interim_policy(symbol, package, announcements)

        bridge_payloads: list[dict[str, Any]] = []
        if symbol in BRIDGE_SPECS:
            bridge_payloads = _build_bridge_reviews(
                symbol,
                package,
                valuation,
                package_ref,
            )
            unresolved_splits.append(_unresolved_split(symbol))
        else:
            yili_condition_review = _yili_condition_review(package)

        spec = replace(
            base_spec,
            model_validity_input=replace(
                base_spec.model_validity_input,
                event_scan=None,
            ),
            human_research_approval=receipt,
            event_materiality_review=event_review,
            research_case_payload=package["research_case"],
            facts_payload=package["facts"],
            assumptions_payload=package["assumptions"],
            bridge_contribution_reviews=(),
            interim_report_policy=interim,
        )
        # The typed bridge reviews are emitted independently as append-only
        # policy artifacts; they do not alter the frozen valuation inputs.
        outcome = service.run_company_research(spec)
        approvals.append(receipt.as_policy())
        event_reviews.append(event_review.as_policy())
        interim_policies.append(interim.as_policy())
        bridge_reviews.extend(bridge_payloads)
        if symbol != "600887":
            wacc_sensitivities.append(_wacc_sensitivity(symbol, descriptor))
        integrated_runs.append(
            _outcome_payload(
                spec=spec,
                outcome=outcome,
                receipt=receipt,
                valuation=valuation,
                model_id=route.selected_model,
                package=package,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "review_as_of": REVIEW_AS_OF.isoformat(),
        "frozen_m1_package_integrity": frozen_integrity,
        "human_research_approvals": approvals,
        "event_materiality_reviews": event_reviews,
        "interim_report_policies": interim_policies,
        "bridge_contribution_reviews": bridge_reviews,
        "unresolved_bridge_splits": unresolved_splits,
        "wacc_sensitivities": wacc_sensitivities,
        "yili_condition_review": yili_condition_review,
        "integrated_runs": integrated_runs,
    }


def _write_runtime(payload: dict[str, Any], root: Path) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m1-post-review-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    file_specs = {
        "human-research-approvals.json": payload["human_research_approvals"],
        "event-materiality-reviews.json": payload["event_materiality_reviews"],
        "interim-report-policy.json": payload["interim_report_policies"],
        "bridge-contribution-reviews.json": payload["bridge_contribution_reviews"],
        "unresolved-bridge-splits.json": payload["unresolved_bridge_splits"],
        "wacc-sensitivities.json": payload["wacc_sensitivities"],
        "yili-condition-review.json": payload["yili_condition_review"],
        "integrated-runs.json": payload["integrated_runs"],
        "evidence.json": payload,
    }
    outputs: dict[str, str] = {}
    for filename, value in file_specs.items():
        path = target / filename
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        outputs[filename] = str(path.relative_to(root))
    evidence_path = target / "evidence.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "action": ACTION_NO_ORDER,
        "evidence_sha256": _sha256(evidence_path),
        "files": {name: _sha256(target / name) for name in file_specs},
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs["manifest.json"] = str((target / "manifest.json").relative_to(root))
    return outputs


def _report(payload: dict[str, Any]) -> str:
    event_counts: dict[str, int] = {}
    for review in payload["event_materiality_reviews"]:
        event_counts[review["symbol"]] = len(review["decisions"])
    lines = [
        "M1 POST-REVIEW RECEIPT BUILD",
        f"generated_at: {payload['generated_at']}",
        f"action: {payload['action']}",
        "approvals: " + ", ".join(
            f"{item['symbol']}={item['decision']}"
            for item in payload["human_research_approvals"]
        ),
        "event decisions: " + ", ".join(
            f"{symbol}={count}" for symbol, count in sorted(event_counts.items())
        ),
        "bridge reviews: " + str(len(payload["bridge_contribution_reviews"])),
        "integrated runs: " + str(len(payload["integrated_runs"])),
        "",
        "No frozen package, production database, scheduler, WPS or server files were modified.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    payload = build_bundle(args.root)
    outputs = {} if args.no_write else _write_runtime(payload, args.root)
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_report(payload))
        if outputs:
            print("\nruntime outputs:")
            for key in ("human-research-approvals.json", "event-materiality-reviews.json", "integrated-runs.json", "manifest.json"):
                print(f"- {outputs[key]}")
    if payload["action"] != ACTION_NO_ORDER:
        print("ERROR: no_order contract violated", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
