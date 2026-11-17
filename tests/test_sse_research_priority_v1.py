"""TEST_ONLY mechanism fixtures; no network, no new source admission."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.research import sse_research_priority_v1 as m
from test_m2_opportunity_discovery import _financial_points

NOW = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)


def bound(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    (tmp_path / "runtime").mkdir()
    points = [dict(p, available_at="2026-09-20T07:00:00+00:00",
        raw_file_hash="a"*64, source_url="https://example.com/TEST_ONLY",
        data_point_id=str(i)) for i, p in enumerate(_financial_points())]
    rows = [dict(symbol=f"{600001+i:06}", company_name=f"TEST_ONLY {i}", industry="制造",
        status="CANDIDATE", channels=["value"], risk_warning=False, price_conflict=False,
        profile_status="GENERAL_RESEARCH", reason="TEST_ONLY", gaps=[],
        applicability={"kind": None}, financial_crosscheck={"conflict_count": 0}) for i in range(36)]
    capture = dict(screen=dict(scope="SSE_MAIN_A_ONLY", action="no_order",
        coverage_complete=True, available_at="2026-11-01T10:00:00+00:00", run_id="TEST_ONLY",
        counts={"candidate": len(rows)}, rows=rows), receipt={"action": "no_order"}, points=points,
        native_revalidated_points=[],
        financial_payload={"points": points, "public_financial_input": {"TEST_ONLY": True}})
    monkeypatch.setattr(m.sse_main_screening, "replay_research_inputs", lambda **kwargs: deepcopy(capture))
    monkeypatch.setattr(m, "consume_retained_enrichment",
        lambda root, points, sources, evaluation_at, **kwargs: (points, []))
    export = tmp_path / "runtime/export.json"
    args = dict(root=tmp_path, manifest_binding={"path": "runtime/manifest.json", "sha256": "a"*64},
        financial_export_path=export, financial_export_sha256=bound(export, capture["financial_payload"]),
        now=NOW)
    return args, capture


def all_rows(result):
    return result["deep_research_priority"] + result["evidence_enrichment_work_queue"]


def test_decision_register_keeps_included_excluded_and_data_gap_reasons_dated():
    rows = [
        dict(symbol="600003", company_name="gap", status="UNASSESSABLE", updated_at="2026-11-05T03:00:00+00:00",
             gaps=["missing cash flow"], channel_evaluations=[dict(channel="quality", status="DATA_GAP", reason="missing cash flow")]),
        dict(symbol="600001", company_name="candidate", status="CANDIDATE", updated_at="2026-11-05T03:00:00+00:00",
             reason="value observation", gaps=[], channel_evaluations=[dict(channel="value", status="CANDIDATE", reason="value observation")]),
        dict(symbol="600002", company_name="excluded", status="EXCLUDED", updated_at="2026-11-05T03:00:00+00:00",
             gaps=[], channel_evaluations=[dict(channel="quality", status="EXCLUDED", reason="quality observation failed")]),
    ]
    result = m._screening_decision_register(rows, evaluation_at=NOW, source_available_at=NOW)
    assert [item["symbol"] for item in result] == ["600001", "600002", "600003"]
    assert [item["queue_decision"] for item in result] == ["INCLUDED_CANDIDATE", "EXCLUDED", "DATA_GAP"]
    assert result[1]["excluded_reasons"] == ["quality observation failed"]
    assert result[2]["data_gaps"] == ["missing cash flow"]
    assert all(item["evaluation_at"] == NOW.isoformat() for item in result)


def test_decision_register_rejects_unknown_status():
    with pytest.raises(ValueError, match="outcome status"):
        m._screening_decision_register([dict(symbol="600001", status="BUY")], evaluation_at=NOW, source_available_at=NOW)


def test_full_queue_budget_and_native_quality(setup):
    args, capture = setup
    before = deepcopy(capture)
    result = m.build_sse_research_priority(**args)
    assert len(all_rows(result)) == 36
    assert result["tracking_count"] == 30
    assert result["candidate_count"] == 36
    assert len(result["screening_decision_register"]) == 36
    assert {item["queue_decision"] for item in result["screening_decision_register"]} == {"INCLUDED_CANDIDATE"}
    assert len(result["deep_research_priority"]) == 1
    assert result["deep_research_priority"][0]["quality_score"] == "100"
    assert sum(r["tracking_selected"] for r in all_rows(result)) == 30
    assert all(r["action"] == "no_order" and not r["formal_eligibility"] for r in all_rows(result))
    assert all(r["first_seen_at"] == NOW.isoformat() for r in all_rows(result))
    assert capture == before
    assert result == m.build_sse_research_priority(**args)
    assert result["source_available_at"] == capture["screen"]["available_at"]
    assert result["content_sha256"] == m._canonical_hash({k:v for k,v in result.items() if k != "content_sha256"})


@pytest.mark.parametrize("damage", ["conflict", "st", "special", "price"])
def test_ineligible_retained_but_never_selected(setup, damage):
    args, capture = setup
    row = capture["screen"]["rows"][0]
    if damage == "conflict": row["financial_crosscheck"]["conflict_count"] = 1
    if damage == "st": row["risk_warning"] = True
    if damage == "special": row["applicability"]["kind"] = "bank"
    if damage == "price": row["price_conflict"] = True
    result = m.build_sse_research_priority(**args)
    item = next(r for r in all_rows(result) if r["symbol"] == row["symbol"])
    assert not item["tracking_selected"]
    assert item["quality_score"] is None
    assert result["candidate_count"] == 36


@pytest.mark.parametrize("damage", ["hash", "points", "verified", "metadata", "future", "naive", "budget", "source"])
def test_fail_closed(setup, monkeypatch, damage):
    args, capture = setup
    if damage == "hash": args["financial_export_sha256"] = "0"*64
    if damage in {"points", "verified", "metadata"}:
        payload = deepcopy(capture["financial_payload"])
        if damage == "points": payload["points"] = []
        if damage == "verified": payload["points"][0]["validation_status"] = "pending"
        if damage == "metadata": payload["public_financial_input"] = {}
        args["financial_export_sha256"] = bound(args["financial_export_path"], payload)
    if damage == "future": capture["screen"]["available_at"] = (NOW+timedelta(days=1)).isoformat()
    if damage == "naive": args["now"] = NOW.replace(tzinfo=None)
    if damage == "budget": args["budget"] = True
    if damage == "source":
        def reject(**kwargs): raise ValueError("bad original")
        monkeypatch.setattr(m.sse_main_screening, "replay_research_inputs", reject)
    with pytest.raises(ValueError): m.build_sse_research_priority(**args)


def test_explicit_sources_only_current_adoption(setup, monkeypatch):
    args, capture = setup
    payload = deepcopy(capture["financial_payload"])
    payload["value_enrichment_sources"] = [{"symbol":"600001", "TEST_ONLY": True}]
    args["financial_export_sha256"] = bound(args["financial_export_path"], payload)
    calls = []
    def consume(root, points, sources, evaluation_at, **kwargs):
        calls.append((deepcopy(points), sources, evaluation_at, kwargs))
        return points, [{"TEST_ONLY": "native replay"}]
    monkeypatch.setattr(m, "consume_retained_enrichment", consume)
    result = m.build_sse_research_priority(**args)
    assert calls == [(capture["points"], payload["value_enrichment_sources"], NOW, {"write_cache": False})]
    assert result["retained_enrichment_sources"] == payload["value_enrichment_sources"]
    assert result["retained_enrichment_adoption"] == [{"TEST_ONLY": "native replay"}]


@pytest.mark.parametrize("state", ["EXCLUDED", "MISSING", "CONFLICT"])
def test_same_day_carry_pause_reappearance(setup, state):
    args, capture = setup
    first = m.build_sse_research_priority(**args)
    previous = args["root"] / "runtime/previous.json"
    args.update(previous_path=previous, previous_sha256=bound(previous, first), now=NOW+timedelta(seconds=1))
    original = deepcopy(capture["screen"]["rows"][0])
    if state == "MISSING":
        capture["screen"]["rows"].pop(0)
    elif state == "CONFLICT":
        capture["screen"]["rows"][0]["financial_crosscheck"]["conflict_count"] = 1
    else:
        capture["screen"]["rows"][0]["status"] = "EXCLUDED"
    capture["screen"]["counts"]["candidate"] = sum(r["status"] == "CANDIDATE" for r in capture["screen"]["rows"])
    second = m.build_sse_research_priority(**args)
    history = second["tracking_history"][0]
    assert history["symbol"] == original["symbol"]
    assert history["tracking_status"] == "PAUSED" and not history["tracking_selected"]
    assert history["first_seen_at"] == NOW.isoformat() and not history["exit_confirmed"]
    args.update(previous_sha256=bound(previous, second), now=NOW+timedelta(seconds=2))
    capture["screen"]["rows"] = [original]+[r for r in capture["screen"]["rows"] if r["symbol"] != original["symbol"]]
    capture["screen"]["counts"]["candidate"] = 36
    third = m.build_sse_research_priority(**args)
    carried = next(r for r in all_rows(third) if r["symbol"] == original["symbol"])
    assert carried["tracking_status"] == "CARRIED"
    assert carried["first_seen_at"] == NOW.isoformat()
    assert third["tracking_history"] == []


@pytest.mark.parametrize("damage", ["same_time", "content", "schema", "first_seen", "unpaired"])
def test_previous_rejection(setup, damage):
    args, _ = setup
    prior = m.build_sse_research_priority(**args)
    if damage == "schema": prior["schema_version"] = "value-research-priority-v2"
    if damage == "first_seen": all_rows(prior)[0]["first_seen"] = "2026-11-02T10:00:00"
    if damage != "content":
        prior["content_sha256"] = m._canonical_hash({k:v for k,v in prior.items() if k != "content_sha256"})
    else: prior["budget"] = 9
    path = args["root"]/"runtime/prior.json"
    args.update(previous_path=path, previous_sha256=bound(path, prior),
        now=NOW if damage == "same_time" else NOW+timedelta(seconds=1))
    if damage == "unpaired": args["previous_sha256"] = None
    with pytest.raises(ValueError): m.build_sse_research_priority(**args)


def test_736_candidates_preserved(setup):
    args, capture = setup
    template = capture["screen"]["rows"][0]
    capture["screen"]["rows"] = [dict(deepcopy(template), symbol=str(600001+i)) for i in range(736)]
    capture["screen"]["counts"]["candidate"] = 736
    result = m.build_sse_research_priority(**args)
    assert len(all_rows(result)) == result["candidate_count"] == 736
    assert result["tracking_count"] == 30
    assert sum(not r["tracking_selected"] for r in all_rows(result)) == 706


def test_boolean_is_not_equal_numeric_source_fact(setup):
    args, capture = setup
    capture["points"][0]["TEST_ONLY"] = 1
    payload = deepcopy(capture["financial_payload"])
    payload["points"][0]["TEST_ONLY"] = True
    args["financial_export_sha256"] = bound(args["financial_export_path"], payload)
    with pytest.raises(ValueError, match="points differ"):
        m.build_sse_research_priority(**args)


def test_previous_alias_tamper_rejected(setup):
    args, _ = setup
    prior = m.build_sse_research_priority(**args)
    all_rows(prior)[0]["first_seen_at"] = "2026-01-01T00:00:00+00:00"
    prior["content_sha256"] = m._canonical_hash({k:v for k,v in prior.items() if k != "content_sha256"})
    path = args["root"]/"runtime/prior.json"
    args.update(previous_path=path, previous_sha256=bound(path, prior), now=NOW+timedelta(seconds=1))
    with pytest.raises(ValueError, match="aliases"):
        m.build_sse_research_priority(**args)

def _continue(args, result):
    path = args["root"] / "runtime/continuity.json"
    return dict(args, previous_path=path, previous_sha256=bound(path, result),
        now=args["now"]+timedelta(seconds=1))


def _selected(result):
    return {r["symbol"] for r in all_rows(result) if r["tracking_selected"]}


def test_rank_change_keeps_eligible_tracking(setup, monkeypatch):
    args, _ = setup
    first = m.build_sse_research_priority(**args)
    native = m.rank_research_candidates
    def reverse(rows, *, limit):
        ranked, _ = native(rows, limit=limit)
        ranked.reverse()
        return ranked, [r for r in ranked if r["research_priority_eligible"]][:limit]
    monkeypatch.setattr(m, "rank_research_candidates", reverse)
    second = m.build_sse_research_priority(**_continue(args, first))
    assert _selected(second) == _selected(first)
    assert all(r["was_tracking_selected"] for r in all_rows(second) if r["tracking_selected"])
    assert len(all_rows(second)) == 36


def test_budget_shrink_rejects_without_mutation(setup):
    args, _ = setup
    first = m.build_sse_research_priority(**args)
    later = _continue(args, first)
    raw = later["previous_path"].read_bytes()
    with pytest.raises(ValueError, match="BUDGET_BELOW_RETAINED_TRACKING_COUNT"):
        m.build_sse_research_priority(**dict(later, budget=29))
    assert later["previous_path"].read_bytes() == raw


def test_budget_growth_fills_ranked_slots(setup):
    args, _ = setup
    first = m.build_sse_research_priority(**dict(args, budget=2))
    second = m.build_sse_research_priority(**dict(_continue(args, first), budget=4))
    assert _selected(first) <= _selected(second)
    assert second["tracking_count"] == 4
    ranked = sorted(all_rows(second), key=lambda r: r["research_priority_rank"])
    assert _selected(second) == {r["symbol"] for r in ranked[:4]}


@pytest.mark.parametrize("state", ["conflict", "excluded", "missing"])
def test_paused_tracking_survives_multiple_rounds(setup, state):
    args, capture = setup
    first = m.build_sse_research_priority(**args)
    symbol = next(r["symbol"] for r in all_rows(first) if r["tracking_selected"])
    row = next(r for r in capture["screen"]["rows"] if r["symbol"] == symbol)
    if state == "conflict": row["financial_crosscheck"]["conflict_count"] = 1
    if state == "excluded": row["status"] = "EXCLUDED"
    if state == "missing": capture["screen"]["rows"].remove(row)
    capture["screen"]["counts"]["candidate"] = sum(r["status"] == "CANDIDATE" for r in capture["screen"]["rows"])
    later = _continue(args, first)
    second = m.build_sse_research_priority(**later)
    third = m.build_sse_research_priority(**_continue(later, second))
    for result in (second, third):
        paused = next(r for r in result["tracking_history"] if r["symbol"] == symbol)
        assert paused["was_tracking_selected"] is True
        assert paused["tracking_selected"] is False
        assert paused["tracking_status"] == "PAUSED"
        assert paused["exit_confirmed"] is False
        assert "NOT_BUSINESS_DETERIORATION" in paused["history_interpretation"]
        assert symbol not in _selected(result)
        assert result["tracking_count"] == 30

def _native_claim(setup):
    args, capture = setup
    point = next(p for p in capture["points"] if p["field_name"] == "debt_ratio")
    point["data_point_id"] = "TEST_ONLY-native-balance"
    point["metadata"] = dict(derivation_formula="OFFICIAL_BALANCE_RECONCILIATION_V1",
        verification_method="OFFICIAL_BALANCE_RECONCILIATION_V1",
        single_source_balance_verification=True, automatic_cross_source_verification=False,
        statement_scope="consolidated")
    args["financial_export_sha256"] = bound(args["financial_export_path"], capture["financial_payload"])
    capture["native_revalidated_points"] = [deepcopy(point)]
    return args, capture, deepcopy(point)


def test_native_claim_without_declarations_survives_real_consumer(setup, monkeypatch):
    args, capture, native = _native_claim(setup)
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    monkeypatch.setattr(m, "consume_retained_enrichment", consume_retained_enrichment)
    result = m.build_sse_research_priority(**args)
    row = next(r for r in all_rows(result) if r["symbol"] == native["symbol"])
    found = [p for p in row["field_observations"] if p["data_point_id"] == native["data_point_id"]]
    assert len(found) == 1
    assert {k:v for k,v in found[0].items() if k != "accepted_by_existing_quality_policy"} == native
    assert found[0]["metadata"]["automatic_cross_source_verification"] is False
    assert result["retained_enrichment_adoption"] == []


def test_rehashed_native_export_injection_rejected(setup):
    args, capture, native = _native_claim(setup)
    payload = deepcopy(capture["financial_payload"])
    next(p for p in payload["points"] if p["data_point_id"] == native["data_point_id"])["value"] = "0"
    args["financial_export_sha256"] = bound(args["financial_export_path"], payload)
    with pytest.raises(ValueError, match="points differ"):
        m.build_sse_research_priority(**args)


@pytest.mark.parametrize("mode", ["exact", "alias", "identity_conflict", "semantic_conflict"])
def test_native_new_source_merge_cannot_manufacture_crosssource(setup, monkeypatch, mode):
    args, capture, native = _native_claim(setup)
    added = deepcopy(native)
    if mode in {"alias", "semantic_conflict"}:
        added["data_point_id"] = "TEST_ONLY-alias"
        added["source_id"] = "TEST_ONLY-renamed-same-original"
        added["metadata"]["automatic_cross_source_verification"] = True
    if mode in {"identity_conflict", "semantic_conflict"}: added["value"] = "999"
    def consume(root, points, sources, **kwargs):
        assert all(p["data_point_id"] != native["data_point_id"] for p in points)
        assert kwargs["write_cache"] is False
        return [*points, added], []
    monkeypatch.setattr(m, "consume_retained_enrichment", consume)
    if "conflict" in mode:
        with pytest.raises(ValueError, match="conflicting"):
            m.build_sse_research_priority(**args)
    else:
        result = m.build_sse_research_priority(**args)
        row = next(r for r in all_rows(result) if r["symbol"] == native["symbol"])
        matches = [p for p in row["field_observations"] if p["field_name"] == "debt_ratio"]
        assert len(matches) == 1
        assert matches[0]["data_point_id"] == native["data_point_id"]
        assert matches[0]["metadata"]["automatic_cross_source_verification"] is False


def test_historical_claim_without_explicit_native_revalidation_rejected(setup, monkeypatch):
    args, capture, _ = _native_claim(setup)
    capture["native_revalidated_points"] = []
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    monkeypatch.setattr(m, "consume_retained_enrichment", consume_retained_enrichment)
    with pytest.raises(ValueError, match="Official balance ratio does not match"):
        m.build_sse_research_priority(**args)


@pytest.mark.parametrize("damage", ["missing", "null", "different_value", "different_id", "duplicate"])
def test_native_revalidation_requires_explicit_exact_identity_and_content(setup, damage):
    args, capture, _ = _native_claim(setup)
    if damage == "missing": del capture["native_revalidated_points"]
    if damage == "null": capture["native_revalidated_points"] = None
    if damage == "different_value": capture["native_revalidated_points"][0]["value"] = "999"
    if damage == "different_id": capture["native_revalidated_points"][0]["data_point_id"] = "not-in-capture"
    if damage == "duplicate": capture["native_revalidated_points"] *= 2
    with pytest.raises(ValueError, match="native"):
        m.build_sse_research_priority(**args)


def test_unlisted_derived_points_still_reach_legacy_consumer(setup, monkeypatch):
    args, capture, _ = _native_claim(setup)
    capture["native_revalidated_points"] = []
    original = deepcopy(capture["points"])
    def consume(root, points, sources, **kwargs):
        assert points == original
        raise ValueError("TEST_ONLY legacy validation enforced")
    monkeypatch.setattr(m, "consume_retained_enrichment", consume)
    with pytest.raises(ValueError, match="legacy validation enforced"):
        m.build_sse_research_priority(**args)
