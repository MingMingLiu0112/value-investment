"""Three-company frozen-runtime replay through the shared research pipeline.

The frozen runtime snapshots remain the source of record. This adapter turns
their typed payloads into explicit ``ResearchRunSpec`` inputs, executes the
symbol-free Application Runner and Batch service, then compares the replayed
semantics with the frozen C3 acceptance baseline. It never reconstructs a
missing valuation input or produces an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .fixed_sample_admission import FixedSampleAdmissionReview, review_fixed_sample
from .fixed_sample_manifest import FixedSampleManifest, load_fixed_sample_manifest
from .quote_snapshot import (
    QUOTE_STATUS_VERIFIED_CLOSE,
    QuoteSnapshot,
)
from .research_application import (
    ModelValidityEvaluationInput,
    ResearchApplicationService,
    ResearchRunSpec,
)
from .research_artifact_codecs import (
    ARTIFACT_SCHEMA_VERSION,
    artifact_payload,
    decode_artifact,
)
from .research_artifact_repository import (
    InMemoryResearchArtifactRepository,
    ResearchArtifactRepository,
)
from .research_artifacts import (
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_FIXED_SAMPLE_ADMISSION,
    ARTIFACT_RESEARCH_CASE,
    SCOPE_REVIEW,
    ResearchArtifactIdentity,
    canonicalize_artifact_payload,
    sha256_text,
)
from .research_batch import (
    ResearchBatchCompanySpec,
    ResearchBatchService,
    ResearchBatchSpec,
)
from .research_runtime_import import (
    RESEARCH_POINTER,
    REVIEW_POINTER,
    VALUATION_POINTERS,
    PinnedEvidence,
    resolve_pinned,
    sha256_file,
)
from .valuation_models.cyclical import CyclicalFacts
from .valuation_models.fcff import FinancialFacts
from .valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


REPLAY_SCHEMA_VERSION = "c3-three-company-e2e-replay-v1"
REPLAY_RULE_VERSION = "c3-three-company-e2e-replay-v1"
MOUTAI_CURRENT_MODEL_POINTER = (
    "runtime/company-research/"
    "600519-consolidated-parent-equity-residual-income-current-latest.json"
)
SYMBOLS = ("600519", "000333", "601088")

EXPECTED_REPLAY_SEMANTICS: dict[str, dict[str, Any]] = {
    "600519": {
        "profile_id": "quality_compounder",
        "valuation_status": "conditional_research_only",
        "confidence": "\u4f4e",
        "model_validity_present": True,
        "bridge_status": "READY",
        "cash_return_status": "PARTIAL",
        "decision": "CONTINUE_CONDITIONAL_MODEL",
        "production_valuation_status": "NOT_AVAILABLE",
        "bounded_value_judgment": "CONDITIONAL",
        "action": "no_order",
        "current_normalized_distinct": False,
    },
    "000333": {
        "profile_id": "mature_manufacturing",
        "valuation_status": "not_ready",
        "confidence": "\u4f4e",
        "model_validity_present": False,
        "bridge_status": "PENDING_EXTERNAL_DATA",
        "cash_return_status": "PARTIAL",
        "decision": "RESOLVE_MODEL_INPUTS",
        "production_valuation_status": "NOT_AVAILABLE",
        "bounded_value_judgment": "NOT_AVAILABLE",
        "action": "no_order",
        "current_normalized_distinct": False,
    },
    "601088": {
        "profile_id": "cyclical_cash_return",
        "valuation_status": "not_ready",
        "confidence": "\u4f4e",
        "model_validity_present": False,
        "bridge_status": "PENDING_EXTERNAL_DATA",
        "cash_return_status": "PARTIAL",
        "decision": "PAUSE_PRODUCTION_VALUATION",
        "production_valuation_status": "NOT_AVAILABLE",
        "bounded_value_judgment": "NOT_AVAILABLE",
        "action": "no_order",
        "current_normalized_distinct": True,
    },
}


@dataclass(frozen=True)
class FrozenReplayBundle:
    """Hash-verified frozen payloads and the versioned fixed-sample manifest."""

    root: Path
    research_payload: Mapping[str, Any]
    research_pin: PinnedEvidence
    valuation_payloads: Mapping[str, Mapping[str, Any]]
    valuation_pins: Mapping[str, PinnedEvidence]
    review_payload: Mapping[str, Any]
    review_pin: PinnedEvidence
    moutai_model_payload: Mapping[str, Any]
    moutai_model_pin: PinnedEvidence
    manifest: FixedSampleManifest
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True)
class ReplayCompanyInput:
    symbol: str
    profile_id: str
    company_spec: ResearchBatchCompanySpec
    valuation_pointer: str
    valuation_sha256: str


@dataclass(frozen=True)
class CompanyReplayParity:
    symbol: str
    profile_id: str
    route_model_type: str
    route_status: str
    valuation_status: str
    confidence: str
    model_validity_present: bool
    model_validity_status: str | None
    bridge_status: str
    cash_return_status: str
    yield_types: tuple[str, ...]
    decision: str
    production_valuation_status: str
    bounded_value_judgment: str
    action: str
    batch_status: str
    outcome_status: str
    source_pointer: str
    source_sha256: str
    input_sha256: str
    artifact_ids: Mapping[str, str]
    semantics_matched: bool
    mismatches: tuple[str, ...]

    @property
    def current_normalized_distinct(self) -> bool:
        return "current" in self.yield_types and "normalized" in self.yield_types

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "route_model_type": self.route_model_type,
            "route_status": self.route_status,
            "valuation_status": self.valuation_status,
            "confidence": self.confidence,
            "model_validity_present": self.model_validity_present,
            "model_validity_status": self.model_validity_status,
            "bridge_status": self.bridge_status,
            "cash_return_status": self.cash_return_status,
            "yield_types": list(self.yield_types),
            "decision": self.decision,
            "production_valuation_status": self.production_valuation_status,
            "bounded_value_judgment": self.bounded_value_judgment,
            "action": self.action,
            "batch_status": self.batch_status,
            "outcome_status": self.outcome_status,
            "source_pointer": self.source_pointer,
            "source_sha256": self.source_sha256,
            "input_sha256": self.input_sha256,
            "artifact_ids": dict(self.artifact_ids),
            "semantics_matched": self.semantics_matched,
            "mismatches": list(self.mismatches),
        }


@dataclass(frozen=True)
class ThreeCompanyReplayResult:
    run_id: str
    rule_version: str
    started_at: datetime
    finished_at: datetime
    manifest_version: str
    manifest_sha256: str
    companies: tuple[CompanyReplayParity, ...]
    batch_result: Any
    aggregate_review: FixedSampleAdmissionReview
    aggregate_review_artifact_id: str
    all_semantics_matched: bool

    @property
    def action(self) -> str:
        return "no_order"

    def as_policy(self) -> dict[str, Any]:
        _, review_payload = artifact_payload(self.aggregate_review)
        return {
            "schema_version": REPLAY_SCHEMA_VERSION,
            "run_id": self.run_id,
            "rule_version": self.rule_version,
            "generated_at": self.finished_at.isoformat(),
            "manifest": {
                "version": self.manifest_version,
                "sha256": self.manifest_sha256,
            },
            "companies": [item.as_policy() for item in self.companies],
            "batch": self.batch_result.as_policy(),
            "fixed_sample_admission": review_payload,
            "fixed_sample_admission_artifact_id": (
                self.aggregate_review_artifact_id
            ),
            "all_semantics_matched": self.all_semantics_matched,
            "action": self.action,
        }


def _records(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(record["case"]["symbol"]): dict(record)
        for record in payload["records"]
        if str(record["case"]["symbol"]) in SYMBOLS
    }


def _companies(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(company["symbol"]): dict(company)
        for company in payload.get("companies", [])
        if str(company["symbol"]) in SYMBOLS
    }


def load_replay_bundle(
    root: Path,
    *,
    manifest_path: Path | None = None,
) -> FrozenReplayBundle:
    resolved_root = root.resolve()
    research, research_pin = resolve_pinned(resolved_root, RESEARCH_POINTER)
    review, review_pin = resolve_pinned(resolved_root, REVIEW_POINTER)
    records = _records(research)
    companies = _companies(review)
    if set(records) != set(SYMBOLS) or set(companies) != set(SYMBOLS):
        raise ValueError("Frozen research and admission payloads must cover all three symbols")

    valuations: dict[str, dict[str, Any]] = {}
    valuation_pins: dict[str, PinnedEvidence] = {}
    for symbol in SYMBOLS:
        payload, pin = resolve_pinned(resolved_root, VALUATION_POINTERS[symbol])
        valuations[symbol] = payload
        valuation_pins[symbol] = pin

    moutai_model, moutai_model_pin = resolve_pinned(
        resolved_root, MOUTAI_CURRENT_MODEL_POINTER
    )
    if str(moutai_model.get("symbol")) != "600519":
        raise ValueError("The resolved Moutai current model is not bound to 600519")

    selected_manifest = (
        manifest_path.resolve()
        if manifest_path is not None
        else (resolved_root / "config" / "fixed-sample-manifest.json").resolve()
    )
    if not selected_manifest.is_relative_to(resolved_root):
        raise ValueError("Replay manifest must remain under the replay root")
    manifest = load_fixed_sample_manifest(selected_manifest)
    if {entry.symbol for entry in manifest.companies} != set(SYMBOLS):
        raise ValueError("Fixed-sample manifest must cover all three symbols")

    return FrozenReplayBundle(
        root=resolved_root,
        research_payload=research,
        research_pin=research_pin,
        valuation_payloads=valuations,
        valuation_pins=valuation_pins,
        review_payload=review,
        review_pin=review_pin,
        moutai_model_payload=moutai_model,
        moutai_model_pin=moutai_model_pin,
        manifest=manifest,
        manifest_path=selected_manifest,
        manifest_sha256=sha256_file(selected_manifest),
    )


def _moutai_facts(
    valuation_payload: Mapping[str, Any],
    model_payload: Mapping[str, Any],
) -> QualityCompounderFacts:
    result = dict(valuation_payload["result"])
    facts = dict(model_payload["facts"])
    policy = dict(model_payload["model_policy"])
    growth_years = int(policy["forecast_years"])
    calculations = {
        str(item["scenario"]): dict(item["basis_origin_calculation"])
        for item in model_payload["results"]
    }
    if set(calculations) != {"bear", "base", "bull"}:
        raise ValueError("Frozen Moutai model does not contain bear/base/bull scenarios")
    scenarios: dict[str, ResidualIncomeScenarioInputs] = {}
    for name in ("bear", "base", "bull"):
        calculation = calculations[name]
        forecast = list(calculation["forecast_years"])
        if len(forecast) < growth_years:
            raise ValueError(f"Frozen Moutai {name} scenario is missing forecast years")
        scenarios[name] = ResidualIncomeScenarioInputs(
            cost_of_equity=Decimal(
                str(calculation["cost_of_equity_cny_nominal"])
            ),
            forecast_roes=tuple(
                Decimal(str(row["roe_assumption"]))
                for row in forecast[:growth_years]
            ),
            terminal_roe=Decimal(str(calculation["terminal_roe"])),
            terminal_growth=Decimal(str(policy["terminal_growth"])),
            retention=Decimal(str(forecast[0]["retention_assumption"])),
        )
    return QualityCompounderFacts(
        symbol="600519",
        as_of=date.fromisoformat(str(result["valuation_date"])),
        verified=True,
        confidence="\u4f4e",
        evidence_refs=[dict(item) for item in result.get("evidence_refs") or []],
        blockers=[],
        operating_inputs={
            "start_book_equity": Decimal(str(facts["parent_equity_cny"])),
            "ordinary_shares": Decimal(str(facts["issued_shares"])),
        },
        scenario_inputs=scenarios,
    )


def _gap_facts(
    symbol: str,
    profile_id: str,
    valuation_payload: Mapping[str, Any],
) -> FinancialFacts | CyclicalFacts:
    result = dict(valuation_payload["result"])
    as_of = date.fromisoformat(str(result["valuation_date"]))
    evidence_refs = [dict(item) for item in result.get("evidence_refs") or []]
    blockers = [str(item) for item in result.get("blockers") or []]
    if profile_id == "mature_manufacturing":
        return FinancialFacts(
            symbol=symbol,
            as_of=as_of,
            verified=False,
            evidence_refs=evidence_refs,
            blockers=blockers,
        )
    if profile_id == "cyclical_cash_return":
        return CyclicalFacts(
            symbol=symbol,
            as_of=as_of,
            verified=False,
            confidence="\u4f4e",
            evidence_refs=evidence_refs,
            blockers=blockers,
        )
    raise ValueError(f"Unsupported gap profile for frozen replay: {profile_id}")


def _facts_for(
    symbol: str,
    profile_id: str,
    valuation_payload: Mapping[str, Any],
    moutai_model_payload: Mapping[str, Any] | None,
) -> Any:
    if profile_id == "quality_compounder":
        if moutai_model_payload is None:
            raise ValueError("Moutai replay requires its frozen current model")
        return _moutai_facts(valuation_payload, moutai_model_payload)
    return _gap_facts(symbol, profile_id, valuation_payload)


def _distribution_result(company: Mapping[str, Any]) -> Any:
    cash_return = company.get("cash_return_research")
    if cash_return is None:
        return None
    return decode_artifact(
        ARTIFACT_DIVIDEND_RESEARCH,
        dict(cash_return),
    )


def _quote_and_validity(
    valuation_payload: Mapping[str, Any],
) -> tuple[QuoteSnapshot | None, ModelValidityEvaluationInput | None]:
    bridge_payload = valuation_payload.get("price_bridge")
    if not isinstance(bridge_payload, Mapping):
        return None, None
    bridge = dict(bridge_payload)
    quote_date = bridge.get("quote_date")
    current_price = bridge.get("current_price")
    quote_status = bridge.get("quote_status")
    if (
        quote_date is None
        or current_price is None
        or quote_status != QUOTE_STATUS_VERIFIED_CLOSE
    ):
        return None, None

    quote = QuoteSnapshot(
        symbol=str(bridge["symbol"]),
        quote_date=date.fromisoformat(str(quote_date)),
        current_price=Decimal(str(current_price)),
        status=QUOTE_STATUS_VERIFIED_CLOSE,
        evidence_refs=[
            dict(item)
            for item in (
                bridge.get("quote_evidence_refs")
                or bridge.get("evidence_refs")
                or []
            )
        ],
    )
    validity_payload = valuation_payload.get("model_validity")
    if not isinstance(validity_payload, Mapping):
        return quote, None
    validity = dict(validity_payload)
    return quote, ModelValidityEvaluationInput(
        model_id=str(validity["model_id"]),
        valid_from=date.fromisoformat(str(validity["valid_from"])),
        events=(),
        event_scan_evidence_refs=tuple(
            dict(item) for item in validity.get("evidence_refs") or []
        ),
        blockers=(),
    )


def _input_fingerprint(
    symbol: str,
    case_payload: Mapping[str, Any],
    valuation_payload: Mapping[str, Any],
    company_payload: Mapping[str, Any],
    manifest_entry: Any,
    moutai_model_payload: Mapping[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "symbol": symbol,
        "case": dict(case_payload),
        "valuation": dict(valuation_payload),
        "admission": dict(company_payload),
        "manifest": manifest_entry.as_policy_dict(),
    }
    if moutai_model_payload is not None:
        payload["moutai_current_model"] = dict(moutai_model_payload)
    return sha256_text(canonicalize_artifact_payload(payload))


def build_replay_inputs(
    bundle: FrozenReplayBundle,
    *,
    run_id: str,
) -> dict[str, ReplayCompanyInput]:
    records = _records(bundle.research_payload)
    companies = _companies(bundle.review_payload)
    inputs: dict[str, ReplayCompanyInput] = {}
    for symbol in SYMBOLS:
        entry = bundle.manifest.entry(symbol)
        profile_id = str(companies[symbol]["profile_id"])
        if entry.profile_id != profile_id:
            raise ValueError(
                f"Manifest profile does not match frozen admission for {symbol}"
            )
        case_payload = dict(records[symbol]["case"])
        case = decode_artifact(ARTIFACT_RESEARCH_CASE, case_payload)
        valuation_payload = dict(bundle.valuation_payloads[symbol])
        moutai_model = (
            bundle.moutai_model_payload if symbol == "600519" else None
        )
        facts = _facts_for(
            symbol,
            profile_id,
            valuation_payload,
            moutai_model,
        )
        quote, validity_input = _quote_and_validity(valuation_payload)
        spec = ResearchRunSpec(
            run_id=f"{run_id}:{symbol}",
            symbol=symbol,
            profile_id=profile_id,
            research_case=case,
            facts=facts,
            requested_model=entry.primary_model,
            quote=quote,
            model_validity_input=validity_input,
            distribution_result=_distribution_result(companies[symbol]),
            as_of=case.as_of,
            available_at=case.generated_at,
        )
        pin = bundle.valuation_pins[symbol]
        inputs[symbol] = ReplayCompanyInput(
            symbol=symbol,
            profile_id=profile_id,
            company_spec=ResearchBatchCompanySpec(
                spec,
                _input_fingerprint(
                    symbol,
                    case_payload,
                    valuation_payload,
                    companies[symbol],
                    entry,
                    moutai_model,
                ),
            ),
            valuation_pointer=pin.pointer.as_posix(),
            valuation_sha256=pin.sha256,
        )
    return inputs


def _outcome_payloads(
    outcome: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_stored = next(
        stored
        for stored in outcome.stored_artifacts
        if stored.envelope.identity.artifact_type == ARTIFACT_RESEARCH_CASE
    )
    case = decode_artifact(
        ARTIFACT_RESEARCH_CASE,
        case_stored.envelope.payload_object(),
    )
    _, case_payload = artifact_payload(case)
    _, gate_payload = artifact_payload(outcome.gate)
    _, result_payload = artifact_payload(outcome.valuation)
    _, bridge_payload = artifact_payload(outcome.price_bridge)
    valuation_payload: dict[str, Any] = {
        "result": result_payload,
        "price_bridge": bridge_payload,
        "valuation_approved": False,
    }
    if outcome.model_validity is not None:
        _, validity_payload = artifact_payload(outcome.model_validity)
        valuation_payload["model_validity"] = validity_payload
    return case_payload, gate_payload, valuation_payload


def _parity(
    outcome: Any,
    batch_status: str,
    admission: Any,
    source_pointer: str,
    source_sha256: str,
    input_sha256: str,
) -> CompanyReplayParity:
    symbol = outcome.symbol
    expected = EXPECTED_REPLAY_SEMANTICS[symbol]
    distribution = outcome.distribution_result
    yield_types = tuple(
        snapshot.yield_type for snapshot in (
            distribution.yield_snapshots if distribution is not None else ()
        )
    )
    current_normalized_distinct = (
        "current" in yield_types and "normalized" in yield_types
    )
    actual: dict[str, Any] = {
        "profile_id": outcome.profile_id,
        "valuation_status": outcome.valuation.status,
        "confidence": outcome.valuation.confidence,
        "model_validity_present": outcome.model_validity is not None,
        "bridge_status": outcome.price_bridge.bridge_status,
        "cash_return_status": (
            distribution.cash_return_status
            if distribution is not None
            else "NOT_ASSESSED"
        ),
        "decision": admission.decision,
        "production_valuation_status": admission.production_valuation_status,
        "bounded_value_judgment": admission.bounded_value_judgment,
        "action": admission.action,
        "current_normalized_distinct": current_normalized_distinct,
    }
    mismatches = tuple(
        sorted(
            f"{key}:expected={expected[key]};actual={actual[key]}"
            for key in expected
            if actual[key] != expected[key]
        )
    )
    artifact_ids = {
        stored.envelope.identity.artifact_type: stored.artifact_id
        for stored in outcome.stored_artifacts
    }
    return CompanyReplayParity(
        symbol=symbol,
        profile_id=outcome.profile_id,
        route_model_type=outcome.route.model_type or "",
        route_status=outcome.route.status,
        valuation_status=outcome.valuation.status,
        confidence=outcome.valuation.confidence,
        model_validity_present=outcome.model_validity is not None,
        model_validity_status=(
            outcome.model_validity.status
            if outcome.model_validity is not None
            else None
        ),
        bridge_status=outcome.price_bridge.bridge_status,
        cash_return_status=actual["cash_return_status"],
        yield_types=yield_types,
        decision=admission.decision,
        production_valuation_status=admission.production_valuation_status,
        bounded_value_judgment=admission.bounded_value_judgment,
        action=admission.action,
        batch_status=batch_status,
        outcome_status=outcome.status,
        source_pointer=source_pointer,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
        artifact_ids=artifact_ids,
        semantics_matched=not mismatches,
        mismatches=mismatches,
    )


def run_three_company_replay(
    repository: ResearchArtifactRepository | None = None,
    *,
    root: Path,
    manifest_path: Path | None = None,
    run_id: str,
    rule_version: str = REPLAY_RULE_VERSION,
    now_utc: Callable[[], datetime] | None = None,
) -> ThreeCompanyReplayResult:
    if repository is None:
        repository = InMemoryResearchArtifactRepository()
    now = now_utc or (lambda: datetime.now(timezone.utc))
    started_at = now()
    bundle = load_replay_bundle(root, manifest_path=manifest_path)
    inputs = build_replay_inputs(bundle, run_id=run_id)

    application = ResearchApplicationService(repository, now_utc=now)
    batch_service = ResearchBatchService(
        repository,
        application_service=application,
        now_utc=now,
    )
    batch_result = batch_service.run(
        ResearchBatchSpec(
            run_id=run_id,
            rule_version=rule_version,
            companies=tuple(
                item.company_spec for item in inputs.values()
            ),
            started_at=started_at,
        )
    )

    outcomes = {
        result.symbol: result.outcome
        for result in batch_result.results
        if result.outcome is not None
    }
    if set(outcomes) != set(SYMBOLS):
        failed = sorted(set(SYMBOLS) - set(outcomes))
        raise RuntimeError(
            "Three-company replay did not produce all research outcomes: "
            + ",".join(failed)
        )

    research_records: list[dict[str, Any]] = []
    valuation_payloads: dict[str, dict[str, Any]] = {}
    distribution_results: dict[str, Any] = {}
    for symbol in SYMBOLS:
        outcome = outcomes[symbol]
        case_payload, gate_payload, valuation_payload = _outcome_payloads(outcome)
        research_records.append(
            {"case": case_payload, "gate": gate_payload}
        )
        valuation_payloads[symbol] = valuation_payload
        if outcome.distribution_result is not None:
            distribution_results[symbol] = outcome.distribution_result

    aggregate_review = review_fixed_sample(
        research_records=research_records,
        valuation_payloads=valuation_payloads,
        policies=bundle.manifest.policies,
        as_of=date.fromisoformat(str(bundle.review_payload["as_of"])),
        distribution_results=distribution_results,
    )
    finished_at = now()
    stored_review = repository.save_object(
        aggregate_review,
        identity=ResearchArtifactIdentity(
            scope_type=SCOPE_REVIEW,
            scope_key=f"c3-e2e-{run_id}",
            artifact_type=ARTIFACT_FIXED_SAMPLE_ADMISSION,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            as_of=aggregate_review.as_of,
            available_at=finished_at,
        ),
        evidence_refs=aggregate_review.evidence_refs,
        run_id=run_id,
    )

    admissions = {
        item.symbol: item for item in aggregate_review.companies
    }
    parities: list[CompanyReplayParity] = []
    for symbol in SYMBOLS:
        batch_company = batch_result.results_by_symbol[symbol]
        source = inputs[symbol]
        parities.append(
            _parity(
                outcomes[symbol],
                batch_company.status,
                admissions[symbol],
                source.valuation_pointer,
                source.valuation_sha256,
                source.company_spec.input_sha256 or "",
            )
        )

    all_matched = (
        all(item.semantics_matched for item in parities)
        and aggregate_review.action == "no_order"
        and aggregate_review.production_valuation_available is False
    )
    return ThreeCompanyReplayResult(
        run_id=run_id,
        rule_version=rule_version,
        started_at=started_at,
        finished_at=finished_at,
        manifest_version=bundle.manifest.manifest_version,
        manifest_sha256=bundle.manifest_sha256,
        companies=tuple(parities),
        batch_result=batch_result,
        aggregate_review=aggregate_review,
        aggregate_review_artifact_id=stored_review.artifact_id,
        all_semantics_matched=all_matched,
    )
