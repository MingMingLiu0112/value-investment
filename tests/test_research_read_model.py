from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json

import pytest

from value_investment_agent.research_read_model import (
    ACTION_NO_ORDER,
    DOSSIER_PARTIAL,
    DOSSIER_READABLE,
    SECTION_BUSINESS_QUALITY,
    SECTION_BLOCKED,
    SECTION_COMPLETE,
    SECTION_MISSING,
    SECTION_NOT_APPLICABLE,
    SECTION_NOT_STARTED,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
    BUSINESS_DIMENSION_CASH_CONVERSION,
    BUSINESS_DIMENSION_DURATION,
    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
    BUSINESS_DIMENSION_MOAT,
    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
    BUSINESS_DIMENSION_REINVESTMENT,
    BUSINESS_DIMENSION_ROIC,
    CONFIDENCE_UNKNOWN,
    DOSSIER_SCHEMA_VERSION,
    ResearchDimension,
    ResearchDossier,
    ResearchStatement,
    dossier_collection_from_payload,
    dossier_from_payload,
    not_started_dossier,
    section,
    statement,
)


AS_OF = date(2025, 12, 31)
GENERATED_AT = datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)
REF = {"id": "source", "path": "source.pdf", "sha256": "a" * 64}


def _section(key: str, status: str) -> "ResearchSection":
    return section(key, key.replace("_", " ").title(), status)


def _dossier(
    *,
    symbol: str = "600519",
    status: str = SECTION_PARTIAL,
) -> ResearchDossier:
    common = {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "symbol": symbol,
        "name": "Fixture Company",
        "as_of": AS_OF,
        "run_id": "fixture",
        "generated_at": GENERATED_AT,
        "research_version": "v1",
        "profile_id": "quality_compounder",
        "primary_model": "residual_income_or_equity_value",
        "action": ACTION_NO_ORDER,
        "business_quality": _section("business_quality", status),
        "financial_quality": _section("financial_quality", status),
        "capital_allocation": _section("capital_allocation", status),
        "thesis": _section("thesis", status),
        "counter_evidence": _section("counter_evidence", status),
        "thesis_breakers": _section("thesis_breakers", status),
        "next_events": _section("next_events", status),
        "research_gaps": _section("research_gaps", status),
        "evidence_refs": [REF],
        "financial_period": AS_OF,
    }
    return ResearchDossier(**common)


def _complete_sections() -> dict[str, "ResearchSection"]:
    finding = statement(
        "fact",
        "evidenced observation",
        confidence=CONFIDENCE_UNKNOWN,
        evidence_refs=["source"],
    )
    dimensions = [
        ResearchDimension(
            key,
            SECTION_NOT_APPLICABLE,
            "Explicitly not applicable in the reviewed period.",
        )
        for key in (
            BUSINESS_DIMENSION_MOAT,
            BUSINESS_DIMENSION_PRICING_CUSTOMERS,
            BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
            BUSINESS_DIMENSION_ROIC,
            BUSINESS_DIMENSION_REINVESTMENT,
            BUSINESS_DIMENSION_CAPITAL_INTENSITY,
            BUSINESS_DIMENSION_CASH_CONVERSION,
            BUSINESS_DIMENSION_DURATION,
        )
    ]
    sections = {
        key: section(key, key.title(), SECTION_COMPLETE, findings=[finding])
        for key in (
            "financial_quality",
            "capital_allocation",
            "thesis",
            "counter_evidence",
            "thesis_breakers",
            "next_events",
            "research_gaps",
        )
    }
    sections[SECTION_BUSINESS_QUALITY] = section(
        SECTION_BUSINESS_QUALITY,
        "Business Quality",
        SECTION_COMPLETE,
        findings=[finding],
        dimensions=dimensions,
    )
    return sections


def test_fact_or_interpretation_requires_evidence():
    with pytest.raises(ValueError, match="require evidence"):
        statement("fact", "unbacked fact")
    with pytest.raises(ValueError, match="require evidence"):
        statement("interpretation", "unbacked interpretation")
    statement("hypothesis", "testable hypothesis", evidence_refs=["source"])
    statement("gap", "known missing fact")


def test_missing_and_unknown_states_remain_visible_after_round_trip():
    dossier = replace(
        _dossier(),
        financial_quality=section(
            "financial_quality",
            "Financial Quality",
            SECTION_UNKNOWN,
            explanation="Coverage has not been independently verified.",
        ),
        capital_allocation=section(
            "capital_allocation",
            "Capital Allocation",
            SECTION_MISSING,
            explanation="No reviewed capital-allocation section exists yet.",
        ),
    )
    restored = dossier_from_payload(dossier.as_policy())

    assert restored.financial_quality.status == SECTION_UNKNOWN
    assert restored.capital_allocation.status == SECTION_MISSING
    assert restored.readiness == DOSSIER_PARTIAL
    assert "not been independently verified" in restored.financial_quality.explanation
    assert "No reviewed capital-allocation section" in restored.capital_allocation.explanation


def test_missing_required_section_is_rejected():
    with pytest.raises(ValueError, match="required section"):
        dossier_from_payload({**_dossier().as_policy(), "thesis": None})


def test_partial_sections_cannot_become_readable():
    dossier = _dossier(status=SECTION_PARTIAL)
    assert dossier.readiness == DOSSIER_PARTIAL
    assert dossier.action == ACTION_NO_ORDER


def test_complete_business_quality_requires_every_registered_dimension():
    sections = _complete_sections()
    business = replace(
        sections[SECTION_BUSINESS_QUALITY],
        dimensions=(
            ResearchDimension(
                BUSINESS_DIMENSION_MOAT,
                SECTION_COMPLETE,
                "Reviewed moat.",
                evidence_refs=["source"],
            ),
        ),
    )
    common = _dossier().as_policy()
    payload = {**common, **{key: value.as_policy() for key, value in sections.items()}}
    payload[SECTION_BUSINESS_QUALITY] = business.as_policy()
    with pytest.raises(ValueError, match="every registered dimension"):
        dossier_from_payload(payload)


def test_complete_business_quality_keeps_explicit_unknown_dimension_readable():
    sections = _complete_sections()
    business = replace(
        sections[SECTION_BUSINESS_QUALITY],
        dimensions=(
            ResearchDimension(
                BUSINESS_DIMENSION_ROIC,
                SECTION_UNKNOWN,
                "The report discloses ROE but not a verifiable ROIC.",
            ),
            *(
                ResearchDimension(
                    key,
                    SECTION_COMPLETE,
                    "Reviewed from retained evidence.",
                    evidence_refs=["source"],
                )
                for key in (
                    BUSINESS_DIMENSION_MOAT,
                    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    BUSINESS_DIMENSION_REINVESTMENT,
                    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    BUSINESS_DIMENSION_CASH_CONVERSION,
                    BUSINESS_DIMENSION_DURATION,
                )
            ),
        ),
    )
    common = _dossier().as_policy()
    payload = {**common, **{key: value.as_policy() for key, value in sections.items()}}
    payload[SECTION_BUSINESS_QUALITY] = business.as_policy()

    dossier = dossier_from_payload(payload)

    assert dossier.readiness == DOSSIER_READABLE
    assert dossier.business_quality.dimensions[0].status == SECTION_UNKNOWN


def test_round_trip_preserves_no_order_and_point_in_time_facts():
    dossier = _dossier()
    dossier = replace(
        dossier,
        business_quality=_complete_sections()[SECTION_BUSINESS_QUALITY],
        financial_quality=_complete_sections()["financial_quality"],
        capital_allocation=_complete_sections()["capital_allocation"],
        thesis=_complete_sections()["thesis"],
        counter_evidence=_complete_sections()["counter_evidence"],
        thesis_breakers=_complete_sections()["thesis_breakers"],
        next_events=_complete_sections()["next_events"],
        research_gaps=_complete_sections()["research_gaps"],
    )
    payload = json.loads(dossier.to_json())
    restored = dossier_from_payload(payload)

    assert payload["action"] == ACTION_NO_ORDER
    assert payload["as_of"] == "2025-12-31"
    assert payload["generated_at"] == "2026-09-23T04:00:00+00:00"
    assert payload["financial_period"] == "2025-12-31"
    assert restored.action == ACTION_NO_ORDER
    assert restored.as_of == AS_OF
    assert restored.generated_at == GENERATED_AT
    assert restored.financial_period == AS_OF
    assert restored.readiness == DOSSIER_READABLE


def test_complete_dossier_requires_counter_breakers_and_next_events():
    sections = _complete_sections()
    for key in ("counter_evidence", "thesis_breakers", "next_events"):
        sections[key] = replace(sections[key], findings=())
    common = _dossier().as_policy()
    payload = {**common, **{key: value.as_policy() for key, value in sections.items()}}
    dossier = dossier_from_payload(payload)

    assert dossier.readiness == DOSSIER_PARTIAL


def test_bad_dossier_is_isolated_without_wiping_other_companies():
    good = _dossier(symbol="600519").as_policy()
    tampered = _dossier(symbol="000333").as_policy()
    tampered["action"] = "buy"
    collection = dossier_collection_from_payload(
        {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "generated_at": GENERATED_AT.isoformat(),
            "action": ACTION_NO_ORDER,
            "dossiers": [good, tampered],
            "input_failures": [],
        }
    )

    assert set(collection.by_symbol) == {"600519"}
    assert len(collection.input_failures) == 1
    assert collection.input_failures[0].symbol == "000333"
    assert "no_order" in collection.input_failures[0].error


def test_not_started_dossier_keeps_known_blockers_without_claiming_research():
    dossier = not_started_dossier(
        symbol="000333",
        name="Fixture Manufacturing",
        as_of=AS_OF,
        run_id="not-started",
        generated_at=GENERATED_AT,
        research_version="v1",
        profile_id="mature_manufacturing",
        primary_model="fcff",
        known_blockers=["facts_not_verified"],
    )

    assert dossier.readiness == "NOT_STARTED"
    assert dossier.action == ACTION_NO_ORDER
    assert dossier.research_gaps.blockers == ("facts_not_verified",)
    assert all(
        getattr(dossier, key).status == SECTION_NOT_STARTED
        for key in (
            "business_quality",
            "financial_quality",
            "capital_allocation",
            "thesis",
            "counter_evidence",
            "thesis_breakers",
            "next_events",
        )
    )
