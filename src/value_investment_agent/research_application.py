"""Profile-driven application orchestration for one company research run.

Domain objects carry investment and data semantics. This service validates an
explicit run contract, selects a model from the economic profile, executes the
research and price-bridge pipeline, and persists immutable artifacts through a
repository. It contains no symbol-based branching and no execution logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
from typing import Any, Callable, Mapping, Sequence

from .current_research_status import (
    ENGINEERING_READY,
    CurrentResearchStatus,
    evaluate_current_research_status,
)
from .distribution import DividendResearchResult
from .event_scan import EventScanResult
from .event_materiality import EventMaterialityReview
from .fixed_sample_admission import (
    FixedSampleAdmissionPolicy,
    FixedSampleAdmissionReview,
    review_fixed_sample,
)
from .human_research_approval import (
    HumanResearchApprovalReceipt,
    resolve_human_research_approval,
)
from .interim_report_policy import InterimReportPolicyDecision
from .model_validity import (
    MaterialEvent,
    ModelValidity,
    evaluate_model_validity,
)
from .price_attractiveness import (
    PriceAttractivenessAssessment,
    assess_price_attractiveness,
)
from .price_bridge import (
    PriceBridgeResult,
    bridge_with_quote,
    pending_price_bridge_for_incomplete_valuation,
)
from .pre_decision_eligibility import (
    PreDecisionEligibility,
    evaluate_pre_decision_eligibility,
)
from .quote_snapshot import (
    QUOTE_STATUS_PENDING_EXTERNAL_DATA,
    QuoteSnapshot,
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
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_FIXED_SAMPLE_ADMISSION,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_ATTRACTIVENESS,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ARTIFACT_VALUATION_RESULT,
    SCOPE_REVIEW,
    SCOPE_SECURITY,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
)
from .research_case import ResearchCase
from .research_gate import (
    ResearchGate,
    evaluate_with_human_approval,
    evaluate_with_valuation,
)
from .research_profile import PROFILES
from .research_run_contract import (
    AssumptionScenarioBinding,
    ResearchSourceDescriptor,
    ResearchValuationApproval,
    validate_assumption_bindings,
)
from .valuation_assumptions import ValuationAssumptionSet
from .valuation_bridge_review import BridgeContributionAssessment
from .valuation_models.base import ValuationResult
from .valuation_router import (
    ROUTE_SUPPORTED,
    ValuationRoute,
    ValuationRouter,
)


RUN_COMPLETED = "COMPLETED"
RUN_COMPLETED_WITH_BLOCKERS = "COMPLETED_WITH_BLOCKERS"
RUN_UNSUPPORTED = "UNSUPPORTED"
RUN_STATUSES = {
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_BLOCKERS,
    RUN_UNSUPPORTED,
}


def _merge_evidence_refs(
    *groups: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Research evidence references require ids")
            existing = merged.get(ref_id)
            if existing is None:
                merged[ref_id] = ref
                continue
            for key, value in ref.items():
                if key in existing and existing[key] != value:
                    raise ValueError(
                        f"Research evidence id conflict: {ref_id}"
                    )
                existing[key] = value
    return list(merged.values())


@dataclass(frozen=True)
class ModelValidityEvaluationInput:
    """Explicit event-scan contract used to derive model validity."""

    model_id: str
    valid_from: date
    events: tuple[MaterialEvent, ...] = ()
    event_scan_evidence_refs: tuple[dict[str, Any], ...] = ()
    event_scan: EventScanResult | None = None
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("Model validity evaluation requires a model id")
        if not isinstance(self.valid_from, date):
            raise ValueError("Model validity valid_from must be a date")
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(
            self,
            "event_scan_evidence_refs",
            tuple(dict(ref) for ref in self.event_scan_evidence_refs),
        )
        if self.event_scan is not None and not isinstance(
            self.event_scan, EventScanResult
        ):
            raise TypeError("Model validity event_scan must be an EventScanResult")
        object.__setattr__(
            self,
            "blockers",
            tuple(str(blocker) for blocker in self.blockers),
        )


@dataclass(frozen=True)
class ResearchRunSpec:
    """Explicit inputs for one security; no field may imply a symbol policy."""

    run_id: str
    symbol: str
    profile_id: str
    research_case: ResearchCase
    facts: Any
    requested_model: str | None = None
    assumptions: ValuationAssumptionSet | None = None
    quote: QuoteSnapshot | None = None
    model_validity_input: ModelValidityEvaluationInput | None = None
    valuation_approval: ResearchValuationApproval | None = None
    distribution_result: DividendResearchResult | None = None
    as_of: date | None = None
    available_at: datetime | None = None
    report_period: date | None = None
    valuation_date: date | None = None
    computed_at: datetime | None = None
    input_sources: tuple[ResearchSourceDescriptor, ...] = ()
    assumption_bindings: tuple[AssumptionScenarioBinding, ...] = ()
    rule_version: str | None = None
    model_version: str | None = None
    parser_version: str | None = None
    scan_watermark: str | None = None
    input_descriptor_sha256: str | None = None
    human_research_approval: HumanResearchApprovalReceipt | None = None
    event_materiality_review: EventMaterialityReview | None = None
    research_case_payload: Mapping[str, Any] | None = None
    facts_payload: Mapping[str, Any] | None = None
    assumptions_payload: Mapping[str, Any] | None = None
    bridge_contribution_reviews: tuple[BridgeContributionAssessment, ...] = ()
    interim_report_policy: InterimReportPolicyDecision | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("Research run id is required")
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Research run symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError(f"Unknown research profile: {self.profile_id}")
        if not isinstance(self.research_case, ResearchCase):
            raise TypeError("Research run requires a typed ResearchCase")
        if self.research_case.symbol != self.symbol:
            raise ValueError("Research case symbol does not match the run spec")
        if getattr(self.facts, "symbol", None) != self.symbol:
            raise ValueError("Research facts symbol does not match the run spec")
        if self.assumptions is not None:
            if not isinstance(self.assumptions, ValuationAssumptionSet):
                raise TypeError("Research assumptions must be typed")
            if self.assumptions.symbol != self.symbol:
                raise ValueError("Assumption symbol does not match the run spec")
            if self.assumptions.profile_id != self.profile_id:
                raise ValueError("Assumption profile does not match the run spec")
        if self.quote is not None:
            if not isinstance(self.quote, QuoteSnapshot):
                raise TypeError("Research quote must be typed")
            if self.quote.symbol != self.symbol:
                raise ValueError("Quote symbol does not match the run spec")
        if self.distribution_result is not None:
            if not isinstance(self.distribution_result, DividendResearchResult):
                raise TypeError("Research distribution must be typed")
            if self.distribution_result.symbol != self.symbol:
                raise ValueError("Distribution symbol does not match the run spec")
            if self.distribution_result.profile_id != self.profile_id:
                raise ValueError("Distribution profile does not match the run spec")
            if self.distribution_result.action != "no_order":
                raise ValueError("Research distribution must remain no_order")
        if self.available_at is not None and self.available_at.tzinfo is None:
            raise ValueError("Research available_at must include timezone")
        if self.as_of is not None and not isinstance(self.as_of, date):
            raise ValueError("Research as_of must be a date")
        facts_as_of = getattr(self.facts, "as_of", None)
        if not isinstance(facts_as_of, date):
            raise ValueError("Research facts require a typed as_of date")
        if self.as_of is not None and self.as_of != self.research_case.as_of:
            raise ValueError("Research as_of cannot override the case date")
        if self.research_case.as_of < facts_as_of:
            raise ValueError("Research case cannot precede its financial facts")
        if self.available_at is not None and self.available_at.date() < self.research_case.as_of:
            raise ValueError("Research availability cannot precede research as-of")
        if self.input_sources and self.available_at is None:
            raise ValueError("Research input sources require available_at")
        for source in self.input_sources:
            if not isinstance(source, ResearchSourceDescriptor):
                raise TypeError("Research input sources must use the shared contract")
            if (
                source.published_at is not None
                and source.published_at > self.available_at
            ):
                raise ValueError(
                    "Research source cannot be published after availability"
                )
            if (
                source.retrieved_at is not None
                and source.retrieved_at > self.available_at
            ):
                raise ValueError(
                    "Research source cannot be retrieved after availability"
                )
        if self.report_period is not None and self.report_period > facts_as_of:
            raise ValueError("Research report period cannot follow facts as-of")
        if self.valuation_date is not None and self.valuation_date != facts_as_of:
            raise ValueError("Research valuation date must match facts as-of")
        if self.computed_at is not None:
            if self.computed_at.tzinfo is None:
                raise ValueError("Research computed_at must include timezone")
            if (
                self.available_at is not None
                and self.available_at > self.computed_at
            ):
                raise ValueError("Research availability cannot follow computation")
        if self.quote is not None and self.quote.quote_date is not None:
            if self.quote.quote_date > self.research_case.as_of:
                raise ValueError("Quote date cannot follow research as-of")
        if self.model_validity_input is not None:
            if self.model_validity_input.valid_from > self.research_case.as_of:
                raise ValueError("Model validity cannot begin after research as-of")
        if self.valuation_approval is not None:
            if not isinstance(
                self.valuation_approval,
                ResearchValuationApproval,
            ):
                raise TypeError(
                    "Research valuation approval must use the shared contract"
                )
            if self.valuation_approval.valuation_date != facts_as_of:
                raise ValueError(
                    "Research valuation approval date must match facts as-of"
                )
            if (
                self.computed_at is not None
                and self.valuation_approval.approved_at > self.computed_at
            ):
                raise ValueError(
                    "Research valuation approval cannot follow computation"
                )
        if self.distribution_result is not None:
            if self.distribution_result.as_of > facts_as_of:
                raise ValueError("Distribution as-of cannot follow research as-of")
        if self.assumptions is not None and self.assumptions.as_of != facts_as_of:
            raise ValueError("Assumption as_of does not match the research facts")
        if self.rule_version is not None and not self.rule_version.strip():
            raise ValueError("Research rule_version cannot be empty")
        if self.input_descriptor_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.input_descriptor_sha256
        ):
            raise ValueError("Research input descriptor hash must be SHA-256 hex")
        if self.human_research_approval is not None:
            if not isinstance(
                self.human_research_approval,
                HumanResearchApprovalReceipt,
            ):
                raise TypeError("Human G3 approval must use the typed receipt")
            if self.human_research_approval.symbol != self.symbol:
                raise ValueError("Human G3 approval symbol does not match the run spec")
            if self.human_research_approval.action != "no_order":
                raise ValueError("Human G3 approval must remain no_order")
        if self.event_materiality_review is not None:
            if not isinstance(
                self.event_materiality_review,
                EventMaterialityReview,
            ):
                raise TypeError("Event materiality review must be typed")
            if self.event_materiality_review.symbol != self.symbol:
                raise ValueError("Event materiality symbol does not match the run spec")
            if self.event_materiality_review.action != "no_order":
                raise ValueError("Event materiality review must remain no_order")
        if self.interim_report_policy is not None:
            if not isinstance(
                self.interim_report_policy,
                InterimReportPolicyDecision,
            ):
                raise TypeError("Interim report policy must be typed")
            if self.interim_report_policy.symbol != self.symbol:
                raise ValueError("Interim report policy symbol does not match the run spec")
            if self.interim_report_policy.action != "no_order":
                raise ValueError("Interim report policy must remain no_order")
        for review in self.bridge_contribution_reviews:
            if not isinstance(review, BridgeContributionAssessment):
                raise TypeError("Bridge contribution review must be typed")
            if review.symbol != self.symbol:
                raise ValueError("Bridge contribution symbol does not match the run spec")
            if review.action != "no_order":
                raise ValueError("Bridge contribution review must remain no_order")
        if (
            self.human_research_approval is not None
            and self.valuation_approval is not None
        ):
            raise ValueError(
                "Human G3 receipt and legacy valuation approval cannot both be supplied"
            )
        object.__setattr__(self, "input_sources", tuple(self.input_sources))
        object.__setattr__(
            self,
            "assumption_bindings",
            tuple(self.assumption_bindings),
        )
        object.__setattr__(
            self,
            "bridge_contribution_reviews",
            tuple(self.bridge_contribution_reviews),
        )


@dataclass(frozen=True)
class CompanyResearchRunOutcome:
    """Complete, blocked, or unsupported result; never an execution instruction."""

    run_id: str
    symbol: str
    profile_id: str
    status: str
    route: ValuationRoute | None
    gate: ResearchGate | None
    valuation: ValuationResult | None
    assumptions: ValuationAssumptionSet | None
    model_validity: ModelValidity | None
    quote_snapshot: QuoteSnapshot | None
    price_bridge: PriceBridgeResult | None
    price_attractiveness: PriceAttractivenessAssessment | None
    distribution_result: DividendResearchResult | None
    current_status: CurrentResearchStatus | None
    blockers: tuple[str, ...]
    stored_artifacts: tuple[StoredResearchArtifact, ...]
    as_of: date
    available_at: datetime
    human_research_approval: HumanResearchApprovalReceipt | None = None
    event_materiality_review: EventMaterialityReview | None = None
    pre_decision_eligibility: PreDecisionEligibility | None = None
    bridge_contribution_reviews: tuple[BridgeContributionAssessment, ...] = ()
    interim_report_policy: InterimReportPolicyDecision | None = None

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise ValueError(f"Unknown research run status: {self.status}")
        if self.available_at.tzinfo is None:
            raise ValueError("Research outcome available_at must include timezone")
        if self.status == RUN_UNSUPPORTED:
            if not self.blockers:
                raise ValueError("An unsupported run must name its blocker")
            if any(
                (
                    self.gate,
                    self.valuation,
                    self.model_validity,
                    self.price_bridge,
                    self.price_attractiveness,
                    self.current_status,
                    self.human_research_approval,
                    self.event_materiality_review,
                    self.pre_decision_eligibility,
                    self.interim_report_policy,
                )
            ) or self.bridge_contribution_reviews:
                raise ValueError("An unsupported run cannot contain downstream artifacts")
        else:
            if self.gate is None or self.valuation is None or self.current_status is None:
                raise ValueError("A completed run requires gate, valuation and status")
            if self.symbol != self.gate.symbol or self.symbol != self.valuation.symbol:
                raise ValueError("Completed run artifacts must share one symbol")
        if self.human_research_approval is not None:
            if self.human_research_approval.symbol != self.symbol:
                raise ValueError("Completed run human approval symbol does not match")
            if self.human_research_approval.action != "no_order":
                raise ValueError("Completed run human approval must remain no_order")
        if self.event_materiality_review is not None:
            if self.event_materiality_review.symbol != self.symbol:
                raise ValueError("Completed run event review symbol does not match")
            if self.event_materiality_review.action != "no_order":
                raise ValueError("Completed run event review must remain no_order")
        if self.pre_decision_eligibility is not None:
            if self.pre_decision_eligibility.symbol != self.symbol:
                raise ValueError("Completed run predecision symbol does not match")
            if self.pre_decision_eligibility.action != "no_order":
                raise ValueError("Completed run predecision must remain no_order")


class ResearchApplicationService:
    """Application orchestration; repository and presentation stay outside Domain."""

    def __init__(
        self,
        repository: ResearchArtifactRepository | None = None,
        *,
        router: ValuationRouter | None = None,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository or InMemoryResearchArtifactRepository()
        self.router = router or ValuationRouter()
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def run_company_research(
        self,
        spec: ResearchRunSpec,
    ) -> CompanyResearchRunOutcome:
        if not isinstance(spec, ResearchRunSpec):
            raise TypeError("Research run requires a ResearchRunSpec")

        available_at = spec.available_at or self.now_utc()
        profile = PROFILES[spec.profile_id]
        route = self.router.route(profile, spec.requested_model)
        if route.status != ROUTE_SUPPORTED:
            return CompanyResearchRunOutcome(
                run_id=spec.run_id,
                symbol=spec.symbol,
                profile_id=spec.profile_id,
                status=RUN_UNSUPPORTED,
                route=route,
                gate=None,
                valuation=None,
                assumptions=spec.assumptions,
                model_validity=None,
                quote_snapshot=spec.quote,
                price_bridge=None,
                price_attractiveness=None,
                distribution_result=spec.distribution_result,
                current_status=None,
                blockers=tuple(route.blockers),
                stored_artifacts=(),
                as_of=spec.as_of or spec.research_case.as_of,
                available_at=available_at,
                human_research_approval=None,
                event_materiality_review=None,
                pre_decision_eligibility=None,
                bridge_contribution_reviews=(),
                interim_report_policy=None,
            )

        self._validate_route_contract(spec, route)
        as_of = spec.as_of or spec.research_case.as_of
        binding_blockers = validate_assumption_bindings(
            spec.facts,
            spec.assumption_bindings,
        )

        model = route.build_model()
        valuation = model.value(spec.facts, spec.research_case)
        if not isinstance(valuation, ValuationResult):
            raise TypeError("Registered model returned a non-valuation result")
        approval_decision = None
        if spec.human_research_approval is not None:
            case_payload, facts_payload, assumptions_payload = (
                self._human_approval_payloads(spec)
            )
            gate = evaluate_with_human_approval(
                spec.research_case,
                valuation,
                model_id=route.selected_model,
                approval=spec.human_research_approval,
                research_case_payload=case_payload,
                facts_payload=facts_payload,
                assumptions_payload=assumptions_payload,
            )
            approval_decision = resolve_human_research_approval(
                spec.human_research_approval,
                valuation,
                model_id=route.selected_model,
                research_case_payload=case_payload,
                facts_payload=facts_payload,
                assumptions_payload=assumptions_payload,
            )
        else:
            gate = evaluate_with_valuation(
                spec.research_case,
                valuation,
                model_id=route.selected_model,
                approval=spec.valuation_approval,
            )

        validity, quote = self._resolve_validity_and_quote(spec, valuation)
        price_bridge = self._resolve_price_bridge(
            valuation,
            validity,
            quote,
            blockers=list(validity.blockers) if validity is not None else [],
        )
        price_attractiveness = assess_price_attractiveness(
            gate,
            valuation,
            price_bridge,
            profile_id=spec.profile_id,
            human_approval_price_assessment_eligible=(
                approval_decision.price_assessment_eligible
                if approval_decision is not None else False
            ),
        )
        current_status = evaluate_current_research_status(
            gate,
            valuation,
            price_bridge,
            engineering_status=ENGINEERING_READY,
            profile_id=spec.profile_id,
            human_approval_price_assessment_eligible=(
                approval_decision.price_assessment_eligible
                if approval_decision is not None else False
            ),
        )

        pre_decision = None
        if (
            spec.human_research_approval is not None
            and spec.event_materiality_review is not None
            and validity is not None
            and price_bridge is not None
        ):
            case_payload, facts_payload, assumptions_payload = (
                self._human_approval_payloads(spec)
            )
            pre_decision = evaluate_pre_decision_eligibility(
                gate=gate,
                valuation=valuation,
                approval=spec.human_research_approval,
                model_validity=validity,
                price_bridge=price_bridge,
                event_materiality=spec.event_materiality_review,
                decision_as_of=as_of,
                model_id=route.selected_model,
                research_case_payload=case_payload,
                facts_payload=facts_payload,
                assumptions_payload=assumptions_payload,
                price_attractiveness=price_attractiveness,
            )

        blockers = tuple(
            dict.fromkeys(
                [
                    *gate.blockers,
                    *valuation.blockers,
                    *binding_blockers,
                    *price_bridge.blockers,
                    *price_attractiveness.blockers,
                    *current_status.blockers,
                    *(
                        pre_decision.blockers
                        if pre_decision is not None else []
                    ),
                    *(
                        blocker
                        for review in spec.bridge_contribution_reviews
                        for blocker in review.blockers
                    ),
                    *(
                        spec.interim_report_policy.blockers
                        if spec.interim_report_policy is not None else []
                    ),
                    *(spec.distribution_result.blockers if spec.distribution_result else []),
                    *(spec.assumptions.blockers if spec.assumptions else []),
                ]
            )
        )
        stored = self._persist_core_artifacts(
            spec=spec,
            gate=gate,
            valuation=valuation,
            validity=validity,
            quote=quote,
            price_bridge=price_bridge,
            price_attractiveness=price_attractiveness,
            current_status=current_status,
            available_at=available_at,
        )
        return CompanyResearchRunOutcome(
            run_id=spec.run_id,
            symbol=spec.symbol,
            profile_id=spec.profile_id,
            status=RUN_COMPLETED if not blockers else RUN_COMPLETED_WITH_BLOCKERS,
            route=route,
            gate=gate,
            valuation=valuation,
            assumptions=spec.assumptions,
            model_validity=validity,
            quote_snapshot=quote,
            price_bridge=price_bridge,
            price_attractiveness=price_attractiveness,
            distribution_result=spec.distribution_result,
            current_status=current_status,
            blockers=blockers,
            stored_artifacts=tuple(stored),
            as_of=as_of,
            available_at=available_at,
            human_research_approval=spec.human_research_approval,
            event_materiality_review=spec.event_materiality_review,
            pre_decision_eligibility=pre_decision,
            bridge_contribution_reviews=spec.bridge_contribution_reviews,
            interim_report_policy=spec.interim_report_policy,
        )

    def review_company_research(
        self,
        outcome: CompanyResearchRunOutcome,
        policy: FixedSampleAdmissionPolicy,
        *,
        as_of: date | None = None,
        persist: bool = True,
    ) -> FixedSampleAdmissionReview:
        if not isinstance(outcome, CompanyResearchRunOutcome):
            raise TypeError("Fixed-sample review requires a company run outcome")
        if not isinstance(policy, FixedSampleAdmissionPolicy):
            raise TypeError("Fixed-sample review requires a typed admission policy")
        if outcome.status == RUN_UNSUPPORTED:
            raise ValueError("An unsupported company run cannot be admitted for review")
        if policy.profile_id != outcome.profile_id:
            raise ValueError("Admission policy profile does not match the run outcome")
        if outcome.gate is None or outcome.valuation is None or outcome.price_bridge is None:
            raise ValueError("Fixed-sample review requires a completed company run")

        _, case_payload = artifact_payload(self._case_from_outcome(outcome))
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

        distribution_results = (
            {outcome.symbol: outcome.distribution_result}
            if outcome.distribution_result is not None
            else None
        )
        review = review_fixed_sample(
            research_records=[
                {
                    "case": case_payload,
                    "gate": gate_payload,
                }
            ],
            valuation_payloads={outcome.symbol: valuation_payload},
            policies={outcome.symbol: policy},
            as_of=as_of or outcome.as_of,
            distribution_results=distribution_results,
        )
        if persist:
            identity = ResearchArtifactIdentity(
                scope_type=SCOPE_REVIEW,
                scope_key=outcome.run_id,
                artifact_type=ARTIFACT_FIXED_SAMPLE_ADMISSION,
                schema_version=ARTIFACT_SCHEMA_VERSION,
                as_of=review.as_of,
                available_at=outcome.available_at,
            )
            self.repository.save_object(
                review,
                identity=identity,
                evidence_refs=review.evidence_refs,
                run_id=outcome.run_id,
            )
        return review

    def _validate_route_contract(
        self,
        spec: ResearchRunSpec,
        route: ValuationRoute,
    ) -> None:
        if route.status != ROUTE_SUPPORTED:
            raise ValueError("Only a supported valuation route may execute")
        if route.model_factory is None or route.facts_contract is None:
            raise ValueError("Supported valuation route is missing its model contract")
        if not isinstance(spec.facts, route.facts_contract):
            raise TypeError(
                f"{route.model_type} facts require {route.facts_contract.__name__}"
            )
        if spec.assumptions is not None and (
            spec.assumptions.model_type != route.model_type
        ):
            raise ValueError("Assumption model type does not match the routed model")

    def _resolve_validity_and_quote(
        self,
        spec: ResearchRunSpec,
        valuation: ValuationResult,
    ) -> tuple[ModelValidity | None, QuoteSnapshot | None]:
        quote = spec.quote
        if quote is None or quote.quote_date is None:
            return None, quote
        if spec.model_validity_input is None:
            return None, quote
        validity_input = spec.model_validity_input
        validity = evaluate_model_validity(
            model_id=validity_input.model_id,
            symbol=spec.symbol,
            model_as_of=valuation.valuation_date,
            valid_from=validity_input.valid_from,
            quote_date=quote.quote_date,
            events=list(validity_input.events),
            event_scan_evidence_refs=list(
                validity_input.event_scan_evidence_refs
            ),
            blockers=list(validity_input.blockers),
            event_scan=validity_input.event_scan,
            event_materiality=spec.event_materiality_review,
        )
        return validity, quote

    def _human_approval_payloads(
        self,
        spec: ResearchRunSpec,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
        """Require exact payload bindings when a human receipt is supplied."""
        if (
            spec.research_case_payload is None
            or spec.facts_payload is None
            or spec.assumptions_payload is None
        ):
            raise ValueError(
                "Human G3 approval requires exact research case, facts and assumptions payloads"
            )
        return (
            spec.research_case_payload,
            spec.facts_payload,
            spec.assumptions_payload,
        )

    def _resolve_price_bridge(
        self,
        valuation: ValuationResult,
        validity: ModelValidity | None,
        quote: QuoteSnapshot | None,
        *,
        blockers: list[str],
    ) -> PriceBridgeResult:
        if validity is not None and quote is not None:
            return bridge_with_quote(
                valuation,
                validity,
                quote,
                blockers=blockers,
            )
        if all(
            value is None
            for value in (
                valuation.bear_value,
                valuation.base_value,
                valuation.bull_value,
            )
        ):
            return pending_price_bridge_for_incomplete_valuation(
                valuation,
                evidence_refs=list(valuation.evidence_refs),
                blockers=blockers,
            )

        quote_evidence_refs = list(quote.evidence_refs) if quote is not None else []
        evidence_refs = _merge_evidence_refs(
            valuation.evidence_refs,
            quote_evidence_refs,
        )
        if quote is not None and quote.status != QUOTE_STATUS_PENDING_EXTERNAL_DATA:
            resolved_blockers = [
                *blockers,
                "verified quote requires a model validity input",
            ]
            return PriceBridgeResult(
                symbol=valuation.symbol,
                valuation_date=valuation.valuation_date,
                quote_date=quote.quote_date,
                current_price=None,
                margin_to_bear=None,
                margin_to_base=None,
                model_validity_status="UNKNOWN",
                quote_status=quote.status,
                bridge_status="INVALID",
                evidence_refs=evidence_refs,
                quote_evidence_refs=quote_evidence_refs,
                blockers=resolved_blockers,
                model_version=valuation.model_version,
                model_as_of=valuation.valuation_date,
                quote_symbol=quote.symbol,
                valuation_bear_value=valuation.bear_value,
                valuation_base_value=valuation.base_value,
            )
        return PriceBridgeResult(
            symbol=valuation.symbol,
            valuation_date=valuation.valuation_date,
            quote_date=None,
            current_price=None,
            margin_to_bear=None,
            margin_to_base=None,
            model_validity_status="UNKNOWN",
            quote_status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
            bridge_status="PENDING_EXTERNAL_DATA",
            evidence_refs=evidence_refs,
            quote_evidence_refs=quote_evidence_refs,
            blockers=[*blockers, "等待已验证收盘行情"],
            model_version=valuation.model_version,
            model_as_of=valuation.valuation_date,
            quote_symbol=valuation.symbol,
            valuation_bear_value=valuation.bear_value,
            valuation_base_value=valuation.base_value,
        )

    def _persist_core_artifacts(
        self,
        *,
        spec: ResearchRunSpec,
        gate: ResearchGate,
        valuation: ValuationResult,
        validity: ModelValidity | None,
        quote: QuoteSnapshot | None,
        price_bridge: PriceBridgeResult,
        price_attractiveness: PriceAttractivenessAssessment,
        current_status: CurrentResearchStatus,
        available_at: datetime,
    ) -> list[StoredResearchArtifact]:
        stored: list[StoredResearchArtifact] = []

        def save(
            value: Any,
            artifact_type: str,
            as_of: date | None,
            evidence_refs: Sequence[Mapping[str, Any]],
        ) -> None:
            identity = ResearchArtifactIdentity(
                scope_type=SCOPE_SECURITY,
                scope_key=spec.symbol,
                artifact_type=artifact_type,
                schema_version=ARTIFACT_SCHEMA_VERSION,
                as_of=as_of,
                available_at=available_at,
            )
            stored.append(
                self.repository.save_object(
                    value,
                    identity=identity,
                    evidence_refs=evidence_refs,
                    run_id=spec.run_id,
                )
            )

        save(
            spec.research_case,
            ARTIFACT_RESEARCH_CASE,
            spec.research_case.as_of,
            spec.research_case.evidence_refs,
        )
        gate_evidence_refs = _merge_evidence_refs(
            spec.research_case.evidence_refs,
            spec.valuation_approval.evidence_refs
            if spec.valuation_approval is not None
            else (),
        )
        save(
            gate,
            ARTIFACT_RESEARCH_GATE,
            spec.research_case.as_of,
            gate_evidence_refs,
        )
        if spec.assumptions is not None:
            save(
                spec.assumptions,
                ARTIFACT_VALUATION_ASSUMPTIONS,
                spec.assumptions.as_of,
                spec.assumptions.evidence_refs,
            )
        save(
            valuation,
            ARTIFACT_VALUATION_RESULT,
            valuation.valuation_date,
            valuation.evidence_refs,
        )
        if validity is not None:
            save(
                validity,
                ARTIFACT_MODEL_VALIDITY,
                validity.model_as_of,
                validity.evidence_refs,
            )
        if quote is not None:
            save(
                quote,
                ARTIFACT_QUOTE_SNAPSHOT,
                quote.quote_date,
                quote.evidence_refs,
            )
        save(
            price_bridge,
            ARTIFACT_PRICE_BRIDGE,
            valuation.valuation_date,
            price_bridge.evidence_refs,
        )
        save(
            price_attractiveness,
            ARTIFACT_PRICE_ATTRACTIVENESS,
            valuation.valuation_date,
            price_attractiveness.evidence_refs,
        )
        if spec.distribution_result is not None:
            save(
                spec.distribution_result,
                ARTIFACT_DIVIDEND_RESEARCH,
                spec.distribution_result.as_of,
                spec.distribution_result.evidence_refs,
            )
        save(
            current_status,
            ARTIFACT_CURRENT_RESEARCH_STATUS,
            valuation.valuation_date,
            current_status.evidence_refs,
        )
        return stored

    @staticmethod
    def _facts_as_of(spec: ResearchRunSpec) -> date:
        value = getattr(spec.facts, "as_of", None)
        if not isinstance(value, date):
            raise ValueError("Research facts require a typed as_of date")
        return value

    @staticmethod
    def _case_as_of(spec: ResearchRunSpec) -> date:
        return spec.research_case.as_of

    @staticmethod
    def _case_from_outcome(outcome: CompanyResearchRunOutcome) -> ResearchCase:
        # The run spec itself is not retained; restore the persisted canonical
        # case so the review never depends on mutable caller state.
        for stored in outcome.stored_artifacts:
            if (
                stored.envelope.identity.artifact_type
                == ARTIFACT_RESEARCH_CASE
            ):
                return decode_artifact(
                    ARTIFACT_RESEARCH_CASE,
                    stored.envelope.payload_object(),
                )
        raise ValueError("Completed research outcome has no persisted ResearchCase")
