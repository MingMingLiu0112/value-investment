"""Versioned fixed-sample input descriptor to typed research run adapter.

The descriptor keeps source provenance, dependency versions and distinct
point-in-time dates together with every domain object consumed by the shared
research application. It never chooses a model from a stock symbol and never
creates an execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any, Mapping, Sequence

from .distribution import DividendResearchResult
from .event_scan import event_scan_from_payload
from .model_validity import MaterialEvent, model_validity_from_payload
from .quote_snapshot import QuoteSnapshot
from .research_application import (
    ModelValidityEvaluationInput,
    ResearchRunSpec,
)
from .research_artifact_codecs import (
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    artifact_payload,
    decode_artifact,
)
from .research_case import ResearchCase
from .research_profile import PROFILES
from .research_run_contract import (
    INPUT_DESCRIPTOR_SCHEMA,
    AssumptionScenarioBinding,
    ResearchDependencyFingerprint,
    ResearchPitFrame,
    ResearchSourceDescriptor,
    ResearchValuationApproval,
    canonical_contract_payload,
    validate_assumption_bindings,
)
from .scenario_valuation import BridgeItem, ForecastYear, Terminal
from .valuation_assumptions import ValuationAssumptionSet
from .valuation_confidence import ConfidenceEvidence
from .valuation_models.cyclical import CyclicalFacts
from .valuation_models.fcff import FCFFScenarioInputs, FinancialFacts
from .valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)
from .valuation_router import route_profile


_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Input descriptor decimals must be finite")
        return str(value)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Input descriptor timestamps must include timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(value.__dict__)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported input descriptor value: {type(value).__name__}")


def _decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return number


def _optional_decimal(value: object, field: str) -> Decimal | None:
    return None if value is None else _decimal(value, field)


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _refs(value: object, field: str = "evidence_refs") -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = [dict(item) for item in value]
    if any(not ref.get("id") for ref in result):
        raise ValueError(f"{field} entries require ids")
    return result


def _confidence_payload(value: ConfidenceEvidence | None) -> dict[str, Any] | None:
    return None if value is None else _jsonable(value)


def _confidence_from_payload(value: object) -> ConfidenceEvidence | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("confidence_evidence must be an object")
    data = dict(value)
    return ConfidenceEvidence(
        data_completeness=_decimal(data["data_completeness"], "data_completeness"),
        business_stability=_string(data["business_stability"], "business_stability"),
        parameter_sensitivity=_string(
            data["parameter_sensitivity"], "parameter_sensitivity"
        ),
        cyclicality=_string(data["cyclicality"], "cyclicality"),
        forecast_horizon_years=int(data["forecast_horizon_years"]),
        terminal_value_share=_optional_decimal(
            data.get("terminal_value_share"), "terminal_value_share"
        ),
        cross_check_disagreement=_optional_decimal(
            data.get("cross_check_disagreement"), "cross_check_disagreement"
        ),
        evidence_refs=_refs(data.get("evidence_refs")),
    )


def _residual_scenario_payload(value: ResidualIncomeScenarioInputs) -> dict[str, Any]:
    return {
        "cost_of_equity": str(value.cost_of_equity),
        "forecast_roes": [str(item) for item in value.forecast_roes],
        "terminal_roe": str(value.terminal_roe),
        "terminal_growth": str(value.terminal_growth),
        "retention": str(value.retention),
    }


def _residual_scenario_from_payload(
    value: Mapping[str, Any],
) -> ResidualIncomeScenarioInputs:
    return ResidualIncomeScenarioInputs(
        cost_of_equity=_decimal(value["cost_of_equity"], "cost_of_equity"),
        forecast_roes=tuple(
            _decimal(item, "forecast_roes") for item in value["forecast_roes"]
        ),
        terminal_roe=_decimal(value["terminal_roe"], "terminal_roe"),
        terminal_growth=_decimal(value["terminal_growth"], "terminal_growth"),
        retention=_decimal(value.get("retention", "0.30"), "retention"),
    )


def _fcff_scenario_payload(value: FCFFScenarioInputs) -> dict[str, Any]:
    return {
        "forecast": [
            {
                "year": item.year,
                "ebit": str(item.ebit),
                "cash_tax_rate": str(item.cash_tax_rate),
                "depreciation": str(item.depreciation),
                "capex": str(item.capex),
                "working_capital_increase": str(item.working_capital_increase),
                "wacc": str(item.wacc),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in value.forecast
        ],
        "terminal": {
            "next_year_nopat": str(value.terminal.next_year_nopat),
            "growth": str(value.terminal.growth),
            "roic": str(value.terminal.roic),
            "wacc": str(value.terminal.wacc),
            "evidence_refs": list(value.terminal.evidence_refs),
        },
        "bridge": [
            {
                "name": item.name,
                "kind": item.kind,
                "value": str(item.value),
                "exposure_ids": list(item.exposure_ids),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in value.bridge
        ],
        "operating_exposure_ids": list(value.operating_exposure_ids),
        "ordinary_shares": str(value.ordinary_shares),
        "share_evidence_refs": list(value.share_evidence_refs),
        "currency": value.currency,
        "valuation_date": (
            value.valuation_date.isoformat() if value.valuation_date else None
        ),
        "cash_flow_dates": [
            item.isoformat() for item in value.cash_flow_dates or ()
        ],
        "timing_evidence_refs": list(value.timing_evidence_refs),
    }


def _fcff_scenario_from_payload(
    value: Mapping[str, Any],
) -> FCFFScenarioInputs:
    terminal = value["terminal"]
    return FCFFScenarioInputs(
        forecast=tuple(
            ForecastYear(
                year=int(item["year"]),
                ebit=_decimal(item["ebit"], "forecast.ebit"),
                cash_tax_rate=_decimal(
                    item["cash_tax_rate"], "forecast.cash_tax_rate"
                ),
                depreciation=_decimal(item["depreciation"], "forecast.depreciation"),
                capex=_decimal(item["capex"], "forecast.capex"),
                working_capital_increase=_decimal(
                    item["working_capital_increase"],
                    "forecast.working_capital_increase",
                ),
                wacc=_decimal(item["wacc"], "forecast.wacc"),
                evidence_refs=tuple(str(ref) for ref in item["evidence_refs"]),
            )
            for item in value["forecast"]
        ),
        terminal=Terminal(
            next_year_nopat=_decimal(
                terminal["next_year_nopat"], "terminal.next_year_nopat"
            ),
            growth=_decimal(terminal["growth"], "terminal.growth"),
            roic=_decimal(terminal["roic"], "terminal.roic"),
            wacc=_decimal(terminal["wacc"], "terminal.wacc"),
            evidence_refs=tuple(str(ref) for ref in terminal["evidence_refs"]),
        ),
        bridge=tuple(
            BridgeItem(
                name=_string(item["name"], "bridge.name"),
                kind=_string(item["kind"], "bridge.kind"),
                value=_decimal(item["value"], "bridge.value"),
                exposure_ids=tuple(str(ref) for ref in item["exposure_ids"]),
                evidence_refs=tuple(str(ref) for ref in item["evidence_refs"]),
            )
            for item in value["bridge"]
        ),
        operating_exposure_ids=tuple(
            str(ref) for ref in value["operating_exposure_ids"]
        ),
        ordinary_shares=_decimal(value["ordinary_shares"], "ordinary_shares"),
        share_evidence_refs=tuple(
            str(ref) for ref in value["share_evidence_refs"]
        ),
        currency=_string(value.get("currency", "CNY"), "currency"),
        valuation_date=(
            _date(value["valuation_date"], "valuation_date")
            if value.get("valuation_date") else None
        ),
        cash_flow_dates=(
            tuple(_date(item, "cash_flow_dates") for item in value["cash_flow_dates"])
            if value.get("cash_flow_dates") else None
        ),
        timing_evidence_refs=tuple(
            str(ref) for ref in value.get("timing_evidence_refs") or []
        ),
    )


def facts_to_payload(facts: Any) -> dict[str, Any]:
    if isinstance(facts, QualityCompounderFacts):
        return {
            "facts_type": "quality_compounder",
            "symbol": facts.symbol,
            "as_of": facts.as_of.isoformat(),
            "verified": facts.verified,
            "confidence": facts.confidence,
            "evidence_refs": [dict(ref) for ref in facts.evidence_refs],
            "blockers": list(facts.blockers),
            "operating_inputs": _jsonable(facts.operating_inputs),
            "scenario_inputs": (
                {
                    name: _residual_scenario_payload(item)
                    for name, item in facts.scenario_inputs.items()
                }
                if facts.scenario_inputs is not None else None
            ),
            "confidence_evidence": _confidence_payload(facts.confidence_evidence),
        }
    if isinstance(facts, FinancialFacts):
        return {
            "facts_type": "fcff",
            "symbol": facts.symbol,
            "as_of": facts.as_of.isoformat(),
            "verified": facts.verified,
            "confidence": facts.confidence,
            "evidence_refs": [dict(ref) for ref in facts.evidence_refs],
            "blockers": list(facts.blockers),
            "operating_inputs": _jsonable(facts.operating_inputs),
            "scenario_inputs": (
                {
                    name: _fcff_scenario_payload(item)
                    for name, item in facts.scenario_inputs.items()
                }
                if facts.scenario_inputs is not None else None
            ),
            "confidence_evidence": _confidence_payload(facts.confidence_evidence),
        }
    if isinstance(facts, CyclicalFacts):
        return {
            "facts_type": "cyclical",
            "symbol": facts.symbol,
            "as_of": facts.as_of.isoformat(),
            "verified": facts.verified,
            "confidence": facts.confidence,
            "evidence_refs": [dict(ref) for ref in facts.evidence_refs],
            "blockers": list(facts.blockers),
            "operating_inputs": _jsonable(facts.operating_inputs),
            "confidence_evidence": _confidence_payload(facts.confidence_evidence),
        }
    raise TypeError(f"Unsupported research facts type: {type(facts).__name__}")


def facts_from_payload(payload: Mapping[str, Any]) -> Any:
    data = dict(payload)
    facts_type = _string(data.get("facts_type"), "facts_type")
    symbol = _string(data.get("symbol"), "facts.symbol")
    as_of = _date(data.get("as_of"), "facts.as_of")
    verified = bool(data.get("verified"))
    evidence_refs = _refs(data.get("evidence_refs"))
    blockers = [str(item) for item in data.get("blockers") or []]
    operating_inputs = {
        str(key): _optional_decimal(item, f"operating_inputs.{key}")
        for key, item in (data.get("operating_inputs") or {}).items()
    }
    confidence_evidence = _confidence_from_payload(data.get("confidence_evidence"))
    if facts_type == "quality_compounder":
        scenarios = data.get("scenario_inputs")
        return QualityCompounderFacts(
            symbol=symbol,
            as_of=as_of,
            verified=verified,
            confidence=_string(data.get("confidence"), "facts.confidence"),
            evidence_refs=evidence_refs,
            blockers=blockers,
            operating_inputs=operating_inputs,
            scenario_inputs=(
                {
                    str(name): _residual_scenario_from_payload(item)
                    for name, item in scenarios.items()
                }
                if scenarios is not None else None
            ),
            confidence_evidence=confidence_evidence,
        )
    if facts_type == "fcff":
        scenarios = data.get("scenario_inputs")
        return FinancialFacts(
            symbol=symbol,
            as_of=as_of,
            verified=verified,
            evidence_refs=evidence_refs,
            blockers=blockers,
            operating_inputs=operating_inputs,
            scenario_inputs=(
                {
                    str(name): _fcff_scenario_from_payload(item)
                    for name, item in scenarios.items()
                }
                if scenarios is not None else None
            ),
            confidence=_string(data.get("confidence", "低"), "facts.confidence"),
            confidence_evidence=confidence_evidence,
        )
    if facts_type == "cyclical":
        return CyclicalFacts(
            symbol=symbol,
            as_of=as_of,
            verified=verified,
            confidence=_string(data.get("confidence"), "facts.confidence"),
            evidence_refs=evidence_refs,
            blockers=blockers,
            operating_inputs=operating_inputs,
            confidence_evidence=confidence_evidence,
        )
    raise ValueError(f"Unknown research facts type: {facts_type}")


def _validity_payload(value: ModelValidityEvaluationInput | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "model_id": value.model_id,
        "valid_from": value.valid_from.isoformat(),
        "events": [
            {
                "event_date": item.event_date.isoformat(),
                "kind": item.kind,
                "description": item.description,
                "evidence_refs": [dict(ref) for ref in item.evidence_refs],
                "material": item.material,
            }
            for item in value.events
        ],
        "event_scan_evidence_refs": [
            dict(ref) for ref in value.event_scan_evidence_refs
        ],
        "event_scan": (
            value.event_scan.as_policy()
            if value.event_scan is not None else None
        ),
        "blockers": list(value.blockers),
    }


def _validity_from_payload(value: object) -> ModelValidityEvaluationInput | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("model_validity_input must be an object")
    data = dict(value)
    return ModelValidityEvaluationInput(
        model_id=_string(data.get("model_id"), "model_id"),
        valid_from=_date(data.get("valid_from"), "valid_from"),
        events=tuple(
            MaterialEvent(
                event_date=_date(item["event_date"], "event_date"),
                kind=_string(item["kind"], "event.kind"),
                description=_string(item["description"], "event.description"),
                evidence_refs=[dict(ref) for ref in item["evidence_refs"]],
                material=bool(item.get("material", True)),
            )
            for item in data.get("events") or []
        ),
        event_scan_evidence_refs=tuple(
            dict(ref) for ref in data.get("event_scan_evidence_refs") or []
        ),
        event_scan=(
            event_scan_from_payload(data["event_scan"])
            if data.get("event_scan") else None
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or []),
    )


def _source_from_payload(value: object) -> ResearchSourceDescriptor:
    if not isinstance(value, Mapping):
        raise ValueError("input source must be an object")
    data = dict(value)
    return ResearchSourceDescriptor(
        id=_string(data.get("id"), "source.id"),
        kind=_string(data.get("kind"), "source.kind"),
        location=_string(data.get("location"), "source.location"),
        sha256=_string(data.get("sha256"), "source.sha256"),
        published_at=(
            _datetime(data["published_at"], "source.published_at")
            if data.get("published_at") else None
        ),
        retrieved_at=(
            _datetime(data["retrieved_at"], "source.retrieved_at")
            if data.get("retrieved_at") else None
        ),
        parser_version=(
            _string(data["parser_version"], "source.parser_version")
            if data.get("parser_version") else None
        ),
    )


def _valuation_approval_payload(
    value: ResearchValuationApproval | None,
) -> dict[str, Any] | None:
    return None if value is None else value.as_policy()


def _valuation_approval_from_payload(
    value: object,
) -> ResearchValuationApproval | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("valuation_approval must be an object")
    data = dict(value)
    return ResearchValuationApproval(
        model_id=_string(data.get("model_id"), "valuation_approval.model_id"),
        model_type=_string(
            data.get("model_type"),
            "valuation_approval.model_type",
        ),
        model_version=_string(
            data.get("model_version"),
            "valuation_approval.model_version",
        ),
        valuation_date=_date(
            data.get("valuation_date"),
            "valuation_approval.valuation_date",
        ),
        result_sha256=_string(
            data.get("result_sha256"),
            "valuation_approval.result_sha256",
        ),
        approved_at=_datetime(
            data.get("approved_at"),
            "valuation_approval.approved_at",
        ),
        approver=_string(
            data.get("approver"),
            "valuation_approval.approver",
        ),
        evidence_refs=tuple(
            dict(ref)
            for ref in data.get("evidence_refs") or []
        ),
    )


def _pit_from_payload(value: object) -> ResearchPitFrame:
    if not isinstance(value, Mapping):
        raise ValueError("point_in_time must be an object")
    data = dict(value)
    return ResearchPitFrame(
        report_period=_date(data["report_period"], "report_period"),
        research_as_of=_date(data["research_as_of"], "research_as_of"),
        valuation_date=_date(data["valuation_date"], "valuation_date"),
        available_at=_datetime(data["available_at"], "available_at"),
        computed_at=_datetime(data["computed_at"], "computed_at"),
    )


def _dependency_from_payload(value: object) -> ResearchDependencyFingerprint:
    if not isinstance(value, Mapping):
        raise ValueError("dependencies must be an object")
    data = dict(value)
    return ResearchDependencyFingerprint(
        rule_version=_string(data["rule_version"], "rule_version"),
        profile_id=_string(data["profile_id"], "profile_id"),
        model_id=_string(data["model_id"], "model_id"),
        model_version=_string(data["model_version"], "model_version"),
        parser_version=(
            _string(data["parser_version"], "parser_version")
            if data.get("parser_version") else None
        ),
        scan_watermark=(
            _string(data["scan_watermark"], "scan_watermark")
            if data.get("scan_watermark") else None
        ),
    )


def _binding_from_payload(value: object) -> AssumptionScenarioBinding:
    if not isinstance(value, Mapping):
        raise ValueError("assumption_bindings entries must be objects")
    data = dict(value)
    return AssumptionScenarioBinding(
        assumption_name=_string(
            data.get("assumption_name"), "assumption_name"
        ),
        scenario=_string(data.get("scenario"), "scenario"),
        field_path=_string(data.get("field_path"), "field_path"),
        expected_value=data["expected_value"],
        evidence_refs=tuple(dict(ref) for ref in data.get("evidence_refs") or []),
    )


def _decode_artifact_value(
    artifact_type: str,
    value: object,
) -> Any | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{artifact_type} must be an object")
    return decode_artifact(artifact_type, dict(value))


@dataclass(frozen=True)
class ResearchInputDescriptor:
    """One hash-verifiable point-in-time input set for a fixed-sample company."""

    schema_version: str
    descriptor_version: str
    symbol: str
    name: str
    profile_id: str
    requested_model: str | None
    run_id: str
    point_in_time: ResearchPitFrame
    dependencies: ResearchDependencyFingerprint
    sources: tuple[ResearchSourceDescriptor, ...]
    research_case: ResearchCase
    facts: Any
    assumptions: ValuationAssumptionSet | None
    assumption_bindings: tuple[AssumptionScenarioBinding, ...]
    distribution_result: DividendResearchResult | None
    quote: QuoteSnapshot | None
    model_validity_input: ModelValidityEvaluationInput | None
    valuation_approval: ResearchValuationApproval | None
    blockers: tuple[str, ...] = ()
    input_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != INPUT_DESCRIPTOR_SCHEMA:
            raise ValueError("Unknown research input descriptor schema")
        for field in ("descriptor_version", "name", "run_id"):
            if not getattr(self, field).strip():
                raise ValueError(f"Research input descriptor {field} is required")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Research input descriptor symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError(f"Unknown descriptor profile: {self.profile_id}")
        if self.dependencies.profile_id != self.profile_id:
            raise ValueError("Descriptor dependency profile does not match")
        route = route_profile(self.profile_id, self.requested_model)
        if route.status != "SUPPORTED":
            raise ValueError("Descriptor model route must be supported")
        if self.dependencies.model_id != route.selected_model:
            raise ValueError("Descriptor model id does not match the profile route")
        source_ids = [source.id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Descriptor source ids must be unique")
        if self.research_case.symbol != self.symbol:
            raise ValueError("Descriptor research case symbol does not match")
        if self.research_case.as_of != self.point_in_time.research_as_of:
            raise ValueError("Descriptor research case as-of does not match PIT")
        facts_as_of = getattr(self.facts, "as_of", None)
        if not isinstance(facts_as_of, date):
            raise ValueError("Descriptor facts require a typed as_of date")
        if facts_as_of != self.point_in_time.valuation_date:
            raise ValueError("Descriptor facts date does not match valuation date")
        if getattr(self.facts, "symbol", None) != self.symbol:
            raise ValueError("Descriptor facts symbol does not match")
        if self.assumptions is not None:
            if self.assumptions.symbol != self.symbol:
                raise ValueError("Descriptor assumption symbol does not match")
            if self.assumptions.profile_id != self.profile_id:
                raise ValueError("Descriptor assumption profile does not match")
            if self.assumptions.model_type != route.model_type:
                raise ValueError("Descriptor assumption model type does not match route")
            if self.assumptions.as_of != facts_as_of:
                raise ValueError("Descriptor assumption as-of does not match facts")
        if self.valuation_approval is not None:
            if self.valuation_approval.model_id != route.selected_model:
                raise ValueError(
                    "Descriptor valuation approval model does not match route"
                )
            if self.valuation_approval.model_type != route.model_type:
                raise ValueError(
                    "Descriptor valuation approval type does not match route"
                )
            if self.valuation_approval.valuation_date != facts_as_of:
                raise ValueError(
                    "Descriptor valuation approval date does not match facts"
                )
            if self.valuation_approval.approved_at > self.point_in_time.computed_at:
                raise ValueError(
                    "Descriptor valuation approval follows computation"
                )
        binding_blockers = validate_assumption_bindings(
            self.facts,
            self.assumption_bindings,
        )
        if binding_blockers:
            raise ValueError("Descriptor assumption binding is invalid: " + ", ".join(binding_blockers))
        for source in self.sources:
            if source.published_at is not None and source.published_at > self.point_in_time.available_at:
                raise ValueError("Descriptor source is published after availability")
            if source.retrieved_at is not None and source.retrieved_at > self.point_in_time.available_at:
                raise ValueError("Descriptor source is retrieved after availability")
        if self.input_sha256 is not None:
            if not _SHA256.fullmatch(self.input_sha256):
                raise ValueError("Descriptor hash must be SHA-256 hex")
            if self.input_sha256 != descriptor_sha256(self):
                raise ValueError("Descriptor hash does not match its payload")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "descriptor_version": self.descriptor_version,
            "symbol": self.symbol,
            "name": self.name,
            "profile_id": self.profile_id,
            "requested_model": self.requested_model,
            "run_id": self.run_id,
            "point_in_time": self.point_in_time.as_policy(),
            "dependencies": self.dependencies.as_policy(),
            "sources": [source.as_policy() for source in self.sources],
            "research_case": _artifact_payload_value(self.research_case),
            "facts": facts_to_payload(self.facts),
            "assumptions": _artifact_payload_value(self.assumptions),
            "assumption_bindings": [
                binding.as_policy() for binding in self.assumption_bindings
            ],
            "distribution_result": _artifact_payload_value(
                self.distribution_result
            ),
            "quote": _artifact_payload_value(self.quote),
            "model_validity_input": _validity_payload(self.model_validity_input),
            "valuation_approval": _valuation_approval_payload(
                self.valuation_approval
            ),
            "blockers": list(self.blockers),
            "input_sha256": self.input_sha256,
        }


def _artifact_payload_value(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    _, payload = artifact_payload(value)
    return payload


def descriptor_sha256(descriptor: ResearchInputDescriptor) -> str:
    payload = descriptor.as_policy()
    payload.pop("input_sha256", None)
    return hashlib.sha256(
        canonical_contract_payload(payload).encode("utf-8")
    ).hexdigest()


def finalize_input_descriptor(
    descriptor: ResearchInputDescriptor,
) -> ResearchInputDescriptor:
    object.__setattr__(descriptor, "input_sha256", descriptor_sha256(descriptor))
    return descriptor


def descriptor_from_payload(payload: Mapping[str, Any]) -> ResearchInputDescriptor:
    data = dict(payload)
    descriptor = ResearchInputDescriptor(
        schema_version=_string(data.get("schema_version"), "schema_version"),
        descriptor_version=_string(
            data.get("descriptor_version"), "descriptor_version"
        ),
        symbol=_string(data.get("symbol"), "symbol"),
        name=_string(data.get("name"), "name"),
        profile_id=_string(data.get("profile_id"), "profile_id"),
        requested_model=(
            _string(data["requested_model"], "requested_model")
            if data.get("requested_model") else None
        ),
        run_id=_string(data.get("run_id"), "run_id"),
        point_in_time=_pit_from_payload(data.get("point_in_time")),
        dependencies=_dependency_from_payload(data.get("dependencies")),
        sources=tuple(
            _source_from_payload(item) for item in data.get("sources") or []
        ),
        research_case=_decode_artifact_value(
            ARTIFACT_RESEARCH_CASE, data.get("research_case")
        ),
        facts=facts_from_payload(data.get("facts")),
        assumptions=_decode_artifact_value(
            ARTIFACT_VALUATION_ASSUMPTIONS, data.get("assumptions")
        ),
        assumption_bindings=tuple(
            _binding_from_payload(item)
            for item in data.get("assumption_bindings") or []
        ),
        distribution_result=_decode_artifact_value(
            ARTIFACT_DIVIDEND_RESEARCH, data.get("distribution_result")
        ),
        quote=_decode_artifact_value(
            ARTIFACT_QUOTE_SNAPSHOT, data.get("quote")
        ),
        model_validity_input=_validity_from_payload(
            data.get("model_validity_input")
        ),
        valuation_approval=_valuation_approval_from_payload(
            data.get("valuation_approval")
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or []),
        input_sha256=(
            str(data["input_sha256"]) if data.get("input_sha256") else None
        ),
    )
    if descriptor.input_sha256 is None:
        return finalize_input_descriptor(descriptor)
    return descriptor


def build_research_run_spec(
    descriptor: ResearchInputDescriptor,
    *,
    run_id: str | None = None,
) -> ResearchRunSpec:
    if not isinstance(descriptor, ResearchInputDescriptor):
        raise TypeError("Research input adapter requires a typed descriptor")
    return ResearchRunSpec(
        run_id=run_id or descriptor.run_id,
        symbol=descriptor.symbol,
        profile_id=descriptor.profile_id,
        research_case=descriptor.research_case,
        facts=descriptor.facts,
        requested_model=descriptor.requested_model,
        assumptions=descriptor.assumptions,
        quote=descriptor.quote,
        model_validity_input=descriptor.model_validity_input,
        valuation_approval=descriptor.valuation_approval,
        distribution_result=descriptor.distribution_result,
        as_of=descriptor.point_in_time.research_as_of,
        available_at=descriptor.point_in_time.available_at,
        report_period=descriptor.point_in_time.report_period,
        valuation_date=descriptor.point_in_time.valuation_date,
        computed_at=descriptor.point_in_time.computed_at,
        input_sources=descriptor.sources,
        assumption_bindings=descriptor.assumption_bindings,
        rule_version=descriptor.dependencies.rule_version,
        model_version=descriptor.dependencies.model_version,
        parser_version=descriptor.dependencies.parser_version,
        scan_watermark=descriptor.dependencies.scan_watermark,
        input_descriptor_sha256=descriptor.input_sha256 or descriptor_sha256(descriptor),
    )
