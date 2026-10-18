"""Preview binding, missing-data vetoes and delegation without journal writes."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from value_investment_agent.application.portfolio import private_risk_preview as preview
from test_private_ips_policy import service

NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")
ASSUMPTIONS = {key: "0" for key in preview.ASSUMPTION_FIELDS}
ASSUMPTIONS.update(lot_size="100", max_trade_notional_cny="1000")


def binding():
    return {"publication_id": "TEST_ONLY", "plan": {"symbol": "300364",
        "research_version": "TEST_ONLY", "case_sha256": "a" * 64,
        "entry_trigger_price": "30", "invalidation_price": "25",
        "market_trade_date": "2026-10-14", "data_available_at": "2026-10-14T15:01:00+08:00",
        "expires_after_session": "2026-10-15", "formal_eligibility": False,
        "current_reference_close": {"limit_up": False, "limit_down": False}}}


def test_missing_assumptions_and_public_plan_keep_facts_and_null_quantity(service, tmp_path):
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364"})
    assert result["facts"]["cash_cny"] == "8000"
    assert result["sizing_preview"]["review_quantity"] is None
    assert "PUBLIC_SNAPSHOT_UNAVAILABLE" in result["sizing_preview"]["blockers"]
    assert "ASSUMPTION_MISSING:lot_size" in result["sizing_preview"]["blockers"]
    assert service.journal.path.read_bytes() == before


def test_public_quantity_rule_removes_only_lot_assumption_gap(service, tmp_path, monkeypatch):
    rule = {"minimum_buy_quantity": 200, "buy_quantity_increment": 1,
        "maximum_buy_quantity": 100000, "lot_size": 1}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (binding(), None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "300364", "liquidity_profile": "UNKNOWN", "trading_rules": rule}])
    assumptions = {key: value for key, value in ASSUMPTIONS.items() if key != "lot_size"}
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": assumptions})["sizing_preview"]
    assert "ASSUMPTION_MISSING:lot_size" not in result["blockers"]
    assert "CANDIDATE_LIQUIDITY_UNKNOWN" in result["blockers"]
    assert result["effective_sizing_inputs"]["lot_size"] == 1
    assert "lot_size" not in result["assumptions"] and "lot_size" not in assumptions
    assert result["verified_rules"] == rule and result["formal_review_quantity"] is None
    assert service.journal.path.read_bytes() == before
    with pytest.raises(ValueError, match="冲突"):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS})


@pytest.mark.parametrize("quantity,blocked", [(0, False), (199, True), (200, False), (201, False), (100001, True)])
def test_star_minimum_and_increment_gate_existing_engine_without_rounding_up(quantity, blocked):
    output = {"review_quantity": quantity, "status": "QUANTITY_REVIEW_ONLY", "blockers": [],
        "engine": {"hotspot_quantity_review": {"review_quantity": quantity, "blockers": []}}}
    preview._enforce_quantity_rule(output, {"minimum_buy_quantity": 200,
        "buy_quantity_increment": 1, "maximum_buy_quantity": 100000})
    assert output["review_quantity"] == (None if blocked else quantity)
    assert output["engine"]["hotspot_quantity_review"]["review_quantity"] == (None if blocked else quantity)


@pytest.mark.parametrize("quantity,expected", [(199, None), (201, 201), (100001, None)])
def test_preview_delegates_star_increment_then_enforces_distinct_minimum(service, tmp_path, monkeypatch, quantity, expected):
    calls = []
    def engine(*args, **kwargs):
        calls.append(kwargs)
        return {"action": "no_order", "blockers": [], "engine": {"hotspot_quantity_review": {
            "review_quantity": quantity, "status": "QUANTITY_REVIEW_ONLY", "blockers": []}}}
    plan = binding()
    plan["plan"]["symbol"] = "688001"
    rule = {"lot_size": 1, "minimum_buy_quantity": 200,
        "buy_quantity_increment": 1, "maximum_buy_quantity": 100000}
    monkeypatch.setattr(preview, "review_private_risk_rehearsal", engine)
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (plan, None))
    # Explicit TEST_ONLY execution substitute; official observations never certify LIQUID.
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "688001", "liquidity_profile": "LIQUID", "trading_rules": rule}])
    assumptions = {key: value for key, value in ASSUMPTIONS.items() if key != "lot_size"}
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "688001", "assumptions": assumptions})
    assert calls[-1]["hotspot_request"]["lot_size"] == 1
    assert result["sizing_preview"]["review_quantity"] == expected
    assert result["sizing_preview"]["sizing_details"]["review_quantity"] == expected
    assert result["sizing_preview"]["formal_review_quantity"] is None
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("forged", ["entry_price_cny", "stop_price_cny", "formal_eligibility", "security_attributes"])
def test_client_cannot_supply_prices_or_verified_eligibility(service, tmp_path, forged):
    with pytest.raises(ValueError, match="只接受"):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", forged: True})


@pytest.mark.parametrize("field,value", [("lot_size", "0"), ("lot_size", "1.5"),
    ("gap_stress_cny", "NaN"), ("buy_fee_fraction", "1.1"), ("sell_fee_fraction", True)])
def test_invalid_explicit_assumptions_refused(service, tmp_path, field, value):
    with pytest.raises(ValueError):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", "assumptions": {field: value}})


def test_real_unknown_execution_attributes_do_not_become_defaults(service, tmp_path, monkeypatch):
    plan = binding()
    plan["plan"]["current_reference_close"] = {}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (plan, None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "300364", "liquidity_profile": "UNKNOWN"}])
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS})
    assert result["sizing_preview"]["review_quantity"] is None
    assert {"CANDIDATE_LIQUIDITY_UNKNOWN", "PRICE_LIMIT_STATE_UNKNOWN"} <= set(result["sizing_preview"]["blockers"])


def test_full_test_only_binding_delegates_to_existing_engine_and_never_grants_admission(service, tmp_path, monkeypatch):
    calls = []
    def engine(*args, **kwargs):
        calls.append(kwargs)
        return {"action": "no_order", "blockers": [], "engine": {"hotspot_quantity_review":
            {"review_quantity": 100, "status": "QUANTITY_REVIEW_ONLY", "blockers": []}}}
    monkeypatch.setattr(preview, "review_private_risk_rehearsal", engine)
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (binding(), None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "300364", "liquidity_profile": "LIQUID"}])
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS})
    request = calls[-1]["hotspot_request"]
    assert request["entry_price_cny"] == "30"
    assert request["stop_price_cny"] == "25"
    assert request["lot_size"] == 100
    assert result["sizing_preview"]["review_quantity"] == 100
    assert result["sizing_preview"]["trade_eligible"] is False
    assert result["sizing_preview"]["formal_eligibility"] is False
    assert result["sizing_preview"]["scope"] == "CONDITIONAL_SCENARIO_ONLY"
    assert result["sizing_preview"]["formal_review_quantity"] is None
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["chain", "registry", "plan", "retired", "stale"])
def test_current_binding_rejects_chain_registry_plan_and_lifecycle_changes(tmp_path, monkeypatch, mutation):
    plan = binding()["plan"]
    plan["signal_state"] = "WATCH"
    packet = {"publication_id": "TEST_ONLY", "research_version": "TEST_ONLY",
        "identity_inputs": {"chain": [], "current_price_conditions": {"TEST_ONLY": True}},
        "price_conditions": {"items": [{"symbol": "300364", "price_action_plan": deepcopy(plan)}]}}
    if mutation == "chain":
        packet["identity_inputs"]["chain"] = ["old"]
    elif mutation == "registry":
        packet["identity_inputs"]["current_price_conditions"] = {"old": True}
    elif mutation == "plan":
        plan["entry_trigger_price"] = "31"
    elif mutation == "retired":
        plan["candidate_lifecycle"] = "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
        packet["price_conditions"]["items"][0]["price_action_plan"] = deepcopy(plan)
    elif mutation == "stale":
        plan["signal_state"] = "STALE"
        packet["price_conditions"]["items"][0]["price_action_plan"] = deepcopy(plan)
    monkeypatch.setattr(preview, "load_current_packet", lambda root: (packet, None))
    monkeypatch.setattr(preview, "load_current_chain", lambda root: {"bindings": []})
    monkeypatch.setattr(preview, "registry_identity", lambda root: {"TEST_ONLY": True})
    monkeypatch.setattr(preview, "load_price_conditions", lambda *args, **kwargs: {
        "items": [{"symbol": "300364", "price_action_plan": plan}]})
    observed, error = preview._current_plan(tmp_path, "300364", NOW)
    assert observed is None
    assert error


def scenario_input():
    from test_dual_sleeve_risk import synthetic_input
    risk_input = synthetic_input()
    risk_input["portfolio"]["snapshot"]["as_of"] = NOW.date().isoformat()
    risk_input["hotspot_request"].update(quote_as_of=NOW.date().isoformat(),
        available_at=NOW.isoformat(), valid_until=(NOW + timedelta(hours=1)).isoformat())
    return {"acknowledged": True, "risk_input": risk_input}


def test_explicit_scenario_yields_engine_quantity_despite_unknown_actual_execution(service, tmp_path, monkeypatch):
    from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
    plan = binding()
    plan["plan"]["symbol"] = "600519"
    plan["plan"]["current_reference_close"] = {}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (plan, None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "600519", "liquidity_profile": "UNKNOWN"}])
    payload = {"symbol": "600519", "assumptions": ASSUMPTIONS}
    before = service.journal.path.read_bytes()
    actual = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload=payload)
    scenario = scenario_input()
    original = deepcopy(scenario)
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={**payload, "scenario": scenario})
    simulated = result.pop("scenario_preview")
    actual.pop("scenario_preview")
    assert result == actual
    assert {"CANDIDATE_LIQUIDITY_UNKNOWN", "PRICE_LIMIT_STATE_UNKNOWN"} <= set(result["sizing_preview"]["blockers"])
    assert result["sizing_preview"]["formal_review_quantity"] is None
    expected = review_dual_sleeve_risk(scenario["risk_input"], generated_at=NOW, allow_synthetic=True)
    assert simulated["engine"] == expected
    assert simulated["review_quantity"] == expected["hotspot_quantity_review"]["review_quantity"] > 0
    assert simulated["namespace"] == simulated["engine"]["namespace"] == "SIMULATED"
    assert simulated["engine"]["aggregate"]["existing_risk_assessment"]["assessment_namespace"] == "SIMULATED"
    assert simulated["formal_review_quantity"] is None
    assert simulated["formal_eligibility"] is simulated["trade_eligible"] is False
    assert scenario == original
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("change", ["acknowledgement", "namespace", "snapshot_namespace", "policy_scope", "symbol", "missing_execution"])
def test_scenario_requires_explicit_isolated_inputs(service, tmp_path, change):
    scenario = scenario_input()
    risk_input = scenario["risk_input"]
    if change == "acknowledgement":
        scenario["acknowledged"] = False
    elif change == "namespace":
        risk_input["namespace"] = "ACTUAL"
    elif change == "snapshot_namespace":
        risk_input["portfolio"]["snapshot"]["namespace"] = "ACTUAL"
    elif change == "policy_scope":
        risk_input["shared_budget"]["policy_scope"] = "USER_CONFIRMED"
    elif change == "symbol":
        risk_input["hotspot_request"]["symbol"] = "000333"
    else:
        del risk_input["hotspot_request"]["liquidity_verified"]
    before = service.journal.path.read_bytes()
    with pytest.raises(ValueError):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "600519", "scenario": scenario})
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("change,blocker", [
    ("liquidity", "hotspot:liquidity_unknown_or_restricted"),
    ("limit", "hotspot:price_limit_execution_risk"),
    ("risk", "hotspot:committed_risk_unknown"),
    ("expired", "hotspot:stale_or_future_input"),
])
def test_scenario_engine_vetoes_are_not_bypassed(service, tmp_path, change, blocker):
    scenario = scenario_input()
    risk_input = scenario["risk_input"]
    if change == "liquidity":
        risk_input["hotspot_request"]["liquidity_verified"] = False
    elif change == "limit":
        risk_input["hotspot_request"]["limit_up"] = True
    elif change == "risk":
        risk_input["allocations"][0]["committed_risk_cny"] = None
    else:
        risk_input["hotspot_request"]["valid_until"] = (NOW - timedelta(seconds=1)).isoformat()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "600519", "scenario": scenario})
    assert result["scenario_preview"]["review_quantity"] is None
    assert blocker in result["scenario_preview"]["blockers"]
    assert result["scenario_preview"]["status"] == "BLOCKED"


def test_scenario_without_public_plan_is_still_independent_and_opt_in(service, tmp_path):
    baseline = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "600519"})
    assert baseline["scenario_preview"]["status"] == "NOT_REQUESTED"
    assert baseline["scenario_preview"]["review_quantity"] is None
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "600519", "scenario": scenario_input()})
    assert result["scenario_preview"]["review_quantity"] > 0
    assert "PUBLIC_SNAPSHOT_UNAVAILABLE" in result["sizing_preview"]["blockers"]
    assert result["sizing_preview"]["review_quantity"] is None


def scenario_choices():
    return {"acknowledged": True,
        "execution": {"liquid": True, "limit_up": False, "limit_down": False},
        "holding_risks": [{"sleeve": "CORE_VALUE", "symbol": "300364", "committed_risk_cny": "10"}],
        "security_risks": [{"symbol": "300364", "cyclical": False, "common_factors": []}]}


@pytest.fixture
def projected_account(service, tmp_path, monkeypatch):
    from test_private_ips_policy import confirm_policy, quotes
    from value_investment_agent.application.portfolio import private_risk_projection as projection
    from value_investment_agent.domain.portfolio.security_attributes import official_observation
    confirm_policy(service)
    service.reconcile({"idempotency_key": "external-test-only", "expected_revision": len(service.records()),
        "reconciled_at": NOW.isoformat(), "confirmation_note": "TEST_ONLY checked account statement",
        "account_evidence": {"id": "TEST_ONLY-statement", "kind": "broker_statement"}})
    quotes(monkeypatch, price="20")
    observation = official_observation({"symbol": "300364", "name": "TEST_ONLY", "exchange": "SZSE",
        "board": "CHINEXT", "listed_on": "2000-01-01", "security_type": "A股"}, industry_code="I",
        known_at=NOW - timedelta(hours=1), valid_until=NOW + timedelta(days=1),
        evidence_refs=[{"id": "TEST_ONLY-official", "path": "TEST_ONLY.json", "sha256": "a" * 64}])
    monkeypatch.setattr(projection, "_verified_attributes", lambda *args, **kwargs: [deepcopy(observation)])
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [deepcopy(observation)])
    plan = binding()
    plan["plan"]["current_reference_close"] = {}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (deepcopy(plan), None))
    return service


@pytest.mark.parametrize("expiry", [None, "", "not-a-date"])
def test_web_choices_missing_plan_expiry_returns_gap_not_server_error(projected_account, tmp_path, monkeypatch, expiry):
    plan = binding()
    plan["plan"]["expires_after_session"] = expiry
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (deepcopy(plan), None))
    before = projected_account.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(projected_account.journal,
        repository_root=tmp_path, generated_at=NOW,
        payload={"symbol": "300364", "assumptions": ASSUMPTIONS,
                 "scenario": scenario_choices()})
    assert "PLAN_EXPIRY_MISSING_OR_INVALID" in result["scenario_preview"]["blockers"]
    assert result["scenario_preview"]["review_quantity"] is None
    assert projected_account.journal.path.read_bytes() == before


def test_web_choices_project_real_adapter_without_changing_actual_result(projected_account, tmp_path, monkeypatch):
    service = projected_account
    payload = {"symbol": "300364", "assumptions": {**ASSUMPTIONS, "lot_size": "1"}}
    baseline = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload=payload)
    before = service.journal.path.read_bytes()
    choices = scenario_choices()
    original_choices = deepcopy(choices)
    captured = []
    original_engine = preview.review_dual_sleeve_risk
    def engine(data, **kwargs):
        captured.append(deepcopy(data))
        return original_engine(data, **kwargs)
    monkeypatch.setattr(preview, "review_dual_sleeve_risk", engine)
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={**payload, "scenario": choices})
    scenario = result.pop("scenario_preview")
    baseline.pop("scenario_preview")
    assert result == baseline
    assert scenario["review_quantity"] is not None, scenario["blockers"]
    assert scenario["review_quantity"] > 0
    assert scenario["engine"]["namespace"] == captured[0]["namespace"] == "SIMULATED"
    assert captured[0]["portfolio"]["snapshot"]["namespace"] == "SIMULATED"
    assert captured[0]["shared_budget"]["policy_scope"] == "SYNTHETIC_POLICY_ONLY"
    assert captured[0]["portfolio"]["snapshot"]["cash_cny"] == result["facts"]["cash_cny"]
    assert scenario["scope"] == "HYPOTHETICAL_CONFIRMED_ACCOUNT_PROJECTION"
    assert scenario["formal_review_quantity"] is None
    assert scenario["trade_eligible"] is scenario["formal_eligibility"] is False
    assert {"CANDIDATE_LIQUIDITY_UNKNOWN", "PRICE_LIMIT_STATE_UNKNOWN"} <= set(result["sizing_preview"]["blockers"])
    assert choices == original_choices
    assert service.journal.path.read_bytes() == before


def test_test_only_positive_sizing_manual_fills_and_restart_close_the_loop(projected_account, tmp_path, monkeypatch):
    from datetime import date
    from decimal import Decimal
    from value_investment_agent.application.portfolio.private_portfolio_service import (
        PrivatePortfolioService, JournalValidationError,
    )

    service = projected_account
    plan = binding()
    plan["plan"].update(entry_trigger_price="10", invalidation_price="9.9", current_reference_close={})
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (deepcopy(plan), None))
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364",
            "assumptions": ASSUMPTIONS, "scenario": scenario_choices()})
    scenario = result["scenario_preview"]
    quantity = scenario["review_quantity"]
    assert quantity is not None, scenario["blockers"]
    assert quantity >= 100 and quantity % 100 == 0 and scenario["blockers"] == []
    assert scenario["namespace"] == "SIMULATED" and scenario["formal_review_quantity"] is None
    assert scenario["trade_eligible"] is scenario["formal_eligibility"] is False
    before = service.portfolio_view(today=date(2026, 10, 14))

    def request(side, transaction, day, price):
        return {"idempotency_key": transaction + "-prepare", "expected_revision": len(service.records()),
            "fill": {"transaction_id": transaction, "side": side, "sleeve": "HOTSPOT_SATELLITE",
                "symbol": "300364", "exchange": "SZSE", "quantity": str(quantity),
                "price_cny": price, "fees_cny": "1", "trade_date": day,
                "next_sell_session": "2026-10-15" if side == "BUY" else None,
                "trading_unit": "100", "decision_id": "TEST_ONLY-scenario",
                "research_version": "TEST_ONLY"}}

    def confirm(body):
        prior = service.portfolio_view(today=date.fromisoformat(body["fill"]["trade_date"]))
        prepared, digest = service.prepare_fill(body)
        # Preparation is not a transaction and must not change cash or lots.
        current = service.portfolio_view(today=date.fromisoformat(body["fill"]["trade_date"]))
        assert current["cash_cny"] == prior["cash_cny"]
        assert current["positions"] == prior["positions"]
        assert current["pending_draft"] is not None and prepared["status"] == "FILL_PREPARED"
        confirmation = {"idempotency_key": body["fill"]["transaction_id"] + "-confirm",
            "expected_revision": len(service.records()), "prepared_record_sha256": digest,
            "confirmed_at": body["fill"]["trade_date"] + "T20:00:00+08:00",
            "confirmation_note": "TEST_ONLY simulated manual fill; not a broker transaction"}
        first = service.confirm_fill(confirmation)
        assert service.confirm_fill(confirmation) == first
        return first[0]

    bought = confirm(request("BUY", "TEST_ONLY-positive-buy", "2026-10-14", "10"))
    assert Decimal(bought["cash_cny"]) == Decimal(before["cash_cny"]) - Decimal(quantity) * 10 - 1
    journal_before_rejection = service.journal.path.read_bytes()
    with pytest.raises(JournalValidationError):
        service.prepare_fill(request("SELL", "TEST_ONLY-early-sell", "2026-10-14", "11"))
    assert service.journal.path.read_bytes() == journal_before_rejection
    sold = confirm(request("SELL", "TEST_ONLY-positive-sell", "2026-10-15", "11"))
    assert Decimal(sold["cash_cny"]) == Decimal(before["cash_cny"]) + Decimal(quantity) - 2
    assert Decimal(sold["realized_pnl_cny"]) == Decimal(quantity) - 2
    assert sold["positions"] == before["positions"]
    assert [trade["research_version"] for trade in sold["trades"]] == ["TEST_ONLY", "TEST_ONLY"]
    stable = service.journal.path.read_bytes()
    restarted = PrivatePortfolioService(service.journal).portfolio_view(today=date(2026, 10, 15))
    for key in ("cash_cny", "positions", "realized_pnl_cny", "revision"):
        assert restarted[key] == sold[key]
    # A record cannot contain its own digest; replay attaches that audit field.
    for immediate, replayed in zip(sold["trades"], restarted["trades"], strict=True):
        assert len(replayed["record_sha256"]) == 64
        assert {key: value for key, value in replayed.items() if key != "record_sha256"} == {
            key: value for key, value in immediate.items() if key != "record_sha256"}
    assert service.journal.path.read_bytes() == stable
    assert restarted["action"] == "no_order"


@pytest.mark.parametrize("change,blocker", [
    ("no_risks", "SCENARIO_HOLDING_RISK_MISSING:CORE_VALUE:300364"),
    ("no_attributes", "SCENARIO_SECURITY_RISK_MISSING:300364:cyclical"),
    ("not_liquid", "hotspot:liquidity_unknown_or_restricted"),
    ("limit", "hotspot:price_limit_execution_risk"),
    ("missing_assumption", "ASSUMPTION_MISSING:gap_stress_cny"),
])
def test_web_choices_keep_unknowns_and_engine_vetoes(projected_account, tmp_path, change, blocker):
    choices = scenario_choices()
    assumptions = {**ASSUMPTIONS, "lot_size": "1"}
    if change == "no_risks":
        choices["holding_risks"] = []
    elif change == "no_attributes":
        choices["security_risks"] = []
    elif change == "not_liquid":
        choices["execution"]["liquid"] = False
    elif change == "limit":
        choices["execution"]["limit_up"] = True
    else:
        del assumptions["gap_stress_cny"]
    before = projected_account.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(projected_account.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": assumptions, "scenario": choices})
    assert result["scenario_preview"]["review_quantity"] is None
    assert blocker in result["scenario_preview"]["blockers"]
    assert projected_account.journal.path.read_bytes() == before


def test_web_choices_do_not_supply_missing_ips_or_reconciliation(service, tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (binding(), None))
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS, "scenario": scenario_choices()})
    assert {"SCENARIO_CONFIRMED_IPS_REQUIRED", "reconciliation", "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING"} <= set(result["scenario_preview"]["blockers"])
    assert result["scenario_preview"]["review_quantity"] is None


def test_web_choices_require_marked_holdings(projected_account, tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio import private_risk_projection as projection
    monkeypatch.setattr(projection, "_verified_prices", lambda *args: {})
    result = preview.preview_private_hotspot_risk(projected_account.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS, "scenario": scenario_choices()})
    assert "holding_market_value" in result["scenario_preview"]["blockers"]
    assert result["scenario_preview"]["review_quantity"] is None


@pytest.mark.parametrize("change", ["boolean", "cash", "reconciliation", "risk_negative", "risk_duplicate",
    "risk_extra", "risk_list", "factors", "liquid_conflict"])
def test_web_choices_reject_forged_private_inputs_and_ambiguous_choices(projected_account, tmp_path, change):
    choices = scenario_choices()
    if change == "boolean":
        choices["execution"]["liquid"] = "true"
    elif change in {"cash", "reconciliation"}:
        choices[change] = "forged"
    elif change == "risk_negative":
        choices["holding_risks"][0]["committed_risk_cny"] = "-1"
    elif change == "risk_duplicate":
        choices["holding_risks"].append(deepcopy(choices["holding_risks"][0]))
    elif change == "risk_extra":
        choices["holding_risks"][0]["symbol"] = "600519"
    elif change == "risk_list":
        choices["holding_risks"] = None
    elif change == "factors":
        choices["security_risks"][0]["common_factors"] = "none"
    else:
        choices["security_risks"][0]["liquid"] = False
    before = projected_account.journal.path.read_bytes()
    with pytest.raises(ValueError):
        preview.preview_private_hotspot_risk(projected_account.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS, "scenario": choices})
    assert projected_account.journal.path.read_bytes() == before


def test_web_choices_keep_actual_budget_breach(projected_account, tmp_path, monkeypatch):
    from test_private_ips_policy import quotes
    quotes(monkeypatch, price="30")
    result = preview.preview_private_hotspot_risk(projected_account.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS, "scenario": scenario_choices()})
    assert result["scenario_preview"]["review_quantity"] is None
    assert "CORE_VALUE:budget_exceeded" in result["scenario_preview"]["blockers"]


def test_web_choices_require_current_plan_even_with_complete_account(projected_account, tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (None, "CURRENT_PLAN_STALE_OR_INVALIDATED"))
    result = preview.preview_private_hotspot_risk(projected_account.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS, "scenario": scenario_choices()})
    assert "CURRENT_PLAN_STALE_OR_INVALIDATED" in result["scenario_preview"]["blockers"]
    assert result["scenario_preview"]["review_quantity"] is None


def test_scenario_choices_http_contract_auth_validation_and_no_journal_writes(projected_account, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW

    monkeypatch.setattr(private_routes, "datetime", FixedDatetime)
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: projected_account.journal.path)
    app = FastAPI()
    secret = "TEST_ONLY-scenario-http-" + "s" * 40
    private_routes.register_private_routes(app, tmp_path,
        sessions=LocalOperatorSession(bootstrap_secret=secret), port=8791)
    route = "/api/v1/private/portfolio/risk-preview"
    body = {"symbol": "300364", "assumptions": {**ASSUMPTIONS, "lot_size": "1"},
        "scenario": scenario_choices()}
    before = projected_account.journal.path.read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000)) as client:
        client.headers["origin"] = "http://127.0.0.1:8791"
        assert client.post(route, json=body).status_code == 401
        token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
        client.headers["x-local-session"] = token
        response = client.post(route, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        scenario = result["scenario_preview"]
        assert scenario["review_quantity"] > 0
        assert scenario["status"] == "QUANTITY_REVIEW_ONLY"
        assert scenario["namespace"] == scenario["engine"]["namespace"] == "SIMULATED"
        assert scenario["scope"] == "HYPOTHETICAL_CONFIRMED_ACCOUNT_PROJECTION"
        assert scenario["formal_review_quantity"] is None
        assert scenario["formal_eligibility"] is scenario["trade_eligible"] is False
        assert scenario["required_holding_risks"] == scenario["security_risk_gaps"] == []
        assert result["sizing_preview"]["review_quantity"] is None
        assert "CANDIDATE_LIQUIDITY_UNKNOWN" in result["sizing_preview"]["blockers"]
        for field, value in (("holding_risks", [{"sleeve": [], "symbol": "300364", "committed_risk_cny": "1"}]),
                ("cash_cny", "1000000")):
            malformed = deepcopy(body)
            malformed["scenario"][field] = value
            rejected = client.post(route, json=malformed)
            assert rejected.status_code == 422, rejected.text
            assert rejected.json()["status"] == "VALIDATION_FAILED"
    assert projected_account.journal.path.read_bytes() == before
