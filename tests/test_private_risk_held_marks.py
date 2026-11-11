"""Real verifier over TEST_ONLY source/ledger fixtures; no public membership."""
from datetime import date
from types import SimpleNamespace
from copy import deepcopy

import pytest

from test_hotspot_current_price_case import display_capture, NOW
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService


def setup_case(tmp_path, monkeypatch, *, second=False):
    from value_investment_agent.application.product import quote_bridge
    from value_investment_agent.application.hotspot import current_registry
    case = display_capture(tmp_path)
    monkeypatch.setattr(quote_bridge, "execute_quote_bridge_for_symbol", lambda *a, **k: {})
    monkeypatch.setattr(current_registry, "load_price_conditions", lambda *a, **k: {"items": []})
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-journal.jsonl"))
    holdings = [{"symbol": "600519", "exchange": "SSE", "quantity": "100", "cost_basis_cny": "1000"}]
    if second:
        holdings.append({"symbol": "000333", "exchange": "SZSE", "quantity": "100", "cost_basis_cny": "2000"})
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY", "as_of": "2026-09-24", "cash_cny": "8000",
        "holdings": holdings, "sleeve_allocations": {row["symbol"]: {"CORE_VALUE": "100"} for row in holdings},
        "policy": {}, "confirmed_at": "2026-09-24T16:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    return service, case


def test_held_outside_registry_mark_flows_into_portfolio_and_risk_facts_only(tmp_path, monkeypatch):
    service, case = setup_case(tmp_path, monkeypatch)
    before = service.journal.path.read_bytes()
    risk = projection.review_private_risk_rehearsal(service.journal, repository_root=tmp_path,
        generated_at=NOW, today=NOW.date())
    portfolio = service.portfolio_view(repository_root=tmp_path, generated_at=NOW)
    facts = risk["facts"]
    assert facts["positions"][0]["market_value_cny"] == portfolio["positions"][0]["market_value_cny"] == "1234.00"
    assert facts["positions"][0]["unrealized_pnl_cny"] == portfolio["positions"][0]["floating_pnl_cny"] == "234.00"
    binding = facts["positions"][0]["quote_binding"]
    assert binding["case_sha256"] == case["case_sha256"]
    assert binding["current_pit"] is binding["price_admitted"] is binding["formal_eligibility"] is False
    assert "DISPLAY_ONLY_HELD_MARK_NOT_FORMAL_PRICE_INPUT" in risk["blockers"]
    assert risk["engine"]["trade_eligible"] is False
    assert risk["engine"]["position_guidance"] is None
    replayed = service._replay(service.records())
    payload = projection.build_risk_input(replayed, repository_root=tmp_path, generated_at=NOW,
        sellable_as_of=NOW.date())
    assert payload["portfolio"]["snapshot"]["holdings"][0]["market_value_cny"] is None
    assert service.journal.path.read_bytes() == before
    assert not (tmp_path / "config/current-price-conditions.json").exists()


@pytest.mark.parametrize("failure", ["stale", "tampered", "future"])
def test_history_reverification_never_refreshes_invalid_mark(tmp_path, monkeypatch, failure):
    service, case = setup_case(tmp_path, monkeypatch)
    clock = NOW
    if failure == "stale":
        clock = NOW.replace(day=28)
    elif failure == "future":
        clock = NOW.replace(hour=8)
    else:
        source = tmp_path / case["source_bindings"]["60m"]["path"]
        source.write_bytes(source.read_bytes() + b" ")
    view = service.portfolio_view(repository_root=tmp_path, generated_at=clock)
    assert view["positions"][0]["quantity"] == "100"
    assert view["positions"][0]["market_value_cny"] is None


def test_one_missing_case_preserves_other_marks_and_unknown_account_total(tmp_path, monkeypatch):
    service, _ = setup_case(tmp_path, monkeypatch, second=True)
    risk = projection.review_private_risk_rehearsal(service.journal, repository_root=tmp_path,
        generated_at=NOW, today=NOW.date())
    positions = {row["symbol"]: row for row in risk["facts"]["positions"]}
    assert positions["600519"]["market_value_cny"] == "1234.00"
    assert positions["000333"]["market_value_cny"] is None
    assert risk["facts"]["total_equity_cny"] is None


def test_verified_history_close_predating_confirmed_trade_cannot_mark_position(tmp_path, monkeypatch):
    service, _ = setup_case(tmp_path, monkeypatch)
    replayed = service._replay(service.records())
    later_trade_state = SimpleNamespace(state=SimpleNamespace(
        lots=replayed.state.lots, last_trade_date=date(2026, 9, 28)))
    assert projection._verified_prices(tmp_path, later_trade_state, NOW) == {}


@pytest.mark.parametrize("route", ["quote_bridge", "registry", "case_history"])
def test_same_verified_display_case_keeps_facts_but_never_formal_price_on_any_route(tmp_path, monkeypatch, route):
    from value_investment_agent.application.product import quote_bridge
    from value_investment_agent.application.hotspot import current_registry
    from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
    service, case = setup_case(tmp_path, monkeypatch)
    plan = {**project_current_price_action_plan(case), "case_sha256": case["case_sha256"]}
    if route == "quote_bridge":
        monkeypatch.setattr(quote_bridge, "execute_quote_bridge_for_symbol", lambda *a, **k: {
            "price_admitted": False, "current_pit": False,
            "compatibility": {"verified_quote": {"eligible": True}},
            "quote": {"quote_date": case["market_trade_date"], "latest_completed_session": case["market_trade_date"],
                "display_price": case["current_reference_price"], "bundle_sha256": "a" * 64,
                "display_scope": "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"}})
    elif route == "registry":
        monkeypatch.setattr(current_registry, "load_price_conditions", lambda *a, **k:
            {"items": [{"symbol": "600519", "price_action_plan": plan}]})
    replayed = service._replay(service.records())
    prices = projection._verified_prices(tmp_path, replayed, NOW)
    mark = prices["600519"]
    assert mark["price_admitted"] is mark["current_pit"] is mark["formal_eligibility"] is False
    assert "DISPLAY_ONLY" in mark["scope"]
    result = projection.review_private_risk_rehearsal(service.journal, repository_root=tmp_path,
        generated_at=NOW, today=NOW.date())
    assert result["facts"]["positions"][0]["market_value_cny"] == "1234.00"
    assert result["facts"]["positions"][0]["unrealized_pnl_cny"] == "234.00"
    payload = projection.build_risk_input(replayed, repository_root=tmp_path, generated_at=NOW,
        sellable_as_of=NOW.date())
    assert payload["portfolio"]["snapshot"]["holdings"][0]["market_value_cny"] is None
    assert result["engine"]["trade_eligible"] is False
    assert result["engine"]["position_guidance"] is None


@pytest.mark.parametrize("route", ["quote_bridge", "registry"])
@pytest.mark.parametrize("mode", ["unknown", "known_eligible", "contradictory_display", "explicit_false", "pit_false"])
def test_explicit_admission_required_and_strict_known_eligible_compatible(tmp_path, monkeypatch, route, mode):
    from value_investment_agent.application.product import quote_bridge
    from value_investment_agent.application.hotspot import current_registry
    service, case = setup_case(tmp_path, monkeypatch)
    flags = {} if mode == "unknown" else {"price_admitted": mode != "explicit_false"}
    if mode == "pit_false":
        flags["current_pit"] = False
    scope = "LAST_COMPLETED_CLOSE_DISPLAY_ONLY" if mode == "contradictory_display" else "SAME_SESSION_B1"
    if route == "quote_bridge":
        monkeypatch.setattr(quote_bridge, "execute_quote_bridge_for_symbol", lambda *a, **k: {
            **flags, "compatibility": {"verified_quote": {"eligible": True}},
            "quote": {"quote_date": case["market_trade_date"], "latest_completed_session": case["market_trade_date"],
                "display_price": case["current_reference_price"], "bundle_sha256": "a" * 64,
                "display_scope": scope}})
    else:
        monkeypatch.setattr(current_registry, "load_price_conditions", lambda *a, **k:
            {"items": [{"symbol": "600519", "price_action_plan": {**flags,
                "current_reference_price": case["current_reference_price"], "market_trade_date": case["market_trade_date"],
                "case_sha256": case["case_sha256"], "reference_price_scope": scope}}]})
    replayed = service._replay(service.records())
    prices = projection._verified_prices(tmp_path, replayed, NOW)
    assert projection._facts(replayed, prices, generated_at=NOW)["positions"][0]["market_value_cny"] == "1234.00"
    payload = projection.build_risk_input(replayed, repository_root=tmp_path, generated_at=NOW,
        sellable_as_of=NOW.date())
    assert payload["portfolio"]["snapshot"]["holdings"][0]["market_value_cny"] == (
        "1234.00" if mode == "known_eligible" else None)


@pytest.mark.parametrize("namespace", ["ACTUAL", "SIMULATED"])
@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("admission", [None, False])
def test_only_explicit_simulated_assumptions_bypass_formal_price_filter(tmp_path, monkeypatch,
        namespace, explicit, admission):
    from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
    service, _ = setup_case(tmp_path, monkeypatch)
    replayed = service._replay(service.records())
    prices = {"600519": {"price_cny": "12.34", "trade_date": "2026-09-24"}}
    if admission is not None:
        prices["600519"]["price_admitted"] = admission
    original = deepcopy(prices)
    monkeypatch.setattr(projection, "_verified_prices", lambda *a, **k: prices)
    kwargs = {"_prices": prices} if explicit else {}
    payload = projection.build_risk_input(replayed, namespace=namespace,
        generated_at=NOW, sellable_as_of=NOW.date(), **kwargs)
    permitted = namespace == "SIMULATED" and explicit
    assert payload["portfolio"]["snapshot"]["holdings"][0]["market_value_cny"] == (
        "1234.00" if permitted else None)
    assert prices == original
    if namespace == "SIMULATED":
        payload["portfolio"]["snapshot"]["namespace"] = "SIMULATED"
        with pytest.raises(ValueError):
            review_dual_sleeve_risk(payload, generated_at=NOW)
