"""Quantitative mechanics use explicitly isolated synthetic evidence."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from copy import deepcopy
from decimal import Decimal

import pytest

from value_investment_agent.application.hotspot import validation_evidence
from value_investment_agent.application.hotspot.quantitative_validation import ProtocolBinding


def execution_fixture(root, namespace="TEST_ONLY"):
    def time(day, hour="10:00:00"):
        return f"2026-10-{day:02d}T{hour}+08:00"

    bars, orders = [], []
    for day, hour, price in [(19, "10:00:00", "10"), (19, "11:00:00", "10"),
                             (20, "10:00:00", "12"), (20, "11:00:00", "10"),
                             (21, "10:00:00", "9"), (22, "10:00:00", "10"),
                             (23, "10:00:00", "11")]:
        bars.append(dict(symbol="000001", time=time(day, hour), open=price, close=price,
                         limit_down="5", limit_up="15", suspended=False, liquidity_cny="100000"))
    for identity, side, day, hour, fold in [
        ("buy", "BUY", 19, "10:00:00", "a"),
        ("t1", "SELL", 19, "11:00:00", "a"),
        ("win", "SELL", 20, "10:00:00", "a"),
        ("rebuy", "BUY", 20, "11:00:00", "a"),
        ("loss", "SELL", 21, "10:00:00", "a"),
        ("b-buy", "BUY", 22, "10:00:00", "b"),
        ("b-exit", "SELL", 23, "10:00:00", "b")]:
        orders.append(dict(id=identity, side=side, symbol="000001", quantity=100,
            fold=fold, decision_at=time(day, "09:30:00"), available_at=time(day, "09:00:00"),
            execute_at=time(day, hour), liquidity_budget_cny="100000",
            limit_price="14" if side == "BUY" else "6"))
    inputs = dict(namespace=namespace, orders=orders, bars=bars)
    costs = dict(namespace=namespace, commission_rate="0.0003", minimum_commission_cny="5",
                 sell_tax_rate="0.0005", transfer_fee_rate="0", slippage_bps="10", known_at=time(17),
                 effective_start=time(1), effective_end=time(30))
    def write(name, value):
        raw = json.dumps(value, sort_keys=True).encode()
        (root / name).write_bytes(raw)
        return dict(path=name, sha256=sha256(raw).hexdigest())
    rule = write("rule.json", dict(namespace=namespace, rule="Frozen explicit test orders; no fitting"))
    protocol = dict(schema_version="hotspot-execution-protocol-v1", namespace=namespace,
        action="no_order", parameters_changed=False, registered_at=time(18), initial_cash_cny="10000",
        minimum_oos_trades=30, input_binding=write("inputs.json", inputs),
        cost_binding=write("costs.json", costs), rule_bindings=[rule], folds=[
            dict(id="a", train_start=time(1), train_end=time(16), test_start=time(19, "09:00:00"), test_end=time(21, "15:00:00")),
            dict(id="b", train_start=time(1), train_end=time(21, "15:00:00"), test_start=time(22, "09:00:00"), test_end=time(23, "15:00:00"))])
    def run():
        protocol["input_binding"] = write("inputs.json", inputs)
        protocol["cost_binding"] = write("costs.json", costs)
        binding = ProtocolBinding(**write("protocol.json", protocol))
        return validation_evidence.build_hotspot_quantitative_validation(root=root,
            protocol_binding=binding, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
    return protocol, inputs, costs, run


def test_frozen_execution_computes_fees_slippage_t1_returns_and_drawdown(tmp_path):
    _, _, _, run = execution_fixture(tmp_path)
    report = run()
    fold = report["folds"][0]
    assert fold["rejection_counts"] == {"T_PLUS_ONE": 1}
    assert fold["trade_count"] == 2
    assert fold["fills"][0]["price"] == "10.01"
    assert fold["fills"][0]["fees_cny"] == "5.00"
    assert fold["fills"][1]["price"] == "11.98"
    assert Decimal(fold["total_slippage_cny"]) == 5
    assert Decimal(fold["total_fees_cny"]) == Decimal("21.05")
    assert [Decimal(t["pnl_cny"]) for t in fold["trades"]] == [Decimal("186.40"), Decimal("-112.45")]
    assert fold["win_rate"] == "0.5"
    assert abs(Decimal(fold["payoff_ratio"]) - Decimal("186.40") / Decimal("112.45")) < Decimal("1e-24")
    assert Decimal(fold["maximum_drawdown"]) == Decimal("112.45") / Decimal("10186.40")
    assert len(fold["net_return_distribution"]) == 2
    assert Decimal(report["cost_sensitivity"][0]["folds"][0]["ending_equity_cny"]) == 10100
    assert Decimal(report["cost_sensitivity"][1]["folds"][0]["ending_equity_cny"]) < Decimal(fold["ending_equity_cny"])
    assert report["namespace"] == "TEST_ONLY"
    assert report["formal_eligibility"] is report["performance_claim_allowed"] is False


@pytest.mark.parametrize("change,reason", [("suspended", "SUSPENDED"),
    ("liquidity", "LIQUIDITY"), ("limit", "PRICE_LIMIT"), ("missing", "NO_EXECUTION_BAR")])
def test_unfillable_orders_are_counted_not_assumed_filled(tmp_path, change, reason):
    _, inputs, _, run = execution_fixture(tmp_path)
    if change == "suspended":
        inputs["bars"][0]["suspended"] = True
    elif change == "liquidity":
        inputs["bars"][0]["liquidity_cny"] = "1"
    elif change == "limit":
        inputs["bars"][0]["limit_up"] = "10"
    else:
        inputs["bars"].pop(0)
    fold = run()["folds"][0]
    assert any(o == dict(order_id="buy", reason=reason) for o in fold["rejected_orders"])
    assert not any(f["order_id"] == "buy" for f in fold["fills"])


def test_fold_future_prices_cannot_change_earlier_metrics(tmp_path):
    _, inputs, _, run = execution_fixture(tmp_path)
    before = deepcopy(run()["folds"])
    for bar in inputs["bars"]:
        if "10-22" in bar["time"] or "10-23" in bar["time"]:
            bar["open"] = bar["close"] = "14"
    after = run()
    assert after["folds"][0] == before[0]
    assert after["folds"][1] != before[1]


@pytest.mark.parametrize("fault", ["overlap", "registration", "order_crossing", "future_signal"])
def test_rejects_fold_and_signal_lookahead(tmp_path, fault):
    protocol, inputs, _, run = execution_fixture(tmp_path)
    if fault == "overlap":
        protocol["folds"][1]["test_start"] = protocol["folds"][0]["test_end"]
    elif fault == "registration":
        protocol["registered_at"] = "2026-10-20T10:00:00+08:00"
    elif fault == "order_crossing":
        inputs["orders"][0]["execute_at"] = "2026-10-22T10:00:00+08:00"
    else:
        inputs["orders"][0]["available_at"] = "2026-10-19T10:00:00+08:00"
    with pytest.raises(ValueError, match="fold|availability"):
        run()


def test_inadequate_actual_sample_rejects_admission_despite_numeric_outputs(tmp_path):
    _, _, _, run = execution_fixture(tmp_path, namespace="ACTUAL")
    report = run()
    assert report["trade_count"] == 3
    assert report["sample_status"] == "INSUFFICIENT"
    assert report["sample_admission_status"] == "REJECTED_INSUFFICIENT_SAMPLE"
    assert report["actual_sample_accepted"] is False
    assert report["strategy_validation"] == "NOT_PROVEN"


def test_tampered_frozen_inputs_are_rejected(tmp_path):
    _, _, _, run = execution_fixture(tmp_path)
    report = run()
    (tmp_path / "inputs.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
            protocol_binding=report["protocol_binding"], now=datetime(2026, 10, 24, tzinfo=timezone.utc))


def test_open_position_is_marked_and_censored_without_fabricated_trade(tmp_path):
    _, inputs, _, run = execution_fixture(tmp_path)
    inputs["orders"] = [o for o in inputs["orders"] if o["id"] != "loss"]
    fold = run()["folds"][0]
    assert fold["trade_count"] == 1
    assert fold["right_censored_positions"] == 1
    assert Decimal(fold["ending_equity_cny"]) == Decimal(fold["ending_cash_cny"]) + 900


@pytest.mark.parametrize("fault", ["future_cost", "expired_cost", "namespace", "cash", "order_limit", "prior_liquidity"])
def test_cost_and_order_constraints_are_enforced(tmp_path, fault):
    protocol, inputs, costs, run = execution_fixture(tmp_path)
    if fault == "future_cost":
        costs["known_at"] = "2026-10-19T10:00:00+08:00"
    elif fault == "expired_cost":
        costs["effective_end"] = "2026-10-20T10:00:00+08:00"
    elif fault == "namespace":
        costs["namespace"] = "ACTUAL"
    elif fault == "cash":
        protocol["initial_cash_cny"] = "100"
    elif fault == "order_limit":
        inputs["orders"][0]["limit_price"] = "10"
    else:
        inputs["orders"][0]["liquidity_budget_cny"] = "1"
    if fault in ("future_cost", "expired_cost", "namespace"):
        with pytest.raises(ValueError, match="[Cc]ost|namespace"):
            run()
    else:
        report = run()
        expected = {"cash": "CASH", "order_limit": "ORDER_LIMIT", "prior_liquidity": "LIQUIDITY"}[fault]
        assert dict(order_id="buy", reason=expected) in report["folds"][0]["rejected_orders"]


def test_percentage_commission_above_minimum_and_sell_tax_are_numeric(tmp_path):
    _, _, costs, run = execution_fixture(tmp_path)
    costs["commission_rate"] = "0.01"
    fills = run()["folds"][0]["fills"]
    assert Decimal(fills[0]["fees_cny"]) == Decimal("10.01")
    assert Decimal(fills[1]["fees_cny"]) == Decimal("12.58")


def test_transfer_fee_is_applied_to_each_side(tmp_path):
    _, _, costs, run = execution_fixture(tmp_path)
    costs["transfer_fee_rate"] = "0.0001"
    fills = run()["folds"][0]["fills"]
    assert Decimal(fills[0]["fees_cny"]) == Decimal("5.10")
    assert Decimal(fills[1]["fees_cny"]) == Decimal("5.72")


def test_domain_engine_computes_without_application_loader(tmp_path):
    from value_investment_agent.domain.hotspot.quantitative_validation import simulate_fold
    protocol, inputs, costs, _ = execution_fixture(tmp_path)
    fold = simulate_fold({**protocol, "costs": costs}, inputs, protocol["folds"][0])
    assert fold["trade_count"] == 2
    assert fold["ending_equity_cny"] == "10073.95"


def test_execution_cannot_use_out_of_session_bars(tmp_path):
    _, inputs, _, run = execution_fixture(tmp_path)
    inputs["bars"][0]["time"] = "2026-10-19T12:00:00+08:00"
    with pytest.raises(ValueError, match="exchange session"):
        run()


def test_missing_future_fold_exit_does_not_reuse_previous_fold_inventory(tmp_path):
    _, inputs, _, run = execution_fixture(tmp_path)
    inputs["orders"] = [o for o in inputs["orders"] if o["id"] != "b-buy"]
    fold = run()["folds"][1]
    assert fold["ending_cash_cny"] == "10000"
    assert fold["trade_count"] == 0
    assert fold["rejection_counts"] == {"FULL_EXIT_INVENTORY_REQUIRED": 1}


def test_actual_review_handoff_rejects_test_only_quantitative_report(monkeypatch, tmp_path):
    protocol, inputs, costs, run = execution_fixture(tmp_path)
    report = run()
    from test_hotspot_review_handoff import synthetic_validation_report
    source = tmp_path / "actual.json"
    source.write_text('{"namespace":"ACTUAL"}', encoding="utf-8")
    binding = dict(path="actual.json", sha256=sha256(source.read_bytes()).hexdigest())
    structure = synthetic_validation_report(tmp_path)
    structure["source_files"] = dict(selection_report=binding, current_price_conditions=binding, cases={})
    structure["evidence_sha256"] = validation_evidence._recomputed_digest(structure, "evidence_sha256")
    monkeypatch.setattr(validation_evidence, "build_hotspot_structure_validation", lambda **kwargs: structure)
    monkeypatch.setattr(validation_evidence, "build_hotspot_quantitative_validation", lambda **kwargs: report)
    with pytest.raises(ValueError, match="ACTUAL quantitative"):
        validation_evidence.build_hotspot_review_handoff(root=tmp_path,
            evaluated_at=datetime.now(timezone.utc), quantitative_protocol_binding={})


def test_quantitative_validation_requires_bound_protocol_before_computation(tmp_path):
    with pytest.raises(ValueError, match="protocol"):
        validation_evidence.build_hotspot_quantitative_validation(
            root=tmp_path, protocol_binding={}, now=datetime.now(timezone.utc))


@pytest.mark.parametrize("binding", [None, {"path": "p.json"},
    {"path": "p.json", "sha256": "z" * 64}])
def test_quantitative_validation_rejects_malformed_protocol(tmp_path, binding):
    with pytest.raises(ValueError, match="protocol"):
        validation_evidence.build_hotspot_quantitative_validation(
            root=tmp_path, protocol_binding=binding, now=datetime.now(timezone.utc))


def test_quantitative_validation_checks_protocol_hash_before_replay(tmp_path):
    (tmp_path / "p.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="protocol hash mismatch"):
        validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
            protocol_binding=dict(path="p.json", sha256="0" * 64),
            now=datetime.now(timezone.utc))


def test_quantitative_validation_rejects_escape(tmp_path):
    with pytest.raises(ValueError, match="protocol"):
        validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
            protocol_binding=dict(path="../p.json", sha256="0" * 64),
            now=datetime.now(timezone.utc))


def test_quantitative_validation_rejects_bound_unsupported_protocol(tmp_path):
    raw = json.dumps({"schema_version": "unsupported"}).encode()
    (tmp_path / "p.json").write_bytes(raw)
    with pytest.raises(ValueError, match="specification"):
        validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
            protocol_binding=dict(path="p.json", sha256=sha256(raw).hexdigest()),
            now=datetime.now(timezone.utc))
