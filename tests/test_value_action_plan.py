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


def _registered_only_quote(tmp_path, monkeypatch):
    from test_quote_session_collection import Session
    from test_quote_sessions import NOW
    from value_investment_agent.application.decision import value_action_plan as module
    from value_investment_agent.quote_session_collection import collect_session_bundle

    monkeypatch.setattr(module, "load_current_chain", lambda root: dict(model=dict(
        additional_evidence_bindings=[], product_extensions={})))
    config = tmp_path / "config"
    config.mkdir()
    (config / "current-company-research-registry.json").write_text(json.dumps(dict(
        schema_version="current-company-research-registry-v1", action="no_order",
        companies={"000333": dict(name="Synthetic registered company", evidence=[],
            missing_inputs=["valuation_scenarios_missing", "等待已验证收盘行情",
                            "price_bridge_pending_external_data"])})), encoding="utf-8")
    bundle = tmp_path / "runtime/quotes/bundle.json"
    bundle.parent.mkdir(parents=True)
    payload = collect_session_bundle(["000333"], session=Session(), clock=lambda: NOW)
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    pointer = config / "current-quote-bridge.json"
    pointer.write_text(json.dumps(dict(schema_version="current-quote-bridge-v1", action="no_order",
        quotes={"000333": dict(registration_scope="QUOTE_OBSERVATION_ONLY",
            quote_bundle="runtime/quotes/bundle.json",
            quote_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())})), encoding="utf-8")
    return module, bundle, pointer, NOW


def _assert_registry_gates(plan):
    assert plan["qualification"] == "REGISTERED_RESEARCH_GAPS_ONLY"
    assert plan["research_as_of"] is None
    assert plan["research_as_of_basis"] == "REGISTERED_RESEARCH_GAPS_ONLY"
    assert "尚无完整估值情景" in plan["explanation"]
    assert plan["bear"] is plan["base"] is plan["bull"] is None
    assert plan["safety_margin_policy"] is None
    assert plan["price_comparison_eligible"] is False
    assert plan["formal_eligibility"] is plan["security_review_eligible"] is False
    assert plan["portfolio_eligibility"] is plan["action_intent"] is None
    assert plan["position_guidance"] is None and plan["action"] == "no_order"
    assert plan["valuation_recomputed"] is plan["approval_changed"] is False
    assert plan["signal_state"] == "BLOCKED"
    assert "valuation_scenarios_missing" in plan["blockers"]
    assert "price_bridge_pending_external_data" in plan["blockers"]
    for action in ("entry", "add", "reduce", "exit", "hold"):
        assert plan[action + "_condition"] is None


@pytest.mark.parametrize("next_morning", [False, True])
def test_registered_only_shows_real_bridge_verified_close_as_observation(
        tmp_path, monkeypatch, next_morning):
    module, bundle, pointer, now = _registered_only_quote(tmp_path, monkeypatch)
    if next_morning:
        now += timedelta(hours=18)
    execute = module.execute_quote_bridge_for_symbol
    calls = []

    def bridge(root, symbol, *, today):
        calls.append((root, symbol, today))
        execution = execute(root, symbol, today=today)
        assert execution["status"] == "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY"
        assert execution["price_admitted"] is False
        # Even an upstream comparison flag cannot qualify registry-only research.
        execution["compatibility"]["comparison_eligible"]["eligible"] = True
        return execution

    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", bridge)
    result = load_registered_value_action_plans(tmp_path, now=now, symbols=["000333"])
    assert not result["blockers"] and len(result["items"]) == 1
    assert calls == [(tmp_path.resolve(), "000333", now)]
    plan = result["items"][0]
    _assert_registry_gates(plan)
    assert plan["reference_close"] == "60"
    assert plan["market_trade_date"] == "2026-09-07"
    assert plan["current_quote_verified"] is True and not plan["current_quote_blockers"]
    assert plan["reference_price_scope"] == ("LAST_COMPLETED_CLOSE_DISPLAY_ONLY" if next_morning
        else "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY")
    assert plan["resolved_historical_quote_blockers"] == ["等待已验证收盘行情"]
    assert "等待已验证收盘行情" not in plan["blockers"]
    for path in (bundle, pointer):
        binding = dict(path=path.relative_to(tmp_path).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        assert binding in plan["source_bindings"] and binding in result["source_bindings"]


@pytest.mark.parametrize("failure", ["future", "stale", "bundle_tamper", "source_tamper",
    "missing_source", "missing_bundle", "missing_registration"])
def test_registered_quote_failure_keeps_research_item_blocked(tmp_path, monkeypatch, failure):
    module, bundle, pointer, now = _registered_only_quote(tmp_path, monkeypatch)
    if failure == "future":
        now -= timedelta(hours=1)
    elif failure == "stale":
        now += timedelta(days=1)
    elif failure == "bundle_tamper":
        bundle.write_bytes(bundle.read_bytes() + b" ")
    elif failure in {"source_tamper", "missing_source"}:
        payload = json.loads(bundle.read_bytes())
        source = payload["references"]["000333"]["document_refs"]["sina"]
        if failure == "missing_source":
            del payload["documents"][source]
        else:
            payload["documents"][source]["sha256"] = "0" * 64
        bundle.write_text(json.dumps(payload), encoding="utf-8")
        registration = json.loads(pointer.read_bytes())
        registration["quotes"]["000333"]["quote_bundle_sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        pointer.write_text(json.dumps(registration), encoding="utf-8")
    elif failure == "missing_bundle":
        bundle.unlink()
    else:
        pointer.unlink()
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert len(result["items"]) == 1 and not result["blockers"]
    plan = result["items"][0]
    _assert_registry_gates(plan)
    assert plan["reference_close"] is plan["market_trade_date"] is None
    assert plan["reference_price_scope"] == "NO_VERIFIED_CLOSE"
    assert plan["current_quote_verified"] is False
    assert plan["current_quote_blockers"] == ["VALUE_LATEST_COMPLETED_QUOTE_NOT_VERIFIED"]
    assert plan["current_quote_blockers"][0] in plan["blockers"]
    assert "等待已验证收盘行情" in plan["blockers"]


@pytest.mark.parametrize("failure", ["date", "price", "bundle_path", "bundle_sha256", "sources", "exception"])
def test_registered_display_price_alone_or_broken_quote_never_drops_research(
        tmp_path, monkeypatch, failure):
    module, bundle, pointer, now = _registered_only_quote(tmp_path, monkeypatch)
    execution = module.execute_quote_bridge_for_symbol(tmp_path, "000333", today=now)
    if failure == "date":
        future = (now.date() + timedelta(days=1)).isoformat()
        execution["quote"].update(quote_date=future, latest_completed_session=future)
    elif failure == "price":
        execution["quote"]["display_price"] = "NaN"
    elif failure == "sources":
        execution["sources"] = []
    elif failure != "exception":
        del execution["quote"][failure]

    def bridge(*args, **kwargs):
        if failure == "exception":
            raise ValueError("Synthetic broken quote")
        return execution

    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", bridge)
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert len(result["items"]) == 1 and not result["blockers"]
    plan = result["items"][0]
    _assert_registry_gates(plan)
    assert plan["current_quote_verified"] is False and plan["reference_close"] is None
    assert plan["reference_price_scope"] == "NO_VERIFIED_CLOSE"
    assert plan["current_quote_blockers"]


@pytest.mark.parametrize("quote_state", ["verified", "unverified", "invalid_price"])
def test_registered_pointer_changed_after_bridge_is_not_delivered(
        tmp_path, monkeypatch, quote_state):
    module, bundle, pointer, now = _registered_only_quote(tmp_path, monkeypatch)
    execute = module.execute_quote_bridge_for_symbol
    old_binding = dict(path=pointer.relative_to(tmp_path).as_posix(),
        sha256=hashlib.sha256(pointer.read_bytes()).hexdigest())

    def bridge(root, symbol, *, today):
        execution = execute(root, symbol, today=today)
        assert execution["compatibility"]["verified_quote"]["eligible"] is True
        assert execution["pointer"] == old_binding
        pointer.write_bytes(pointer.read_bytes() + b" ")
        if quote_state == "unverified":
            execution["compatibility"]["verified_quote"]["eligible"] = False
        elif quote_state == "invalid_price":
            execution["quote"]["display_price"] = "NaN"
        return execution

    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", bridge)
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert not result["blockers"] and len(result["items"]) == 1
    plan = result["items"][0]
    _assert_registry_gates(plan)
    assert plan["current_quote_verified"] is False
    assert plan["reference_close"] is plan["market_trade_date"] is None
    assert plan["current_quote_blockers"] == ["VALUE_LATEST_COMPLETED_QUOTE_NOT_VERIFIED"]
    assert "等待已验证收盘行情" in plan["blockers"]
    if quote_state == "verified":
        assert plan["quote_bridge_status"] == "NOT_ADMITTED"
        assert "Registered quote pointer hash mismatch" in plan["required_confirmations"]
    for sources in (plan["source_bindings"], result["source_bindings"]):
        assert old_binding not in sources
        assert not any(source["path"] in {old_binding["path"], "runtime/quotes/bundle.json"}
                       for source in sources)


@pytest.mark.parametrize("failure", ["missing", "wrong_path", "wrong_hash"])
def test_registered_observation_requires_exact_pointer_binding(tmp_path, monkeypatch, failure):
    module, bundle, pointer, now = _registered_only_quote(tmp_path, monkeypatch)
    execution = module.execute_quote_bridge_for_symbol(tmp_path, "000333", today=now)
    if failure == "missing":
        del execution["pointer"]
    elif failure == "wrong_path":
        execution["pointer"]["path"] = "config/other-quote-bridge.json"
    else:
        execution["pointer"]["sha256"] = "0" * 64
    monkeypatch.setattr(module, "execute_quote_bridge_for_symbol", lambda *a, **k: execution)
    result = load_registered_value_action_plans(tmp_path, now=now)
    assert not result["blockers"] and len(result["items"]) == 1
    plan = result["items"][0]
    _assert_registry_gates(plan)
    assert plan["reference_close"] is None and plan["current_quote_verified"] is False
    assert plan["current_quote_blockers"]
    for sources in (plan["source_bindings"], result["source_bindings"]):
        assert not any(source["path"] in {"config/current-quote-bridge.json",
            "config/other-quote-bridge.json", "runtime/quotes/bundle.json"} for source in sources)
