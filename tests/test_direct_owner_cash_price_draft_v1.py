"""Explicit fixtures, not production source replay or approval evidence."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json

import pytest

from value_investment_agent.application.decision import direct_owner_cash_price_draft_v1 as adapter
from value_investment_agent.domain.decision.value_price_policy import draft_value_price_policy, preview_draft_prices
from value_investment_agent.valuation_models.base import ValuationResult


@pytest.fixture
def inputs():
    return dict(
        plan=dict(symbol="000568", action="no_order", research_version="TEST_ONLY_R1",
                  valuation_input_version="TEST_ONLY_I1", model_id="TEST_ONLY_RI",
                  model_type="TEST_ONLY_DIRECT", model_version="TEST_ONLY_V1",
                  valuation_date="2025-12-31", bear="10", base="20", bull="30",
                  source_bindings=[dict(path="TEST_ONLY/source.json", sha256="a" * 64)]),
        rule_config=dict(draft_id="TEST_ONLY_D1", policy_id="TEST_ONLY_P1", rule_version="TEST_ONLY_RULE1",
                         profile_id="TEST_ONLY_PROFILE", effective_from="2026-01-01",
                         effective_through="2026-11-30", rationale="TEST_ONLY explicit research assumption",
                         dividend_coverage_risk="TEST_ONLY conditional distribution",
                         rules=[dict(action="entry", scenario="bear", value_fraction="0.83",
                                     comparison="LTE", rationale="TEST_ONLY explicit fraction")]),
        as_of=date(2026, 11, 16),
    )


def test_exact_domain_preview_no_mutation_and_frontend_contract(inputs, monkeypatch):
    original = deepcopy(inputs)
    calls = []

    def draft(*args, **kwargs):
        calls.append("draft")
        return draft_value_price_policy(*args, **kwargs)

    def preview(value):
        calls.append("preview")
        return preview_draft_prices(value)

    monkeypatch.setattr(adapter, "draft_value_price_policy", draft)
    monkeypatch.setattr(adapter, "preview_draft_prices", preview)
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert calls == ["draft", "preview"]
    assert result["draft_prices"] == dict(entry="8.30", add=None, reduce=None, exit=None)
    assert result["currentpricecomparison"] is False
    assert result["action"] == "no_order"
    assert result["approved"] is result["registered"] is False
    assert result["draft"]["registered"] is False
    assert result["expires_at"] == "2026-11-30"
    assert "HISTORICAL_CONDITIONAL" in result["status"]
    assert result["draft"]["basis"]["valuation_date"] == "2025-12-31"
    assert inputs == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field,reason", [
    ("research_version", "MISSING_SOURCE_VERSION:research_version"),
    ("valuation_input_version", "MISSING_SOURCE_VERSION:valuation_input_version"),
    ("source_bindings", "MISSING_OR_INVALID_SOURCE_BINDINGS"),
    ("valuation_date", "INVALID_OR_MISSING_DATE:valuation_date"),
    ("base", "SCENARIOS_UNAVAILABLE"),
])
def test_missing_plan_evidence_rejects_before_domain(inputs, monkeypatch, field, reason):
    del inputs["plan"][field]
    monkeypatch.setattr(adapter, "draft_value_price_policy", lambda *a, **k: pytest.fail("must reject first"))
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert result["status"] == "REJECTED"
    assert result["draft_prices"] is None
    assert reason in result["reason_codes"]


@pytest.mark.parametrize("field,value,reason", [
    ("rationale", " ", "MISSING_RULE_CONFIG:rationale"),
    ("effective_through", None, "INVALID_OR_MISSING_DATE:effective_through"),
    ("effective_through", "2026-11-15", "EXPIRED"),
    ("effective_from", "2026-11-17", "NOT_YET_EFFECTIVE"),
    ("effective_from", "2026-12-01", "INVALID_VALIDITY_INTERVAL"),
    ("rules", [], "EXPLICIT_RULES_REQUIRED"),
])
def test_explicit_config_rejections(inputs, field, value, reason):
    inputs["rule_config"][field] = value
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert result["draft_prices"] is None
    assert reason in result["reason_codes"]
    assert result["action"] == "no_order"


@pytest.mark.parametrize("patch,reason", [
    ({"rationale": ""}, "MISSING_RULE_RATIONALE:0"),
    ({"value_fraction": None}, "INVALID_EXPLICIT_PRICE_POLICY"),
    ({"value_fraction": "NaN"}, "INVALID_EXPLICIT_PRICE_POLICY"),
    ({"comparison": "GTE"}, "INVALID_EXPLICIT_PRICE_POLICY"),
])
def test_invalid_rule_never_falls_back_to_margin(inputs, patch, reason):
    inputs["rule_config"]["rules"][0].update(patch)
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert result["draft_prices"] is None
    assert reason in result["reason_codes"]


def test_current_quote_cannot_change_draft_prices(inputs):
    expected = adapter.draft_direct_owner_cash_price(**inputs)
    for price in ("0.01", "999999"):
        inputs["plan"].update(current_price=price, reference_quote={"price": price})
        assert adapter.draft_direct_owner_cash_price(**inputs) == expected


def test_expiry_day_is_inclusive_and_clock_is_explicit(inputs):
    inputs["as_of"] = date(2026, 11, 30)
    assert adapter.draft_direct_owner_cash_price(**inputs)["draft_prices"] is not None
    inputs["as_of"] = date(2026, 12, 1)
    assert "EXPIRED" in adapter.draft_direct_owner_cash_price(**inputs)["reason_codes"]
    inputs["as_of"] = None
    assert "EXPLICIT_AS_OF_DATE_REQUIRED" in adapter.draft_direct_owner_cash_price(**inputs)["reason_codes"]


def valuation():
    return ValuationResult(symbol="000568", model_type="TEST_ONLY_DIRECT", valuation_date=date(2025, 12, 31),
                           bear_value=Decimal("10"), base_value=Decimal("20"), bull_value=Decimal("30"),
                           confidence="低", assumptions={}, sensitivities=[], evidence_refs=[{"id": "TEST_ONLY"}],
                           blockers=[], status="conditional_research_only", model_version="TEST_ONLY_V1")


def test_valuation_result_projection_and_mismatch_rejection(inputs):
    inputs["valuation"] = valuation()
    del inputs["plan"]["bear"]
    assert adapter.draft_direct_owner_cash_price(**inputs)["draft_prices"]["entry"] == "8.30"
    inputs["plan"]["base"] = "21"
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert result["draft_prices"] is None
    assert "VALUATION_PLAN_MISMATCH:base" in result["reason_codes"]


@pytest.mark.parametrize("field,value,reason", [
    ("symbol", "600519", "VALUATION_PLAN_MISMATCH:symbol"),
    ("model_version", "TEST_ONLY_OTHER", "VALUATION_PLAN_MISMATCH:model_version"),
    ("valuation_date", "2025-12-30", "VALUATION_PLAN_MISMATCH:valuation_date"),
    ("action", "order", "NO_ORDER_PLAN_REQUIRED"),
    ("source_bindings", [{"path": "test", "sha256": "bad"}], "MISSING_OR_INVALID_SOURCE_BINDINGS"),
])
def test_identity_and_source_guards(inputs, field, value, reason):
    inputs["valuation"] = valuation()
    inputs["plan"][field] = value
    result = adapter.draft_direct_owner_cash_price(**inputs)
    assert result["draft_prices"] is None
    assert reason in result["reason_codes"]


def test_not_ready_valuation_rejected(inputs):
    from dataclasses import replace
    inputs["valuation"] = replace(valuation(), status="not_ready")
    assert "VALUATION_NOT_READY_OR_BLOCKED" in adapter.draft_direct_owner_cash_price(**inputs)["reason_codes"]



@pytest.mark.parametrize("fault", [None, "failed_check", "wrong_candidate", "expired", "policy_tampered"])
def test_successor_policy_requires_exact_f2_and_explicit_bound_rules(tmp_path, inputs, fault):
    from datetime import datetime, timezone
    from hashlib import sha256

    from value_investment_agent.application.product.parent_owner_distribution_successor_view_v2 import (
        read_aligned_owner_distribution_price,
    )
    from value_investment_agent.application.research.pending_candidate_alignment import CHECK_IDS, CONFIG_DIRECTORY

    def write(name, data):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        return dict(path=name, sha256=sha256(raw).hexdigest())

    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    candidate = write("candidate.json", {"fixture": "TEST_ONLY"})
    descriptor = "a" * 64
    view = dict(receipt_binding=candidate, input_descriptor_sha256=descriptor,
                symbol="000568", research_case={"research_version": "TEST_ONLY_R1"},
                valuation={key: inputs["plan"][key] for key in ("model_type", "model_version", "valuation_date")},
                scenario_valuations=dict(bear="10", base="20", bull="30"))
    rule = deepcopy(inputs["rule_config"])
    if fault == "expired":
        rule["effective_through"] = "2026-11-15"
    policy = write("policy.json", dict(schema_version="owner-distribution-price-policy-input-v1",
        action="no_order", candidate_binding=candidate if fault != "wrong_candidate" else {},
        input_descriptor_sha256=descriptor, rule_config=rule))
    config = write(f"{CONFIG_DIRECTORY}/{candidate['sha256']}.json", dict(price_policy_binding=policy))
    checks = [dict(id=key, status="PASS") for key in CHECK_IDS]
    if fault == "failed_check":
        checks[1]["status"] = "BLOCKED"
    if fault == "policy_tampered":
        (tmp_path / policy["path"]).write_text("{}", encoding="utf-8")
    alignment = dict(status="ALIGNED_FOR_RESEARCH_COMPARISON", candidate_binding=candidate,
        input_descriptor_sha256=descriptor, evaluated_at=now.isoformat(), action="no_order",
        formal_eligibility=False, currentpricecomparison=True, checks=checks,
        price_bridge={"bridge_status": "READY"}, quote_date="2026-11-16",
        evidence_bindings=[candidate, config])
    result = read_aligned_owner_distribution_price(root=tmp_path, view=view, alignment=alignment, now=now)
    assert result["action"] == "no_order"
    if fault is None:
        assert result["status"] == "UNAPPROVED_ALIGNED_CONDITIONAL_DRAFT"
        assert result["approved"] is False and result["registered"] is False
        assert result["candidate_binding"] == candidate and result["policy_binding"] == policy
    else:
        assert result["status"] in {"BLOCKED", "REJECTED"} and not result.get("draft_prices")
