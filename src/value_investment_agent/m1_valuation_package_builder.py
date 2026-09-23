"""Build versioned M1 valuation input descriptors from data package specs.

The package files own company-specific extracted facts, evidence locations and
reviewed scenario assumptions. This module owns only the common conversion to
typed domain objects; it never chooses a model from a symbol and never creates
an execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .event_scan import load_event_scan_payload
from .model_validity import MaterialEvent
from .m1_distribution_package_builder import optional_dividend_result_for_symbol
from .m1_historical_quote import quote_snapshot_from_historical_close_manifest
from .research_application import ModelValidityEvaluationInput
from .quote_snapshot import QuoteSnapshot
from .quote_session_conversion import quote_snapshot_from_bundle_file
from .research_case import ResearchCase
from .research_input import (
    ResearchInputDescriptor,
    finalize_input_descriptor,
)
from .research_run_contract import (
    INPUT_DESCRIPTOR_SCHEMA,
    AssumptionScenarioBinding,
    ResearchDependencyFingerprint,
    ResearchPitFrame,
    ResearchSourceDescriptor,
)
from .scenario_valuation import BridgeItem, ForecastYear, Terminal
from .valuation_assumptions import (
    ValuationAssumption,
    build_valuation_assumption_set,
)
from .valuation_models.fcff import FCFFScenarioInputs, FinancialFacts
from .valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


PACKAGE_SCHEMA = "m1-valuation-package-v1"


@dataclass(frozen=True)
class PackageDescriptorAttempt:
    """One package conversion result; failures stay isolated from the batch."""

    package_id: str
    symbol: str | None
    descriptor: ResearchInputDescriptor | None
    error: str | None

    def __post_init__(self) -> None:
        if not self.package_id.strip():
            raise ValueError("Package descriptor attempt id is required")
        if (self.descriptor is None) == (self.error is None):
            raise ValueError("Package descriptor attempt must be success or failure")
        if self.symbol is not None and self.descriptor is not None:
            if self.symbol != self.descriptor.symbol:
                raise ValueError("Package descriptor attempt symbol does not match")

    def as_policy(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "symbol": self.symbol,
            "input_sha256": (
                self.descriptor.input_sha256
                if self.descriptor is not None else None
            ),
            "error": self.error,
            "action": "no_order",
        }


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _decimal(value: object, field: str) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    return date.fromisoformat(value)


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _refs(value: object, field: str = "evidence_refs") -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    result = [dict(item) for item in value]
    if any(not ref.get("id") for ref in result):
        raise ValueError(f"{field} entries require ids")
    return result


def _source_descriptor(payload: Mapping[str, Any]) -> ResearchSourceDescriptor:
    data = dict(payload)
    return ResearchSourceDescriptor(
        id=_required_text(data.get("id"), "source.id"),
        kind=_required_text(data.get("kind"), "source.kind"),
        location=_required_text(data.get("location"), "source.location"),
        sha256=_required_text(data.get("sha256"), "source.sha256").lower(),
        published_at=(
            _datetime(data["published_at"], "source.published_at")
            if data.get("published_at") else None
        ),
        retrieved_at=(
            _datetime(data["retrieved_at"], "source.retrieved_at")
            if data.get("retrieved_at") else None
        ),
        parser_version=(
            _required_text(data["parser_version"], "source.parser_version")
            if data.get("parser_version") else None
        ),
    )


def build_research_case(payload: Mapping[str, Any]) -> ResearchCase:
    data = dict(payload)
    evidence_refs = _refs(data.get("evidence_refs"))
    return ResearchCase(
        symbol=_required_text(data["symbol"], "case.symbol"),
        name=_required_text(data["name"], "case.name"),
        as_of=_date(data["as_of"], "case.as_of"),
        run_id=_required_text(data["run_id"], "case.run_id"),
        generated_at=_datetime(data["generated_at"], "case.generated_at"),
        research_version=_required_text(data["research_version"], "case.research_version"),
        industry=_required_text(data["industry"], "case.industry"),
        investment_path=_required_text(data["investment_path"], "case.investment_path"),
        thesis=_required_text(data["thesis"], "case.thesis"),
        return_driver=_required_text(data["return_driver"], "case.return_driver"),
        mispricing_hypothesis=_required_text(
            data["mispricing_hypothesis"], "case.mispricing_hypothesis"
        ),
        financial_summary=dict(data.get("financial_summary") or {}),
        positives=[dict(item) for item in data.get("positives") or []],
        counter_evidence=[dict(item) for item in data.get("counter_evidence") or []],
        thesis_breakers=[dict(item) for item in data.get("thesis_breakers") or []],
        next_events=[dict(item) for item in data.get("next_events") or []],
        evidence_status=_required_text(data["evidence_status"], "case.evidence_status"),
        valuation_status=_required_text(data["valuation_status"], "case.valuation_status"),
        research_status=_required_text(data["research_status"], "case.research_status"),
        blockers=[str(item) for item in data.get("blockers") or []],
        evidence_refs=evidence_refs,
        quote_date=(
            _date(data["quote_date"], "case.quote_date")
            if data.get("quote_date") else None
        ),
        financial_period=(
            _date(data["financial_period"], "case.financial_period")
            if data.get("financial_period") else None
        ),
        missing_date_reasons=dict(data.get("missing_date_reasons") or {}),
    )


def build_quality_facts(payload: Mapping[str, Any]) -> QualityCompounderFacts:
    data = dict(payload)
    scenarios = data.get("scenario_inputs") or {}
    operating = {
        str(key): _decimal(item, f"facts.operating_inputs.{key}")
        for key, item in (data.get("operating_inputs") or {}).items()
        if item is not None
    }
    scenario_objects = {
        name: ResidualIncomeScenarioInputs(
            cost_of_equity=_decimal(item["cost_of_equity"], "cost_of_equity"),
            forecast_roes=tuple(
                _decimal(value, "forecast_roes") for value in item["forecast_roes"]
            ),
            terminal_roe=_decimal(item["terminal_roe"], "terminal_roe"),
            terminal_growth=_decimal(item["terminal_growth"], "terminal_growth"),
            retention=_decimal(item.get("retention", "0.30"), "retention"),
        )
        for name, item in scenarios.items()
    }
    return QualityCompounderFacts(
        symbol=_required_text(data["symbol"], "facts.symbol"),
        as_of=_date(data["as_of"], "facts.as_of"),
        verified=bool(data.get("verified")),
        confidence=_required_text(data.get("confidence", "低"), "facts.confidence"),
        evidence_refs=_refs(data.get("evidence_refs")),
        blockers=[str(item) for item in data.get("blockers") or []],
        operating_inputs=operating,
        scenario_inputs=scenario_objects or None,
    )


def _forecast_row(item: Mapping[str, Any]) -> ForecastYear:
    data = dict(item)
    return ForecastYear(
        year=int(data["year"]),
        ebit=_decimal(data["ebit"], "forecast.ebit"),
        cash_tax_rate=_decimal(data["cash_tax_rate"], "forecast.cash_tax_rate"),
        depreciation=_decimal(data["depreciation"], "forecast.depreciation"),
        capex=_decimal(data["capex"], "forecast.capex"),
        working_capital_increase=_decimal(
            data["working_capital_increase"], "forecast.working_capital_increase"
        ),
        wacc=_decimal(data["wacc"], "forecast.wacc"),
        evidence_refs=tuple(str(item) for item in data["evidence_refs"]),
    )


def _bridge_row(item: Mapping[str, Any]) -> BridgeItem:
    data = dict(item)
    return BridgeItem(
        name=_required_text(data["name"], "bridge.name"),
        kind=_required_text(data["kind"], "bridge.kind"),
        value=_decimal(data["value"], "bridge.value"),
        exposure_ids=tuple(str(item) for item in data["exposure_ids"]),
        evidence_refs=tuple(str(item) for item in data["evidence_refs"]),
    )


def build_fcff_facts(payload: Mapping[str, Any]) -> FinancialFacts:
    data = dict(payload)
    operating = {
        str(key): _decimal(item, f"facts.operating_inputs.{key}")
        for key, item in (data.get("operating_inputs") or {}).items()
        if item is not None
    }
    scenario_objects: dict[str, FCFFScenarioInputs] = {}
    for name, item in (data.get("scenario_inputs") or {}).items():
        terminal = item["terminal"]
        scenario_objects[str(name)] = FCFFScenarioInputs(
            forecast=tuple(_forecast_row(row) for row in item["forecast"]),
            terminal=Terminal(
                next_year_nopat=_decimal(terminal["next_year_nopat"], "terminal.nopat"),
                growth=_decimal(terminal["growth"], "terminal.growth"),
                roic=_decimal(terminal["roic"], "terminal.roic"),
                wacc=_decimal(terminal["wacc"], "terminal.wacc"),
                evidence_refs=tuple(str(ref) for ref in terminal["evidence_refs"]),
            ),
            bridge=tuple(_bridge_row(row) for row in item["bridge"]),
            operating_exposure_ids=tuple(
                str(ref) for ref in item["operating_exposure_ids"]
            ),
            ordinary_shares=_decimal(item["ordinary_shares"], "ordinary_shares"),
            share_evidence_refs=tuple(
                str(ref) for ref in item["share_evidence_refs"]
            ),
            currency=_required_text(item.get("currency", "CNY"), "currency"),
            valuation_date=(
                _date(item["valuation_date"], "scenario.valuation_date")
                if item.get("valuation_date") else None
            ),
            cash_flow_dates=(
                tuple(
                    _date(value, "cash_flow_date")
                    for value in item["cash_flow_dates"]
                )
                if item.get("cash_flow_dates") else None
            ),
            timing_evidence_refs=tuple(
                str(ref) for ref in item.get("timing_evidence_refs") or []
            ),
        )
    return FinancialFacts(
        symbol=_required_text(data["symbol"], "facts.symbol"),
        as_of=_date(data["as_of"], "facts.as_of"),
        verified=bool(data.get("verified")),
        evidence_refs=_refs(data.get("evidence_refs")),
        blockers=[str(item) for item in data.get("blockers") or []],
        operating_inputs=operating,
        scenario_inputs=scenario_objects or None,
        confidence=_required_text(data.get("confidence", "低"), "facts.confidence"),
    )


def build_assumptions(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    profile_id: str,
    model_type: str,
    as_of: date,
) -> Any:
    data = dict(payload)
    assumptions = [
        ValuationAssumption(
            name=_required_text(item["name"], "assumption.name"),
            unit=_required_text(item["unit"], "assumption.unit"),
            bear=(
                _decimal(item["bear"], "assumption.bear")
                if item.get("bear") is not None else None
            ),
            base=(
                _decimal(item["base"], "assumption.base")
                if item.get("base") is not None else None
            ),
            bull=(
                _decimal(item["bull"], "assumption.bull")
                if item.get("bull") is not None else None
            ),
            basis=_required_text(item["basis"], "assumption.basis"),
            rationale=_required_text(item["rationale"], "assumption.rationale"),
            as_of=as_of,
            confidence=_required_text(item["confidence"], "assumption.confidence"),
            sensitivity=_required_text(item["sensitivity"], "assumption.sensitivity"),
            evidence_refs=_refs(item.get("evidence_refs")),
            blockers=[str(blocker) for blocker in item.get("blockers") or []],
            ordering=_required_text(item.get("ordering", "ascending"), "assumption.ordering"),
        )
        for item in data.get("assumptions") or []
    ]
    return build_valuation_assumption_set(
        symbol=symbol,
        profile_id=profile_id,
        model_type=model_type,
        as_of=as_of,
        assumptions=assumptions,
        blockers=[str(item) for item in data.get("blockers") or []],
        evidence_refs=_refs(data.get("evidence_refs")),
    )


def build_bindings(payload: Sequence[Mapping[str, Any]]) -> tuple[AssumptionScenarioBinding, ...]:
    return tuple(
        AssumptionScenarioBinding(
            assumption_name=_required_text(item["assumption_name"], "binding.name"),
            scenario=_required_text(item["scenario"], "binding.scenario"),
            field_path=_required_text(item["field_path"], "binding.field_path"),
            expected_value=str(item["expected_value"]),
            evidence_refs=tuple(_refs(item.get("evidence_refs"))),
        )
        for item in payload
    )


def build_quote(
    payload: Mapping[str, Any] | None,
    *,
    root: Path,
) -> QuoteSnapshot | None:
    if payload is None:
        return None
    data = dict(payload)
    kind = str(data.get("kind") or "quote_session")
    if kind == "historical_dual_source_close":
        return quote_snapshot_from_historical_close_manifest(
            root / _required_text(data["manifest_path"], "quote.manifest_path"),
            root,
            expected_sha256=(
                _required_text(
                    data["manifest_sha256"],
                    "quote.manifest_sha256",
                )
                if data.get("manifest_sha256")
                else None
            ),
        )
    if kind != "quote_session":
        raise ValueError(f"Unknown M1 quote evidence kind: {kind}")
    return quote_snapshot_from_bundle_file(
        root / _required_text(data["bundle_path"], "quote.bundle_path"),
        root,
        symbol=_required_text(data["symbol"], "quote.symbol"),
        ref_id=_required_text(data["ref_id"], "quote.ref_id"),
        expected_sha256=(
            _required_text(data["bundle_sha256"], "quote.bundle_sha256")
            if data.get("bundle_sha256") else None
        ),
    )


def build_validity(
    payload: Mapping[str, Any] | None,
    *,
    root: Path | None = None,
) -> ModelValidityEvaluationInput | None:
    if payload is None:
        return None
    data = dict(payload)
    event_scan_ref = data.get("event_scan_ref")
    event_scan = None
    event_scan_evidence_refs = tuple(_refs(data.get("event_scan_evidence_refs")))
    if event_scan_ref:
        if root is None:
            raise ValueError("event_scan_ref requires a project root")
        reference = dict(event_scan_ref)
        if "id" not in reference:
            raise ValueError("event_scan_ref requires an evidence id")
        event_scan = load_event_scan_payload(reference, root=root)
        event_scan_evidence_refs = tuple(_refs([reference]))
    return ModelValidityEvaluationInput(
        model_id=_required_text(data["model_id"], "validity.model_id"),
        valid_from=_date(data["valid_from"], "validity.valid_from"),
        events=tuple(
            MaterialEvent(
                event_date=_date(item["event_date"], "event.event_date"),
                kind=_required_text(item["kind"], "event.kind"),
                description=_required_text(item["description"], "event.description"),
                evidence_refs=_refs(item.get("evidence_refs")),
            )
            for item in data.get("events") or []
        ),
        event_scan_evidence_refs=event_scan_evidence_refs,
        event_scan=event_scan,
        blockers=tuple(str(item) for item in data.get("blockers") or []),
    )


def build_descriptor(
    payload: Mapping[str, Any],
    *,
    root: Path,
) -> ResearchInputDescriptor:
    data = dict(payload)
    if data.get("schema_version") != PACKAGE_SCHEMA:
        raise ValueError(f"Unknown valuation package schema: {data.get('schema_version')}")
    pit = data["point_in_time"]
    symbol = _required_text(data["symbol"], "package.symbol")
    profile_id = _required_text(data["profile_id"], "package.profile_id")
    requested_model = (
        _required_text(data["requested_model"], "package.requested_model")
        if data.get("requested_model") else None
    )
    research_case = build_research_case(data["research_case"])
    facts_payload = dict(data["facts"])
    facts_kind = _required_text(facts_payload.get("kind"), "facts.kind")
    if facts_kind == "quality_compounder":
        facts = build_quality_facts(facts_payload)
        model_type = "residual_income_or_equity_value"
    elif facts_kind == "fcff":
        facts = build_fcff_facts(facts_payload)
        model_type = "FCFF"
    else:
        raise ValueError(f"Unknown valuation facts kind: {facts_kind}")
    dependencies = data["dependencies"]
    descriptor = ResearchInputDescriptor(
        schema_version=INPUT_DESCRIPTOR_SCHEMA,
        descriptor_version=_required_text(
            data.get("descriptor_version"), "package.descriptor_version"
        ),
        symbol=symbol,
        name=_required_text(data.get("name"), "package.name"),
        profile_id=profile_id,
        requested_model=requested_model,
        run_id=_required_text(data.get("run_id"), "package.run_id"),
        point_in_time=ResearchPitFrame(
            report_period=_date(pit["report_period"], "pit.report_period"),
            research_as_of=_date(pit["research_as_of"], "pit.research_as_of"),
            valuation_date=_date(pit["valuation_date"], "pit.valuation_date"),
            available_at=_datetime(pit["available_at"], "pit.available_at"),
            computed_at=_datetime(pit["computed_at"], "pit.computed_at"),
        ),
        dependencies=ResearchDependencyFingerprint(
            rule_version=_required_text(dependencies["rule_version"], "dependencies.rule_version"),
            profile_id=profile_id,
            model_id=_required_text(dependencies["model_id"], "dependencies.model_id"),
            model_version=_required_text(
                dependencies["model_version"], "dependencies.model_version"
            ),
            parser_version=(
                _required_text(dependencies["parser_version"], "dependencies.parser_version")
                if dependencies.get("parser_version") else None
            ),
            scan_watermark=(
                _required_text(dependencies["scan_watermark"], "dependencies.scan_watermark")
                if dependencies.get("scan_watermark") else None
            ),
        ),
        sources=tuple(_source_descriptor(item) for item in data.get("sources") or []),
        research_case=research_case,
        facts=facts,
        assumptions=build_assumptions(
            data.get("assumptions") or {},
            symbol=symbol,
            profile_id=profile_id,
            model_type=model_type,
            as_of=facts.as_of,
        ),
        assumption_bindings=build_bindings(data.get("assumption_bindings") or []),
        distribution_result=optional_dividend_result_for_symbol(root, symbol),
        quote=build_quote(data.get("quote"), root=root),
        model_validity_input=build_validity(
            data.get("model_validity_input"),
            root=root,
        ),
        valuation_approval=None,
        blockers=tuple(str(item) for item in data.get("blockers") or []),
        input_sha256=None,
    )
    return finalize_input_descriptor(descriptor)


def load_package_specs(root: Path) -> list[dict[str, Any]]:
    package_dir = root / "config" / "m1-valuation-packages-v1"
    if not package_dir.exists():
        raise FileNotFoundError(f"M1 valuation package directory missing: {package_dir}")
    specs: list[dict[str, Any]] = []
    for path in sorted(package_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Valuation package must be an object: {path}")
        specs.append(payload)
    return specs


def load_descriptor_payloads(root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(item["symbol"]): item
        for item in load_package_specs(root)
    }


def build_package_descriptor_attempts(
    root: Path,
) -> tuple[PackageDescriptorAttempt, ...]:
    """Build every package while isolating malformed or unsupported inputs."""
    attempts: list[PackageDescriptorAttempt] = []
    for path in sorted((root / "config" / "m1-valuation-packages-v1").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = (
            str(payload["symbol"])
            if isinstance(payload.get("symbol"), str) and payload["symbol"]
            else None
        )
        package_id = str(
            payload.get("run_id")
            or payload.get("descriptor_version")
            or path.stem
        )
        try:
            descriptor = build_descriptor(payload, root=root)
        except Exception as error:
            attempts.append(
                PackageDescriptorAttempt(
                    package_id=package_id,
                    symbol=symbol,
                    descriptor=None,
                    error=f"{type(error).__name__}: {error}",
                )
            )
        else:
            attempts.append(
                PackageDescriptorAttempt(
                    package_id=package_id,
                    symbol=descriptor.symbol,
                    descriptor=descriptor,
                    error=None,
                )
            )
    return tuple(attempts)
