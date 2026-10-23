"""Execution experiments never turn retrospective observations into admission."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import os

import pytest

from value_investment_agent.domain.hotspot.current_price import aggregate_sessions
from value_investment_agent.domain.hotspot.price_action_plan import RULE_VERSION
from value_investment_agent.domain.hotspot.strategy_execution_replay import replay_strategy_execution
from value_investment_agent.domain.hotspot.quantitative_validation import simulate_fold
from value_investment_agent.application.hotspot.strategy_execution_replay import (
    build_strategy_execution_replay, fingerprint,
)


def fixture():
    rows = []
    for day in (8, 9, 12, 13, 14, 15, 16, 19, 20, 21):
        for hour in ("10:30:00", "11:30:00", "14:00:00", "15:00:00"):
            rows.append(dict(time=f"2026-10-{day:02d} {hour}", open="10", high="10.1",
                low="9.8", close="10", volume="100", amount="1000000"))
    rows[5].update(close="10.4", high="10.5", volume="150")
    rows[6].update(open="10.2", close="9.5", low="9.4", high="10.6")
    rows[7].update(open="9.5", close="9.5", low="9.4")
    rows[8].update(open="9.0", close="9.5", low="8.9")
    bars = dict(daily=aggregate_sessions(rows), **{"60m": rows})
    spec = dict(schema_version="hotspot-event-replay-spec-v1", action="no_order",
        rule_version=RULE_VERSION, primary_period="60m", forward_sessions=5,
        start_date="2026-10-08", development_end="2026-10-15",
        validation_start="2026-10-16", end_date="2026-10-21")
    costs = dict(commission_rate="0.0003", minimum_commission_cny="5",
        sell_tax_rate="0.0005", transfer_fee_rate="0.00001", slippage_bps="10",
        effective_start="2026-01-01T00:00:00+08:00", effective_end="2026-12-31T23:59:59+08:00")
    states = {r["time"]: dict(available_at=r["time"][:10] + "T09:00:00+08:00",
        suspended=False, limit_down="5", limit_up="15") for r in rows}
    return dict(symbol="600519", bars_by_period=bars, spec=spec, costs=costs,
                stock_states=states)


def test_actual_rule_generates_intents_next_open_then_t1_retry_and_gap_exit():
    args = fixture()
    result = replay_strategy_execution(**args)
    fold = result["folds"][0]
    assert fold["signal_event_count"] == 1
    assert fold["trade_count"] == 1
    assert fold["rejection_counts"] == {"T_PLUS_ONE": 1}
    assert fold["fills"][0]["price"] == "10.22"
    assert fold["fills"][1]["price"] == "8.99"
    assert Decimal(fold["total_fees_cny"]) > 10
    assert Decimal(fold["net_return"]) < 0
    assert Decimal(fold["maximum_drawdown"]) > 0
    for intention in fold["generated_intentions"]:
        assert datetime.fromisoformat(intention["actual_execution_at"]) > datetime.fromisoformat(intention["decision_at"])
    protocol = dict(initial_cash_cny="100000", costs=args["costs"])
    raw = simulate_fold(protocol, fold["simulator_inputs"], dict(id="development",
        test_start="2026-10-08T09:30:00+08:00", test_end="2026-10-15T15:00:00+08:00"))
    assert raw["ending_equity_cny"] == fold["ending_equity_cny"]
    assert result["formal_eligibility"] is result["strict_oos_admitted"] is False


@pytest.mark.parametrize("change,reason", [
    ("suspended", "SUSPENDED"), ("limit", "PRICE_LIMIT"),
    ("gap_up", "ORDER_LIMIT"), ("gap_down", "GAP_BELOW_ENTRY_INVALIDATION"),
    ("liquidity", "LIQUIDITY"), ("slip", "SLIPPAGE_OUTSIDE_OBSERVED_BAR"),
])
def test_constraints_are_explicit_rejections(change, reason):
    args = fixture()
    row = args["bars_by_period"]["60m"][6]
    state = args["stock_states"][row["time"]]
    if change == "suspended":
        state["suspended"] = True
    elif change == "limit":
        state["limit_up"] = "10.2"
        row.update(high="10.2", close="10.2")
    elif change == "gap_up":
        row.update(open="10.6", high="10.8")
    elif change == "gap_down":
        row.update(open="9.5")
    elif change == "liquidity":
        row["amount"] = "1"
    else:
        row.update(open="10.2", high="10.2")
    result = replay_strategy_execution(**args)
    assert result["folds"][0]["rejection_counts"][reason] >= 1
    assert result["folds"][0]["trade_count"] == 0


def test_missing_state_fails_closed_and_scenario_is_labelled():
    args = fixture()
    args.pop("stock_states")
    strict = replay_strategy_execution(**args)
    assert strict["trade_count"] == 0
    assert strict["folds"][0]["rejection_counts"]["MISSING_DATED_STOCK_STATUS"] > 0
    scenario = replay_strategy_execution(**args, mode="ASSUMED_REGULAR_TRADING")
    assert scenario["mode"] == "ASSUMED_REGULAR_TRADING"
    assert all(r["state_assumed"] for f in scenario["folds"] for r in f["execution_observations"])
    assert scenario["strategy_validation"] == "NOT_PROVEN"


def test_future_tail_cannot_change_earlier_intents_or_fills():
    args = fixture()
    earlier = replay_strategy_execution(**args)["folds"][0]
    for row in args["bars_by_period"]["60m"][20:]:
        row.update(open="11", close="11", high="11.1", low="10.9", volume="900")
    later = replay_strategy_execution(**args)["folds"][0]
    cutoff = "2026-10-13T15:00:00+08:00"
    assert [f for f in earlier["fills"] if f["time"] <= cutoff] == [f for f in later["fills"] if f["time"] <= cutoff]
    assert [o for o in earlier["generated_intentions"] if o["decision_at"] <= cutoff] == [o for o in later["generated_intentions"] if o["decision_at"] <= cutoff]


def test_partition_end_does_not_force_liquidation_and_censors_final_signal():
    args = fixture()
    rows = args["bars_by_period"]["60m"]
    rows[5].update(close="10", high="10.1", volume="100")
    rows[-1].update(close="10.5", high="10.6", volume="200")
    result = replay_strategy_execution(**args)
    assert result["right_censored_intentions"] == 1
    assert result["folds"][1]["pending_intention"]["side"] == "BUY"
    assert result["trade_count"] == 0


@pytest.mark.parametrize("change", ["late_status", "duplicate", "incomplete", "bad_cost", "wrong_rule", "bad_quantity", "unsupported_board", "scaled_slip"])
def test_invalid_evidence_and_parameters_rejected(change):
    args = fixture()
    if change == "late_status":
        args["stock_states"][args["bars_by_period"]["60m"][6]["time"]]["available_at"] = "2026-10-23T00:00:00+08:00"
    elif change == "duplicate":
        args["bars_by_period"]["60m"].insert(1, deepcopy(args["bars_by_period"]["60m"][0]))
    elif change == "incomplete":
        args["bars_by_period"]["60m"].pop(6)
    elif change == "bad_cost":
        args["costs"]["commission_rate"] = "NaN"
    elif change == "wrong_rule":
        args["spec"]["rule_version"] = "tuned"
    elif change == "bad_quantity":
        args["quantity"] = 1
    elif change == "unsupported_board":
        args["symbol"] = "688001"
    else:
        args["costs"]["slippage_bps"] = "9999"
        args["cost_multiplier"] = "2"
    with pytest.raises(ValueError):
        replay_strategy_execution(**args)


@pytest.mark.skipif(not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Explicit read-only real source root required")
def test_real_retained_strategy_execution_replays_without_admission():
    report = build_strategy_execution_replay(root=Path(os.environ["HOTSPOT_RETAINED_ROOT"]),
        now=datetime(2026, 10, 23, 12, tzinfo=timezone.utc))
    assert report["summary"]["signal_event_count"] == 161
    assert report["summary"]["mature_signal_observation_count"] == 150
    assert report["summary"]["right_censored_signal_observations"] == 11
    assert report["summary"]["strict_closed_trade_count"] == 0
    assert report["summary"]["assumed_state_closed_trade_count"] > 0
    for row in report["results"]:
        for scenario in row["scenarios"]:
            for fold in scenario["folds"]:
                assert Decimal(fold["same_fills_gross_return"]) >= Decimal(fold["net_return"])
                for fill in fold["fills"]:
                    assert sum(map(Decimal, fill["fee_components"].values())) == Decimal(fill["fees_cny"])
                    assert fill["hypothetical_execution_at"] < fill["execution_bar_close_label"]
                if fold["same_fills_gross_equity_curve"]:
                    gross = Decimal(fold["same_fills_gross_equity_curve"][-1]["equity_cny"])
                    assert gross / Decimal(report["parameters"]["initial_cash_cny"]) - 1 == Decimal(fold["same_fills_gross_return"])
    assert report["costs"]["known_at"].startswith("2026-10-23")
    assert report["strict_oos_admitted"] is report["strict_pit_admitted"] is False
    content = dict(report)
    digest = content.pop("content_sha256")
    assert fingerprint(content) == digest
    # No writable runtime, mutable pointer or trading permission is created.
    assert report["action"] == "no_order"
    for binding in report["source_bindings"]:
        from hashlib import sha256
        assert sha256((Path(os.environ["HOTSPOT_RETAINED_ROOT"]) / binding["path"]).read_bytes()).hexdigest() == binding["sha256"]


@pytest.mark.skipif(not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Explicit read-only real source root required")
def test_real_manifest_tampering_is_rejected_before_simulation():
    root = Path(os.environ["HOTSPOT_RETAINED_ROOT"])
    import json
    binding = json.loads((root / "config/hotspot-replay-review-v1.json").read_text())["retained_manifest_binding"]
    with pytest.raises(ValueError, match="hash mismatch"):
        build_strategy_execution_replay(root=root, manifest_binding={**binding, "sha256": "0" * 64},
            now=datetime(2026, 10, 23, 12, tzinfo=timezone.utc))
