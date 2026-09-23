from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from value_investment_agent.m1_valuation_package_builder import (
    PACKAGE_SCHEMA,
    build_descriptor,
    build_package_descriptor_attempts,
    load_descriptor_payloads,
)
from value_investment_agent.research_input import (
    descriptor_from_payload,
    build_research_run_spec,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)


ROOT = Path(__file__).resolve().parents[1]


def _package() -> dict:
    payload = load_descriptor_payloads(ROOT)["600887"]
    payload = deepcopy(payload)
    payload["quote"] = None
    return payload


def test_yili_package_round_trip_preserves_descriptor_hash():
    descriptor = build_descriptor(_package(), root=ROOT)
    restored = descriptor_from_payload(descriptor.as_policy())

    assert restored.as_policy() == descriptor.as_policy()
    assert restored.input_sha256 == descriptor.input_sha256


def test_package_build_isolates_bad_company_input():
    root = Path(__import__("tempfile").mkdtemp())
    package_dir = root / "config" / "m1-valuation-packages-v1"
    package_dir.mkdir(parents=True)
    good = _package()
    good["model_validity_input"].pop("event_scan_ref", None)
    bad = deepcopy(good)
    bad["symbol"] = "600741"
    bad["name"] = "华域汽车"
    bad["run_id"] = "bad-huayu"
    bad["facts"]["kind"] = "unsupported_model"
    (package_dir / "bad.json").write_text(
        json.dumps(bad, ensure_ascii=False),
        encoding="utf-8",
    )
    (package_dir / "good.json").write_text(
        json.dumps(good, ensure_ascii=False),
        encoding="utf-8",
    )

    attempts = build_package_descriptor_attempts(root)

    by_id = {attempt.package_id: attempt for attempt in attempts}
    assert by_id["600887-m1-valuation-20260922"].descriptor is not None
    assert by_id["bad-huayu"].descriptor is None
    assert "Unknown valuation facts kind" in by_id["bad-huayu"].error
    assert all(attempt.as_policy()["action"] == "no_order" for attempt in attempts)


def test_yili_bear_base_bull_ordering_is_registered_before_arithmetic():
    descriptor = build_descriptor(_package(), root=ROOT)
    scenarios = descriptor.facts.scenario_inputs

    assert scenarios is not None
    for year in range(5):
        bear = scenarios["bear"].forecast_roes[year]
        base = scenarios["base"].forecast_roes[year]
        bull = scenarios["bull"].forecast_roes[year]
        assert bear <= base <= bull
    assert (
        scenarios["bear"].terminal_roe
        <= scenarios["base"].terminal_roe
        <= scenarios["bull"].terminal_roe
    )


def test_huayu_package_routes_to_the_shared_fcff_contract():
    payload = load_descriptor_payloads(ROOT)["600741"]
    descriptor = build_descriptor(payload, root=ROOT)
    spec = build_research_run_spec(descriptor)

    assert descriptor.requested_model == "fcff"
    assert descriptor.facts.verified is True
    assert set(descriptor.facts.scenario_inputs) == {"bear", "base", "bull"}
    assert descriptor.facts.scenario_inputs["base"].cash_flow_dates is None

    outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(spec)

    assert outcome.valuation.status == "conditional_research_only"
    assert outcome.valuation.bear_value < outcome.valuation.base_value
    assert outcome.valuation.base_value < outcome.valuation.bull_value
    assert outcome.price_bridge.quote_status == "verified_close"
    assert outcome.price_bridge.bridge_status == "READY"
    assert outcome.gate.results["G3_估值门"] is False
    assert outcome.current_status.research_conclusion == "估值未就绪"
    assert outcome.current_status.price_attractiveness.status == "NOT_ASSESSABLE"


def test_huayu_bridge_exposures_do_not_overlap_operations():
    descriptor = build_descriptor(
        load_descriptor_payloads(ROOT)["600741"],
        root=ROOT,
    )
    scenario = descriptor.facts.scenario_inputs["base"]
    operating = set(scenario.operating_exposure_ids)
    bridge_ids = [
        exposure
        for item in scenario.bridge
        for exposure in item.exposure_ids
    ]

    assert not operating.intersection(bridge_ids)
    assert len(bridge_ids) == len(set(bridge_ids))


def test_gree_package_keeps_industrial_fcff_scope_and_uses_verified_quote():
    payload = load_descriptor_payloads(ROOT)["000651"]
    descriptor = build_descriptor(payload, root=ROOT)
    spec = build_research_run_spec(descriptor)

    assert descriptor.requested_model == "fcff"
    assert descriptor.quote is not None
    assert descriptor.quote.quote_date.isoformat() == "2026-09-22"
    assert descriptor.quote.status == "verified_close"
    assert str(descriptor.quote.current_price) == "38.18"
    assert descriptor.facts.scenario_inputs["base"].cash_flow_dates is None

    outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(spec)

    assert outcome.valuation.status == "conditional_research_only"
    assert outcome.valuation.bear_value < outcome.valuation.base_value
    assert outcome.valuation.base_value < outcome.valuation.bull_value
    assert outcome.price_bridge.quote_status == "verified_close"
    assert outcome.price_bridge.bridge_status == "READY"
    assert outcome.current_status.current_data_status.status == "READY"
    assert any(
        "treasury/financial company scope" in blocker
        for blocker in outcome.blockers
    )
    assert outcome.gate.results["G3_估值门"] is False
    assert outcome.current_status.price_attractiveness.status == "NOT_ASSESSABLE"


def test_gree_bridge_exposures_do_not_overlap_operations():
    descriptor = build_descriptor(
        load_descriptor_payloads(ROOT)["000651"],
        root=ROOT,
    )
    scenario = descriptor.facts.scenario_inputs["base"]
    operating = set(scenario.operating_exposure_ids)
    bridge_ids = [
        exposure
        for item in scenario.bridge
        for exposure in item.exposure_ids
    ]

    assert not operating.intersection(bridge_ids)
    assert len(bridge_ids) == len(set(bridge_ids))


def test_quote_identity_mismatch_is_rejected_before_bridging():
    payload = load_descriptor_payloads(ROOT)["600887"]
    payload = deepcopy(payload)
    payload["quote"]["symbol"] = "600741"
    descriptor = build_descriptor(payload, root=ROOT)

    with pytest.raises(ValueError, match="symbol"):
        build_research_run_spec(descriptor)


def test_material_event_makes_an_otherwise_valid_model_stale():
    payload = load_descriptor_payloads(ROOT)["600887"]
    payload = deepcopy(payload)
    payload["facts"]["blockers"] = []
    payload["model_validity_input"].pop("event_scan_ref", None)
    payload["model_validity_input"]["events"] = [
        {
            "event_date": "2026-09-22",
            "kind": "financial_statement",
            "description": "late material revision test",
            "evidence_refs": [{"id": "yili_2026h1"}],
        }
    ]
    descriptor = build_descriptor(payload, root=ROOT)
    spec = build_research_run_spec(descriptor)
    outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(spec)

    assert outcome.model_validity.status == "STALE"
    assert outcome.price_bridge.bridge_status == "STALE_MODEL"
    assert outcome.valuation.status == "conditional_research_only"


def test_probe_script_executes_one_package_end_to_end():
    bundle = ROOT / "runtime/quote-sessions/20260923T005634211464Z/bundle.json"
    if not bundle.exists():
        pytest.skip("archived quote-session runtime is not present")
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "scripts/probe_m1_valuation_package.py",
            "--symbol",
            "600887",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] is None
    assert payload["run_status"] == "COMPLETED_WITH_BLOCKERS"
    assert payload["valuation"]["status"] == "conditional_research_only"
    assert payload["price_bridge"]["bridge_status"] == "READY"
