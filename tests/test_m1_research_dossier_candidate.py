from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.m1_research_dossier_candidate import (
    build_candidate_collection,
    load_provider_dossiers,
    write_candidate,
)
from value_investment_agent.m1_sample_preregistration import (
    load_m1_sample_preregistration,
)
from value_investment_agent.research_read_model import (
    ACTION_NO_ORDER,
    DOSSIER_BLOCKED,
    DOSSIER_NOT_STARTED,
    SECTION_UNKNOWN,
    not_started_dossier,
)


GENERATED_AT = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
REF = {"id": "source", "path": "source.pdf", "sha256": "a" * 64}


def _record(symbol: str, name: str) -> dict:
    return {
        "case": {
            "symbol": symbol,
            "name": name,
            "as_of": "2025-12-31",
            "run_id": "legacy",
            "generated_at": "2026-09-21T00:00:00+08:00",
            "research_version": "legacy-v1",
            "industry": "fixture",
            "investment_path": "fixture",
            "thesis": "legacy thesis",
            "return_driver": "legacy driver",
            "mispricing_hypothesis": "not proven",
            "financial_summary": {"period_end": "2025-12-31"},
            "positives": [
                {
                    "kind": "fact",
                    "text": "evidenced legacy positive",
                    "evidence_refs": ["source"],
                }
            ],
            "counter_evidence": [
                {
                    "kind": "fact",
                    "text": "evidenced legacy counter",
                    "evidence_refs": ["source"],
                }
            ],
            "thesis_breakers": [
                {
                    "kind": "hypothesis",
                    "text": "conditional breaker",
                    "evidence_refs": ["source"],
                }
            ],
            "next_events": [
                {
                    "kind": "fact",
                    "text": "next filing",
                    "evidence_refs": ["source"],
                }
            ],
            "evidence_status": "verified",
            "valuation_status": "not_ready",
            "research_status": "financial_scope_approved",
            "blockers": ["legacy blocker"],
            "evidence_refs": [REF],
            "quote_date": None,
            "financial_period": "2025-12-31",
            "missing_date_reasons": {"quote_date": "not used"},
        },
        "gate": {},
    }


def _frozen_payload() -> dict:
    return {
        "version": "excel-mvp-research-cases-v1",
        "generated_at": "2026-09-22T00:00:00+08:00",
        "records": [
            _record("600519", "Moutai"),
            _record("000333", "Midea"),
            _record("601088", "Shenhua"),
        ],
        "formal_trade_instructions": False,
    }


def test_candidate_builds_twenty_companies_without_manufacturing_deep_status():
    collection = build_candidate_collection(
        load_m1_sample_preregistration(),
        _frozen_payload(),
        generated_at=GENERATED_AT,
    )

    assert len(collection.dossiers) == 20
    assert len(collection.by_symbol) == 20
    assert collection.action == ACTION_NO_ORDER
    for symbol in ("600519", "000333", "601088"):
        dossier = collection.by_symbol[symbol]
        assert dossier.readiness == DOSSIER_BLOCKED
        assert dossier.research_gaps.blockers == ("legacy blocker",)
        assert dossier.business_quality.status == SECTION_UNKNOWN
        assert len(dossier.business_quality.dimensions) == 8
        assert dossier.evidence_refs[0]["id"] == "source"
    for symbol in ("600887", "000651", "600188"):
        dossier = collection.by_symbol[symbol]
        assert dossier.readiness == DOSSIER_NOT_STARTED
        assert dossier.research_gaps.blockers


def test_candidate_preserves_supported_and_unsupported_model_boundaries():
    collection = build_candidate_collection(
        load_m1_sample_preregistration(),
        _frozen_payload(),
        generated_at=GENERATED_AT,
    )

    assert collection.by_symbol["600519"].primary_model == "residual_income_or_equity_value"
    assert collection.by_symbol["000333"].primary_model == "fcff"
    assert collection.by_symbol["601088"].primary_model == "cyclical_normalized"
    assert collection.by_symbol["600036"].primary_model is None
    assert collection.by_symbol["600036"].readiness == DOSSIER_NOT_STARTED


def test_candidate_rejects_frozen_identity_change():
    payload = _frozen_payload()
    payload["records"][0]["case"]["symbol"] = "999999"
    with pytest.raises(ValueError, match="identity"):
        build_candidate_collection(
            load_m1_sample_preregistration(),
            payload,
            generated_at=GENERATED_AT,
        )


def test_candidate_rejects_trade_instructions_in_frozen_payload():
    payload = _frozen_payload()
    payload["formal_trade_instructions"] = True
    with pytest.raises(ValueError, match="trade instructions"):
        build_candidate_collection(
            load_m1_sample_preregistration(),
            payload,
            generated_at=GENERATED_AT,
        )


def test_candidate_accepts_real_provider_dossier_without_symbol_branching():
    real = not_started_dossier(
        symbol="000651",
        name="Gree",
        as_of=date(2026, 9, 23),
        run_id="gree-provider-v1",
        generated_at=GENERATED_AT,
        research_version="provider-v1",
        profile_id="mature_manufacturing",
        primary_model="fcff",
    )
    collection = build_candidate_collection(
        load_m1_sample_preregistration(),
        _frozen_payload(),
        generated_at=GENERATED_AT,
        real_dossiers={"000651": real},
    )

    assert collection.by_symbol["000651"] is real
    assert collection.by_symbol["000651"].run_id == "gree-provider-v1"


def test_provider_dossier_cannot_replace_a_frozen_platform_case():
    real = not_started_dossier(
        symbol="600519",
        name="Moutai",
        as_of=date(2026, 9, 23),
        run_id="provider-v1",
        generated_at=GENERATED_AT,
        research_version="provider-v1",
        profile_id="quality_compounder",
        primary_model="residual_income_or_equity_value",
    )
    with pytest.raises(ValueError, match="frozen platform case"):
        build_candidate_collection(
            load_m1_sample_preregistration(),
            _frozen_payload(),
            generated_at=GENERATED_AT,
            real_dossiers={"600519": real},
        )


def test_write_candidate_publishes_runtime_json_only(tmp_path):
    collection = build_candidate_collection(
        load_m1_sample_preregistration(),
        _frozen_payload(),
        generated_at=GENERATED_AT,
    )
    result = write_candidate(collection, root=tmp_path)

    target = tmp_path / result["evidence_path"]
    pointer = tmp_path / result["pointer_path"]
    assert target.exists()
    assert pointer.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["action"] == ACTION_NO_ORDER
    assert len(payload["dossiers"]) == 20
    pinned = json.loads(pointer.read_text(encoding="utf-8"))
    assert hashlib.sha256(target.read_bytes()).hexdigest() == pinned["sha256"]


def test_provider_pointer_loader_verifies_hash_and_symbol(tmp_path):
    runtime = tmp_path / "runtime" / "company-research"
    target = runtime / "000651-m1-dossier-test"
    target.mkdir(parents=True)
    dossier = not_started_dossier(
        symbol="000651",
        name="Gree",
        as_of=date(2026, 9, 23),
        run_id="provider-test",
        generated_at=GENERATED_AT,
        research_version="provider-test",
        profile_id="mature_manufacturing",
        primary_model="fcff",
    )
    evidence = target / "evidence.json"
    evidence.write_text(dossier.to_json(), encoding="utf-8")
    pointer = {
        "path": str(target.relative_to(tmp_path)),
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    (runtime / "000651-m1-dossier-latest.json").write_text(
        json.dumps(pointer), encoding="utf-8"
    )

    loaded = load_provider_dossiers(tmp_path)

    assert set(loaded) == {"000651"}
    assert loaded["000651"].run_id == "provider-test"


def test_provider_pointer_loader_rejects_changed_hash(tmp_path):
    runtime = tmp_path / "runtime" / "company-research"
    target = runtime / "000651-m1-dossier-test"
    target.mkdir(parents=True)
    dossier = not_started_dossier(
        symbol="000651",
        name="Gree",
        as_of=date(2026, 9, 23),
        run_id="provider-test",
        generated_at=GENERATED_AT,
        research_version="provider-test",
        profile_id="mature_manufacturing",
        primary_model="fcff",
    )
    evidence = target / "evidence.json"
    evidence.write_text(dossier.to_json(), encoding="utf-8")
    pointer = {"path": str(target.relative_to(tmp_path)), "sha256": "0" * 64}
    (runtime / "000651-m1-dossier-latest.json").write_text(
        json.dumps(pointer), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="invalid"):
        load_provider_dossiers(tmp_path)
