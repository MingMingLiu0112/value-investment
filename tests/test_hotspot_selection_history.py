"""Historical selection consumes originals, not supplied signal winners."""
from copy import deepcopy
from datetime import datetime

import pytest

from test_hotspot_candidate_selection import _fixture, NOW
from value_investment_agent.application.hotspot import selection_history as subject


def specification(root, *, zero_turnover=False):
    watch, case, _, _ = _fixture(root, count=1, zero_turnover=zero_turnover)
    return dict(schema_version=subject.SPEC_VERSION, action="no_order", namespace="TEST_ONLY",
        registered_at=NOW.isoformat(), start_date="2026-09-24", end_date="2026-09-24",
        rule_bindings=subject.implementation_bindings(), snapshots=[dict(session="2026-09-24",
            decision_at=NOW.isoformat(), watch_binding=watch, case_bindings={"600519": case})])


def test_real_loader_reruns_all_members_without_orders_or_side_effects(tmp_path):
    spec = specification(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "REPLAYED"
    assert report["rows"][0]["selection"]["coverage"]["evaluated"] == 1
    assert report["rows"][0]["selection"]["shortlist"] == []
    assert report["rows"][0]["membership_change"] is None
    assert report["strict_oos_admitted"] is report["trade_eligible"] is False
    assert report["strategy_validation"] == "NOT_PROVEN"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_no_valid_market_quotes_is_not_a_complete_zero_candidate_session(tmp_path):
    spec = specification(tmp_path, zero_turnover=True)
    spec["snapshots"][0]["case_bindings"] = {}
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "PARTIAL"
    assert report["replayed_sessions"] == 0
    assert report["rows"][0]["membership_change"] is None
    assert report["rows"][0]["selection"]["coverage"]["market_securities"] == 0


@pytest.mark.parametrize("damage", ["late", "source_hash", "missing_case", "wrong_session"])
def test_bad_snapshots_are_unknown_not_empty_successful_selection(tmp_path, damage):
    spec = specification(tmp_path)
    row = spec["snapshots"][0]
    if damage == "late":
        row["decision_at"] = "2026-09-24T16:00:00+08:00"
    elif damage == "source_hash":
        row["watch_binding"]["sha256"] = "0" * 64
    elif damage == "missing_case":
        row["case_bindings"] = {}
    else:
        spec["start_date"] = "2026-09-23"
        row["session"] = "2026-09-23"
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "PARTIAL"
    assert report["replayed_sessions"] == 0
    assert all(r["membership_change"] is None for r in report["rows"])


@pytest.mark.parametrize("damage", ["orders", "rule", "duplicate", "future", "namespace"])
def test_malformed_or_rewritten_experiment_rejected(tmp_path, damage):
    spec = specification(tmp_path)
    if damage == "orders":
        spec["orders"] = []
    elif damage == "rule":
        spec["rule_bindings"][0]["sha256"] = "f" * 64
    elif damage == "duplicate":
        spec["snapshots"] *= 2
    elif damage == "namespace":
        spec["namespace"] = "APPROVED"
    else:
        spec["registered_at"] = "2099-01-01T00:00:00+08:00"
    with pytest.raises(ValueError):
        subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)


def test_missing_whole_day_breaks_membership_transition(monkeypatch, tmp_path):
    spec = specification(tmp_path)
    spec["start_date"] = "2026-09-22"
    item = deepcopy(spec["snapshots"][0])
    item.update(session="2026-09-22", decision_at="2026-09-22T16:00:00+08:00")
    spec["snapshots"].insert(0, item)
    def selected(**kwargs):
        day = "2026-09-22" if kwargs["now"].day == 22 else "2026-09-24"
        return dict(status="RESEARCH_SELECTION_REPLAYED", data_status="CURRENT", trade_date=day,
            activity_rule_version="test-activity", structure_rule_version="test-structure",
            coverage=dict(market_securities=1, unknown=0, omitted_by_limit=0), source_bindings=[],
            shortlist=[dict(symbol="600519")] if day.endswith("22") else [])
    monkeypatch.setattr(subject, "select_current_hotspot_candidates", selected)
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["missing_sessions"] == ["2026-09-23"]
    assert report["rows"][-1]["membership_change"] is None


def test_registration_claim_does_not_grant_oos_and_empty_history_is_not_registered(tmp_path):
    spec = specification(tmp_path)
    spec["registered_at"] = "2026-01-01T00:00:00+08:00"
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["declared_registration_precedes_decisions"] is True
    assert report["strict_oos_admitted"] is False
    spec["snapshots"] = []
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["declared_registration_precedes_decisions"] is False
    assert report["missing_sessions"] == ["2026-09-24"]


@pytest.mark.parametrize("changed", [False, True, "scope"])
def test_adjacent_days_only_compare_the_same_rule_regime(tmp_path, monkeypatch, changed):
    spec = specification(tmp_path)
    spec["start_date"] = "2026-09-23"
    item = deepcopy(spec["snapshots"][0])
    item.update(session="2026-09-23", decision_at="2026-09-23T16:00:00+08:00")
    spec["snapshots"].insert(0, item)
    def selected(**kwargs):
        first = kwargs["now"].day == 23
        return dict(status="RESEARCH_SELECTION_REPLAYED", data_status="CURRENT",
            trade_date="2026-09-23" if first else "2026-09-24",
            activity_rule_version="old" if changed is True and first else "same",
            structure_rule_version="structure", coverage=dict(market_securities=1, unknown=0, omitted_by_limit=0),
            source_bindings=[], shortlist=[dict(symbol="600519")] if first else [])
    monkeypatch.setattr(subject, "select_current_hotspot_candidates", selected)
    if changed == "scope":
        # Isolate the comparison contract; source admission has separate tests.
        import json
        original_reader = subject._bound_bytes
        calls = []
        def read_watch(root, binding):
            watch = json.loads(original_reader(root, binding))
            if not calls:
                watch.pop("candidate_pool", None)
            calls.append(binding)
            return json.dumps(watch).encode()
        monkeypatch.setattr(subject, "_bound_bytes", read_watch)
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    transition = report["rows"][-1]["membership_change"]
    if changed:
        assert transition is None
    else:
        assert transition == dict(entered=[], left=["600519"],
            scope="RESEARCH_POOL_MEMBERSHIP_NOT_BUY_OR_EXIT")
