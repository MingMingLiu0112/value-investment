from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

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
REVIEW_PATH = ROOT / "docs/current/600887-valuation-readiness-review-20260929.json"
RESULT_PATH = ROOT / "docs/current/600887-shared-valuation-result-20260929.json"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_yili_result_replays_through_registered_model_and_issuer_gate():
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    result_artifact = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assumptions = review["model"]["assumptions"]
    facts_refs = [
        dict(item)
        for item in review["evidence"]
        if str(item.get("id", "")).startswith("cninfo:")
    ]
    sources = tuple(
        ResearchSourceDescriptor(
            id=item["id"],
            kind=item["kind"],
            location=item["url"],
            sha256=item["sha256"],
            issuer_identity=ResearchIssuerIdentity(**item["issuer_identity"]),
        )
        for item in facts_refs
    )
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
        symbol=review["symbol"],
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

    package_path = ROOT / result_artifact["source_package"]["path"]
    assert hashlib.sha256(package_path.read_bytes()).hexdigest() == (
        result_artifact["source_package"]["sha256"]
    )
    descriptor = build_descriptor(
        load_descriptor_payloads(ROOT)["600887"],
        root=ROOT,
    )
    available_at = datetime.fromisoformat(result_artifact["available_at"])
    computed_at = datetime.fromisoformat(result_artifact["computed_at"])
    point_in_time = replace(
        descriptor.point_in_time,
        report_period=facts.as_of,
        valuation_date=facts.as_of,
        available_at=available_at,
        computed_at=computed_at,
    )
    research_case = replace(
        descriptor.research_case,
        quote_date=None,
        missing_date_reasons={
            "quote_date": "Market price is excluded from the valuation model input."
        },
        financial_summary={
            **descriptor.research_case.financial_summary,
            "parent_equity_2026h1_cny": assumptions["opening_parent_equity_cny"],
            "ordinary_shares_as_of_2026_06_30": assumptions[
                "ordinary_shares_as_of_2026_06_30"
            ],
        },
        evidence_refs=facts_refs,
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
    )
    descriptor = replace(
        descriptor,
        run_id=result_artifact["run_id"],
        point_in_time=point_in_time,
        sources=sources,
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
    valuation_payload = json.loads(outcome.valuation.to_json())

    assert descriptor.input_sha256 == result_artifact["input_descriptor_sha256"]
    assert outcome.issuer_identity_status == result_artifact["issuer_identity_status"] == "VERIFIED"
    assert outcome.route.as_policy() == result_artifact["valuation_route"]
    assert valuation_payload == result_artifact["valuation_result"]
    assert _canonical_sha256(valuation_payload) == result_artifact[
        "valuation_result_sha256"
    ]
    assert valuation_payload["status"] == "conditional_research_only"
    assert valuation_payload["blockers"] == []
    assert "not evidence of issuer distributable cash" in valuation_payload[
        "assumptions"
    ]["scope"]
    assert outcome.price_bridge.current_price is None
    assert outcome.price_bridge.model_validity_status == "UNKNOWN"
    assert result_artifact["product_boundary"]["price_review"] == "NOT_ASSESSABLE"
    assert result_artifact["product_boundary"]["action"] == "no_order"
    assert review["price_bridge"] is None
    comparison = review["unvalidated_arithmetic_comparison"]
    assert comparison["status"] == "ARITHMETIC_ONLY_NOT_DECISION_GRADE"
    assert comparison["model_validity"]["status"] == "NOT_ESTABLISHED"
    assert comparison["decision_review"] == "NOT_ASSESSABLE"
    binding = review["model"]["shared_model_binding"]
    assert binding["artifact_path"] == str(RESULT_PATH.relative_to(ROOT)).replace("\\", "/")
    assert binding["artifact_sha256"] == hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest()
    assert binding["source_package_sha256"] == result_artifact["source_package"]["sha256"]
    assert binding["input_descriptor_sha256"] == result_artifact["input_descriptor_sha256"]
    assert binding["valuation_result_sha256"] == result_artifact["valuation_result_sha256"]
    assert [item["id"] for item in valuation_payload["evidence_refs"]] == [
        item["id"] for item in facts_refs
    ]
    assert all(
        item["issuer_identity"]["security_code"] == "600887"
        for item in valuation_payload["evidence_refs"]
    )


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
