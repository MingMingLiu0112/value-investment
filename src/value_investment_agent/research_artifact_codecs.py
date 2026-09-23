"""Typed conversions between domain objects and canonical artifact payloads.

The repository owns database conversion. These codecs are still domain-side
adapters: they import no psycopg and return plain Python mappings/objects.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping, Protocol

from .current_research_status import (
    CurrentDataStatus,
    CurrentResearchStatus,
)
from .distribution import (
    DistributionCapacity,
    DividendHistory,
    DividendRecord,
    DividendResearchResult,
    DividendSustainabilityAssessment,
    DividendYieldSnapshot,
)
from .fixed_sample_admission import (
    FixedSampleAdmissionReview,
    FixedSampleCompanyAdmission,
)
from .investment_decision import (
    ConsistencyComparison,
    DecisionEvidenceBundle,
    DecisionJournalEntry,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
    InvestmentDecisionReview,
    MinimalPortfolioPreconditions,
    consistency_comparison_from_payload,
    decision_evidence_bundle_from_payload,
    decision_journal_entry_from_payload,
    entry_thesis_snapshot_from_payload,
    investment_consistency_review_from_payload,
    investment_decision_review_from_payload,
    minimal_portfolio_preconditions_from_payload,
)
from .model_validity import ModelValidity, model_validity_from_payload
from .price_attractiveness import PriceAttractivenessAssessment
from .price_bridge import PriceBridgeResult, price_bridge_from_payload
from .quote_snapshot import QuoteSnapshot
from .research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DECISION_EVIDENCE_BUNDLE,
    ARTIFACT_DECISION_JOURNAL_ENTRY,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    ARTIFACT_FIXED_SAMPLE_ADMISSION,
    ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    ARTIFACT_INVESTMENT_DECISION_REVIEW,
    ARTIFACT_MINIMAL_PORTFOLIO_PRECONDITIONS,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_ATTRACTIVENESS,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ARTIFACT_VALUATION_RESULT,
)
from .research_case import ResearchCase
from .research_gate import ResearchGate
from .valuation_assumptions import (
    ValuationAssumptionSet,
    assumption_set_from_payload,
)
from .valuation_models.base import ValuationResult


ARTIFACT_SCHEMA_VERSION = "c3-v1"


class ArtifactCodec(Protocol):
    artifact_type: str
    schema_version: str

    def to_payload(self, value: Any) -> dict[str, Any]: ...

    def from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        dependencies: Mapping[str, Any] | None = None,
    ) -> Any: ...


def _payload(value: Any) -> dict[str, Any]:
    """Convert an object with a to_json method to its policy payload."""
    serializer = getattr(value, "to_json", None)
    if not callable(serializer):
        raise TypeError(f"{type(value).__name__} has no to_json serializer")
    parsed = json.loads(serializer())
    if not isinstance(parsed, dict):
        raise TypeError(f"{type(value).__name__} did not serialize to an object")
    return parsed


def _asdict_payload(value: Any) -> dict[str, Any]:
    return dict(asdict(value))


def _required_date(value: object, field: str) -> date:
    if value is None:
        raise ValueError(f"{field} is required")
    parsed = _optional_date(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date string") from error


def _optional_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return number


def _str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_str(value: object, field: str) -> str | None:
    return None if value is None else _str(value, field)


def _refs(value: object, field: str = "evidence_refs") -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return [dict(item) for item in value]


def _decimal_dict(value: object, field: str) -> dict[str, Decimal | None]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {
        str(key): _optional_decimal(item, f"{field}.{key}")
        for key, item in value.items()
    }


class ResearchCaseCodec:
    artifact_type = ARTIFACT_RESEARCH_CASE
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: ResearchCase) -> dict[str, Any]:
        if not isinstance(value, ResearchCase):
            raise TypeError("research_case codec requires ResearchCase")
        return _payload(value)

    def from_payload(self, payload: Mapping[str, Any], **_: Any) -> ResearchCase:
        data = dict(payload)
        return ResearchCase(
            symbol=_str(data.get("symbol"), "symbol"),
            name=_str(data.get("name"), "name"),
            as_of=_required_date(data.get("as_of"), "as_of"),
            run_id=_str(data.get("run_id"), "run_id"),
            generated_at=_optional_datetime(data.get("generated_at"), "generated_at"),
            research_version=_str(data.get("research_version"), "research_version"),
            industry=_str(data.get("industry"), "industry"),
            investment_path=_str(data.get("investment_path"), "investment_path"),
            thesis=_str(data.get("thesis"), "thesis"),
            return_driver=_str(data.get("return_driver"), "return_driver"),
            mispricing_hypothesis=_str(
                data.get("mispricing_hypothesis"), "mispricing_hypothesis"
            ),
            financial_summary=dict(data.get("financial_summary") or {}),
            positives=list(data.get("positives") or []),
            counter_evidence=list(data.get("counter_evidence") or []),
            thesis_breakers=list(data.get("thesis_breakers") or []),
            next_events=list(data.get("next_events") or []),
            evidence_status=_str(data.get("evidence_status"), "evidence_status"),
            valuation_status=_str(data.get("valuation_status"), "valuation_status"),
            research_status=_str(data.get("research_status"), "research_status"),
            blockers=[str(item) for item in data.get("blockers") or []],
            evidence_refs=_refs(data.get("evidence_refs")),
            quote_date=_optional_date(data.get("quote_date"), "quote_date"),
            financial_period=_optional_date(
                data.get("financial_period"), "financial_period"
            ),
            missing_date_reasons={
                str(key): str(value)
                for key, value in (data.get("missing_date_reasons") or {}).items()
            },
        )


class ResearchGateCodec:
    artifact_type = ARTIFACT_RESEARCH_GATE
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: ResearchGate) -> dict[str, Any]:
        if not isinstance(value, ResearchGate):
            raise TypeError("research_gate codec requires ResearchGate")
        return _asdict_payload(value)

    def from_payload(self, payload: Mapping[str, Any], **_: Any) -> ResearchGate:
        data = dict(payload)
        return ResearchGate(
            symbol=_str(data.get("symbol"), "symbol"),
            results={str(key): bool(value) for key, value in data["results"].items()},
            blockers=[str(item) for item in data.get("blockers") or []],
            conclusion=_str(data.get("conclusion"), "conclusion"),
        )


class ValuationAssumptionSetCodec:
    artifact_type = ARTIFACT_VALUATION_ASSUMPTIONS
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: ValuationAssumptionSet) -> dict[str, Any]:
        if not isinstance(value, ValuationAssumptionSet):
            raise TypeError("valuation_assumptions codec requires ValuationAssumptionSet")
        return _payload(value)

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> ValuationAssumptionSet:
        return assumption_set_from_payload(dict(payload))


class ValuationResultCodec:
    artifact_type = ARTIFACT_VALUATION_RESULT
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: ValuationResult) -> dict[str, Any]:
        if not isinstance(value, ValuationResult):
            raise TypeError("valuation_result codec requires ValuationResult")
        return _payload(value)

    def from_payload(self, payload: Mapping[str, Any], **_: Any) -> ValuationResult:
        data = dict(payload)
        return ValuationResult(
            symbol=_str(data.get("symbol"), "symbol"),
            model_type=_str(data.get("model_type"), "model_type"),
            valuation_date=_required_date(
                data.get("valuation_date"), "valuation_date"
            ),
            bear_value=_optional_decimal(data.get("bear_value"), "bear_value"),
            base_value=_optional_decimal(data.get("base_value"), "base_value"),
            bull_value=_optional_decimal(data.get("bull_value"), "bull_value"),
            confidence=_str(data.get("confidence"), "confidence"),
            assumptions=dict(data.get("assumptions") or {}),
            sensitivities=list(data.get("sensitivities") or []),
            evidence_refs=_refs(data.get("evidence_refs")),
            blockers=[str(item) for item in data.get("blockers") or []],
            status=_str(data.get("status"), "status"),
            model_version=_str(data.get("model_version"), "model_version"),
        )


class ModelValidityCodec:
    artifact_type = ARTIFACT_MODEL_VALIDITY
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: ModelValidity) -> dict[str, Any]:
        if not isinstance(value, ModelValidity):
            raise TypeError("model_validity codec requires ModelValidity")
        return _payload(value)

    def from_payload(self, payload: Mapping[str, Any], **_: Any) -> ModelValidity:
        return model_validity_from_payload(dict(payload))


class QuoteSnapshotCodec:
    artifact_type = ARTIFACT_QUOTE_SNAPSHOT
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: QuoteSnapshot) -> dict[str, Any]:
        if not isinstance(value, QuoteSnapshot):
            raise TypeError("quote_snapshot codec requires QuoteSnapshot")
        return _payload(value)

    def from_payload(self, payload: Mapping[str, Any], **_: Any) -> QuoteSnapshot:
        data = dict(payload)
        return QuoteSnapshot(
            symbol=_str(data.get("symbol"), "symbol"),
            quote_date=_optional_date(data.get("quote_date"), "quote_date"),
            current_price=_optional_decimal(
                data.get("current_price"), "current_price"
            ),
            status=_str(data.get("status"), "status"),
            evidence_refs=_refs(data.get("evidence_refs")),
            blockers=[str(item) for item in data.get("blockers") or []],
        )


class PriceBridgeCodec:
    artifact_type = ARTIFACT_PRICE_BRIDGE
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: PriceBridgeResult) -> dict[str, Any]:
        if not isinstance(value, PriceBridgeResult):
            raise TypeError("price_bridge codec requires PriceBridgeResult")
        return _payload(value)

    def from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        dependencies: Mapping[str, Any] | None = None,
    ) -> PriceBridgeResult:
        dependencies = dependencies or {}
        valuation = dependencies.get("valuation")
        if not isinstance(valuation, ValuationResult):
            raise ValueError(
                "price_bridge restore requires a ValuationResult dependency"
            )
        model_validity = dependencies.get("model_validity")
        if model_validity is not None and not isinstance(model_validity, ModelValidity):
            raise ValueError("model_validity dependency has the wrong type")
        return price_bridge_from_payload(
            valuation,
            dict(payload),
            model_validity_payload=(
                json.loads(model_validity.to_json())
                if model_validity is not None
                else None
            ),
        )


class PriceAttractivenessCodec:
    artifact_type = ARTIFACT_PRICE_ATTRACTIVENESS
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(
        self, value: PriceAttractivenessAssessment
    ) -> dict[str, Any]:
        if not isinstance(value, PriceAttractivenessAssessment):
            raise TypeError("price_attractiveness codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> PriceAttractivenessAssessment:
        data = dict(payload)
        return PriceAttractivenessAssessment(
            symbol=_str(data.get("symbol"), "symbol"),
            profile_id=_str(data.get("profile_id"), "profile_id"),
            status=_str(data.get("status"), "status"),
            margin_to_bear=_optional_decimal(
                data.get("margin_to_bear"), "margin_to_bear"
            ),
            margin_to_base=_optional_decimal(
                data.get("margin_to_base"), "margin_to_base"
            ),
            downside_reference=_optional_decimal(
                data.get("downside_reference"), "downside_reference"
            ),
            upside_reference=_optional_decimal(
                data.get("upside_reference"), "upside_reference"
            ),
            confidence=_str(data.get("confidence"), "confidence"),
            reasons=[str(item) for item in data.get("reasons") or []],
            blockers=[str(item) for item in data.get("blockers") or []],
            evidence_refs=_refs(data.get("evidence_refs")),
        )


class CurrentResearchStatusCodec:
    artifact_type = ARTIFACT_CURRENT_RESEARCH_STATUS
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: CurrentResearchStatus) -> dict[str, Any]:
        if not isinstance(value, CurrentResearchStatus):
            raise TypeError("current_research_status codec has the wrong input type")
        return _payload(value)

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> CurrentResearchStatus:
        data = dict(payload)
        current_data = data["current_data_status"]
        attractiveness = data["price_attractiveness"]
        return CurrentResearchStatus(
            symbol=_str(data.get("symbol"), "symbol"),
            research_conclusion=_str(
                data.get("research_conclusion"), "research_conclusion"
            ),
            valuation_status=_str(data.get("valuation_status"), "valuation_status"),
            price_bridge_status=_str(
                data.get("price_bridge_status"), "price_bridge_status"
            ),
            engineering_status=_str(
                data.get("engineering_status"), "engineering_status"
            ),
            current_data_status=CurrentDataStatus(
                status=_str(current_data.get("status"), "current_data.status"),
                waiting_for=[
                    str(item) for item in current_data.get("waiting_for") or []
                ],
                blockers=[
                    str(item) for item in current_data.get("blockers") or []
                ],
                evidence_refs=_refs(current_data.get("evidence_refs")),
            ),
            price_attractiveness=PriceAttractivenessAssessment(
                symbol=_str(attractiveness.get("symbol"), "price.symbol"),
                profile_id=_str(
                    attractiveness.get("profile_id"), "price.profile_id"
                ),
                status=_str(attractiveness.get("status"), "price.status"),
                margin_to_bear=_optional_decimal(
                    attractiveness.get("margin_to_bear"), "price.margin_to_bear"
                ),
                margin_to_base=_optional_decimal(
                    attractiveness.get("margin_to_base"), "price.margin_to_base"
                ),
                downside_reference=_optional_decimal(
                    attractiveness.get("downside_reference"),
                    "price.downside_reference",
                ),
                upside_reference=_optional_decimal(
                    attractiveness.get("upside_reference"), "price.upside_reference"
                ),
                confidence=_str(attractiveness.get("confidence"), "price.confidence"),
                reasons=[
                    str(item) for item in attractiveness.get("reasons") or []
                ],
                blockers=[
                    str(item) for item in attractiveness.get("blockers") or []
                ],
                evidence_refs=_refs(attractiveness.get("evidence_refs")),
            ),
            display_text=_str(data.get("display_text"), "display_text"),
            blockers=[str(item) for item in data.get("blockers") or []],
            evidence_refs=_refs(data.get("evidence_refs")),
        )


def _dividend_record_from_payload(data: Mapping[str, Any]) -> DividendRecord:
    return DividendRecord(
        symbol=_str(data.get("symbol"), "symbol"),
        fiscal_period=_str(data.get("fiscal_period"), "fiscal_period"),
        dividend_type=_str(data.get("dividend_type"), "dividend_type"),
        status=_str(data.get("status"), "status"),
        dividend_per_share=_required_decimal(
            data.get("dividend_per_share"), "dividend_per_share"
        ),
        currency=_str(data.get("currency"), "currency"),
        announcement_date=_optional_date(
            data.get("announcement_date"), "announcement_date"
        ),
        approval_date=_optional_date(data.get("approval_date"), "approval_date"),
        ex_date=_optional_date(data.get("ex_date"), "ex_date"),
        payment_date=_optional_date(data.get("payment_date"), "payment_date"),
        known_at=_required_date(data.get("known_at"), "known_at"),
        share_basis=_str(data.get("share_basis"), "share_basis"),
        evidence_refs=_refs(data.get("evidence_refs")),
        blockers=[str(item) for item in data.get("blockers") or []],
    )


def _required_decimal(value: object, field: str) -> Decimal:
    parsed = _optional_decimal(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _dividend_history_from_payload(data: Mapping[str, Any]) -> DividendHistory:
    return DividendHistory(
        symbol=_str(data.get("symbol"), "symbol"),
        records=tuple(
            _dividend_record_from_payload(item)
            for item in data.get("records") or []
        ),
        as_of=_required_date(data.get("as_of"), "as_of"),
        evidence_refs=_refs(data.get("evidence_refs")),
        status=_str(data.get("status"), "status"),
        blockers=[str(item) for item in data.get("blockers") or []],
    )


def _capacity_from_payload(data: Mapping[str, Any]) -> DistributionCapacity:
    return DistributionCapacity(
        symbol=_str(data.get("symbol"), "symbol"),
        profile_id=_str(data.get("profile_id"), "profile_id"),
        as_of=_required_date(data.get("as_of"), "as_of"),
        earnings_basis=_decimal_dict(data.get("earnings_basis"), "earnings_basis"),
        cash_flow_basis=_decimal_dict(data.get("cash_flow_basis"), "cash_flow_basis"),
        maintenance_reinvestment=_decimal_dict(
            data.get("maintenance_reinvestment"), "maintenance_reinvestment"
        ),
        debt_constraints=_decimal_dict(data.get("debt_constraints"), "debt_constraints"),
        restricted_cash_or_upstream_constraints=_decimal_dict(
            data.get("restricted_cash_or_upstream_constraints"),
            "restricted_cash_or_upstream_constraints",
        ),
        capital_allocation_context=dict(
            data.get("capital_allocation_context") or {}
        ),
        bear_capacity=_optional_decimal(
            data.get("bear_capacity"), "bear_capacity"
        ),
        base_capacity=_optional_decimal(
            data.get("base_capacity"), "base_capacity"
        ),
        bull_capacity=_optional_decimal(
            data.get("bull_capacity"), "bull_capacity"
        ),
        confidence=_str(data.get("confidence"), "confidence"),
        evidence_refs=_refs(data.get("evidence_refs")),
        blockers=[str(item) for item in data.get("blockers") or []],
        status=_str(data.get("status"), "status"),
    )


def _sustainability_from_payload(
    data: Mapping[str, Any],
) -> DividendSustainabilityAssessment:
    return DividendSustainabilityAssessment(
        symbol=_str(data.get("symbol"), "symbol"),
        profile_id=_str(data.get("profile_id"), "profile_id"),
        as_of=_required_date(data.get("as_of"), "as_of"),
        status=_str(data.get("status"), "status"),
        coverage_context=_optional_str(
            data.get("coverage_context"), "coverage_context"
        ),
        capital_requirements=_optional_str(
            data.get("capital_requirements"), "capital_requirements"
        ),
        balance_sheet_pressure=_optional_str(
            data.get("balance_sheet_pressure"), "balance_sheet_pressure"
        ),
        cycle_risk=_optional_str(data.get("cycle_risk"), "cycle_risk"),
        growth_source=_optional_str(data.get("growth_source"), "growth_source"),
        breakers=list(data.get("breakers") or []),
        confidence=_str(data.get("confidence"), "confidence"),
        reasons=[str(item) for item in data.get("reasons") or []],
        blockers=[str(item) for item in data.get("blockers") or []],
        evidence_refs=_refs(data.get("evidence_refs")),
    )


def _yield_snapshot_from_payload(
    data: Mapping[str, Any],
) -> DividendYieldSnapshot:
    return DividendYieldSnapshot(
        symbol=_str(data.get("symbol"), "symbol"),
        basis_type=_str(data.get("basis_type"), "basis_type"),
        dividend_basis_period=_str(
            data.get("dividend_basis_period"), "dividend_basis_period"
        ),
        dividend_per_share=_optional_decimal(
            data.get("dividend_per_share"), "dividend_per_share"
        ),
        dividend_known_at=_optional_date(
            data.get("dividend_known_at"), "dividend_known_at"
        ),
        quote_date=_optional_date(data.get("quote_date"), "quote_date"),
        current_price=_optional_decimal(data.get("current_price"), "current_price"),
        currency=_str(data.get("currency"), "currency"),
        share_basis=_str(data.get("share_basis"), "share_basis"),
        dividend_yield=_optional_decimal(
            data.get("dividend_yield"), "dividend_yield"
        ),
        yield_type=_str(data.get("yield_type"), "yield_type"),
        evidence_refs=_refs(data.get("evidence_refs")),
        status=_str(data.get("status"), "status"),
        blockers=[str(item) for item in data.get("blockers") or []],
    )


class DividendResearchCodec:
    artifact_type = ARTIFACT_DIVIDEND_RESEARCH
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: DividendResearchResult) -> dict[str, Any]:
        if not isinstance(value, DividendResearchResult):
            raise TypeError("dividend_research codec has the wrong input type")
        return _payload(value)

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> DividendResearchResult:
        data = dict(payload)
        return DividendResearchResult(
            symbol=_str(data.get("symbol"), "symbol"),
            profile_id=_str(data.get("profile_id"), "profile_id"),
            history=(
                _dividend_history_from_payload(data["history"])
                if data.get("history") is not None
                else None
            ),
            capacity=(
                _capacity_from_payload(data["capacity"])
                if data.get("capacity") is not None
                else None
            ),
            sustainability=(
                _sustainability_from_payload(data["sustainability"])
                if data.get("sustainability") is not None
                else None
            ),
            yield_snapshots=tuple(
                _yield_snapshot_from_payload(item)
                for item in data.get("yield_snapshots") or []
            ),
            as_of=_required_date(data.get("as_of"), "as_of"),
            blockers=[str(item) for item in data.get("blockers") or []],
            evidence_refs=_refs(data.get("evidence_refs")),
            action=_str(data.get("action", "no_order"), "action"),
        )


def _company_admission_from_payload(
    data: Mapping[str, Any],
) -> FixedSampleCompanyAdmission:
    cash_return_data = data.get("cash_return_research")
    cash_return_result = (
        DividendResearchCodec().from_payload(cash_return_data)
        if cash_return_data is not None
        else None
    )
    return FixedSampleCompanyAdmission(
        symbol=_str(data.get("symbol"), "symbol"),
        profile_id=_str(data.get("profile_id"), "profile_id"),
        engineering_contract_reusable=bool(
            data.get("engineering_contract_reusable")
        ),
        research_sample_status=_str(
            data.get("research_sample_status"), "research_sample_status"
        ),
        admission_evidence=[
            str(item) for item in data.get("admission_evidence") or []
        ],
        production_valuation_status=_str(
            data.get("production_valuation_status"), "production_valuation_status"
        ),
        bounded_value_judgment=_str(
            data.get("bounded_value_judgment"), "bounded_value_judgment"
        ),
        cash_return_status=_str(
            data.get("cash_return_status"), "cash_return_status"
        ),
        cash_return_explanation=str(data.get("cash_return_explanation") or ""),
        decision=_str(data.get("decision"), "decision"),
        decision_reason=_str(data.get("decision_reason"), "decision_reason"),
        required_evidence=[
            str(item) for item in data.get("required_evidence") or []
        ],
        blockers=[str(item) for item in data.get("blockers") or []],
        evidence_refs=_refs(data.get("evidence_refs")),
        human_confirmation_required=True,
        action="no_order",
        cash_return_result=cash_return_result,
    )


class FixedSampleAdmissionCodec:
    artifact_type = ARTIFACT_FIXED_SAMPLE_ADMISSION
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: FixedSampleAdmissionReview) -> dict[str, Any]:
        if not isinstance(value, FixedSampleAdmissionReview):
            raise TypeError("fixed_sample_admission codec has the wrong input type")
        return _payload(value)

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> FixedSampleAdmissionReview:
        data = dict(payload)
        return FixedSampleAdmissionReview(
            protocol_version=_str(
                data.get("protocol_version"), "protocol_version"
            ),
            rule_version=_str(data.get("rule_version"), "rule_version"),
            as_of=_required_date(data.get("as_of"), "as_of"),
            engineering_orchestration_status=_str(
                data.get("engineering_orchestration_status"),
                "engineering_orchestration_status",
            ),
            production_valuation_available=bool(
                data.get("production_valuation_available")
            ),
            research_sample_members=tuple(
                str(item) for item in data.get("research_sample_members") or []
            ),
            companies=tuple(
                _company_admission_from_payload(item)
                for item in data.get("companies") or []
            ),
            blockers=[str(item) for item in data.get("blockers") or []],
            evidence_refs=_refs(data.get("evidence_refs")),
            human_confirmation_required=True,
            action="no_order",
            interpretation=_str(data.get("interpretation"), "interpretation"),
        )


class DecisionEvidenceBundleCodec:
    artifact_type = ARTIFACT_DECISION_EVIDENCE_BUNDLE
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: DecisionEvidenceBundle) -> dict[str, Any]:
        if not isinstance(value, DecisionEvidenceBundle):
            raise TypeError("decision_evidence_bundle codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> DecisionEvidenceBundle:
        return decision_evidence_bundle_from_payload(payload)


class MinimalPortfolioPreconditionsCodec:
    artifact_type = ARTIFACT_MINIMAL_PORTFOLIO_PRECONDITIONS
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: MinimalPortfolioPreconditions) -> dict[str, Any]:
        if not isinstance(value, MinimalPortfolioPreconditions):
            raise TypeError("minimal_portfolio_preconditions codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> MinimalPortfolioPreconditions:
        return minimal_portfolio_preconditions_from_payload(payload)


class InvestmentDecisionReviewCodec:
    artifact_type = ARTIFACT_INVESTMENT_DECISION_REVIEW
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: InvestmentDecisionReview) -> dict[str, Any]:
        if not isinstance(value, InvestmentDecisionReview):
            raise TypeError("investment_decision_review codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> InvestmentDecisionReview:
        return investment_decision_review_from_payload(payload)


class EntryThesisSnapshotCodec:
    artifact_type = ARTIFACT_ENTRY_THESIS_SNAPSHOT
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: EntryThesisSnapshot) -> dict[str, Any]:
        if not isinstance(value, EntryThesisSnapshot):
            raise TypeError("entry_thesis_snapshot codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> EntryThesisSnapshot:
        return entry_thesis_snapshot_from_payload(payload)


class DecisionJournalEntryCodec:
    artifact_type = ARTIFACT_DECISION_JOURNAL_ENTRY
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: DecisionJournalEntry) -> dict[str, Any]:
        if not isinstance(value, DecisionJournalEntry):
            raise TypeError("decision_journal_entry codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> DecisionJournalEntry:
        return decision_journal_entry_from_payload(payload)


class InvestmentConsistencyReviewCodec:
    artifact_type = ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW
    schema_version = ARTIFACT_SCHEMA_VERSION

    def to_payload(self, value: InvestmentConsistencyReview) -> dict[str, Any]:
        if not isinstance(value, InvestmentConsistencyReview):
            raise TypeError("investment_consistency_review codec has the wrong input type")
        return value.as_policy()

    def from_payload(
        self, payload: Mapping[str, Any], **_: Any
    ) -> InvestmentConsistencyReview:
        return investment_consistency_review_from_payload(payload)


CODECS: dict[str, ArtifactCodec] = {
    codec.artifact_type: codec
    for codec in (
        ResearchCaseCodec(),
        ResearchGateCodec(),
        ValuationAssumptionSetCodec(),
        ValuationResultCodec(),
        ModelValidityCodec(),
        QuoteSnapshotCodec(),
        PriceBridgeCodec(),
        PriceAttractivenessCodec(),
        CurrentResearchStatusCodec(),
        DividendResearchCodec(),
        FixedSampleAdmissionCodec(),
        DecisionEvidenceBundleCodec(),
        MinimalPortfolioPreconditionsCodec(),
        InvestmentDecisionReviewCodec(),
        EntryThesisSnapshotCodec(),
        DecisionJournalEntryCodec(),
        InvestmentConsistencyReviewCodec(),
    )
}


def get_codec(artifact_type: str) -> ArtifactCodec:
    try:
        return CODECS[artifact_type]
    except KeyError as error:
        raise ValueError(f"Unsupported research artifact type: {artifact_type}") from error


def artifact_payload(value: Any) -> tuple[str, dict[str, Any]]:
    """Return (artifact_type, canonical-compatible payload) for a domain object."""
    for artifact_type, codec in CODECS.items():
        try:
            return artifact_type, codec.to_payload(value)
        except TypeError:
            continue
    raise TypeError(f"No research artifact codec accepts {type(value).__name__}")


def decode_artifact(
    artifact_type: str,
    payload: Mapping[str, Any],
    *,
    dependencies: Mapping[str, Any] | None = None,
) -> Any:
    return get_codec(artifact_type).from_payload(
        dict(payload), dependencies=dependencies
    )


@dataclass(frozen=True)
class TypedArtifactRoundTrip:
    artifact_type: str
    schema_version: str
    original_payload: dict[str, Any]
    restored_object: Any
    restored_payload: dict[str, Any]

    @property
    def semantically_equal(self) -> bool:
        return self.original_payload == self.restored_payload
