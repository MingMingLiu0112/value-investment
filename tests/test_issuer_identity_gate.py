from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
import shutil

import pytest

from value_investment_agent.research_application import (
    RUN_COMPLETED_WITH_BLOCKERS,
    ResearchApplicationService,
    ResearchRunSpec,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.fcff import FinancialFacts
from value_investment_agent.valuation_router import ValuationRoute
from value_investment_agent.application.valuation.company_valuation_result import (
    build_company_valuation_result,
)
from value_investment_agent.application.product.valuation import (
    build_company_valuation_for_symbol,
)
from value_investment_agent.domain.research.issuer_identity import (
    ISSUER_IDENTITY_NOT_READY,
    ISSUER_IDENTITY_REJECTED,
    ISSUER_IDENTITY_VERIFIED,
    assess_issuer_identity,
)
from value_investment_agent.domain.research.research_run_contract import (
    ResearchIssuerIdentity,
    ResearchSourceDescriptor,
)
from value_investment_agent.m1_valuation_package_builder import _source_descriptor
from value_investment_agent.research_input import _source_from_payload


ROOT = Path(__file__).resolve().parents[1]
CASE_FIXTURE = ROOT / "tests" / "fixtures" / "midea_research_case_fixture.json"
FACTS_FIXTURE = ROOT / "tests" / "fixtures" / "midea_fcff_partial_facts_fixture.json"
FACTS_HASH = "b" * 64
AS_OF = date(2025, 12, 31)
AVAILABLE_AT = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)

CNINFO_CASES = (
    ("600519", "gssh0600519", "贵州茅台"),
    ("000333", "9900005965", "美的集团"),
    ("601088", "9900003701", "中国神华"),
    ("600887", "gssh0600887", "伊利股份"),
)


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _build_standalone(tmp_path: Path, facts: dict) -> dict:
    case_path = tmp_path / "case.json"
    facts_path = tmp_path / "facts.json"
    shutil.copyfile(CASE_FIXTURE, case_path)
    _write_json(facts_path, facts)
    return build_company_valuation_result(
        root=tmp_path,
        symbol="000333",
        case_path=case_path,
        facts_path=facts_path,
        model="fcff",
    )


def _build_product_wrapper(tmp_path: Path, facts: dict) -> dict:
    case_path = tmp_path / "case.json"
    facts_path = tmp_path / "facts.json"
    output_path = tmp_path / "valuation.json"
    shutil.copyfile(CASE_FIXTURE, case_path)
    _write_json(facts_path, facts)
    return build_company_valuation_for_symbol(
        root=tmp_path,
        symbol="000333",
        case_path=case_path,
        facts_path=facts_path,
        model="fcff",
        output_path=output_path,
    )


def test_standalone_builder_rejects_facts_symbol_mismatch_even_when_call_and_case_match(
    tmp_path,
):
    facts = json.loads(FACTS_FIXTURE.read_text(encoding="utf-8"))
    facts["symbol"] = "600519"

    wrapper = _build_product_wrapper(tmp_path, facts)
    result = wrapper["result"]

    assert wrapper["issuer_identity_status"] == ISSUER_IDENTITY_REJECTED
    assert result["facts_payload_symbol"] == "600519"
    assert result["issuer_identity_status"] == ISSUER_IDENTITY_REJECTED
    assert result["result"]["status"] == "not_ready"
    assert result["result"]["base_value"] is None
    assert result["action"] == "no_order"


def test_standalone_builder_requires_hash_bound_identity_evidence(tmp_path):
    facts = json.loads(FACTS_FIXTURE.read_text(encoding="utf-8"))

    result = _build_standalone(tmp_path, facts)

    assert result["issuer_identity_status"] == ISSUER_IDENTITY_NOT_READY
    assert result["result"]["status"] == "not_ready"
    assert result["result"]["bear_value"] is None
    assert result["result"]["base_value"] is None
    assert result["result"]["bull_value"] is None
    assert result["action"] == "no_order"


def test_standalone_builder_treats_missing_facts_symbol_as_not_ready(tmp_path):
    facts = json.loads(FACTS_FIXTURE.read_text(encoding="utf-8"))
    facts.pop("symbol")

    result = _build_standalone(tmp_path, facts)

    assert result["issuer_identity_status"] == ISSUER_IDENTITY_NOT_READY
    assert "issuer_identity_unverified:financial_facts_symbol_missing" in result[
        "issuer_identity_blockers"
    ]
    assert result["result"]["base_value"] is None


def test_standalone_builder_rejects_authoritative_cninfo_identity_contradiction(
    tmp_path,
):
    facts = json.loads(FACTS_FIXTURE.read_text(encoding="utf-8"))
    facts["evidence_refs"] = [{
        "id": "filing",
        "sha256": FACTS_HASH,
        "source_url": "https://www.cninfo.com.cn/example.pdf",
        "issuer_identity": {
            "venue": "CNINFO",
            "security_code": "000999",
            "issuer_name": "美的集团",
            "organization_id": "authoritative-org-id",
        },
    }]

    result = _build_standalone(tmp_path, facts)

    assert result["issuer_identity_status"] == ISSUER_IDENTITY_REJECTED
    assert any("issuer_identity_mismatch:sec_code" in item
               for item in result["issuer_identity_blockers"])
    assert result["result"]["base_value"] is None
    assert result["action"] == "no_order"


def _source(
    *,
    symbol="600519",
    organization_id="gssh0600519",
    issuer_name="贵州茅台",
    security_code=None,
    venue="CNINFO",
    location="https://www.cninfo.com.cn/annual-report.pdf",
    sha256=FACTS_HASH,
    source_id="facts",
):
    return ResearchSourceDescriptor(
        id=source_id,
        kind="annual_report",
        location=location,
        sha256=sha256,
        issuer_identity=ResearchIssuerIdentity(
            venue=venue,
            security_code=security_code or symbol,
            issuer_name=issuer_name,
            organization_id=organization_id,
        ),
    )


def _assess_identity(
    *,
    symbol="600519",
    identity: ResearchIssuerIdentity | None = None,
    facts_symbol: str | None = None,
    source_sha256=FACTS_HASH,
    source_location="https://www.cninfo.com.cn/annual-report.pdf",
):
    sources = (ResearchSourceDescriptor(
        id="facts",
        kind="annual_report",
        location=source_location,
        sha256=source_sha256,
        issuer_identity=identity,
    ),)
    return assess_issuer_identity(
        symbol=symbol,
        facts_symbol=symbol if facts_symbol is None else facts_symbol,
        fact_evidence_refs=[{"id": "facts", "sha256": FACTS_HASH}],
        sources=sources,
    )


@pytest.mark.parametrize("symbol,organization_id,issuer_name", CNINFO_CASES)
def test_registered_cninfo_identity_pairs_are_verified(symbol, organization_id, issuer_name):
    assessment = _assess_identity(
        symbol=symbol,
        identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code=symbol,
            issuer_name=issuer_name,
            organization_id=organization_id,
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_VERIFIED
    assert assessment.matched_source_ids == ("facts",)


@pytest.mark.parametrize("symbol,organization_id,issuer_name", CNINFO_CASES)
def test_registered_cninfo_identity_rejects_wrong_security_code(
    symbol, organization_id, issuer_name
):
    assessment = _assess_identity(
        symbol=symbol,
        identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code="000999",
            issuer_name=issuer_name,
            organization_id=organization_id,
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_REJECTED
    assert any("issuer_identity_mismatch:sec_code" in item for item in assessment.blockers)


@pytest.mark.parametrize("symbol,organization_id,issuer_name", CNINFO_CASES)
def test_registered_cninfo_identity_rejects_wrong_org_id(
    symbol, organization_id, issuer_name
):
    assessment = _assess_identity(
        symbol=symbol,
        identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code=symbol,
            issuer_name=issuer_name,
            organization_id="wrong-org-id",
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_REJECTED
    assert any("issuer_identity_mismatch:org_id" in item for item in assessment.blockers)


def test_identity_requires_hash_bound_official_source_and_complete_identity():
    missing_identity = _assess_identity(identity=None)
    wrong_source_hash = _assess_identity(
        identity=ResearchIssuerIdentity(
            venue="CNINFO", security_code="600519", issuer_name="贵州茅台",
            organization_id="gssh0600519",
        ),
        source_sha256="c" * 64,
    )
    incomplete_identity = _assess_identity(
        identity=ResearchIssuerIdentity(venue="CNINFO", security_code="600519")
    )

    assert missing_identity.status == ISSUER_IDENTITY_NOT_READY
    assert any("source_identity_missing" in item for item in missing_identity.blockers)
    assert wrong_source_hash.status == ISSUER_IDENTITY_NOT_READY
    assert any("sha256_not_bound" in item for item in wrong_source_hash.blockers)
    assert incomplete_identity.status == ISSUER_IDENTITY_NOT_READY


def test_hash_bound_derived_artifact_is_not_an_issuer_identity_anchor():
    assessment = assess_issuer_identity(
        symbol="600519",
        facts_symbol="600519",
        fact_evidence_refs=[{"id": "derived", "sha256": FACTS_HASH}],
        sources=(ResearchSourceDescriptor(
            id="derived",
            kind="research_artifact",
            location="derived-facts.json",
            sha256=FACTS_HASH,
        ),),
    )

    assert assessment.status == ISSUER_IDENTITY_NOT_READY
    assert "issuer_identity_unverified:identity_not_established" in assessment.blockers


def test_conflicting_duplicate_financial_ref_ids_cannot_be_masked_by_a_valid_source():
    assessment = assess_issuer_identity(
        symbol="600519",
        facts_symbol="600519",
        fact_evidence_refs=[
            {"id": "facts", "sha256": FACTS_HASH},
            {"id": "facts", "sha256": "c" * 64},
        ],
        sources=(
            _source(),
            _source(sha256="c" * 64),
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_NOT_READY
    assert "issuer_identity_unverified:financial_fact_ref_id_conflict:facts" in assessment.blockers


def test_malformed_financial_ref_cannot_be_masked_by_a_valid_source():
    assessment = assess_issuer_identity(
        symbol="600519",
        facts_symbol="600519",
        fact_evidence_refs=[{"id": "facts", "sha256": FACTS_HASH}, {"id": "broken"}],
        sources=(_source(),),
    )

    assert assessment.status == ISSUER_IDENTITY_NOT_READY
    assert any("financial_fact_ref_sha256_missing:broken" in item
               for item in assessment.blockers)


def test_unresolved_second_financial_ref_cannot_be_masked_by_a_valid_source():
    assessment = assess_issuer_identity(
        symbol="600519",
        facts_symbol="600519",
        fact_evidence_refs=[
            {"id": "facts", "sha256": FACTS_HASH},
            {"id": "another-fact-source", "sha256": "c" * 64},
        ],
        sources=(_source(),),
    )

    assert assessment.status == ISSUER_IDENTITY_NOT_READY
    assert "issuer_identity_unverified:financial_source_missing:another-fact-source" in assessment.blockers


def test_identity_requires_an_official_host_not_a_payload_claim():
    assessment = _assess_identity(
        identity=ResearchIssuerIdentity(
            venue="CNINFO", security_code="600519", issuer_name="贵州茅台",
            organization_id="gssh0600519",
        ),
        source_location="https://example.com/annual-report.pdf",
    )

    assert assessment.status == ISSUER_IDENTITY_NOT_READY


def test_approved_hkex_shenhua_identity_maps_to_a_share_601088():
    assessment = _assess_identity(
        symbol="601088",
        identity=ResearchIssuerIdentity(
            venue="HKEX", security_code="01088", issuer_name="中國神華",
        ),
        source_location="https://www1.hkexnews.hk/listedco/listconews/report.pdf",
    )

    assert assessment.status == ISSUER_IDENTITY_VERIFIED
    assert assessment.matched_source_ids == ("facts",)


def test_registered_cninfo_name_alias_is_accepted():
    assessment = _assess_identity(
        identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code="600519",
            issuer_name="贵州茅台酒股份有限公司",
            organization_id="gssh0600519",
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_VERIFIED


def test_registered_cninfo_identity_rejects_wrong_issuer_name():
    assessment = _assess_identity(
        identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code="600519",
            issuer_name="美的集团",
            organization_id="gssh0600519",
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_REJECTED
    assert any("issuer_identity_mismatch:sec_name" in item
               for item in assessment.blockers)


def test_fact_symbol_mismatch_is_rejected_even_when_source_is_hash_bound():
    assessment = _assess_identity(
        symbol="000333",
        facts_symbol="600519",
        identity=ResearchIssuerIdentity(
            venue="CNINFO", security_code="000333", issuer_name="美的集团",
            organization_id="9900005965",
        ),
    )

    assert assessment.status == ISSUER_IDENTITY_REJECTED
    assert "issuer_identity_mismatch:financial_facts_symbol" in assessment.blockers


def _application_spec(
    *, facts_payload_symbol: str, source_symbol: str, research_symbol="000333"
):
    source_identity = {
        "600519": ("gssh0600519", "贵州茅台"),
        "000333": ("9900005965", "美的集团"),
        "601088": ("9900003701", "中国神华"),
        "600887": ("gssh0600887", "伊利股份"),
    }
    organization_id, issuer_name = source_identity[source_symbol]
    facts = FinancialFacts(
        symbol=research_symbol,
        as_of=AS_OF,
        verified=True,
        evidence_refs=[{"id": "facts", "sha256": FACTS_HASH}],
        blockers=[],
    )
    case = ResearchCase(
        symbol=research_symbol,
        name="caller declaration is not identity evidence",
        as_of=AS_OF,
        run_id="identity-gate-test",
        generated_at=AVAILABLE_AT,
        research_version="test-v1",
        industry="manufacturing",
        investment_path="test",
        thesis="test",
        return_driver="test",
        mispricing_hypothesis="not established",
        financial_summary={"period_end": AS_OF.isoformat()},
        positives=[],
        counter_evidence=[],
        thesis_breakers=[],
        next_events=[],
        evidence_status="partial",
        valuation_status="not_ready",
        research_status="financial_scope_blocked",
        blockers=[],
        evidence_refs=[{"id": "case", "sha256": "a" * 64}],
        quote_date=None,
        financial_period=AS_OF,
        missing_date_reasons={"quote_date": "not used"},
    )
    source = _source(
        symbol=source_symbol,
        organization_id=organization_id,
        issuer_name=issuer_name,
        source_id="facts",
    )
    return ResearchRunSpec(
        run_id="identity-gate-test",
        symbol=research_symbol,
        profile_id="mature_manufacturing",
        research_case=case,
        facts=facts,
        available_at=AVAILABLE_AT,
        input_sources=(source,),
        facts_payload={"symbol": facts_payload_symbol},
    )


def test_shared_application_rejects_false_matching_caller_declaration_before_model(
    monkeypatch,
):
    def model_must_not_run(self):
        raise AssertionError("valuation model ran before issuer identity admission")

    monkeypatch.setattr(ValuationRoute, "build_model", model_must_not_run)
    spec = _application_spec(facts_payload_symbol="000333", source_symbol="600519")

    outcome = ResearchApplicationService().run_company_research(spec)

    assert outcome.status == RUN_COMPLETED_WITH_BLOCKERS
    assert outcome.issuer_identity_status == ISSUER_IDENTITY_REJECTED
    assert outcome.valuation.status == "not_ready"
    assert outcome.valuation.base_value is None
    assert "issuer_identity_mismatch:sec_code:facts" in outcome.blockers
    assert outcome.current_status is not None


def test_shared_application_reports_missing_identity_not_ready_before_model(monkeypatch):
    def model_must_not_run(self):
        raise AssertionError("valuation model ran before issuer identity admission")

    monkeypatch.setattr(ValuationRoute, "build_model", model_must_not_run)
    spec = _application_spec(facts_payload_symbol="000333", source_symbol="000333")
    missing_official_mapping = ResearchSourceDescriptor(
        id="facts",
        kind="annual_report",
        location="https://www.cninfo.com.cn/annual-report.pdf",
        sha256=FACTS_HASH,
    )
    spec = replace(spec, input_sources=(missing_official_mapping,))

    outcome = ResearchApplicationService().run_company_research(spec)

    assert outcome.issuer_identity_status == ISSUER_IDENTITY_NOT_READY
    assert outcome.valuation.status == "not_ready"


def test_shared_application_rejects_financial_fact_scope_mismatch_before_model(
    monkeypatch,
):
    def model_must_not_run(self):
        raise AssertionError("valuation model ran before issuer identity admission")

    monkeypatch.setattr(ValuationRoute, "build_model", model_must_not_run)
    spec = _application_spec(facts_payload_symbol="600519", source_symbol="000333")

    outcome = ResearchApplicationService().run_company_research(spec)

    assert outcome.issuer_identity_status == ISSUER_IDENTITY_REJECTED
    assert (
        "issuer_identity_mismatch:financial_facts_payload_symbol"
        in outcome.blockers
    )
    assert outcome.valuation.status == "not_ready"


def test_shared_application_rejects_midea_source_bound_to_yili_facts_before_model(
    monkeypatch,
):
    def model_must_not_run(self):
        raise AssertionError("valuation model ran before issuer identity admission")

    monkeypatch.setattr(ValuationRoute, "build_model", model_must_not_run)
    spec = _application_spec(
        facts_payload_symbol="600887",
        source_symbol="000333",
        research_symbol="600887",
    )

    outcome = ResearchApplicationService().run_company_research(spec)

    assert outcome.issuer_identity_status == ISSUER_IDENTITY_REJECTED
    assert "issuer_identity_mismatch:sec_code:facts" in outcome.blockers
    assert outcome.valuation.status == "not_ready"
    assert outcome.valuation.base_value is None


def test_shared_application_rejects_cross_issuer_event_evidence_before_model(
    monkeypatch,
):
    def model_must_not_run(self):
        raise AssertionError("valuation model ran before issuer identity admission")

    monkeypatch.setattr(ValuationRoute, "build_model", model_must_not_run)
    spec = _application_spec(
        facts_payload_symbol="600887",
        source_symbol="600887",
        research_symbol="600887",
    )
    event_hash = "c" * 64
    case = replace(
        spec.research_case,
        evidence_refs=[
            *spec.research_case.evidence_refs,
            {"id": "event-midea", "sha256": event_hash},
        ],
        next_events=[{
            "kind": "fact",
            "text": "Issuer event evidence must match the research case.",
            "evidence_refs": ["event-midea"],
        }],
    )
    event_source = _source(
        symbol="000333",
        organization_id="9900005965",
        issuer_name="美的集团",
        sha256=event_hash,
        source_id="event-midea",
    )
    spec = replace(spec, research_case=case, input_sources=(
        *spec.input_sources,
        event_source,
    ))

    outcome = ResearchApplicationService().run_company_research(spec)

    assert outcome.issuer_identity_status == ISSUER_IDENTITY_REJECTED
    assert "issuer_identity_mismatch:event_scope:sec_code:event-midea" in outcome.blockers
    assert outcome.valuation.base_value is None


def test_run_spec_rejects_research_case_symbol_mismatch_with_identity_code():
    spec = _application_spec(
        facts_payload_symbol="600887",
        source_symbol="600887",
        research_symbol="600887",
    )
    case = replace(spec.research_case, symbol="000333")
    with pytest.raises(ValueError, match="REJECTED_ISSUER_MISMATCH.*research case symbol"):
        replace(spec, research_case=case)

    assessment = assess_issuer_identity(
        symbol="600887",
        facts_symbol="600887",
        research_case_symbol="000333",
        fact_evidence_refs=[{"id": "facts", "sha256": FACTS_HASH}],
        sources=(_source(
            symbol="600887",
            organization_id="gssh0600887",
            issuer_name="伊利股份",
        ),),
    )
    assert assessment.status == ISSUER_IDENTITY_REJECTED
    assert "issuer_identity_mismatch:research_case_symbol" in assessment.blockers


def test_run_spec_rejects_typed_fact_symbol_mismatch_with_identity_code():
    spec = _application_spec(
        facts_payload_symbol="600887",
        source_symbol="600887",
        research_symbol="600887",
    )
    with pytest.raises(ValueError, match="REJECTED_ISSUER_MISMATCH.*facts symbol"):
        replace(spec, facts=replace(spec.facts, symbol="000333"))


def test_non_cninfo_exchange_identity_is_venue_aware_without_cninfo_organization_id():
    assessment = _assess_identity(
        symbol="601088",
        identity=ResearchIssuerIdentity(
            venue="HKEX",
            security_code="01088",
            issuer_name="中國神華",
        ),
        source_location="https://www1.hkexnews.hk/listedco/listconews/report.pdf",
    )

    assert assessment.status == ISSUER_IDENTITY_VERIFIED
    assert assessment.blockers == ()


def test_research_source_identity_survives_input_payload_round_trip():
    source = ResearchSourceDescriptor(
        id="facts",
        kind="annual_report",
        location="https://example.com/annual-report.pdf",
        sha256=FACTS_HASH,
        issuer_identity=ResearchIssuerIdentity(
            venue="SSE",
            security_code="600519",
            issuer_name="公司600519",
        ),
    )

    payload = source.as_policy()
    assert _source_from_payload(payload) == source
    assert _source_descriptor(payload) == source
