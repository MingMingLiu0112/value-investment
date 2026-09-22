"""Fixed-sample admission protocol for research observation, never execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .current_research_status import (
    CONCLUSION_REMOVED,
    CONCLUSION_RESEARCH_NOT_PASSED,
    CONCLUSION_THESIS_DAMAGED,
    ENGINEERING_READY,
    current_research_status_from_payloads,
)
from .research_profile import PROFILES
from .valuation_router import ROUTE_SUPPORTED, route_profile


PROTOCOL_VERSION = "fixed-sample-admission-v1"

ENGINEERING_REUSABLE = "REUSABLE"
ENGINEERING_NOT_REUSABLE = "NOT_REUSABLE"

RESEARCH_SAMPLE_ADMITTED = "ADMITTED_FOR_RESEARCH"
RESEARCH_SAMPLE_REJECTED = "REJECTED_FOR_RESEARCH"
RESEARCH_SAMPLE_STATUSES = {RESEARCH_SAMPLE_ADMITTED, RESEARCH_SAMPLE_REJECTED}

PRODUCTION_VALUATION_AVAILABLE = "AVAILABLE"
PRODUCTION_VALUATION_NOT_AVAILABLE = "NOT_AVAILABLE"
PRODUCTION_VALUATION_STATUSES = {
    PRODUCTION_VALUATION_AVAILABLE,
    PRODUCTION_VALUATION_NOT_AVAILABLE,
}

BOUNDED_VALUE_AVAILABLE = "AVAILABLE"
BOUNDED_VALUE_CONDITIONAL = "CONDITIONAL"
BOUNDED_VALUE_NOT_AVAILABLE = "NOT_AVAILABLE"
BOUNDED_VALUE_STATUSES = {
    BOUNDED_VALUE_AVAILABLE,
    BOUNDED_VALUE_CONDITIONAL,
    BOUNDED_VALUE_NOT_AVAILABLE,
}

CASH_RETURN_NOT_ASSESSED = "NOT_ASSESSED"
CASH_RETURN_PARTIAL = "PARTIAL"
CASH_RETURN_AVAILABLE = "AVAILABLE"
CASH_RETURN_STATUSES = {
    CASH_RETURN_NOT_ASSESSED,
    CASH_RETURN_PARTIAL,
    CASH_RETURN_AVAILABLE,
}

DECISION_CONTINUE_CONDITIONAL_MODEL = "CONTINUE_CONDITIONAL_MODEL"
DECISION_RESOLVE_MODEL_INPUTS = "RESOLVE_MODEL_INPUTS"
DECISION_PAUSE_PRODUCTION_VALUATION = "PAUSE_PRODUCTION_VALUATION"
DECISION_MODEL_REPLACEMENT_OR_STOP = "MODEL_REPLACEMENT_OR_STOP"
DECISION_STOP_RESEARCH = "STOP_RESEARCH"
DECISIONS = {
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    DECISION_RESOLVE_MODEL_INPUTS,
    DECISION_PAUSE_PRODUCTION_VALUATION,
    DECISION_MODEL_REPLACEMENT_OR_STOP,
    DECISION_STOP_RESEARCH,
}

_STOP_RESEARCH_CONCLUSIONS = {
    CONCLUSION_REMOVED,
    CONCLUSION_RESEARCH_NOT_PASSED,
    CONCLUSION_THESIS_DAMAGED,
}


def _validate_refs(refs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(ref) for ref in refs]
    if any(not ref.get("id") for ref in result):
        raise ValueError("Fixed-sample evidence requires named references")
    ids = [ref["id"] for ref in result]
    if len(set(ids)) != len(ids):
        raise ValueError("Fixed-sample evidence ids must be unique")
    return result


def _merge_refs(*groups: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for ref in group:
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Fixed-sample evidence requires named references")
            if ref_id in merged and merged[ref_id] != ref:
                raise ValueError(
                    f"Fixed-sample evidence references with the same id must match: {ref_id}"
                )
            merged[ref_id] = dict(ref)
    return list(merged.values())


@dataclass(frozen=True)
class FixedSampleAdmissionPolicy:
    """Explicit human-authored policy for one candidate in the fixed sample."""

    profile_id: str
    decision: str
    decision_reason: str
    cash_return_status: str
    cash_return_explanation: str
    admission_evidence: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.profile_id not in PROFILES:
            raise ValueError(f"Unknown research profile: {self.profile_id}")
        if self.decision not in DECISIONS:
            raise ValueError(f"Unknown fixed-sample decision: {self.decision}")
        if not self.decision_reason.strip():
            raise ValueError("A fixed-sample decision requires a reason")
        if self.cash_return_status not in CASH_RETURN_STATUSES:
            raise ValueError("Unknown cash-return status")
        if self.cash_return_status != CASH_RETURN_NOT_ASSESSED and not self.cash_return_explanation.strip():
            raise ValueError("A non-empty cash-return status requires an explanation")
        if not self.admission_evidence:
            raise ValueError("Fixed-sample admission requires named evidence requirements")
        if any(not item.strip() for item in self.admission_evidence):
            raise ValueError("Admission evidence entries must be nonempty")
        if self.decision != DECISION_STOP_RESEARCH and not self.required_evidence:
            raise ValueError("A non-stop decision requires the evidence needed to advance")
        if any(not item.strip() for item in self.required_evidence):
            raise ValueError("Required evidence entries must be nonempty")


@dataclass(frozen=True)
class FixedSampleCompanyAdmission:
    symbol: str
    profile_id: str
    engineering_contract_reusable: bool
    research_sample_status: str
    admission_evidence: list[str]
    production_valuation_status: str
    bounded_value_judgment: str
    cash_return_status: str
    cash_return_explanation: str
    decision: str
    decision_reason: str
    required_evidence: list[str]
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]
    human_confirmation_required: bool
    action: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Fixed-sample symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError(f"Unknown research profile: {self.profile_id}")
        if self.research_sample_status not in RESEARCH_SAMPLE_STATUSES:
            raise ValueError("Unknown fixed-sample research status")
        if not self.admission_evidence or any(not item.strip() for item in self.admission_evidence):
            raise ValueError("Fixed-sample admission evidence requirements are required")
        if self.production_valuation_status not in PRODUCTION_VALUATION_STATUSES:
            raise ValueError("Unknown production-valuation status")
        if self.bounded_value_judgment not in BOUNDED_VALUE_STATUSES:
            raise ValueError("Unknown bounded-value status")
        if self.cash_return_status not in CASH_RETURN_STATUSES:
            raise ValueError("Unknown cash-return status")
        if self.decision not in DECISIONS:
            raise ValueError(f"Unknown fixed-sample decision: {self.decision}")
        if not self.decision_reason.strip():
            raise ValueError("A fixed-sample decision requires a reason")
        if not self.required_evidence and self.decision != DECISION_STOP_RESEARCH:
            raise ValueError("A non-stop decision requires required evidence")
        if self.action != "no_order":
            raise ValueError("Fixed-sample admission can only record no_order")
        if self.human_confirmation_required is not True:
            raise ValueError("Fixed-sample state changes always require human confirmation")
        object.__setattr__(self, "evidence_refs", _validate_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "engineering_contract_reusable": self.engineering_contract_reusable,
            "research_sample_status": self.research_sample_status,
            "admission_evidence": list(self.admission_evidence),
            "production_valuation_status": self.production_valuation_status,
            "bounded_value_judgment": self.bounded_value_judgment,
            "cash_return_status": self.cash_return_status,
            "cash_return_explanation": self.cash_return_explanation,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "required_evidence": list(self.required_evidence),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "human_confirmation_required": self.human_confirmation_required,
            "action": self.action,
        }


@dataclass(frozen=True)
class FixedSampleAdmissionReview:
    protocol_version: str
    rule_version: str
    as_of: date
    engineering_orchestration_status: str
    production_valuation_available: bool
    research_sample_members: tuple[str, ...]
    companies: tuple[FixedSampleCompanyAdmission, ...]
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]
    human_confirmation_required: bool
    action: str
    interpretation: str

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("Unknown fixed-sample protocol version")
        if self.engineering_orchestration_status not in {
            ENGINEERING_REUSABLE,
            ENGINEERING_NOT_REUSABLE,
        }:
            raise ValueError("Unknown engineering-orchestration status")
        if self.action != "no_order":
            raise ValueError("Fixed-sample review can only record no_order")
        if self.human_confirmation_required is not True:
            raise ValueError("Fixed-sample review always requires human confirmation")
        if not self.companies:
            raise ValueError("A fixed-sample review requires at least one company")
        object.__setattr__(self, "evidence_refs", _validate_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "rule_version": self.rule_version,
            "as_of": self.as_of.isoformat(),
            "engineering_orchestration_status": self.engineering_orchestration_status,
            "production_valuation_available": self.production_valuation_available,
            "research_sample_members": list(self.research_sample_members),
            "companies": [company.as_policy() for company in self.companies],
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "human_confirmation_required": self.human_confirmation_required,
            "action": self.action,
            "interpretation": self.interpretation,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Scenario values must be finite decimal strings") from error
    if not number.is_finite() or number <= 0:
        raise ValueError("Scenario values must be positive and finite")
    return number


def _bounded_value_judgment(
    result: Mapping[str, Any],
    *,
    formal_valuation_approved: bool,
) -> str:
    values = [
        _optional_decimal(result.get(key))
        for key in ("bear_value", "base_value", "bull_value")
    ]
    if all(value is not None for value in values):
        return (
            BOUNDED_VALUE_AVAILABLE
            if formal_valuation_approved
            else BOUNDED_VALUE_CONDITIONAL
        )
    if all(value is None for value in values):
        return BOUNDED_VALUE_NOT_AVAILABLE
    return BOUNDED_VALUE_NOT_AVAILABLE


def _production_valuation_status(
    result: Mapping[str, Any],
    *,
    formal_valuation_approved: bool,
) -> str:
    values = [
        _optional_decimal(result.get(key))
        for key in ("bear_value", "base_value", "bull_value")
    ]
    approved_status = result.get("status") in {"approved_research_only", "ready"}
    if (
        formal_valuation_approved
        and approved_status
        and all(value is not None for value in values)
    ):
        return PRODUCTION_VALUATION_AVAILABLE
    return PRODUCTION_VALUATION_NOT_AVAILABLE


def _valuation_model_matches_route(result: Mapping[str, Any], route_model_type: str | None) -> bool:
    model_type = str(result.get("model_type", ""))
    if route_model_type == "residual_income_or_equity_value":
        return model_type == route_model_type or model_type.startswith("归母权益剩余收益")
    return route_model_type is not None and model_type == route_model_type


def _research_sample_status(
    research_conclusion: str,
    *,
    has_research_evidence: bool,
    has_admission_requirements: bool,
) -> str:
    conclusion = str(research_conclusion)
    if conclusion in _STOP_RESEARCH_CONCLUSIONS:
        return RESEARCH_SAMPLE_REJECTED
    if not has_research_evidence or not has_admission_requirements:
        return RESEARCH_SAMPLE_REJECTED
    return RESEARCH_SAMPLE_ADMITTED


def assess_fixed_sample_company(
    *,
    gate_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
    price_bridge_payload: Mapping[str, Any],
    policy: FixedSampleAdmissionPolicy,
    formal_valuation_approved: bool,
    research_evidence_refs: Sequence[dict[str, Any]],
    model_validity_payload: Mapping[str, Any] | None = None,
    engineering_status: str = ENGINEERING_READY,
) -> FixedSampleCompanyAdmission:
    """Restore common contracts, then apply one explicit fixed-sample policy."""
    route = route_profile(policy.profile_id)
    model_matches_route = _valuation_model_matches_route(result_payload, route.model_type)
    engineering_contract_reusable = (
        engineering_status == ENGINEERING_READY
        and route.status == ROUTE_SUPPORTED
        and model_matches_route
    )
    status = current_research_status_from_payloads(
        dict(gate_payload),
        dict(result_payload),
        dict(price_bridge_payload),
        model_validity_payload=(
            dict(model_validity_payload) if model_validity_payload is not None else None
        ),
        engineering_status=engineering_status,
        profile_id=policy.profile_id,
    )
    symbol = str(result_payload["symbol"])
    if status.symbol != symbol:
        raise ValueError("Fixed-sample status symbol differs from the valuation")

    bounded_value_judgment = _bounded_value_judgment(
        result_payload,
        formal_valuation_approved=formal_valuation_approved,
    )
    production_valuation_status = _production_valuation_status(
        result_payload,
        formal_valuation_approved=formal_valuation_approved,
    )
    research_sample_status = _research_sample_status(
        status.research_conclusion,
        has_research_evidence=bool(research_evidence_refs),
        has_admission_requirements=bool(policy.admission_evidence),
    )

    blockers = list(dict.fromkeys(status.blockers))
    if not engineering_contract_reusable:
        blockers.append("engineering_contract_not_reusable")
    if not model_matches_route:
        blockers.append("valuation_model_does_not_match_profile_route")
    if research_sample_status == RESEARCH_SAMPLE_REJECTED:
        blockers.append("research_sample_admission_evidence_not_met")
    if production_valuation_status == PRODUCTION_VALUATION_NOT_AVAILABLE:
        if formal_valuation_approved is False:
            blockers.append("formal_valuation_not_approved")
        if result_payload.get("status") == "conditional_research_only":
            blockers.append("conditional_valuation_not_promoted")
        elif result_payload.get("status") == "not_ready":
            blockers.append("valuation_scenarios_not_available")

    evidence_refs = _merge_refs(
        status.evidence_refs,
        research_evidence_refs,
    )
    return FixedSampleCompanyAdmission(
        symbol=symbol,
        profile_id=policy.profile_id,
        engineering_contract_reusable=engineering_contract_reusable,
        research_sample_status=research_sample_status,
        admission_evidence=list(policy.admission_evidence),
        production_valuation_status=production_valuation_status,
        bounded_value_judgment=bounded_value_judgment,
        cash_return_status=policy.cash_return_status,
        cash_return_explanation=policy.cash_return_explanation,
        decision=policy.decision,
        decision_reason=policy.decision_reason,
        required_evidence=list(policy.required_evidence),
        blockers=blockers,
        evidence_refs=evidence_refs,
        human_confirmation_required=True,
        action="no_order",
    )


def review_fixed_sample(
    *,
    research_records: Sequence[Mapping[str, Any]],
    valuation_payloads: Mapping[str, Mapping[str, Any]],
    policies: Mapping[str, FixedSampleAdmissionPolicy],
    as_of: date,
) -> FixedSampleAdmissionReview:
    """Apply one admission policy to every explicitly supplied frozen payload."""
    records = [dict(record) for record in research_records]
    record_symbols = [str(record["case"]["symbol"]) for record in records]
    if len(set(record_symbols)) != len(record_symbols):
        raise ValueError("Fixed-sample research records must have unique symbols")
    if set(record_symbols) != set(policies):
        raise ValueError("Fixed-sample policies must match the supplied research records")
    if set(record_symbols) != set(valuation_payloads):
        raise ValueError("Fixed-sample valuation payloads must match the supplied research records")

    companies: list[FixedSampleCompanyAdmission] = []
    for record in records:
        symbol = str(record["case"]["symbol"])
        payload = dict(valuation_payloads[symbol])
        result = dict(payload["result"])
        companies.append(
            assess_fixed_sample_company(
                gate_payload=dict(record["gate"]),
                result_payload=result,
                price_bridge_payload=dict(payload["price_bridge"]),
                policy=policies[symbol],
                formal_valuation_approved=bool(
                    payload.get("valuation_approved", payload.get("formal_valuation_approved", False))
                ),
                research_evidence_refs=record["case"].get("evidence_refs", []),
                model_validity_payload=payload.get("model_validity"),
            )
        )

    reusable = all(
        company.engineering_contract_reusable for company in companies
    )
    production_available = any(
        company.production_valuation_status == PRODUCTION_VALUATION_AVAILABLE
        for company in companies
    )
    members = tuple(
        company.symbol
        for company in companies
        if company.research_sample_status == RESEARCH_SAMPLE_ADMITTED
    )
    blockers = list(
        dict.fromkeys(blocker for company in companies for blocker in company.blockers)
    )
    evidence_refs = _merge_refs(
        *(company.evidence_refs for company in companies)
    )

    if not reusable:
        interpretation = (
            "固定样本公共编排尚不可复用；先修复共享合同或工程失败，不能扩大样本。"
        )
    elif production_available:
        interpretation = (
            "固定样本中存在生产估值可用候选；仍只作研究结论，人工确认前不生成任何交易。"
        )
    else:
        interpretation = (
            "固定样本公共编排可复用，但当前候选均未达到生产估值可用；"
            "仅保留研究观察、显式未完成项和人工确认边界。"
        )

    return FixedSampleAdmissionReview(
        protocol_version=PROTOCOL_VERSION,
        rule_version=PROTOCOL_VERSION,
        as_of=as_of,
        engineering_orchestration_status=(
            ENGINEERING_REUSABLE if reusable else ENGINEERING_NOT_REUSABLE
        ),
        production_valuation_available=production_available,
        research_sample_members=members,
        companies=tuple(companies),
        blockers=blockers,
        evidence_refs=evidence_refs,
        human_confirmation_required=True,
        action="no_order",
        interpretation=interpretation,
    )
