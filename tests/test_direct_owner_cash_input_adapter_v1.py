"""TEST_ONLY descriptor -> shared spec/service -> persisted bundle integration."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from test_direct_owner_cash_v1 import facts
from test_research_application import quality_spec
from value_investment_agent.application.research import direct_owner_cash_input_adapter_v1 as adapter
from value_investment_agent.valuation_models.direct_owner_cash_v1 import (
    MODEL_ID, MODEL_VERSION, DirectOwnerCashScenario, facts_to_payload, facts_from_payload,
)
from value_investment_agent.research_input import build_research_run_spec, descriptor_sha256
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_artifacts import (
    ARTIFACT_FINANCIAL_FACTS, ARTIFACT_RESEARCH_CASE, ResearchArtifactIdentity, SCOPE_SECURITY,
)

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def package():
    spec, _ = quality_spec(run_id="TEST_ONLY_direct_adapter")
    f = facts(evidence_refs=spec.facts.evidence_refs)
    c = replace(spec.research_case, research_version="TEST_ONLY_direct_adapter",
                run_id="TEST_ONLY_direct_adapter")
    financial = facts_to_payload(f)
    financial["kind"] = financial.pop("facts_type")
    # These are expressly synthetic pins, not a claim of official-source replay.
    return dict(
        schema_version="m1-valuation-package-v2", descriptor_version=adapter.DESCRIPTOR_VERSION,
        symbol=spec.symbol, name=c.name, profile_id=spec.profile_id, requested_model=MODEL_ID,
        run_id=spec.run_id, research_case=artifact_payload(c)[1], facts=financial,
        point_in_time=dict(report_period=f.as_of.isoformat(), research_as_of=c.as_of.isoformat(),
            valuation_date=f.as_of.isoformat(), available_at=spec.available_at.isoformat(),
            computed_at=spec.available_at.isoformat()),
        dependencies=dict(rule_version="TEST_ONLY_direct_adapter", model_id=MODEL_ID,
                          model_version=MODEL_VERSION, parser_version="TEST_ONLY"),
        sources=[s.as_policy() for s in spec.input_sources], assumptions=None,
        assumption_bindings=[dict(assumption_name="actual_retention", scenario="base",
            field_path="forecast_retentions.0", expected_value="0",
            evidence_refs=[{"id": "facts"}])],
        source_contract=dict(schema_version="TEST_ONLY_direct_source_contract_v1",
                             scope="TEST_ONLY_NOT_OFFICIAL_EVIDENCE", binding_sha256="c" * 64),
    )


def test_package_descriptor_roundtrip_and_shared_spec_keep_all_inputs():
    p = package()
    before = deepcopy(p)
    desc = adapter.build_direct_owner_cash_descriptor(p)
    policy = desc.as_policy()
    restored = adapter.descriptor_from_payload(json.loads(json.dumps(policy)))
    assert restored.as_policy() == policy
    assert desc.input_sha256 == descriptor_sha256(desc) == restored.input_sha256
    spec = build_research_run_spec(restored)
    assert spec.model_version == MODEL_VERSION
    assert spec.input_descriptor_sha256 == desc.input_sha256
    assert spec.facts_payload is None  # No evidence-ref/raw side channel.
    assert isinstance(spec.facts.scenario_inputs["base"], DirectOwnerCashScenario)
    for name in ("bear", "base", "bull"):
        for field in ("opening", "years", "terminal"):
            assert policy["facts"]["scenario_inputs"][name][field] == p["facts"]["scenario_inputs"][name][field]
    assert spec.assumption_bindings[0].expected_value == "0"
    assert spec.source_contract_payload == p["source_contract"]
    assert p == before


@pytest.mark.parametrize("field", ["opening", "years", "terminal", "source_contract"])
def test_hash_covers_direct_raw_and_source_contract(field):
    p = package()
    original = adapter.build_direct_owner_cash_descriptor(p)
    changed = deepcopy(p)
    if field == "source_contract":
        changed[field]["binding_sha256"] = "d" * 64
    else:
        branch = changed["facts"]["scenario_inputs"]["base"]
        if field == "opening": branch[field]["capacity"] = "1"
        if field == "years": branch[field][0]["policy"]["investment_cash_received"] = "1"
        if field == "terminal": branch[field]["rationale"] += " changed"
    newer = adapter.build_direct_owner_cash_descriptor(changed)
    assert newer.input_sha256 != original.input_sha256
    stale = newer.as_policy() | {"input_sha256": original.input_sha256}
    with pytest.raises(ValueError, match="hash does not match"):
        adapter.descriptor_from_payload(stale)


def test_actual_service_saves_restorable_financial_facts_and_bundle():
    from value_investment_agent.application.product.company_research import _serialize_outcome
    from value_investment_agent.valuation_models.direct_owner_cash_v1 import DirectOwnerCashValuationModel

    repository = adapter.DirectOwnerCashResearchRepository()
    outcome, descriptor = adapter.run_direct_owner_cash_research(package(), NOW, repository=repository)
    assert outcome.valuation.model_version == MODEL_VERSION
    assert outcome.valuation.status == "conditional_research_only"
    assert outcome.valuation.base_value == 10
    assert outcome.decision_recommendation.action == "no_order"
    assert outcome.decision_recommendation.position_guidance is None
    saved = repository.load_latest(SCOPE_SECURITY, descriptor.symbol, ARTIFACT_FINANCIAL_FACTS)
    payload = saved.envelope.payload_object()
    assert payload == descriptor.as_policy()["facts"]
    assert payload["direct_owner_cash_contract"] == MODEL_VERSION
    assert "retention_contract" not in payload["scenario_inputs"]["base"]
    assert repository.load_by_hash(saved.envelope.payload_sha256)[0] == saved
    restored = facts_from_payload(payload)
    assert DirectOwnerCashValuationModel().value(restored, descriptor.research_case) == outcome.valuation
    exported = _serialize_outcome(outcome)
    item = next(x for x in exported["artifact_bundle"]["artifacts"]
                if x["identity"]["artifact_type"] == ARTIFACT_FINANCIAL_FACTS)
    assert json.loads(item["canonical_payload"]) == payload
    # Ordinary case and all service decisions still use inherited storage.
    assert repository.load_latest(SCOPE_SECURITY, descriptor.symbol, ARTIFACT_RESEARCH_CASE)


def test_thin_repository_leaves_legacy_and_other_artifacts_unchanged():
    spec, _ = quality_spec(run_id="TEST_ONLY_legacy_passthrough")
    repo, legacy = adapter.DirectOwnerCashResearchRepository(), InMemoryResearchArtifactRepository()
    for value, kind in ((spec.facts, ARTIFACT_FINANCIAL_FACTS), (spec.research_case, ARTIFACT_RESEARCH_CASE)):
        kwargs = dict(identity=ResearchArtifactIdentity(
            scope_type=SCOPE_SECURITY, scope_key=spec.symbol, artifact_type=kind,
            schema_version="1", as_of=value.as_of, available_at=spec.available_at),
            run_id=spec.run_id, evidence_refs=value.evidence_refs)
        actual, expected = repo.save_object(value, **kwargs), legacy.save_object(value, **kwargs)
        assert actual.envelope == expected.envelope


def test_repository_rejects_mixed_direct_contracts_and_wrong_artifact_type():
    spec, _ = quality_spec(run_id="TEST_ONLY_rejected_repository")
    direct = facts()
    repo = adapter.DirectOwnerCashResearchRepository()
    identity = ResearchArtifactIdentity(scope_type=SCOPE_SECURITY, scope_key=direct.symbol,
        artifact_type=ARTIFACT_FINANCIAL_FACTS, schema_version="1", as_of=direct.as_of,
        available_at=spec.available_at)
    mixed = replace(direct, scenario_inputs=direct.scenario_inputs | {"bull": spec.facts.scenario_inputs["bull"]})
    with pytest.raises(TypeError, match="TYPED_FACTS"):
        repo.save_object(mixed, identity=identity, run_id=spec.run_id)
    with pytest.raises(ValueError, match="ARTIFACT_IDENTITY_MISMATCH"):
        repo.save_object(direct, identity=replace(identity, artifact_type=ARTIFACT_RESEARCH_CASE), run_id=spec.run_id)
    assert repo.list_versions(SCOPE_SECURITY, direct.symbol, ARTIFACT_FINANCIAL_FACTS) == []


@pytest.mark.parametrize("change", ["model", "descriptor", "mode", "timing", "hash", "approval", "legacy_source"])
def test_package_rejects_inconsistent_versions_and_authority(change):
    p = package()
    if change == "model": p["dependencies"]["model_version"] = "residual-income-equity-path-v2"
    if change == "descriptor": p["descriptor_version"] = "old"
    if change == "mode": p["research_mode"] = "research_only"
    if change == "timing": p["facts"]["valuation_timing"] = dict(basis_at="2025-01-01T00:00:00+08:00",
        valuation_at="2025-06-01T00:00:00+08:00", evidence_refs=[dict(id="timing")])
    if change == "hash": p["input_sha256"] = "0" * 64
    if change == "approval": p["valuation_approval"] = {}
    if change == "legacy_source": p["source_contract"]["schema_version"] = "source-bound-research-inputs-v1"
    with pytest.raises(ValueError):
        adapter.build_direct_owner_cash_descriptor(p)


def test_test_only_runner_checks_mode_hash_clock_and_repository():
    desc = adapter.build_direct_owner_cash_descriptor(package())
    result = adapter.run_test_only_direct_owner_cash(desc, execution_mode="TEST_ONLY", now_utc=lambda: NOW)
    assert result.valuation.base_value == 10
    with pytest.raises(ValueError, match="TEST_ONLY_REQUIRED"):
        adapter.run_test_only_direct_owner_cash(desc, execution_mode="LIVE")
    with pytest.raises(TypeError, match="VERSIONED_REPOSITORY"):
        adapter.run_test_only_direct_owner_cash(desc, execution_mode="TEST_ONLY", repository=InMemoryResearchArtifactRepository())
    with pytest.raises(ValueError, match="NOT_AVAILABLE"):
        adapter.run_direct_owner_cash_research(package(), datetime(2025, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="NOT_AVAILABLE"):
        adapter.run_direct_owner_cash_research(package(), NOW.replace(tzinfo=None))
    desc.facts.scenario_inputs["base"].terminal["rationale"] = "mutated"
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        adapter.run_test_only_direct_owner_cash(desc, execution_mode="TEST_ONLY", now_utc=lambda: NOW)


def test_sealed_reader_rejects_unknown_fields_and_missing_hash():
    policy = adapter.build_direct_owner_cash_descriptor(package()).as_policy()
    with pytest.raises(ValueError, match="ROUNDTRIP_CHANGED"):
        adapter.descriptor_from_payload(policy | {"ignored_raw_input": "must not disappear"})
    with pytest.raises(ValueError, match="SEALED_DESCRIPTOR_REQUIRED"):
        adapter.descriptor_from_payload(policy | {"input_sha256": None})


def test_root_compilation_diagnostics_cannot_supply_final_valuation(monkeypatch):
    from value_investment_agent.valuation_models import direct_owner_cash_v1 as model

    p = package()
    for row in p["facts"]["scenario_inputs"].values():
        row.pop("scenario_contract")
        row["calculation"] = {"per_share_value": "999999999", "conditional_equity_value_cny": "1"}
    original = deepcopy(p)
    calls = []
    compiler = model.compile_direct_owner_cash_path

    def observed(**kwargs):
        calls.append(kwargs)
        return compiler(**kwargs)

    monkeypatch.setattr(model, "compile_direct_owner_cash_path", observed)
    outcome, descriptor = adapter.run_direct_owner_cash_research(p, NOW)
    assert len(calls) == 3
    assert outcome.valuation.base_value == 10
    assert p == original
    assert "calculation" not in descriptor.as_policy()["facts"]["scenario_inputs"]["base"]
    changed = deepcopy(p)
    changed["facts"]["scenario_inputs"]["base"]["calculation"] = {}
    assert adapter.build_direct_owner_cash_descriptor(changed).input_sha256 == descriptor.input_sha256
    # Raw cash remains authoritative and must agree with the declared annual path.
    changed["facts"]["scenario_inputs"]["base"]["years"][0]["policy"]["operating_cash"] = "50"
    with pytest.raises(ValueError, match="ANNUAL_VECTOR_MISMATCH"):
        adapter.run_direct_owner_cash_research(changed, NOW)


@pytest.mark.parametrize("change", ["extra", "missing", "not_mapping"])
def test_root_compilation_shape_is_explicit(change):
    row = deepcopy(package()["facts"]["scenario_inputs"]["base"])
    row.pop("scenario_contract")
    row["calculation"] = {}
    if change == "extra": row["hidden_cash"] = "1"
    if change == "missing": row.pop("terminal")
    if change == "not_mapping": row["calculation"] = "1"
    with pytest.raises(ValueError, match="EXACT_COMPILATION_SCENARIO"):
        adapter.scenario_from_compilation(row)
