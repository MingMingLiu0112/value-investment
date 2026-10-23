"""TEST_ONLY fixtures exercise the native loader, lifecycle and isolated journal."""
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_hotspot_lifecycle_bound_history import (
    _history, _binding, ENTRY_AT, CURRENT_AT,
)
from value_investment_agent.application.hotspot.simulated_lifecycle import (
    run_simulated_hotspot_lifecycle,
)


def _run(root, entry, current, **overrides):
    arguments = dict(source_root=root, workspace_root=root, symbol="600519",
        entry_case_binding=_binding(entry), entry_at=ENTRY_AT,
        followups=[dict(case_binding=_binding(current), evaluated_at=CURRENT_AT)],
        generated_at=CURRENT_AT + timedelta(days=1))
    arguments.update(overrides)
    return run_simulated_hotspot_lifecycle(**arguments)


@pytest.mark.parametrize("breach", [False, True])
def test_real_engine_preserves_freeze_and_never_fills_followup(tmp_path, breach):
    root, entry, _, current = _history(tmp_path, breach=breach)
    sources = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = _run(root, entry, current)
    assert all(p.read_bytes() == raw for p, raw in sources.items())
    assert result["namespace"] == "SIMULATED"
    assert result["market_source_scope"] == "TEST_ONLY"
    assert result["actual_account_used"] is result["actual_owned_entry_created"] is False
    assert result["trade_eligible"] is result["formal_eligibility"] is False
    assert result["position_guidance"] is None
    assert result["simulated_fill_count"] == 1 and result["followup_fill_count"] == 0
    frozen = result["entry_reference"]
    assert frozen["original_protection_price"] == "11"
    assert frozen["generated_at"] != frozen["assumed_entry_at"]
    assert frozen["entry_origin"] == "DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED"
    review = result["steps"][0]["lifecycle_review"]
    assert review["observed_review"] == "UNKNOWN"
    assert review["price_comparability"]["status"] == "UNKNOWN"
    if breach:
        assert review["original_entry_comparison"]["current_rolling_protection_price"] == "9"
        assert review["original_entry_comparison"]["original_protection_price"] == "11"
        assert review["unadjusted_structural_observation"]["observed_review"] == "EXIT_STRUCTURE_REVIEW"
    receipt = result["journal_receipt"]
    assert receipt["restart_verified"] and receipt["confirmation_idempotent"]
    journal = root / receipt["path"]
    assert sha256(journal.read_bytes()).hexdigest() == receipt["sha256"]
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert len(records) == receipt["record_count"]
    assert len([row for row in records if row["kind"] == "FILL_CONFIRMED"]) == 1
    for step in result["steps"]:
        for intention in step["intentions"].values():
            assert intention["status"] == "REVIEW_ONLY_NO_SIMULATED_FOLLOWUP_FILL"
            assert intention["action"] == "no_order"
            assert "SIMULATED_ENTRY_IS_NOT_VERIFIED_OWNERSHIP" in intention["blockers"]


def test_missing_bar_is_reported_not_filled_or_repaired(tmp_path):
    root, entry, _, current = _history(tmp_path, missing_day=23)
    result = _run(root, entry, current)
    review = result["steps"][0]["lifecycle_review"]
    assert review["original_entry_comparison"]["coverage"] == "INCOMPLETE"
    assert "ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE" in review["blockers"]
    assert result["followup_fill_count"] == 0


@pytest.mark.parametrize("change", ["future", "before_entry", "naive", "out_of_order"])
def test_bad_timeline_rejected_before_any_journal(tmp_path, change):
    root, entry, _, current = _history(tmp_path)
    followups = [dict(case_binding=_binding(current), evaluated_at=CURRENT_AT)]
    if change == "future":
        followups[0]["evaluated_at"] = CURRENT_AT + timedelta(days=2)
    elif change == "before_entry":
        followups[0]["evaluated_at"] = ENTRY_AT
    elif change == "naive":
        followups[0]["evaluated_at"] = CURRENT_AT.replace(tzinfo=None)
    else:
        followups.append(dict(case_binding=_binding(current), evaluated_at=CURRENT_AT - timedelta(hours=1)))
    with pytest.raises(ValueError):
        _run(root, entry, current, followups=followups)
    assert not (root / "runtime/swing-simulated-lifecycle").exists()


def test_corrupt_entry_cannot_create_simulated_journal(tmp_path):
    root, entry, _, current = _history(tmp_path)
    (root / entry["source_bindings"]["60m"]["path"]).write_bytes(b"TEST_ONLY corrupt")
    with pytest.raises(ValueError, match="Entry source"):
        _run(root, entry, current)
    assert not (root / "runtime/swing-simulated-lifecycle").exists()


def test_corrupt_followup_preserves_specific_rejection_without_add_or_exit(tmp_path):
    root, entry, _, current = _history(tmp_path)
    (root / current["source_bindings"]["15m"]["path"]).write_bytes(b"TEST_ONLY corrupt")
    result = _run(root, entry, current)
    review = result["steps"][0]["lifecycle_review"]
    assert review["current_data_status"] == "INVALID"
    assert "CURRENT_CASE_EVIDENCE_INVALID" in review["blockers"]
    assert review["original_entry_comparison"] is None
    assert result["followup_fill_count"] == 0


def test_each_run_has_new_journal_and_followups_never_reconfirm_entry(tmp_path):
    root, entry, _, current = _history(tmp_path)
    followups = [dict(case_binding=_binding(current), evaluated_at=CURRENT_AT + timedelta(minutes=i))
        for i in range(2)]
    first = _run(root, entry, current, followups=followups)
    old_path = root / first["journal_receipt"]["path"]
    old_bytes = old_path.read_bytes()
    second = _run(root, entry, current, followups=followups)
    assert first["journal_receipt"]["path"] != second["journal_receipt"]["path"]
    assert first["entry_freeze_sha256"] == second["entry_freeze_sha256"]
    assert old_path.read_bytes() == old_bytes
    assert len(first["steps"]) == 2
    assert first["journal_receipt"]["record_count"] == second["journal_receipt"]["record_count"]


def test_existing_non_directory_runtime_is_not_overwritten(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    root, entry, _, current = _history(source)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "runtime").write_bytes(b"DO_NOT_OVERWRITE")
    with pytest.raises(ValueError, match="non-directory"):
        _run(root, entry, current, workspace_root=workspace)
    assert (workspace / "runtime").read_bytes() == b"DO_NOT_OVERWRITE"


@pytest.mark.skipif(not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Optional local sealed public evidence")
def test_retained_300750_window_remains_descriptive(tmp_path):
    from datetime import datetime
    root = Path(os.environ["HOTSPOT_RETAINED_ROOT"])
    names = ("300750-2026-10-22-33fb0e21b19e42c298afea658cf277fe",
        "300750-2026-10-23-0562d041ff2a473581ec1fd21b17fafc")
    bindings = []
    for name in names:
        path = Path("runtime/hotspot-current-price-cases") / name / "case.json"
        bindings.append(dict(path=path.as_posix(), sha256=sha256((root / path).read_bytes()).hexdigest()))
    result = run_simulated_hotspot_lifecycle(source_root=root, workspace_root=tmp_path,
        symbol="300750", entry_case_binding=bindings[0],
        entry_at=datetime.fromisoformat("2026-10-22T18:00:00+08:00"),
        followups=[dict(case_binding=bindings[1],
            evaluated_at=datetime.fromisoformat("2026-10-23T21:00:00+08:00"))],
        generated_at=datetime.now().astimezone())
    assert result["entry_reference"]["original_protection_price"] == "218.450"
    assert result["market_source_scope"] == "PUBLIC_PROVIDER_ARCHIVE_NOT_INDEPENDENT_MINUTE_VALIDATION"
    review = result["steps"][0]["lifecycle_review"]
    assert review["original_entry_comparison"]["coverage"] == "COMPLETE"
    assert review["original_entry_comparison"]["inspected_bar_count"] == 4
    assert review["original_entry_comparison"]["current_rolling_protection_price"] == "216.510"
    assert review["unadjusted_structural_observation"]["observed_review"] == "REDUCE_STRUCTURE_REVIEW"
    assert review["observed_review"] == "UNKNOWN"
    assert result["followup_fill_count"] == 0
