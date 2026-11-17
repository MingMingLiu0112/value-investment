"""Opt-in direct-owner input/persistence adapter, outside frozen shared codecs.

This module binds typed inputs to their complete descriptor hash; it does not
authenticate issuer filings or admit a public research candidate. Root's E2
source validator owns those gates. The convenience runner is TEST_ONLY.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ...research_application import CompanyResearchRunOutcome, ResearchApplicationService
from ...research_artifact_repository import InMemoryResearchArtifactRepository
from ...research_artifacts import (
    ARTIFACT_FINANCIAL_FACTS, ResearchArtifactEnvelope, ResearchArtifactIdentity,
    StoredResearchArtifact,
)
from ...research_input import (
    ResearchInputDescriptor, build_research_run_spec, descriptor_sha256,
    finalize_input_descriptor, descriptor_from_payload as legacy_descriptor_from_payload,
)
from ...research_run_contract import (
    INPUT_DESCRIPTOR_SCHEMA, AssumptionScenarioBinding, canonical_contract_payload,
)
from ...valuation_models.direct_owner_cash_v1 import (
    MODEL_ID, MODEL_VERSION, DirectOwnerCashScenario, build_direct_owner_cash_router,
    SCENARIO_CONTRACT, scenario_to_payload, scenario_from_payload,
    facts_to_payload, facts_from_payload,
)
from ...valuation_models.residual_income import QualityCompounderFacts

DESCRIPTOR_VERSION = "direct-owner-cash-input-v1"


def scenario_from_compilation(payload: Mapping[str, Any]) -> DirectOwnerCashScenario:
    """Adapt Root's exact compiler output; its calculation is diagnostic only.

    No upstream price/equity result is copied to model inputs. The model will
    independently compile raw policies and check both annual vectors again.
    Root's replay/receipt owns retention and comparison of the diagnostic result.
    """
    expected = {"symbol", "opening", "years", "terminal", "ordinary_shares",
                "cost_of_equity", "currency", "scope", "forecast_roes",
                "forecast_retentions", "calculation"}
    if (not isinstance(payload, Mapping) or set(payload) != expected
            or not isinstance(payload["calculation"], Mapping)):
        raise ValueError("DIRECT_OWNER_EXACT_COMPILATION_SCENARIO_REQUIRED")
    data = deepcopy(dict(payload))
    data.pop("calculation")
    data["scenario_contract"] = SCENARIO_CONTRACT
    return scenario_from_payload(data)


class DirectOwnerCashDescriptor(ResearchInputDescriptor):
    """Shared metadata, but complete versioned direct facts in its hashed policy."""

    def __post_init__(self) -> None:
        if (self.descriptor_version != DESCRIPTOR_VERSION
                or self.dependencies.model_version != MODEL_VERSION
                or self.dependencies.model_id != MODEL_ID
                or self.requested_model != MODEL_ID or self.research_mode != "valuation"):
            raise ValueError("DIRECT_OWNER_EXPLICIT_DESCRIPTOR_VERSION_REQUIRED")
        # Reject legacy v1's deliberate source-contract hash exclusion.
        if (self.source_contract is not None and self.source_contract.as_policy().get("schema_version")
                == "source-bound-research-inputs-v1"):
            raise ValueError("DIRECT_OWNER_LEGACY_SOURCE_HASH_EXCLUSION_UNSUPPORTED")
        # Detach raw mutable inputs while validating the explicit facts contract.
        object.__setattr__(self, "facts", facts_from_payload(facts_to_payload(self.facts)))
        super().__post_init__()

    def as_policy(self) -> dict[str, Any]:
        payload = super().as_policy()
        # The shared metadata serializer is retained, but its V2 facts projection
        # never leaves this method and is never used for the descriptor hash.
        payload["facts"] = facts_to_payload(self.facts)
        return payload


def build_direct_owner_cash_descriptor_from_fields(
    *, facts: QualityCompounderFacts, **descriptor_fields: Any,
) -> DirectOwnerCashDescriptor:
    """Finalize shared ResearchInputDescriptor fields with exact direct facts.

    Required metadata is the shared constructor's metadata. Only schema and
    descriptor versions default here; callers must explicitly declare the model
    dependency and requested model. A supplied hash must already match.
    """
    values = dict(descriptor_fields)
    values.setdefault("schema_version", INPUT_DESCRIPTOR_SCHEMA)
    values.setdefault("descriptor_version", DESCRIPTOR_VERSION)
    descriptor = DirectOwnerCashDescriptor(facts=facts, **values)
    return finalize_input_descriptor(descriptor)


def _from_policy(payload: Mapping[str, Any]) -> DirectOwnerCashDescriptor:
    original = deepcopy(dict(payload))
    direct_facts = facts_from_payload(original["facts"])
    metadata = deepcopy(original)
    # Parse shared metadata only. No surrogate scenario or terminal is invented.
    metadata["facts"].pop("direct_owner_cash_contract")
    metadata["facts"]["scenario_inputs"] = None
    metadata["assumption_bindings"] = []
    metadata["input_sha256"] = None
    parsed = legacy_descriptor_from_payload(metadata)
    values = {item.name: getattr(parsed, item.name) for item in fields(ResearchInputDescriptor)}
    values.update(facts=direct_facts, input_sha256=original.get("input_sha256"),
                  assumption_bindings=tuple(AssumptionScenarioBinding(**item)
                      for item in original.get("assumption_bindings", [])))
    descriptor = DirectOwnerCashDescriptor(**values)
    return finalize_input_descriptor(descriptor)


def descriptor_from_payload(payload: Mapping[str, Any]) -> DirectOwnerCashDescriptor:
    """Restore a sealed direct policy; reject stale hashes or lossy metadata."""
    if not isinstance(payload, Mapping) or not payload.get("input_sha256"):
        raise ValueError("DIRECT_OWNER_SEALED_DESCRIPTOR_REQUIRED")
    original = deepcopy(dict(payload))
    descriptor = _from_policy(original)
    if canonical_contract_payload(descriptor.as_policy()) != canonical_contract_payload(original):
        raise ValueError("DIRECT_OWNER_DESCRIPTOR_ROUNDTRIP_CHANGED")
    return descriptor


def build_direct_owner_cash_descriptor(
    package: Mapping[str, Any], root: Path | None = None,
) -> DirectOwnerCashDescriptor:
    """Parse an m1-v2-shaped package; Root owns source-byte/economic admission.

    ``root`` is API-compatible context only: this adapter performs no disk reads
    or writes and does not claim source verification. Package facts may use
    ``kind`` or ``facts_type``; scenario contracts and model versions are exact.
    Quote/approval/distribution inputs are deliberately outside this lane.
    """
    from ...m1_valuation_package_builder import build_research_case, build_assumptions
    from ...research_artifact_codecs import artifact_payload

    if not isinstance(package, Mapping) or package.get("schema_version") != "m1-valuation-package-v2":
        raise ValueError("DIRECT_OWNER_M1_V2_PACKAGE_REQUIRED")
    data = deepcopy(dict(package))
    if any(data.get(key) is not None for key in (
            "quote", "valuation_approval", "distribution_result", "model_validity_input",
            "human_research_approval", "event_materiality_review", "entry_thesis",
            "investment_consistency_review", "valuation", "price_bridge", "position_guidance")):
        raise ValueError("DIRECT_OWNER_CONDITIONAL_RESEARCH_INPUTS_ONLY")
    if data.get("research_mode", "valuation") != "valuation":
        raise ValueError("DIRECT_OWNER_VALUATION_MODE_REQUIRED")
    financial = deepcopy(data["facts"])
    if financial.pop("kind", "quality_compounder") != "quality_compounder":
        raise ValueError("DIRECT_OWNER_QUALITY_FACTS_REQUIRED")
    financial.setdefault("facts_type", "quality_compounder")
    financial.setdefault("direct_owner_cash_contract", MODEL_VERSION)
    scenarios = financial.get("scenario_inputs")
    if isinstance(scenarios, Mapping):
        financial["scenario_inputs"] = {
            name: (scenario_to_payload(scenario_from_compilation(row))
                   if isinstance(row, Mapping) and "calculation" in row else row)
            for name, row in scenarios.items()
        }
    direct_facts = facts_from_payload(financial)
    case = build_research_case(data["research_case"])
    assumptions = (None if data.get("assumptions") is None else build_assumptions(
        data["assumptions"], symbol=data["symbol"], profile_id=data["profile_id"],
        model_type=MODEL_ID, as_of=direct_facts.as_of))
    dependencies = deepcopy(data["dependencies"])
    dependencies.setdefault("profile_id", data["profile_id"])
    policy = dict(
        schema_version=INPUT_DESCRIPTOR_SCHEMA,
        descriptor_version=data.get("descriptor_version", DESCRIPTOR_VERSION),
        symbol=data["symbol"], name=data["name"], profile_id=data["profile_id"],
        requested_model=data["requested_model"], run_id=data["run_id"],
        point_in_time=data["point_in_time"], dependencies=dependencies,
        sources=data.get("sources", []), research_case=artifact_payload(case)[1],
        facts=facts_to_payload(direct_facts),
        assumptions=artifact_payload(assumptions)[1] if assumptions is not None else None,
        assumption_bindings=data.get("assumption_bindings", []),
        distribution_result=None, quote=None, model_validity_input=None,
        valuation_approval=None, blockers=data.get("blockers", []),
        input_sha256=data.get("input_sha256"),
    )
    for key in ("source_contract", "recommendation_schema_version"):
        if key in data:
            policy[key] = data[key]
    return _from_policy(policy)


class DirectOwnerCashResearchRepository(InMemoryResearchArtifactRepository):
    """Same in-memory store/envelopes; only direct facts use an explicit codec."""

    def save_object(
        self, value: Any, *, identity: ResearchArtifactIdentity,
        evidence_refs: Sequence[dict[str, Any]] = (), run_id: str,
        advance_head: bool = True,
    ) -> StoredResearchArtifact:
        direct = (isinstance(value, QualityCompounderFacts)
                  and isinstance(value.scenario_inputs, dict)
                  and any(isinstance(item, DirectOwnerCashScenario)
                          for item in value.scenario_inputs.values()))
        if not direct:
            return super().save_object(value, identity=identity, evidence_refs=evidence_refs,
                                      run_id=run_id, advance_head=advance_head)
        if identity.artifact_type != ARTIFACT_FINANCIAL_FACTS:
            raise ValueError("DIRECT_OWNER_FACTS_ARTIFACT_IDENTITY_MISMATCH")
        # Mixed/incomplete direct scenarios fail in facts_to_payload; never fall
        # back to the frozen V2 serializer after detecting a direct input.
        envelope = ResearchArtifactEnvelope.build(
            identity=identity, payload=facts_to_payload(value),
            evidence_refs=evidence_refs, run_id=run_id,
        )
        return self.save(envelope, advance_head=advance_head)


def run_direct_owner_cash_research(
    package: Mapping[str, Any], now: datetime, *, root: Path | None = None,
    repository: DirectOwnerCashResearchRepository | None = None,
) -> tuple[CompanyResearchRunOutcome, DirectOwnerCashDescriptor]:
    """Shared-service conditional execution with full direct-facts persistence.

    Returns ``(outcome, descriptor)``. This is not a source replay/receipt or a
    public admission: the caller must verify the package against original bytes.
    """
    descriptor = build_direct_owner_cash_descriptor(package, root=root)
    if now.utcoffset() is None or descriptor.point_in_time.computed_at > now:
        raise ValueError("DIRECT_OWNER_INPUT_NOT_AVAILABLE_AT_CLOCK")
    if repository is not None and not isinstance(repository, DirectOwnerCashResearchRepository):
        raise TypeError("DIRECT_OWNER_VERSIONED_REPOSITORY_REQUIRED")
    outcome = ResearchApplicationService(
        repository=repository if repository is not None else DirectOwnerCashResearchRepository(),
        router=build_direct_owner_cash_router(), now_utc=lambda: now,
    ).run_company_research(build_research_run_spec(descriptor))
    return outcome, descriptor


def run_test_only_direct_owner_cash(
    descriptor: DirectOwnerCashDescriptor, *, execution_mode: str,
    repository: DirectOwnerCashResearchRepository | None = None,
    now_utc: Callable[[], datetime] | None = None,
) -> CompanyResearchRunOutcome:
    """Run synthetic integration only; never source-admit, quote, approve or publish."""
    if execution_mode != "TEST_ONLY":
        raise ValueError("DIRECT_OWNER_TEST_ONLY_REQUIRED")
    if not isinstance(descriptor, DirectOwnerCashDescriptor):
        raise TypeError("DIRECT_OWNER_TYPED_DESCRIPTOR_REQUIRED")
    if (not descriptor.run_id.startswith("TEST_ONLY")
            or not descriptor.research_case.research_version.startswith("TEST_ONLY")):
        raise ValueError("DIRECT_OWNER_SYNTHETIC_IDENTITY_REQUIRED")
    if any(getattr(descriptor, key) is not None for key in (
            "quote", "valuation_approval", "model_validity_input", "distribution_result",
            "entry_thesis", "investment_consistency_review")):
        raise ValueError("DIRECT_OWNER_TEST_ONLY_RESEARCH_INPUTS_REQUIRED")
    if repository is not None and not isinstance(repository, DirectOwnerCashResearchRepository):
        raise TypeError("DIRECT_OWNER_VERSIONED_REPOSITORY_REQUIRED")
    if descriptor.input_sha256 is None or descriptor.input_sha256 != descriptor_sha256(descriptor):
        raise ValueError("DIRECT_OWNER_DESCRIPTOR_HASH_CHANGED")
    clock = now_utc or (lambda: datetime.now(timezone.utc))
    now = clock()
    if now.utcoffset() is None or descriptor.point_in_time.computed_at > now:
        raise ValueError("DIRECT_OWNER_INPUT_NOT_AVAILABLE_AT_TEST_CLOCK")
    # Restore a detached exact-hash snapshot before running the shared service.
    snapshot = descriptor_from_payload(descriptor.as_policy())
    return ResearchApplicationService(
        repository=repository if repository is not None else DirectOwnerCashResearchRepository(),
        router=build_direct_owner_cash_router(), now_utc=lambda: now,
    ).run_company_research(build_research_run_spec(snapshot))
