from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.research_application import ResearchRunSpec
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_BATCH_RUN_RESULT,
    ARTIFACT_VALUATION_RESULT,
    SCOPE_BATCH,
    SCOPE_SECURITY,
)
from value_investment_agent.research_batch import (
    BATCH_COMPLETED_WITH_BLOCKERS,
    BATCH_FAILED,
    BATCH_GAP,
    BATCH_PARTIAL,
    BATCH_UNCHANGED,
    BATCH_UNSUPPORTED,
    build_batch_spec_from_descriptor_payloads,
    ResearchBatchCompanySpec,
    ResearchBatchResult,
    ResearchBatchService,
    ResearchBatchSpec,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_input import (
    ResearchInputDescriptor,
    descriptor_from_payload,
    finalize_input_descriptor,
)
from value_investment_agent.research_run_contract import (
    ResearchDependencyFingerprint,
    ResearchPitFrame,
    ResearchSourceDescriptor,
)
from value_investment_agent.valuation_models.cyclical import CyclicalFacts
from value_investment_agent.valuation_models.fcff import FinancialFacts
from value_investment_agent.valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


AS_OF = date(2025, 12, 31)
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def case(symbol: str) -> ResearchCase:
    return ResearchCase(
        symbol=symbol,
        name=f"公司{symbol}",
        as_of=AS_OF,
        run_id="fixture",
        generated_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
        research_version="v1",
        industry="测试",
        investment_path="测试路径",
        thesis="测试论点",
        return_driver="测试驱动",
        mispricing_hypothesis="未证明",
        financial_summary={"period_end": "2025-12-31"},
        positives=[],
        counter_evidence=[],
        thesis_breakers=[],
        next_events=[],
        evidence_status="partial",
        valuation_status="not_ready",
        research_status="financial_scope_blocked",
        blockers=[],
        evidence_refs=[{"id": "case", "path": "case.json", "sha256": "a" * 64}],
        quote_date=None,
        financial_period=AS_OF,
        missing_date_reasons={"quote_date": "not used"},
    )


def residual_facts() -> QualityCompounderFacts:
    return QualityCompounderFacts(
        symbol="600519",
        as_of=AS_OF,
        verified=True,
        confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "b" * 64}],
        blockers=[],
        operating_inputs={
            "start_book_equity": D("1000"),
            "ordinary_shares": D("100"),
        },
        scenario_inputs={
            "bear": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.08"),
                terminal_growth=D("0.02"),
            ),
            "base": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.10"),
                terminal_growth=D("0.02"),
            ),
            "bull": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.12"),
                terminal_growth=D("0.02"),
            ),
        },
    )


def quality_spec(*, fingerprint: str | None = None) -> ResearchRunSpec:
    return ResearchRunSpec(
        run_id="input-600519",
        symbol="600519",
        profile_id="quality_compounder",
        research_case=case("600519"),
        facts=residual_facts(),
        available_at=NOW,
    )


def descriptor_payload() -> dict:
    descriptor = ResearchInputDescriptor(
        schema_version="m1-fixed-sample-input-v1",
        descriptor_version="batch-descriptor-fixture-v1",
        symbol="600519",
        name="贵州茅台",
        profile_id="quality_compounder",
        requested_model=None,
        run_id="descriptor-input-600519",
        point_in_time=ResearchPitFrame(
            report_period=AS_OF,
            research_as_of=AS_OF,
            valuation_date=AS_OF,
            available_at=NOW,
            computed_at=NOW,
        ),
        dependencies=ResearchDependencyFingerprint(
            rule_version="research-batch-v1",
            profile_id="quality_compounder",
            model_id="residual_income_or_equity_value",
            model_version="residual-income-equity-shared-v1",
            parser_version="parser-v1",
            scan_watermark="scan-v1",
        ),
        sources=(
            ResearchSourceDescriptor(
                id="facts-source",
                kind="filing",
                location="tests/fixtures/facts.json",
                sha256="d" * 64,
                published_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
                parser_version="parser-v1",
            ),
        ),
        research_case=case("600519"),
        facts=residual_facts(),
        assumptions=None,
        assumption_bindings=(),
        distribution_result=None,
        quote=None,
        model_validity_input=None,
        valuation_approval=None,
    )
    return finalize_input_descriptor(descriptor).as_policy()


def descriptor_payload_with_dependencies(**changes: str) -> dict:
    payload = descriptor_payload()
    payload["dependencies"] = {
        **payload["dependencies"],
        **changes,
    }
    payload.pop("input_sha256", None)
    return descriptor_from_payload(payload).as_policy()


def fcff_gap_spec(*, fingerprint: str | None = None) -> ResearchRunSpec:
    return ResearchRunSpec(
        run_id="input-000333",
        symbol="000333",
        profile_id="mature_manufacturing",
        research_case=case("000333"),
        facts=FinancialFacts(
            symbol="000333",
            as_of=AS_OF,
            verified=False,
            evidence_refs=[{"id": "facts", "path": "facts.json"}],
            blockers=["shares_not_verified"],
        ),
        available_at=NOW,
    )


def cyclical_gap_spec() -> ResearchRunSpec:
    return ResearchRunSpec(
        run_id="input-601088",
        symbol="601088",
        profile_id="cyclical_cash_return",
        research_case=case("601088"),
        facts=CyclicalFacts(
            symbol="601088",
            as_of=AS_OF,
            verified=False,
            confidence="低",
            evidence_refs=[{"id": "facts", "path": "facts.json"}],
            blockers=["cycle_inputs_not_verified"],
        ),
        available_at=NOW,
    )


@dataclass(frozen=True)
class BadFacts:
    symbol: str
    as_of: date


def test_batch_isolates_gaps_unsupported_routes_and_unexpected_failures():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    companies = (
        ResearchBatchCompanySpec(quality_spec(), "1" * 64),
        ResearchBatchCompanySpec(fcff_gap_spec(), "2" * 64),
        ResearchBatchCompanySpec(cyclical_gap_spec(), "3" * 64),
        ResearchBatchCompanySpec(
            ResearchRunSpec(
                run_id="broken",
                symbol="999999",
                profile_id="quality_compounder",
                research_case=case("999999"),
                facts=BadFacts("999999", AS_OF),
                available_at=NOW,
            ),
            "4" * 64,
        ),
    )
    spec = ResearchBatchSpec(
        run_id="batch-isolated",
        rule_version="research-batch-v1",
        companies=companies,
    )

    result = service.run(spec)

    assert result.status == BATCH_PARTIAL
    assert result.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert result.results_by_symbol["000333"].status == BATCH_GAP
    assert result.results_by_symbol["601088"].status == BATCH_GAP
    assert result.results_by_symbol["000333"].gaps
    assert result.results_by_symbol["601088"].gaps
    assert result.results_by_symbol["999999"].status == BATCH_FAILED
    assert result.results_by_symbol["999999"].error


def test_batch_marks_unsupported_profile_without_cascade():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    spec = ResearchBatchSpec(
        run_id="batch-unsupported",
        rule_version="research-batch-v1",
        companies=(
            ResearchBatchCompanySpec(
                ResearchRunSpec(
                    run_id="unsupported",
                    symbol="000333",
                    profile_id="mature_manufacturing",
                    requested_model="generic_pe",
                    research_case=case("000333"),
                    facts=FinancialFacts(
                        symbol="000333",
                        as_of=AS_OF,
                        verified=False,
                        evidence_refs=[{"id": "facts"}],
                        blockers=[],
                    ),
                    available_at=NOW,
                ),
                "6" * 64,
            ),
            ResearchBatchCompanySpec(quality_spec(), "7" * 64),
        ),
    )

    result = service.run(spec)

    assert result.results_by_symbol["000333"].status == BATCH_UNSUPPORTED
    assert result.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert result.status == BATCH_PARTIAL


def test_incremental_batch_only_reruns_changed_company():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    first = service.run(
        ResearchBatchSpec(
            run_id="batch-v1",
            rule_version="research-batch-v1",
            companies=(
                ResearchBatchCompanySpec(quality_spec(), "a" * 64),
                ResearchBatchCompanySpec(fcff_gap_spec(), "b" * 64),
            ),
        )
    )
    moutai_before = len(
        repository.list_versions(
            SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
        )
    )
    midea_before = len(
        repository.list_versions(
            SCOPE_SECURITY, "000333", ARTIFACT_VALUATION_RESULT
        )
    )

    changed_midea = replace(
        fcff_gap_spec().facts,
        blockers=["shares_not_verified", "updated_fcff_facts"],
    )
    changed_midea_spec = replace(
        fcff_gap_spec(),
        facts=changed_midea,
    )
    second = service.run(
        ResearchBatchSpec(
            run_id="batch-v2",
            rule_version="research-batch-v1",
            previous_run_id="batch-v1",
            companies=(
                ResearchBatchCompanySpec(quality_spec(), "a" * 64),
                ResearchBatchCompanySpec(changed_midea_spec, "c" * 64),
            ),
        )
    )

    moutai = second.results_by_symbol["600519"]
    midea = second.results_by_symbol["000333"]
    assert moutai.status == BATCH_UNCHANGED
    assert moutai.unchanged_from_run_id == first.results_by_symbol["600519"].run_id
    assert midea.status == BATCH_GAP
    assert len(
        repository.list_versions(
            SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
        )
    ) == moutai_before
    assert len(
        repository.list_versions(
            SCOPE_SECURITY, "000333", ARTIFACT_VALUATION_RESULT
        )
    ) == midea_before + 1


def test_repeated_identical_batch_is_idempotent_at_artifact_level():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    spec = ResearchBatchSpec(
        run_id="batch-idempotent",
        rule_version="research-batch-v1",
        companies=(
            ResearchBatchCompanySpec(quality_spec(), "d" * 64),
            ResearchBatchCompanySpec(fcff_gap_spec(), "e" * 64),
        ),
    )

    first = service.run(spec)
    second = service.run(spec)

    assert first.stored_artifact == second.stored_artifact
    assert len(
        repository.list_versions(
            SCOPE_BATCH, "batch-idempotent", ARTIFACT_BATCH_RUN_RESULT
        )
    ) == 1
    assert len(
        repository.list_versions(
            SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
        )
    ) == 1


def test_batch_receipt_round_trips_and_remains_no_order():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    spec = ResearchBatchSpec(
        run_id="batch-roundtrip",
        rule_version="research-batch-v1",
        companies=(ResearchBatchCompanySpec(quality_spec(), "f" * 64),),
    )
    result = service.run(spec)
    stored = repository.load_latest(
        SCOPE_BATCH, "batch-roundtrip", ARTIFACT_BATCH_RUN_RESULT
    )
    restored = ResearchBatchResult.from_policy(stored.envelope.payload_object())

    assert restored.as_policy() == result.as_policy()
    assert restored.as_policy()["action"] == "no_order"
    assert (
        restored.results_by_symbol["600519"].dependency_sha256
        == result.results_by_symbol["600519"].dependency_sha256
    )
    assert restored.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS


def test_incremental_batch_requires_input_fingerprints():
    with pytest.raises(ValueError, match="fingerprints"):
        ResearchBatchSpec(
            run_id="batch-no-fingerprint",
            rule_version="research-batch-v1",
            previous_run_id="previous",
            companies=(ResearchBatchCompanySpec(quality_spec()),),
        )


def test_rule_version_change_reruns_company_with_identical_input_hash():
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    first = service.run(
        ResearchBatchSpec(
            run_id="batch-rule-v1",
            rule_version="research-batch-v1",
            companies=(ResearchBatchCompanySpec(quality_spec(), "9" * 64),),
        )
    )
    before = len(
        repository.list_versions(
            SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
        )
    )

    second = service.run(
        ResearchBatchSpec(
            run_id="batch-rule-v2",
            rule_version="research-batch-v2",
            previous_run_id="batch-rule-v1",
            companies=(ResearchBatchCompanySpec(quality_spec(), "9" * 64),),
        )
    )

    assert first.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert second.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert second.results_by_symbol["600519"].unchanged_from_run_id is None
    assert second.results_by_symbol["600519"].run_id == "batch-rule-v2:600519"
    assert len(
        repository.list_versions(
            SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
        )
    ) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_version", "model-v2"),
        ("parser_version", "parser-v2"),
        ("scan_watermark", "scan-v2"),
        ("requested_model", "residual_income_or_equity_value"),
        ("profile_id", "mature_manufacturing"),
    ],
)
def test_dependency_version_change_reruns_identical_input_hash(field, value):
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    first = service.run(
        ResearchBatchSpec(
            run_id="batch-dependency-v1",
            rule_version="research-batch-v1",
            companies=(ResearchBatchCompanySpec(quality_spec(), "8" * 64),),
        )
    )

    changed_spec = replace(quality_spec(), **{field: value})
    second = service.run(
        ResearchBatchSpec(
            run_id="batch-dependency-v2",
            rule_version="research-batch-v1",
            previous_run_id="batch-dependency-v1",
            companies=(
                ResearchBatchCompanySpec(changed_spec, "8" * 64),
            ),
        )
    )

    result = second.results_by_symbol["600519"]
    assert first.results_by_symbol["600519"].status != BATCH_UNCHANGED
    assert result.status != BATCH_UNCHANGED
    assert result.unchanged_from_run_id is None
    assert result.run_id == "batch-dependency-v2:600519"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_version", "model-v2"),
        ("parser_version", "parser-v2"),
        ("scan_watermark", "scan-v2"),
    ],
)
def test_descriptor_dependency_change_changes_hash_and_reruns(field, value):
    repository = InMemoryResearchArtifactRepository()
    service = ResearchBatchService(repository, now_utc=lambda: NOW)
    first_payload = descriptor_payload()
    changed_payload = descriptor_payload_with_dependencies(**{field: value})
    assert changed_payload["input_sha256"] != first_payload["input_sha256"]

    first = service.run(
        build_batch_spec_from_descriptor_payloads(
            (first_payload,),
            run_id="batch-descriptor-dependency-v1",
            rule_version="research-batch-v1",
        )
    )
    second_spec = build_batch_spec_from_descriptor_payloads(
        (changed_payload,),
        run_id="batch-descriptor-dependency-v2",
        rule_version="research-batch-v1",
    )
    second = service.run(
        replace(
            second_spec,
            previous_run_id="batch-descriptor-dependency-v1",
        )
    )

    result = second.results_by_symbol["600519"]
    assert result.unchanged_from_run_id is None
    assert result.run_id == "batch-descriptor-dependency-v2:600519"
    assert first.results_by_symbol["600519"].input_sha256 != result.input_sha256


def test_future_availability_input_is_isolated_without_blocking_admitted_company():
    good = descriptor_payload()
    future = dict(good)
    future["point_in_time"] = dict(future["point_in_time"])
    future["point_in_time"]["available_at"] = datetime(
        2026, 9, 23, 12, 0, tzinfo=timezone.utc
    ).isoformat()
    future.pop("input_sha256", None)

    spec = build_batch_spec_from_descriptor_payloads(
        (future, good),
        run_id="batch-future-availability",
        rule_version="research-batch-v1",
    )
    assert len(spec.companies) == 1
    assert len(spec.input_failures) == 1
    assert "availability" in spec.input_failures[0].error

    result = ResearchBatchService(
        InMemoryResearchArtifactRepository(),
        now_utc=lambda: NOW,
    ).run(spec)

    assert result.status == BATCH_PARTIAL
    assert result.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert len(result.input_failures) == 1
    assert result.results_by_symbol["600519"].input_sha256 == good["input_sha256"]


def test_descriptor_batch_isolates_bad_and_unknown_inputs():
    good = descriptor_payload()
    tampered = dict(good)
    tampered["facts"] = dict(good["facts"])
    tampered["facts"]["operating_inputs"] = dict(
        good["facts"]["operating_inputs"]
    )
    tampered["facts"]["operating_inputs"]["start_book_equity"] = "999"
    unknown = dict(good)
    unknown["profile_id"] = "unknown_economic_profile"

    spec = build_batch_spec_from_descriptor_payloads(
        (good, tampered, unknown),
        run_id="batch-descriptor-isolation",
        rule_version="research-batch-v1",
    )
    assert len(spec.companies) == 1
    assert len(spec.input_failures) == 2

    repository = InMemoryResearchArtifactRepository()
    result = ResearchBatchService(
        repository,
        now_utc=lambda: NOW,
    ).run(spec)

    assert result.status == BATCH_PARTIAL
    assert result.results_by_symbol["600519"].status == BATCH_COMPLETED_WITH_BLOCKERS
    assert len(result.input_failures) == 2
    assert result.input_failures[0].symbol == "600519"
    assert result.as_policy()["action"] == "no_order"
    stored = repository.load_latest(
        SCOPE_BATCH,
        "batch-descriptor-isolation",
        ARTIFACT_BATCH_RUN_RESULT,
    )
    restored = ResearchBatchResult.from_policy(stored.envelope.payload_object())
    assert restored.input_failures == result.input_failures
