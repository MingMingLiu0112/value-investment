from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
from hotspot_retained_originals import require_retained_originals

from value_investment_agent.application.hotspot.observation_continuity import (
    _bound, _compare, compare_observation_continuity,
)


def observation(state="WATCH", day="2026-10-19", digest="a", selected=True):
    return dict(symbol="000001", selected=selected, case_binding={"sha256": digest},
        plan=dict(signal_state=state, market_trade_date=day, expires_after_session="2026-10-20",
                  model_or_rule_version="existing-v1", price_behavior={"daily_trend": "RANGE"}))


@pytest.mark.parametrize("state,old,session,leave,expected", [
    ("WATCH", False, "2026-10-20", (), "new"),
    ("WATCH", True, "2026-10-20", (), "continue"),
    ("TRIGGER_PENDING", True, "2026-10-20", (), "approach"),
    ("TRIGGER_OBSERVED", True, "2026-10-20", (), "triggered"),
    ("TRIGGER_REJECTED", True, "2026-10-20", (), "invalid"),
    ("BLOCKED", True, "2026-10-20", (), "invalid"),
    ("STALE", True, "2026-10-20", (), "expired"),
    ("TRIGGER_OBSERVED", True, "2026-10-21", (), "expired"),
    ("WATCH", True, "2026-10-20", ("000001",), "left"),
])
def test_transitions_preserve_evidence(state, old, session, leave, expected):
    current = {"000001": observation(state)}
    previous = {"000001": observation()} if old else {}
    before = deepcopy((current, previous))
    row = _compare(current, previous, completed_session=date.fromisoformat(session), leave_symbols=leave)[0]
    assert row["transition"] == expected
    assert row["formal_eligibility"] is False
    assert row["action_eligibility"] is False
    assert row["current_price_admitted"] is row["price_admitted"] is False
    assert row["action"] == "no_order"
    assert row["observation"]["plan"]["market_trade_date"] == "2026-10-19"
    assert (current, previous) == before


def test_dropped_shortlist_retained_until_original_expiry():
    previous = {"000001": observation()}
    row = _compare({}, previous, completed_session=date(2026, 10, 20), leave_symbols=())[0]
    assert row["transition"] == "continue"
    assert row["selected_today"] is False
    assert row["fresh_evidence"] is False
    assert row["reason"] == "RETAINED_WITHOUT_FRESH_REASSESSMENT"
    assert row["observation"] == previous["000001"]
    assert _compare({}, previous, completed_session=date(2026, 10, 21), leave_symbols=())[0]["transition"] == "expired"


def test_strengthening_requires_new_evidence_and_same_rule():
    previous = {"000001": observation()}
    fresh = observation(digest="b", day="2026-10-20")
    fresh["plan"]["price_behavior"]["daily_trend"] = "UPTREND"
    assert _compare({"000001": fresh}, previous, completed_session=date(2026, 10, 20), leave_symbols=())[0]["trend_strengthened"]
    fresh["plan"]["model_or_rule_version"] = "new-rule"
    assert not _compare({"000001": fresh}, previous, completed_session=date(2026, 10, 20), leave_symbols=())[0]["trend_strengthened"]


def test_reject_future_regression_unknown_state_and_unbounded_union():
    for current, previous in [
        ({"000001": observation(day="2026-10-21")}, {}),
        ({"000001": observation()}, {"000001": observation(day="2026-10-20")}),
        ({"000001": observation("ACTION_ELIGIBLE")}, {}),
        ({str(i): observation() for i in range(41)}, {}),
    ]:
        with pytest.raises(ValueError):
            _compare(current, previous, completed_session=date(2026, 10, 20), leave_symbols=())


def test_bound_rejects_tampering_and_escape(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    path = runtime / "registry.json"
    path.write_text(json.dumps({"action": "no_order"}), encoding="utf-8")
    binding = dict(path="runtime/registry.json", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert _bound(tmp_path, binding)["action"] == "no_order"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        _bound(tmp_path, binding)
    with pytest.raises(ValueError, match="under runtime"):
        _bound(tmp_path, {**binding, "path": "../outside.json"})


def test_naive_cutoff_rejected_before_io(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        compare_observation_continuity(root=tmp_path, current_binding={}, previous_binding=None,
            completed_session=date(2026, 10, 20), now=datetime(2026, 10, 20))


def test_same_day_before_exchange_close_is_not_a_completed_session(tmp_path):
    with pytest.raises(ValueError, match="completed exchange session"):
        compare_observation_continuity(root=tmp_path, current_binding={}, previous_binding=None,
            completed_session=date(2026, 10, 20),
            now=datetime.fromisoformat("2026-10-20T14:59:59+08:00"))


def test_held_security_outside_shortlist_or_expired_still_requests_monitoring(monkeypatch, tmp_path):
    from value_investment_agent.application.hotspot import observation_continuity as service

    monkeypatch.setattr(service, "_observations", lambda root, binding, now:
        {"000001": observation()} if binding.get("previous") else {})
    result = compare_observation_continuity(root=tmp_path, current_binding={},
        previous_binding={"previous": True}, completed_session=date(2026, 10, 21),
        now=datetime.fromisoformat("2026-10-21T16:00:00+08:00"), held_symbols=("000001", "600150"))
    assert result["items"][0]["transition"] == "expired"
    requests = result["holding_monitoring_requests"]
    assert [row["symbol"] for row in requests] == ["000001", "600150"]
    assert requests[0]["observation_transition"] == "expired"
    assert requests[1]["observation_binding"] is None
    assert all(row["ownership_verified"] is row["action_eligibility"] is False for row in requests)
    assert all(row["action"] == "no_order" for row in requests)


@pytest.mark.parametrize("symbols", [("000001", "000001"), ("bad",), tuple(str(i) for i in range(21))])
def test_invalid_held_scope_rejected_before_io(tmp_path, symbols):
    with pytest.raises(ValueError, match="held security"):
        compare_observation_continuity(root=tmp_path, current_binding={}, previous_binding=None,
            completed_session=date(2026, 10, 20), now=datetime(2026, 10, 21, tzinfo=timezone.utc),
            held_symbols=symbols)


def retained_two_day_replay():
    root = Path(__file__).resolve().parents[1]
    previous = dict(path="runtime/hotspot-current-refresh/778da53185194f9090ae7a1b68915b4e/previous-registry.json",
        sha256="9f2351ff37a5299291f11c5ac680b50e71051da82f9b41e954e78b57a14913b2")
    current = dict(path="runtime/hotspot-current-refresh/1a1abfa7672647cd97f39a930c4abe82/previous-registry.json",
        sha256="317f151100baaaac268f6dd759290b623ec66b4835e932901f63448cdfff7f93")
    require_retained_originals(root, root / previous["path"], root / current["path"])
    return compare_observation_continuity(root=root, current_binding=current,
        previous_binding=previous, completed_session=date(2026, 10, 16),
        now=datetime.now(timezone.utc))


def test_real_oct15_oct16_continuity_revalidates_original_handles():
    result = retained_two_day_replay()
    observations = [row["observation"] for row in result["items"]]
    assert {"2026-10-15", "2026-10-16"} <= {row["plan"]["market_trade_date"] for row in observations}
    retained = [row for row in result["items"] if not row["selected_today"]]
    assert retained
    assert all(row["observation"]["plan"]["market_trade_date"] <= "2026-10-16" for row in retained)
    assert all(row["formal_eligibility"] is False for row in result["items"])


def test_synthetic_source_bound_continuity_replays_and_rejects_changed_original(tmp_path):
    from test_current_price_registry import register
    from test_hotspot_current_price_case import NOW
    case = register(tmp_path)
    registry = json.loads((tmp_path / "config/current-price-conditions.json").read_bytes())
    watch = tmp_path / "runtime/watch.json"
    watch.write_text(json.dumps(dict(schema_version="hotspot-observation-report-v1", action="no_order",
        dated_quote_observations=[dict(symbol="600519", quote_date="2026-09-24",
            status="DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION")])), encoding="utf-8")
    registry["watch_source_binding"]["sha256"] = hashlib.sha256(watch.read_bytes()).hexdigest()
    snapshot = tmp_path / "runtime/continuity-registry.json"
    snapshot.write_text(json.dumps(registry), encoding="utf-8")
    binding = dict(path=snapshot.relative_to(tmp_path).as_posix(),
                   sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest())
    args = dict(root=tmp_path, current_binding=binding, previous_binding=None,
                completed_session=date(2026, 9, 24), now=NOW)
    result = compare_observation_continuity(**args)
    assert result["items"][0]["transition"] == "new"
    assert result["items"][0]["observation"]["case_binding"]["sha256"] == case["case_sha256"]
    assert result["formal_eligibility"] is False
    original = tmp_path / case["source_bindings"]["15m"]["path"]
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        compare_observation_continuity(**args)


def test_service_rebuilds_retained_case_at_acquisition_cutoff(monkeypatch, tmp_path):
    from value_investment_agent.application.hotspot import observation_continuity as service

    acquired = "2026-10-19T16:00:00+08:00"
    documents = {
        "registry": dict(schema_version="current-price-conditions-v1", action="no_order",
            watch_source_binding={"path": "watch", "sha256": "watch-hash"},
            items=[dict(symbol="000001", case_path="case", case_sha256="case-hash")]),
        "watch": dict(schema_version="hotspot-daily-selection-v1", trade_date="2026-10-19",
                      candidate_pool=[{"symbol": "000001"}]),
        "case": dict(current_reference_close={"bundle_path": "bundle", "bundle_sha256": "bundle-hash"},
                     source_bindings={"60m": {"fetched_at": acquired}}),
        "bundle": {"finished_at": acquired},
    }
    monkeypatch.setattr(service, "_bound", lambda root, binding: deepcopy(documents[binding["path"]]))
    monkeypatch.setattr(service, "verify_daily_selection", lambda root, watch: None)
    calls = []

    def load(**kwargs):
        calls.append(kwargs)
        return {"verified": True}

    monkeypatch.setattr(service, "load_current_price_case", load)
    monkeypatch.setattr(service, "project_current_price_action_plan", lambda case: observation()["plan"])
    args = dict(root=tmp_path, current_binding={"path": "registry", "sha256": "registry-hash"},
                previous_binding=None, completed_session=date(2026, 10, 20),
                now=datetime(2026, 10, 20, 10, tzinfo=timezone.utc))
    result = compare_observation_continuity(**args)
    assert calls[0]["now"] == datetime.fromisoformat(acquired)
    assert calls[0]["expected_sha256"] == "case-hash"
    assert result["items"][0]["observation"]["plan"]["market_trade_date"] == "2026-10-19"
    assert result["holdings_scope"] == "NOT_EVALUATED_SEPARATE_MONITORING_REQUIRED"
    documents["watch"] = dict(schema_version="hotspot-observation-report-v1", action="no_order",
        dated_quote_observations=[dict(symbol="000001", quote_date="2026-10-16",
            status="DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION")])
    legacy = compare_observation_continuity(**args)["items"][0]["observation"]
    assert legacy["selection_trade_date"] == "2026-10-16"
    assert legacy["plan"]["market_trade_date"] == "2026-10-19"
    documents["bundle"]["finished_at"] = "2026-10-21T16:00:00+08:00"
    with pytest.raises(ValueError, match="unavailable"):
        compare_observation_continuity(**args)


@pytest.mark.parametrize("day", [date(2026, 10, 18), date(2026, 10, 21)])
def test_service_rejects_non_session_and_future_session(tmp_path, day):
    with pytest.raises(ValueError, match="completed exchange session"):
        compare_observation_continuity(root=tmp_path, current_binding={}, previous_binding=None,
            completed_session=day, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
