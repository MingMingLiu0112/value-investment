from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.m1_provider_dossier import (
    build_provider_dossier,
    write_provider_dossier,
)
from value_investment_agent.research_read_model import (
    ACTION_NO_ORDER,
    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
    BUSINESS_DIMENSION_CASH_CONVERSION,
    BUSINESS_DIMENSION_DURATION,
    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
    BUSINESS_DIMENSION_MOAT,
    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
    BUSINESS_DIMENSION_REINVESTMENT,
    BUSINESS_DIMENSION_ROIC,
    CONFIDENCE_MEDIUM,
    DOSSIER_PARTIAL,
    SECTION_COMPLETE,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
)


GENERATED_AT = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
EVIDENCE_ID = "source"
SOURCE_HASH = "a" * 64


def _section(status: str, findings=(), dimensions=(), blockers=(), explanation=""):
    return {
        "status": status,
        "findings": list(findings),
        "dimensions": list(dimensions),
        "blockers": list(blockers),
        "explanation": explanation,
    }


def _finding(kind: str, text: str, status=SECTION_COMPLETE):
    return {
        "kind": kind,
        "text": text,
        "confidence": CONFIDENCE_MEDIUM,
        "status": status,
        "evidence_refs": [EVIDENCE_ID] if kind != "gap" else [],
    }


def _dimension(key: str, status: str):
    return {
        "key": key,
        "status": status,
        "observation": f"{key} observation",
        "evidence_refs": [EVIDENCE_ID]
        if status not in {SECTION_UNKNOWN, "NOT_APPLICABLE", "MISSING", "NOT_STARTED"}
        else [],
    }


def _spec() -> dict:
    business_dimensions = [
        _dimension(BUSINESS_DIMENSION_MOAT, SECTION_COMPLETE),
        _dimension(BUSINESS_DIMENSION_PRICING_CUSTOMERS, SECTION_COMPLETE),
        _dimension(BUSINESS_DIMENSION_INDUSTRY_STRUCTURE, SECTION_COMPLETE),
        _dimension(BUSINESS_DIMENSION_ROIC, SECTION_UNKNOWN),
        _dimension(BUSINESS_DIMENSION_REINVESTMENT, SECTION_PARTIAL),
        _dimension(BUSINESS_DIMENSION_CAPITAL_INTENSITY, SECTION_COMPLETE),
        _dimension(BUSINESS_DIMENSION_CASH_CONVERSION, SECTION_COMPLETE),
        _dimension(BUSINESS_DIMENSION_DURATION, SECTION_UNKNOWN),
    ]
    return {
        "symbol": "000651",
        "name": "Fixture Company",
        "as_of": "2026-09-23",
        "run_id": "provider-v1",
        "research_version": "provider-v1",
        "profile_id": "mature_manufacturing",
        "primary_model": "fcff",
        "financial_period": "2026-06-30",
        "valuation_status": "NOT_READY",
        "research_status": "financial_scope_partial",
        "evidence_refs": [
            {
                "id": EVIDENCE_ID,
                "kind": "official_issuer_filing",
                "path": "official.pdf",
                "sha256": SOURCE_HASH,
            }
        ],
        "sections": {
            "business_quality": _section(
                SECTION_PARTIAL,
                findings=[_finding("fact", "business fact")],
                dimensions=business_dimensions,
                blockers=["roic_not_verified"],
            ),
            "financial_quality": _section(
                SECTION_PARTIAL,
                findings=[_finding("fact", "financial fact")],
            ),
            "capital_allocation": _section(
                SECTION_PARTIAL,
                findings=[_finding("fact", "capital fact")],
            ),
            "thesis": _section(
                SECTION_PARTIAL,
                findings=[
                    _finding("interpretation", "thesis"),
                    _finding("gap", "mispricing not established", SECTION_UNKNOWN),
                ],
            ),
            "counter_evidence": _section(
                SECTION_COMPLETE,
                findings=[_finding("fact", "counter fact")],
            ),
            "thesis_breakers": _section(
                SECTION_COMPLETE,
                findings=[_finding("hypothesis", "breaker")],
            ),
            "next_events": _section(
                SECTION_COMPLETE,
                findings=[_finding("fact", "next event")],
            ),
            "research_gaps": _section(
                SECTION_COMPLETE,
                blockers=["roic_not_verified", "valuation_not_ready"],
            ),
        },
    }


def test_provider_spec_builds_partial_no_order_dossier():
    dossier = build_provider_dossier(_spec(), generated_at=GENERATED_AT)

    assert dossier.readiness == DOSSIER_PARTIAL
    assert dossier.action == ACTION_NO_ORDER
    assert dossier.symbol == "000651"
    assert len(dossier.business_quality.dimensions) == 8


def test_provider_spec_rejects_execution_semantics():
    spec = _spec()
    spec["action"] = "buy"
    with pytest.raises(ValueError, match="no_order"):
        build_provider_dossier(spec, generated_at=GENERATED_AT)


def test_provider_spec_rejects_unknown_evidence_reference():
    spec = _spec()
    spec["sections"]["financial_quality"]["findings"][0]["evidence_refs"] = ["missing"]
    with pytest.raises(ValueError, match="unknown evidence"):
        build_provider_dossier(spec, generated_at=GENERATED_AT)


def test_provider_spec_requires_every_business_dimension():
    spec = _spec()
    dimensions = spec["sections"]["business_quality"]["dimensions"]
    spec["sections"]["business_quality"]["dimensions"] = dimensions[:-1]
    with pytest.raises(ValueError, match="every required dimension"):
        build_provider_dossier(spec, generated_at=GENERATED_AT)


def test_write_provider_dossier_pins_source_and_pointer(tmp_path):
    source = tmp_path / "official.pdf"
    source.write_bytes(b"%PDF fixture")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    spec = _spec()
    spec["evidence_refs"][0]["path"] = source.name
    spec["evidence_refs"][0]["sha256"] = digest

    result = write_provider_dossier(spec, generated_at=GENERATED_AT, root=tmp_path)
    pointer = json.loads(
        (tmp_path / result["pointer_path"]).read_text(encoding="utf-8")
    )
    evidence = tmp_path / result["evidence_path"]

    assert pointer["sha256"] == result["sha256"]
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pointer["sha256"]
    assert json.loads(evidence.read_text(encoding="utf-8"))["action"] == ACTION_NO_ORDER


def test_write_provider_dossier_rejects_changed_source_hash(tmp_path):
    source = tmp_path / "official.pdf"
    source.write_bytes(b"%PDF fixture")
    spec = _spec()
    spec["evidence_refs"][0]["path"] = source.name

    with pytest.raises(ValueError, match="hash changed"):
        write_provider_dossier(spec, generated_at=GENERATED_AT, root=tmp_path)
