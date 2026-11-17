"""Direct negative gates for unapproved pending-candidate research thresholds."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research import pending_candidate_price_proposal as adapter


@pytest.fixture
def case():
    root = Path(__file__).resolve().parents[1]
    path = next((root / adapter.CONFIG_DIRECTORY).glob("97a83c*.json"))
    config = json.loads(path.read_text(encoding="utf-8"))
    bound = config["exact_basis"]
    analysis = dict(status="CONDITIONAL_ANALYSIS_VERIFIED", action="no_order",
        arithmetic_complete=True, strategy_admitted=False, action_admitted=False,
        price_comparison_eligible=False, symbol=bound["symbol"],
        review_binding=deepcopy(bound["review_binding"]),
        input_descriptor_sha256=bound["input_descriptor_sha256"],
        research_version=bound["research_version"], valuation_date=bound["valuation_date"],
        available_at=bound["available_at"], computed_at=bound["computed_at"],
        valuation=dict(model_version=bound["model_version"], model_type=bound["model_type"],
            valuation_date=bound["valuation_date"], confidence=bound["confidence"],
            **{name + "_value": bound[name] for name in ("bear", "base", "bull")}),
        consumed_operating_inputs=dict(ordinary_shares=bound["ordinary_shares"]),
        source_catalog=[dict(id="test-source", available_at=bound["available_at"])],
        source_bindings=[dict(path="test-source.json", sha256="a" * 64)],
        scenarios=[dict(scenario=name, per_share_value=bound[name]) for name in ("bear", "base", "bull")],
        joint_capital_review=dict(economic_path=dict(currency="CNY"),
            candidate_binding=deepcopy(bound["candidate_binding"]),
            input_descriptor_sha256=bound["input_descriptor_sha256"],
            policy_binding=deepcopy(bound["economic_policy_binding"]),
            proposal_binding=deepcopy(bound["valuation_proposal_binding"]),
            scenarios=[dict(scenario=name, valuation_per_share=bound[name])
                       for name in ("bear", "base", "bull")]))
    config["exact_basis"] = adapter.exact_basis(analysis)
    return analysis, config, datetime.fromisoformat(config["available_at"])


def project(case, **kwargs):
    analysis, config, now = case
    return adapter.project_pending_candidate_price_proposal(analysis=analysis,
        config=config, now=kwargs.get("now", now), policy_artifact_sha256="b" * 64)


def assert_rejected(result):
    assert result["status"] == "rejected"
    assert result["draft_prices"] is None
    assert result["draft"] is None
    assert result["formal_eligibility"] is False
    assert result["proposal_validity"]["current_valid"] is False
    assert result["reason_codes"]


def test_domain_preview_strings_and_authority_remain_separate(case):
    before = deepcopy(case)
    result = project(case)
    assert case == before
    assert result["status"] == "researcher_proposal"
    assert result["draft"]["schema_version"] == "value-price-policy-draft-v1"
    assert result["draft"]["registered"] is False
    assert result["draft"]["rules"] == case[1]["rules"]
    assert result["draft_prices"] == dict(entry=case[0]["valuation"]["bear_value"],
        reduce=case[0]["valuation"]["bull_value"], add=None, exit=None)
    for name in ("formal_eligibility", "user_approved", "formally_prepared", "currentpricecomparison"):
        assert result[name] is False
    assert result["quantities"] is result["value"] is None
    assert result["unit"] == "CNY/share"
    assert result["action"] == "no_order"
    assert result["price_comparison"]["status"] == "not_performed"
    assert result["currentqualification"]["status"] == "not_established"
    assert result["sourcebindings"]["candidate_sha256"] == case[1]["exact_basis"]["candidate_binding"]["sha256"]
    assert "LOW_CONFIDENCE_BEAR_NOT_SUFFICIENT_SAFETY_MARGIN" in result["reason_codes"]


@pytest.mark.parametrize("path,value", [
    (("review_binding", "candidate_binding", "sha256"), "f" * 64),
    (("input_descriptor_sha256",), "f" * 64),
    (("research_version",), "changed"),
    (("valuation_date",), "2026-07-01"),
    (("valuation", "model_version"), "changed"),
    (("valuation", "bear_value"), "1"),
    (("valuation", "confidence"), "HIGH"),
    (("consumed_operating_inputs", "ordinary_shares"), "1"),
    (("available_at",), "2026-10-29T00:00:00+00:00"),
    (("computed_at",), "2026-10-29T00:00:00+00:00"),
    (("joint_capital_review", "economic_path", "currency"), "USD"),
    (("joint_capital_review", "policy_binding", "sha256"), "f" * 64),
    (("source_bindings",), []), (("source_catalog",), []),
    (("strategy_admitted",), True), (("price_comparison_eligible",), True),
    (("share_basis",), "adjusted"), (("currency",), "USD"),
])
def test_changed_identity_never_falls_back(case, path, value):
    target = case[0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert_rejected(project(case))


@pytest.mark.parametrize("field,value", [
    ("available_at", True), ("available_at", 1), ("expires_at", False),
    ("expires_at", "2026-11-01"), ("rationale", True),
    ("dividend_coverage_risk", 1), ("explanation", []),
    ("reopenconditions", "not-an-array"), ("reopenconditions", [False]),
    ("reopenconditions", []), ("reopenconditions", [""]),
    ("currency", "USD"), ("share_basis", "adjusted"),
    ("rules", []), ("rules", [True]), ("registered", True),
])
def test_malformed_or_unauthorized_config_rejects(case, field, value):
    case[1][field] = value
    assert_rejected(project(case))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "999999"])
def test_even_rebound_invalid_scenario_cannot_calculate(case, value):
    case[0]["valuation"]["bear_value"] = value
    case[1]["exact_basis"] = adapter.exact_basis(case[0])
    assert_rejected(project(case))


def test_changed_fraction_is_not_generic_discount(case):
    case[1]["rules"][0]["value_fraction"] = "0.8"
    assert_rejected(project(case))


def test_fixed_expiry_retains_dated_draft_without_current_qualification(case):
    expiry = datetime.fromisoformat(case[1]["expires_at"])
    before = project(case, now=expiry - timedelta(microseconds=1))
    expired = project(case, now=expiry)
    later = project(case, now=expiry + timedelta(days=30))
    assert before["proposal_validity"]["current_valid"] is True
    assert expired["proposal_validity"]["status"] == "expired"
    assert expired["proposal_validity"]["current_valid"] is False
    assert expired["draft"] == later["draft"] == before["draft"]
    assert expired["draft_prices"] == later["draft_prices"] == before["draft_prices"]
    assert later["proposal_validity"]["expires_at"] == case[1]["expires_at"]
    assert later["draft"]["basis"]["valuation_date"] == "2026-06-30"
    assert later["currentpricecomparison"] is False


def test_future_and_naive_time_do_not_publish(case):
    future = project(case, now=case[2] - timedelta(microseconds=1))
    assert_rejected(future)
    assert future["proposal_validity"]["status"] == "not_yet_available"
    assert_rejected(project(case, now=case[2].replace(tzinfo=None)))
    assert_rejected(project(case, now=True))
    case[1]["expires_at"] = case[1]["available_at"]
    assert_rejected(project(case))


def write_config(root, case):
    path = root / adapter.CONFIG_DIRECTORY / (case[1]["exact_basis"]["candidate_binding"]["sha256"] + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(case[1]), encoding="utf-8")
    return path


def test_no_candidate_config_is_precise_rejection(case, tmp_path):
    result = adapter.load_pending_candidate_price_proposal(root=tmp_path, analysis=case[0], now=case[2])
    assert_rejected(result)
    assert result["reason_codes"] == ["NO_EXPLICIT_CANDIDATE_PRICE_PROPOSAL"]


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_source_bytes_are_verified_before_and_after(case, tmp_path, monkeypatch, fail_at):
    from value_investment_agent.application.research import value_research_analysis
    write_config(tmp_path, case)
    calls = []
    def bound(root, binding):
        calls.append(binding)
        if len(calls) == fail_at:
            raise ValueError("source changed")
    monkeypatch.setattr(value_research_analysis, "_bound", bound)
    result = adapter.load_pending_candidate_price_proposal(root=tmp_path, analysis=case[0], now=case[2])
    assert_rejected(result)
    assert "source changed" in result["reason_codes"][0]


def test_policy_changed_during_read_is_rejected(case, tmp_path, monkeypatch):
    from value_investment_agent.application.research import value_research_analysis
    path = write_config(tmp_path, case)
    def bound(root, binding):
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    monkeypatch.setattr(value_research_analysis, "_bound", bound)
    result = adapter.load_pending_candidate_price_proposal(root=tmp_path, analysis=case[0], now=case[2])
    assert_rejected(result)
    assert "POLICY_ARTIFACT_CHANGED_DURING_READ" in result["reason_codes"][0]
