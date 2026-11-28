"""Unsigned V3 handoff contract tests with isolated candidate/scan fixtures."""
from datetime import date, datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research import parent_cash_task_alignment_v3 as service
from value_investment_agent.research_run_contract import canonical_contract_payload


@pytest.fixture
def handoff_inputs(tmp_path, monkeypatch):
    (tmp_path / "runtime").mkdir()

    def write(name, value):
        name = "runtime/" + name
        data = json.dumps(value).encode()
        (tmp_path / name).write_bytes(data)
        return dict(path=name, sha256=hashlib.sha256(data).hexdigest())

    start, end = date(2025, 12, 31), date(2026, 1, 3)
    now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    original = write("original.json", {"scope": "TEST_ONLY"})
    result_binding = write("result.json", {"scope": "TEST_ONLY"})
    task_head = write("head.json", {"scope": "TEST_ONLY"})
    spec = write("spec.json", {"scope": "TEST_ONLY"})
    receipt = write("receipt.json", dict(schema_version="parent-cash-task-backed-receipt-v3",
        result_binding=result_binding, inputs=dict(task_id="rt-test-only", task_head=task_head)))
    observation = write("observation.json", {"scope": "TEST_ONLY"})
    scan_binding = write("scan.json", {"scope": "TEST_ONLY"})
    result = dict(symbol="000568", action="no_order", formal_eligibility=False,
        main_range_adopted=False, input_descriptor_sha256="a" * 64,
        descriptor=dict(symbol="000568", input_sha256="a" * 64,
                        point_in_time=dict(valuation_date=start.isoformat())),
        valuation=dict(symbol="000568", valuation_date=start.isoformat(), status="conditional_research_only"),
        source_bindings=[original], provenance=dict(spec_binding=spec, task_record_binding=task_head))
    row = dict(announcement_id="TEST_ONLY", title="TEST_ONLY", evidence_refs=[original])
    window = dict(source_integrity_verified=True, full_calendar_window_elapsed=True, coverage_status="COMPLETE",
                  acquired_at=now.isoformat(), scan_binding=scan_binding, announcements=[row])
    scan = SimpleNamespace(symbol="000568", validity_from=start, scan_from=start, scan_to=end,
                           retrieved_at=now, announcements=[row], coverage_status="COMPLETE")

    def replay_receipt(**kwargs):
        assert kwargs == dict(root=tmp_path, receipt_binding=receipt, now=now)
        return result

    def replay_scan(root, analysis, refs, at, read):
        assert (root, analysis["symbol"], refs, at) == (tmp_path, "000568", [observation], now)
        read(observation)
        read(scan_binding)
        return [window], [scan]

    monkeypatch.setattr(service, "replay_parent_cash_task_receipt", replay_receipt)
    monkeypatch.setattr(service, "_event_windows", replay_scan)
    return (dict(root=tmp_path, receipt_binding=receipt, observation_binding=observation,
                 review_through=end, now=now), result, window, scan)


def test_v3_unsigned_handoff_binds_receipt_scan_and_evidence(handoff_inputs):
    args, result, window, _ = handoff_inputs
    handoff = service.prepare_parent_cash_task_materiality_handoff(**args)
    assert handoff == service.prepare_parent_cash_task_materiality_handoff(**args)
    assert handoff["candidate_binding"] == args["receipt_binding"]
    assert handoff["observation_binding"] == args["observation_binding"]
    assert handoff["input_descriptor_sha256"] == result["input_descriptor_sha256"]
    assert handoff["scan_binding"] == window["scan_binding"]
    assert handoff["announcements"] == window["announcements"]
    assert handoff["status"] == "UNSIGNED_REVIEW_REQUIRED"
    assert handoff["action"] == "no_order"
    assert not handoff["materiality_approved"] and not handoff["formal_eligibility"]
    assert not {"signature", "unsigned_response", "package_binding"} & handoff.keys()
    digest = handoff.pop("handoff_sha256")
    assert digest == hashlib.sha256(canonical_contract_payload(handoff).encode()).hexdigest()


def test_f2_keeps_unsigned_task_materiality_out_of_comparison(handoff_inputs):
    from value_investment_agent.application.research.pending_candidate_alignment import _materiality

    args, _, window, scan = handoff_inputs
    calls = []

    def prepare(bound_window):
        calls.append(bound_window)
        return service.prepare_parent_cash_task_materiality_handoff(**args)

    analysis = dict(review_binding={}, prepare_unsigned_task_materiality=prepare)
    for ref in (None, args["observation_binding"]):
        materiality, route = _materiality(
            args["root"], analysis, ref, [window], [scan], args["now"], None
        )
        assert materiality is None
        if ref is None:
            assert route["status"] == "UNSIGNED_TASK_MATERIALITY_REVIEW_REQUIRED"
            assert route["unsigned_task_handoff"]["materiality_approved"] is False
        else:
            assert route["status"] == "NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED"
            assert "unsigned_task_handoff" not in route
    assert calls == [window]


@pytest.mark.parametrize("variant, error", [
    ("descriptor", "CANDIDATE_IDENTITY_MISMATCH"),
    ("snapshot", "EXACT_CLOSED_SCAN_REQUIRED"),
    ("wrong_symbol", "EXACT_CLOSED_SCAN_REQUIRED"),
    ("wrong_start", "EXACT_CLOSED_SCAN_REQUIRED"),
    ("wrong_end", "EXACT_CLOSED_SCAN_REQUIRED"),
    ("duplicate", "ANNOUNCEMENT_IDENTITY_INVALID"),
    ("missing_original", "ANNOUNCEMENT_IDENTITY_INVALID"),
])
def test_v3_unsigned_handoff_fails_closed(handoff_inputs, variant, error):
    args, result, window, scan = handoff_inputs
    if variant == "descriptor":
        result["descriptor"]["input_sha256"] = "0" * 64
    elif variant == "snapshot":
        window["full_calendar_window_elapsed"] = False
    elif variant == "wrong_symbol":
        scan.symbol = "600887"
    elif variant == "wrong_start":
        scan.scan_from = date(2026, 1, 1)
    elif variant == "wrong_end":
        args["review_through"] = date(2026, 1, 4)
    elif variant == "duplicate":
        window["announcements"] *= 2
    else:
        window["announcements"][0]["evidence_refs"] = []
    with pytest.raises(ValueError, match=error):
        service.prepare_parent_cash_task_materiality_handoff(**args)
