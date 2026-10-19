"""Isolated policies and replay fixtures; never real investment approvals."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json

import pytest

from test_value_decision_explanation import synthetic_restored
from value_investment_agent.application.decision.value_action_plan import (
    load_registered_value_action_plans, load_value_action_policy, project_value_action_plan,
)
from value_investment_agent.application.product.value_decision_explanation import project_value_decision_explanation
from value_investment_agent.domain.decision.value_action_plan import (
    ACTION_INTENTS, RegisteredValueActionPolicy, ValuePriceRule, build_value_action_plan,
)


def _explanation(kind="BUY_CANDIDATE"):
    return project_value_decision_explanation(synthetic_restored(kind), evidence_scope="SYNTHETIC_TEST")


def _policy(explanation, actions=("entry",)):
    day = date.fromisoformat(explanation["decision_as_of"])
    return RegisteredValueActionPolicy(
        policy_id="isolated-test-policy", rule_version="isolated-policy-v1",
        symbol=explanation["symbol"],
        profile_id=explanation["price_context"]["price_attractiveness"]["profile_id"],
        model_id=explanation["model_validity"]["model_id"],
        model_version=explanation["valuation"]["model_version"],
        effective_from=day, effective_through=day + timedelta(days=30),
        registered_at=datetime.combine(day, datetime.min.time(), timezone.utc),
        rules=tuple(ValuePriceRule(action=action, scenario="bear" if action in {"entry", "add"} else "bull",
            value_fraction=Decimal("0.93") if action in {"entry", "add"} else Decimal("1.07"),
            comparison="LTE" if action in {"entry", "add"} else "GTE",
            rationale="Explicit isolated policy example, not a real registered issuer threshold") for action in actions),
        source_binding=dict(path="runtime/isolated-policy.json", sha256="a" * 64))


@pytest.mark.parametrize("kind", ["BUY_CANDIDATE", "ADD_CANDIDATE", "HOLD", "TRIM_CANDIDATE", "SELL_CANDIDATE", "NO_ACTION"])
def test_existing_decisions_are_projected_without_implicit_prices_or_approval(kind):
    restored = synthetic_restored(kind)
    original = deepcopy(restored.recommendation.as_policy())
    plan = project_value_action_plan(restored, evidence_scope="SYNTHETIC_TEST")
    explanation = project_value_decision_explanation(restored, evidence_scope="SYNTHETIC_TEST")
    if kind == "NO_ACTION":
        assert plan["action_intent"] is None
    else:
        assert plan["action_intent"] in ACTION_INTENTS
    assert plan["candidate_action"] == kind
    if kind == "HOLD":
        assert plan["action_intent"] == "HOLD"
        assert plan["hold_condition"]["kind"] == "HOLD_THESIS"
        assert plan["hold_condition"]["triggered"] is True
        assert plan["hold_condition"]["reasoning"] == explanation["entry_thesis"]["hold_logic"]
        assert plan["qualification"] == "EXISTING_THESIS_HOLD_REVIEW"
    assert plan["bear"] == original["valuation_range"]["bear"]
    assert plan["base"] == original["valuation_range"]["base"]
    assert plan["bull"] == original["valuation_range"]["bull"]
    assert plan["safety_margin_policy"] is None
    assert all(plan[action + "_trigger_price"] is None for action in ("entry", "add", "reduce", "exit"))
    expected_formal = kind in {"HOLD", "TRIM_CANDIDATE", "SELL_CANDIDATE"}
    assert plan["formal_eligibility"] is expected_formal
    assert plan["portfolio_eligibility"] is None
    assert "BLOCKED_PRIVATE_INPUT" not in plan["blockers"]
    assert plan["position_guidance"] is None and plan["action"] == "no_order"
    assert plan["valuation_recomputed"] is False and plan["approval_changed"] is False
    assert restored.recommendation.as_policy() == original
    if kind in {"TRIM_CANDIDATE", "SELL_CANDIDATE"}:
        action = "reduce" if kind == "TRIM_CANDIDATE" else "exit"
        assert plan[action + "_condition"]["triggered"] is True
        assert plan[action + "_condition"]["price"] is None
        assert plan[action + "_condition"]["entry_id"] == original["entry_id"]
        assert plan["price_comparison_eligible"] is False
        assert plan["qualification"] == "INDEPENDENT_THESIS_REVIEW"
        assert plan["action_intent"] == ("REDUCE" if action == "reduce" else "EXIT")


def test_policy_math_uses_only_explicit_thresholds_and_is_decimal_context_stable():
    explanation = _explanation()
    policy = _policy(explanation, ("entry", "add", "reduce", "exit"))
    first = build_value_action_plan(explanation=explanation, policy=policy).as_policy()
    with localcontext() as context:
        context.prec = 6
        second = build_value_action_plan(explanation=explanation, policy=policy).as_policy()
    assert first == second
    assert first["entry_trigger_price"] == str(Decimal(explanation["valuation"]["bear_value"]) * Decimal("0.93"))
    assert first["exit_trigger_price"] == str(Decimal(explanation["valuation"]["bull_value"]) * Decimal("1.07"))
    assert first["entry_condition"]["source_binding"] == dict(policy.source_binding)
    assert first["qualification"] == "CONDITIONAL_PRICE_PLAN"
    assert first["formal_eligibility"] is False


@pytest.mark.parametrize("kind,action", [("BUY_CANDIDATE", "entry"), ("ADD_CANDIDATE", "add")])
def test_full_existing_admission_can_qualify_security_without_private_inputs(kind, action):
    restored = synthetic_restored(kind)
    explanation = project_value_decision_explanation(restored, evidence_scope="SYNTHETIC_TEST")
    plan = project_value_action_plan(restored, evidence_scope="SYNTHETIC_TEST",
        policy=replace(_policy(explanation, (action,)), model_id=restored.recommendation.input_model_id))
    assert plan[action + "_condition"]["triggered"] is True
    assert plan["formal_eligibility"] is True
    assert plan["formal_eligibility_blockers"] == []
    assert plan["portfolio_eligibility"] is None
    assert "BLOCKED_PRIVATE_INPUT" not in plan["blockers"]
    assert plan["requires_human_review"] is True
    assert plan["action"] == "no_order" and plan["position_guidance"] is None


def test_replay_flag_alone_cannot_replace_existing_predecision():
    explanation = _explanation()
    plan = build_value_action_plan(explanation=explanation, policy=_policy(explanation),
                                  repository_replayed=True).as_policy()
    assert plan["formal_eligibility"] is False
    assert "VALUE_VERIFIED_PREDECISION_REQUIRED" in plan["formal_eligibility_blockers"]


@pytest.mark.parametrize("gate", ["g3", "date", "price", "policy", "rule"])
def test_missing_existing_gate_blocks_only_security_formal_qualification(gate):
    restored = synthetic_restored("BUY_CANDIDATE")
    explanation = project_value_decision_explanation(restored, evidence_scope="SYNTHETIC_TEST")
    admission = restored.dependency_objects["pre_decision"]
    policy = _policy(explanation)
    if gate == "g3":
        admission = replace(admission, status="NOT_ELIGIBLE", positive_price_review_eligible=False,
                            price_attractiveness_status="NOT_ASSESSABLE",
                            blockers=("human_research_approval_not_resolved",))
    elif gate == "date":
        admission = replace(admission, decision_as_of=admission.decision_as_of - timedelta(days=1))
    elif gate == "price":
        explanation["price_context"]["positive_price_review_eligible"] = False
    elif gate == "policy":
        policy = None
    else:
        explanation["rule_evidence"]["full_buy_gate_passed"] = False
    plan = build_value_action_plan(explanation=explanation, policy=policy,
        repository_replayed=True, verified_predecision=admission).as_policy()
    assert plan["formal_eligibility"] is False
    assert plan["formal_eligibility_blockers"]
    assert plan["portfolio_eligibility"] is None


@pytest.mark.parametrize("change,blocker", [
    ({"symbol": "000333"}, "VALUE_POLICY_NOT_APPLICABLE"),
    ({"model_version": "wrong-version"}, "VALUE_POLICY_NOT_APPLICABLE"),
    ({"profile_id": "wrong-profile"}, "VALUE_POLICY_NOT_APPLICABLE"),
    ({"effective_through": date(2026, 1, 1), "effective_from": date(2025, 1, 1)}, "VALUE_POLICY_NOT_CURRENT_OR_NOT_YET_REGISTERED"),
])
def test_wrong_issuer_profile_version_or_expired_policy_cannot_emit_price(change, blocker):
    explanation = _explanation()
    policy = replace(_policy(explanation), **change)
    plan = build_value_action_plan(explanation=explanation, policy=policy).as_policy()
    assert plan["entry_trigger_price"] is None and blocker in plan["blockers"]


def test_pending_g3_does_not_become_a_trigger_or_formal_approval():
    explanation = _explanation()
    explanation["price_context"]["positive_price_review_eligible"] = False
    explanation["blockers"].append("human_research_approval_not_resolved")
    plan = build_value_action_plan(explanation=explanation, policy=_policy(explanation)).as_policy()
    assert plan["entry_trigger_price"] is not None
    assert plan["entry_condition"]["triggered"] is None
    assert plan["price_comparison_eligible"] is False and plan["formal_eligibility"] is False
    assert "human_research_approval_not_resolved" in plan["blockers"]


def test_new_quote_not_covered_by_model_scan_cannot_emit_a_current_price_plan():
    explanation = _explanation()
    day = date.fromisoformat(explanation["decision_as_of"])
    next_day = day + timedelta(days=1)
    quote = dict(symbol=explanation["symbol"], price="10", quote_date=next_day.isoformat(),
                 status="verified_close", comparison_eligible=True)
    plan = build_value_action_plan(explanation=explanation, policy=_policy(explanation),
                                   reference_quote=quote, decision_as_of=next_day).as_policy()
    assert plan["entry_trigger_price"] is None and plan["price_comparison_eligible"] is False
    assert "VALUE_MODEL_EVENT_SCAN_DOES_NOT_COVER_QUOTE" in plan["blockers"]


def test_requires_replayed_typed_decision_and_does_not_mutate_inputs():
    restored = synthetic_restored("BUY_CANDIDATE")
    with pytest.raises(ValueError, match="repository-restored"):
        project_value_action_plan(restored.recommendation.as_policy(), evidence_scope="SYNTHETIC_TEST")
    with pytest.raises(ValueError, match="successful existing replay"):
        project_value_action_plan(replace(restored, verification={}), evidence_scope="SYNTHETIC_TEST")


def _published(tmp_path, monkeypatch, kind="NO_ACTION"):
    from value_investment_agent.application.decision import value_action_plan as module
    explanation = _explanation(kind)
    explanation["evidence_scope"] = "RETAINED_RESEARCH"
    # This is an isolated published fixture, never a real retained approval.
    explanation["valuation"]["evidence_refs"] = [dict(id="isolated-fact", path="runtime/fact.txt", sha256=hashlib.sha256(b"fact").hexdigest())]
    directory = tmp_path / "runtime"
    directory.mkdir()
    (directory / "fact.txt").write_bytes(b"fact")
    path = directory / (explanation["symbol"] + "-value-decision-explanation.json")
    path.write_text(json.dumps(explanation), encoding="utf-8")
    binding = dict(path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    chain = dict(model=dict(additional_evidence_bindings=[binding], product_extensions={}))
    monkeypatch.setattr(module, "load_current_chain", lambda root: chain)
    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", lambda *args, **kwargs: dict(
        status="PENDING_EXTERNAL_DATA", quote=None, next_step="need source"))
    return module, explanation, path, chain


def test_published_projection_rechecks_bindings_and_financial_originals(tmp_path, monkeypatch):
    module, explanation, path, chain = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert len(result["items"]) == 1 and not result["blockers"]
    assert result["items"][0]["formal_eligibility"] is False
    assert result["policy_inventory"]["implicit_safety_margin_policy"] is None
    (tmp_path / "runtime/fact.txt").write_bytes(b"tampered")
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert not result["items"] and "evidence hash mismatch" in result["blockers"][0]
    path.write_bytes(path.read_bytes() + b" ")
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert not result["items"] and "binding hash mismatch" in result["blockers"][0]


def test_published_ready_bridge_is_restored_against_existing_valuation(tmp_path, monkeypatch):
    module, explanation, path, chain = _published(tmp_path, monkeypatch, kind="BUY_CANDIDATE")
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert len(result["items"]) == 1 and not result["blockers"]
    assert result["items"][0]["formal_eligibility"] is False
    explanation["price_context"]["price_bridge"]["valuation_bear_value"] = "999"
    path.write_text(json.dumps(explanation), encoding="utf-8")
    chain["model"]["additional_evidence_bindings"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert not result["items"]
    assert "Price bridge" in result["blockers"][0]


@pytest.mark.parametrize("verified,latest_offset,current", [
    (True, 0, True), (False, 0, False), (True, 1, False), (True, None, False)])
def test_display_quote_requires_verification_and_latest_completed_date(
        tmp_path, monkeypatch, verified, latest_offset, current):
    module, explanation, path, chain = _published(tmp_path, monkeypatch, kind="BUY_CANDIDATE")
    explanation["blockers"].extend(["等待已验证收盘行情", "price_bridge_pending_external_data"])
    path.write_text(json.dumps(explanation), encoding="utf-8")
    chain["model"]["additional_evidence_bindings"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    day = date.fromisoformat(explanation["decision_as_of"])
    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", lambda *args, **kwargs: dict(
        status="QUOTE_OBSERVATION", quote=dict(display_price="10", quote_date=day.isoformat(),
            latest_completed_session=None if latest_offset is None else
                (day + timedelta(days=latest_offset)).isoformat(),
            bundle_path="runtime/quote.json", bundle_sha256="b" * 64),
        compatibility=dict(verified_quote=dict(eligible=verified), comparison_eligible=dict(eligible=True))))
    now = datetime.combine(day + timedelta(days=2), datetime.min.time(), timezone.utc)
    plan = load_registered_value_action_plans(tmp_path, now=now)["items"][0]
    assert plan["reference_close"] == "10"
    assert plan["current_quote_verified"] is current
    assert "等待已验证收盘行情" in plan["historical_research_blockers"]
    assert ("等待已验证收盘行情" in plan["blockers"]) is not current
    if not current:
        assert plan["price_comparison_eligible"] is False
        assert plan["reference_price_scope"] == "RETAINED_QUOTE_DISPLAY_ONLY_NOT_CURRENT_VERIFIED"
        assert plan["current_quote_blockers"]


def test_policy_loader_rejects_unregistered_and_future_registration(tmp_path, monkeypatch):
    module, explanation, path, chain = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="not registered"):
        load_value_action_policy(root=tmp_path, binding=chain["model"]["additional_evidence_bindings"][0],
                                 symbol=explanation["symbol"], now=now)
    policy_path = tmp_path / "runtime/policy.json"
    policy_path.write_text(json.dumps(dict(schema_version="registered-value-action-policies-v1",
        action="no_order", status="REGISTERED", policies=[dict(symbol=explanation["symbol"],
        registered_at=(now + timedelta(days=1)).isoformat())])), encoding="utf-8")
    binding = dict(path="runtime/policy.json", sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest())
    chain["model"]["product_extensions"]["value_action_policy_registry"] = binding
    with pytest.raises(ValueError, match="not available"):
        load_value_action_policy(root=tmp_path, binding=binding, symbol=explanation["symbol"], now=now)
