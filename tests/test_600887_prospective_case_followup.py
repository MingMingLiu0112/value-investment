from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from value_investment_agent.domain.research.research_run_contract import (
    ResearchIssuerIdentity,
    ResearchSourceDescriptor,
)
from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_input import (
    build_research_run_spec,
    finalize_input_descriptor,
)
from value_investment_agent.valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "docs/current/600887-prospective-case-followup-20260930.json"
REVIEW_PATH = ROOT / "docs/current/600887-valuation-readiness-review-20260929.json"
PRIOR_RESULT_PATH = ROOT / "docs/current/600887-shared-valuation-result-20260929.json"
BASELINE_INPUT_PATH = ROOT / "config/prospective-baseline-input-v1.json"
OBSERVATION_PLAN_PATH = ROOT / "config/prospective-research-observation-plan-v2.json"
SNAPSHOT_PATH = ROOT / "runtime/prospective-baseline-20260927/snapshot-v13-midea-h1-verified.json"
REGISTRATION_PATH = ROOT / "runtime/prospective-v2-fc1e811/receipt.json"
FROZEN_RECEIPT_SHA256 = "8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5"
FROZEN_BASELINE_INPUT_SHA256 = "e39386945fa67e653b2424f3c761c6c206f46a73cc522a0af35a8016b2453c6c"
FROZEN_PLAN_SHA256 = "f98304dbfb73276073d57537e90aee37b6233821d8b0200df944718bf23a2c7a"
FROZEN_SNAPSHOT_SHA256 = "ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _published_at(source_url: str) -> datetime:
    parts = [part for part in urlsplit(source_url).path.split("/") if part]
    return datetime.fromisoformat(f"{parts[-2]}T00:00:00+08:00")


def _build_followup_run(artifact: dict, review: dict):
    binding = artifact["case_binding"]
    run = artifact["run"]
    case_id = binding["case_id"]
    research_as_of = date.fromisoformat(run["research_as_of"])
    available_at = datetime.fromisoformat(run["available_at"])
    computed_at = datetime.fromisoformat(run["computed_at"])

    baseline_input = _json(BASELINE_INPUT_PATH)
    plan = _json(OBSERVATION_PLAN_PATH)
    snapshot = _json(SNAPSHOT_PATH)
    receipt = _json(REGISTRATION_PATH)
    baseline_case = next(
        item for item in baseline_input["cases"] if item["case_id"] == case_id
    )
    plan_case = next(
        item for item in plan["cases"] if item["case_id"] == case_id
    )
    snapshot_case = next(
        item for item in snapshot["cards"] if item["case_id"] == case_id
    )
    recorded_case = artifact["research_case"]

    assert _sha256_file(BASELINE_INPUT_PATH) == binding["baseline_input"]["sha256"]
    assert _sha256_file(OBSERVATION_PLAN_PATH) == binding["observation_plan"]["sha256"]
    assert _sha256_file(SNAPSHOT_PATH) == binding["baseline_snapshot"]["sha256"]
    assert _sha256_file(REGISTRATION_PATH) == binding["registration_receipt"]["sha256"]
    assert _sha256_file(REVIEW_PATH) == binding["readiness_review"]["sha256"]
    assert _sha256_file(PRIOR_RESULT_PATH) == binding["prior_shared_valuation"]["sha256"]
    assert receipt["plan_sha256"] == binding["observation_plan"]["sha256"]
    assert snapshot["registration_receipt_sha256"] == binding["registration_receipt"]["sha256"]
    assert snapshot["baseline_input_sha256"] == binding["baseline_input"]["sha256"]
    assert binding["registration_receipt"]["sha256"] == FROZEN_RECEIPT_SHA256
    assert binding["baseline_input"]["sha256"] == FROZEN_BASELINE_INPUT_SHA256
    assert binding["observation_plan"]["sha256"] == FROZEN_PLAN_SHA256
    assert binding["baseline_snapshot"]["sha256"] == FROZEN_SNAPSHOT_SHA256
    receipt_case = next(
        item
        for item in receipt["registration"]["cases"]
        if item["case_id"] == case_id
    )
    assert receipt_case["baseline_cutoff_at"] == baseline_case["baseline_cutoff_at"]
    assert plan_case["symbol"] == baseline_case["symbol"] == snapshot_case["symbol"]
    assert plan_case["name"] == baseline_case["company"] == snapshot_case["company"]
    assert plan_case["profile_id"] == baseline_case["profile"]
    assert recorded_case["run_id"] == case_id
    assert recorded_case["symbol"] == baseline_case["symbol"]
    assert recorded_case["name"] == plan_case["name"]
    assert recorded_case["research_as_of"] == run["research_as_of"]
    assert recorded_case["research_status"] == baseline_case["research_status"]
    assert recorded_case["baseline_valuation_status"] == baseline_case["valuation_status"]
    assert recorded_case["followup_valuation_status"] == artifact["followup"]["valuation_readiness"]
    assert baseline_case["valuation_status"] == "VALUATION_NOT_READY"
    assert snapshot_case["valuation_status"] == "VALUATION_NOT_READY"
    assert snapshot["strict_pit_admissible"] is False
    assert binding["baseline_snapshot"]["strict_pit"] == "NOT_PROVEN"

    facts_refs = [
        dict(item)
        for item in review["evidence"]
        if str(item.get("id", "")).startswith("cninfo:")
    ]
    official_sources = tuple(
        ResearchSourceDescriptor(
            id=item["id"],
            kind=item["kind"],
            location=item["url"],
            sha256=item["sha256"],
            published_at=_published_at(item["url"]),
            issuer_identity=ResearchIssuerIdentity(**item["issuer_identity"]),
        )
        for item in facts_refs
    )
    binding_sources = (
        ResearchSourceDescriptor(
            id="prospective-registration-receipt-v13",
            kind="research_artifact",
            location=binding["registration_receipt"]["path"],
            sha256=binding["registration_receipt"]["sha256"],
        ),
        ResearchSourceDescriptor(
            id="prospective-baseline-snapshot-v13",
            kind="research_artifact",
            location=binding["baseline_snapshot"]["path"],
            sha256=binding["baseline_snapshot"]["sha256"],
        ),
        ResearchSourceDescriptor(
            id="yili-readiness-review-20260929",
            kind="research_artifact",
            location=binding["readiness_review"]["path"],
            sha256=binding["readiness_review"]["sha256"],
        ),
        ResearchSourceDescriptor(
            id="yili-prior-shared-valuation-20260929",
            kind="research_artifact",
            location=binding["prior_shared_valuation"]["path"],
            sha256=binding["prior_shared_valuation"]["sha256"],
        ),
    )
    binding_refs = [
        {"id": source.id, "sha256": source.sha256}
        for source in binding_sources
    ]

    assumptions = review["model"]["assumptions"]
    percent = Decimal("0.01")
    scenarios = {
        name: ResidualIncomeScenarioInputs(
            cost_of_equity=Decimal("0.09"),
            forecast_roes=tuple(
                Decimal(str(value)) * percent
                for value in assumptions["forecast_roe_pct"][name]
            ),
            terminal_roe=(
                Decimal(str(assumptions["terminal_roe_pct"][name])) * percent
            ),
            terminal_growth=Decimal("0.02"),
            retention=Decimal("0.25"),
        )
        for name in ("bear", "base", "bull")
    }
    facts = QualityCompounderFacts(
        symbol=baseline_case["symbol"],
        as_of=date.fromisoformat(review["valuation_basis_as_of"]),
        verified=True,
        confidence="低",
        evidence_refs=facts_refs,
        blockers=[],
        operating_inputs={
            "start_book_equity": Decimal(assumptions["opening_parent_equity_cny"]),
            "ordinary_shares": Decimal(
                assumptions["ordinary_shares_as_of_2026_06_30"]
            ),
        },
        scenario_inputs=scenarios,
    )

    package_path = ROOT / artifact["run"]["source_package"]["path"]
    assert _sha256_file(package_path) == artifact["run"]["source_package"]["sha256"]
    descriptor = build_descriptor(
        load_descriptor_payloads(ROOT)[baseline_case["symbol"]],
        root=ROOT,
    )
    point_in_time = replace(
        descriptor.point_in_time,
        research_as_of=research_as_of,
        report_period=facts.as_of,
        valuation_date=facts.as_of,
        available_at=available_at,
        computed_at=computed_at,
    )
    research_case = replace(
        descriptor.research_case,
        run_id=case_id,
        symbol=baseline_case["symbol"],
        name=plan_case["name"],
        as_of=research_as_of,
        generated_at=computed_at,
        mispricing_hypothesis=baseline_case["mispricing_hypothesis"],
        financial_summary={
            **descriptor.research_case.financial_summary,
            "parent_equity_2026h1_cny": assumptions["opening_parent_equity_cny"],
            "ordinary_shares_as_of_2026_06_30": assumptions[
                "ordinary_shares_as_of_2026_06_30"
            ],
            "prospective_baseline_case_id": case_id,
        },
        evidence_refs=[*facts_refs, *binding_refs],
        positives=_remap_case_references(
            descriptor.research_case.positives
        ),
        counter_evidence=_remap_case_references(
            descriptor.research_case.counter_evidence
        ),
        thesis_breakers=_remap_case_references(
            descriptor.research_case.thesis_breakers
        ),
        next_events=_remap_case_references(
            descriptor.research_case.next_events
        ),
        valuation_status=artifact["followup"]["valuation_readiness"],
        research_status=baseline_case["research_status"],
        quote_date=None,
        financial_period=facts.as_of,
        missing_date_reasons={
            "quote_date": "No price or price bridge is admitted in this research-only run."
        },
    )
    descriptor = replace(
        descriptor,
        name=plan_case["name"],
        run_id=run["run_id"],
        point_in_time=point_in_time,
        sources=(*official_sources, *binding_sources),
        research_case=research_case,
        facts=facts,
        assumptions=None,
        assumption_bindings=(),
        distribution_result=None,
        quote=None,
        model_validity_input=None,
        valuation_approval=None,
        blockers=(),
        input_sha256=None,
    )
    descriptor = finalize_input_descriptor(descriptor)
    outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(build_research_run_spec(descriptor))
    return descriptor, outcome


def _remap_case_references(items: list[dict]) -> list[dict]:
    source_id_map = {
        "yili_fy2025_annual": "cninfo:1225259562",
        "yili_2026h1": "cninfo:1225511409",
    }
    return [
        {
            **item,
            "evidence_refs": [
                source_id_map.get(ref, ref)
                for ref in item.get("evidence_refs", [])
            ],
        }
        for item in items
    ]


def test_followup_runs_for_the_registered_yili_case_without_rewriting_v13():
    artifact = _json(ARTIFACT_PATH)
    review = _json(REVIEW_PATH)
    descriptor, outcome = _build_followup_run(artifact, review)
    valuation_payload = json.loads(outcome.valuation.to_json())

    assert descriptor.run_id == artifact["run"]["run_id"]
    assert descriptor.research_case.run_id == artifact["case_binding"]["case_id"]
    assert descriptor.research_case.symbol == "600887"
    assert descriptor.research_case.name == "伊利股份"
    assert descriptor.research_case.valuation_status == artifact["research_case"][
        "followup_valuation_status"
    ]
    assert descriptor.research_case.research_status == artifact["research_case"][
        "research_status"
    ]
    assert descriptor.input_sha256 == artifact["run"]["input_descriptor_sha256"]
    assert outcome.issuer_identity_status == artifact["issuer_identity_status"] == "VERIFIED"
    assert outcome.route.as_policy() == artifact["valuation_route"]
    assert valuation_payload == artifact["valuation_result"]
    assert _canonical_sha256(valuation_payload) == artifact["valuation_result_sha256"]
    assert valuation_payload["status"] == "conditional_research_only"
    assert valuation_payload["blockers"] == []
    assert artifact["followup"]["blocker_classification"] == review["blocker_classification"]
    expected_cash_scenarios = json.loads(
        json.dumps(review["distributable_cash_scenarios"])
    )
    exact_base_proxy = Decimal("11.307") * (Decimal("1") - Decimal("0.30"))
    policy_amount = (
        Decimal("1.22") * Decimal("6325360667") / Decimal("1000000000")
    )
    exact_headroom = exact_base_proxy - policy_amount
    assert exact_headroom == Decimal("0.19795998626")
    expected_cash_scenarios["policy_floor_stress_check"][
        "base_proxy_headroom_before_unmodeled_uses_cny_bn"
    ] = str(exact_headroom)
    assert artifact["followup"]["normalized_distributable_cash_scenarios"] == (
        expected_cash_scenarios
    )
    assert artifact["followup"]["numeric_correction"]["prior_value"] == (
        "0.19805998626"
    )
    assert artifact["followup"]["numeric_correction"]["corrected_value"] == (
        str(exact_headroom)
    )
    assert review["blocker_classification"]["A_BLOCKING_UNKNOWN"] == {
        "before": 2,
        "now": 0,
        "items_closed_or_downgraded": [
            "June 30 ordinary-share basis verified from H1 share-capital note",
            "normalized ROE moved into explicit low-confidence bear/base/bull assumptions",
        ],
    }
    assert outcome.price_bridge.current_price is None
    assert outcome.price_bridge.model_validity_status == "UNKNOWN"
    assert outcome.price_bridge.bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.gate.internal_status == artifact["result_gates"]["research_gate_status"]
    assert artifact["result_gates"]["price_bridge_status"] == "PENDING_EXTERNAL_DATA"
    assert artifact["followup"]["baseline_mutated"] is False
    assert artifact["followup"]["strict_pit"] == "NOT_PROVEN"
    assert artifact["followup"]["quote_day_model_validity"] == "NOT_ESTABLISHED"
    assert artifact["followup"]["price_bridge"] is None
    assert artifact["followup"]["decision_review"] == "NOT_ASSESSABLE"
    assert artifact["action"] == "no_order"
