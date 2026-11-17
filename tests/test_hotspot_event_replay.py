"""Synthetic chronology tests; these fixtures are not market-performance evidence."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.domain.hotspot.current_price import CURRENT_BLOCKERS, SESSION_TIMES, aggregate_sessions, current_signal
from value_investment_agent.domain.hotspot.event_replay import replay_v1
from value_investment_agent.domain.hotspot.price_action_plan import RULE_VERSION, calculate_price_levels
from value_investment_agent.domain.hotspot.shadow_observation import make_shadow_baseline, compare_archived_baseline
from value_investment_agent.application.hotspot import event_replay as application
from value_investment_agent.quote_sessions import CHINA
from value_investment_agent.virtual_account import VirtualAccount, replay as execution_replay, fee


def bars():
    result = {"60m": [], "15m": []}
    day = date(2026, 6, 22)
    while day <= date(2026, 7, 10):
        if day.weekday() < 5:
            for period in result:
                for clock in SESSION_TIMES[period]:
                    result[period].append(dict(time=f"{day} {clock}", open="10", high="11", low="9",
                                               close="10", volume="100", amount="1000"))
        day += timedelta(days=1)
    result["daily"] = aggregate_sessions(result["60m"])
    return result


def spec():
    return dict(schema_version="hotspot-event-replay-spec-v1", action="no_order", rule_version=RULE_VERSION,
                primary_period="60m", forward_sessions=5, start_date="2026-06-24",
                development_end="2026-06-30", validation_start="2026-07-01", end_date="2026-07-10")


def trigger(value, stamp):
    row = next(row for row in value["60m"] if row["time"] == stamp)
    row.update(close="12", high="13", volume="150")
    value["daily"] = aggregate_sessions(value["60m"])


def test_development_outcomes_never_cross_validation_and_censor_is_not_failure():
    value = bars()
    trigger(value, "2026-06-26 15:00:00")
    result = replay_v1(value, spec())
    event = result["events"]["development"][0]
    assert event["outcome"]["right_censored"] is True
    assert event["outcome"]["failed_within_five_sessions"] is None
    assert event["outcome"]["fifth_session_close_change_pct"] is None
    assert event["outcome"]["last_observed_bar"] == "2026-06-30 15:00:00"
    assert result["segments"]["development"]["failure_proxy_denominator"] == 0


def test_future_bars_cannot_change_frozen_signal_or_completed_context():
    value = bars()
    stamp = "2026-07-01 10:30:00"
    trigger(value, stamp)
    initial = replay_v1(value, spec())["events"]["validation"][0]
    changed = deepcopy(value)
    for period in changed:
        for row in changed[period]:
            close_at = row["time"] + " 15:00:00" if period == "daily" else row["time"]
            if close_at > stamp:
                row.update(open="100", high="110", low="90", close="100", volume="10000")
    after = replay_v1(changed, spec())["events"]["validation"][0]
    assert after["levels"] == initial["levels"]
    assert after["completed_context"] == initial["completed_context"]
    assert initial["completed_context"]["daily"]["last_bar"] == "2026-06-30"
    assert initial["completed_context"]["15m"]["last_bar"] <= stamp
    assert after["outcome"] != initial["outcome"]


def test_full_horizon_reports_price_proxies_and_keeps_execution_unknown():
    value = bars()
    trigger(value, "2026-07-01 15:00:00")
    breach = next(row for row in value["60m"] if row["time"] == "2026-07-02 10:30:00")
    breach.update(low="7", close="8")
    value["daily"] = aggregate_sessions(value["60m"])
    result = replay_v1(value, spec())
    outcome = result["events"]["validation"][0]["outcome"]
    assert outcome["horizon_complete"] is True
    assert outcome["observed_followup_sessions"] == 5
    assert outcome["last_observed_bar"] == "2026-07-08 15:00:00"
    assert outcome["failed_within_five_sessions"] is True
    assert outcome["false_breakout_next_session_proxy"] is True
    assert Decimal(outcome["adverse_excursion_from_signal_close_pct"]) == (Decimal(7) / 12 - 1) * 100
    assert outcome["execution"]["unfilled"] is None
    assert outcome["execution"]["cost_cny"] is None
    assert outcome["execution"]["net_trade_return_pct"] is None
    assert result["segments"]["validation"]["net_return_distribution"] is None
    assert result["strict_oos_admitted"] is False
    assert result["historical_classification_used"] is False


def test_end_of_data_signal_is_censored_not_zero_return():
    value = bars()
    trigger(value, "2026-07-10 15:00:00")
    result = replay_v1(value, spec())
    event = result["events"]["validation"][0]
    assert event["outcome"]["next_session_close_change_pct"] is None
    assert event["outcome"]["false_breakout_next_session_proxy"] is None
    assert result["segments"]["validation"]["false_breakout_proxy_denominator"] == 0


@pytest.mark.parametrize("field,value", [("rule_version", "new-rule"), ("forward_sessions", 4),
                                         ("forward_sessions", True), ("action", "order"),
                                         ("validation_start", "2026-06-29")])
def test_protocol_changes_are_rejected(field, value):
    changed = spec()
    changed[field] = value
    with pytest.raises(ValueError):
        replay_v1(bars(), changed)


def test_bad_or_duplicate_bars_are_rejected():
    value = bars()
    value["60m"][0]["volume"] = "0"
    with pytest.raises(ValueError, match="volume"):
        replay_v1(value, spec())
    value = bars()
    value["15m"][1]["time"] = value["15m"][0]["time"]
    with pytest.raises(ValueError, match="ordered"):
        replay_v1(value, spec())


def make_case(symbol="300364"):
    value = bars()
    levels = {period: calculate_price_levels(rows, period=period) for period, rows in value.items()}
    state, explanation = current_signal(levels)
    return dict(schema_version="hotspot-current-price-case-v1", action="no_order", action_eligibility=False,
                symbol=symbol, market_trade_date="2026-07-10", case_sha256="synthetic-case-hash",
                current_reference_price="10", levels=levels, bars=value, signal_state=state, explanation=explanation,
                blockers=list(CURRENT_BLOCKERS), data_available_at="2026-07-10T16:10:00+08:00",
                source_bindings={period: dict(fetched_at="2026-07-10T16:00:00+08:00", sha256="synthetic-source-hash")
                                 for period in value},
                current_reference_close=dict(status="VERIFIED_DUAL_SOURCE_CLOSE", next_session="2026-07-13",
                                             bundle_sha256="synthetic-bundle-hash", evidence_refs=[]))


def test_shadow_baseline_is_actual_and_has_no_future_session_or_prior_judgment():
    case = make_case()
    baseline = make_shadow_baseline(case, application._v1_shadow_plan(case),
                                    observed_at=datetime(2026, 7, 10, 17, tzinfo=CHINA))
    assert baseline["market_trade_date"] == "2026-07-10"
    assert baseline["previous_judgment"] is None
    assert baseline["elapsed_real_shadow_sessions"] == 0
    assert "next_session" not in baseline
    assert baseline["potential_cost"] is None
    assert baseline["formal_eligibility"] is False


def test_shadow_rejects_future_source_or_bar_and_same_day_comparison():
    case = make_case()
    plan = application._v1_shadow_plan(case)
    with pytest.raises(ValueError, match="Future"):
        make_shadow_baseline(case, plan, observed_at=datetime(2026, 7, 10, 14, tzinfo=CHINA))
    with pytest.raises(ValueError, match="not yet available"):
        make_shadow_baseline(case, plan, observed_at=datetime(2026, 7, 10, 16, 5, tzinfo=CHINA))
    baseline = make_shadow_baseline(case, plan, observed_at=datetime(2026, 7, 10, 17, tzinfo=CHINA))
    with pytest.raises(ValueError, match="archived"):
        compare_archived_baseline(baseline, baseline)


def test_previous_baseline_compares_only_actual_later_close_not_execution():
    case = make_case()
    prior = make_shadow_baseline(case, application._v1_shadow_plan(case),
                                observed_at=datetime(2026, 7, 10, 17, tzinfo=CHINA))
    current = {**prior, "market_trade_date": "2026-07-13", "observed_at": "2026-07-13T17:00:00+08:00",
               "current_reference_price": "8", "case_sha256": "synthetic-new-case"}
    comparison = compare_archived_baseline(prior, current)
    assert comparison["close_below_prior_invalidation"] is True
    assert comparison["profit"] is None and comparison["real_trade"] is False


def test_dependency_availability_is_maximum_not_earliest_fetch():
    case = make_case()
    case["source_bindings"]["15m"]["fetched_at"] = "2026-07-10T16:25:00+08:00"
    bundle = {"finished_at": "2026-07-10T16:20:00+08:00",
              "references": {case["symbol"]: {"document_refs": {"tencent": "t", "sina": "s", "calendar_documents": ["c"]}}},
              "documents": {key: {"fetched_at": "2026-07-10T16:15:00+08:00"} for key in ("t", "s", "c")}}
    assert application._availability(case, bundle) == "2026-07-10T16:25:00+08:00"


def test_hash_and_path_escape_fail_closed(tmp_path):
    path = tmp_path / "bound.json"
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="hash"):
        application._bound_bytes(tmp_path, {"path": "bound.json", "sha256": "wrong"})
    with pytest.raises(ValueError, match="escapes"):
        application._bound_bytes(tmp_path, {"path": "../outside.json", "sha256": "wrong"})


def test_output_evidence_cannot_be_overwritten(tmp_path):
    report = dict(computed_at="2026-07-10T17:00:00+08:00", data_available_at="2026-07-10T16:00:00+08:00",
                  spec_binding={}, rule_bindings=[], implementation_bindings=[], results=[], shadow_baselines=[], action="no_order")
    directory = Path("artifacts/current/tl11-p5-20261014")
    manifest = application.write_replay(root=tmp_path, report=report, directory=directory)
    for binding in manifest["outputs"]:
        assert hashlib.sha256((tmp_path / binding["path"]).read_bytes()).hexdigest() == binding["sha256"]
    with pytest.raises(FileExistsError):
        application.write_replay(root=tmp_path, report=report, directory=directory)
    with pytest.raises(ValueError, match="outside"):
        application.write_replay(root=tmp_path, report=report, directory=Path(".tmp/not-authorized"))


def execution_terms():
    return dict(version="next-session-bounded-order-v1", valid_session="2026-07-02",
                liquidity_as_of="2026-07-01", basis_id="synthetic-frozen-basis", limit_price="20",
                cash_budget_cny="10000", liquidity_budget_cny="10000", slippage_bps="10")


@pytest.mark.parametrize("ready,opening,reason", [(None, "10", "execution_state_unknown"),
                                                  (False, "10", "session_not_executable"),
                                                  (True, "11", "opening_at_or_outside_price_limit")])
def test_existing_execution_engine_unknown_halted_and_limit_unfilled_controls(ready, opening, reason):
    sessions = [dict(date="2026-07-01", open="10", close="10", execution_ready=False),
                dict(date="2026-07-02", open=opening, close="10", execution_ready=ready,
                     price_limit_down="9", price_limit_up="11")]
    decisions = {"2026-07-01": dict(state="proposed_entry", decision_id="synthetic-1", quantity=100,
                                    execution_terms=execution_terms(), action="no_order")}
    account, journal = execution_replay(sessions, decisions, account=VirtualAccount(cash=Decimal("10000")))
    assert account.shares == 0
    assert journal[-1]["fill"] is None
    assert journal[-1]["rejected_order_reason"] == reason


def test_existing_execution_engine_explicit_synthetic_cost_slippage_and_t1():
    sessions = [dict(date="2026-07-01", open="10", close="10", execution_ready=False),
                dict(date="2026-07-02", open="10", close="10", execution_ready=True,
                     price_limit_down="9", price_limit_up="11")]
    decisions = {"2026-07-01": dict(state="proposed_entry", decision_id="synthetic-1", quantity=100,
                                    execution_terms=execution_terms(), action="no_order")}
    account, journal = execution_replay(sessions, decisions, account=VirtualAccount(cash=Decimal("10000")),
        fee_calculator=lambda side, quantity, price, day: fee(side, quantity, price,
            commission_rate=Decimal("0.0003"), minimum_commission=Decimal("5"), stamp_duty_rate=Decimal("0.0005")))
    assert account.cash == Decimal("8994.00")
    assert journal[-1]["fill"] is not None
    assert account.sellable_shares(date(2026, 7, 2)) == 0
    assert account.sellable_shares(date(2026, 7, 3)) == 100
