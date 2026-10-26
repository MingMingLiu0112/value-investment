"""TEST_ONLY fixtures exercise the native loader, lifecycle and isolated journal."""
from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_hotspot_lifecycle_bound_history import (
    _history, _binding, ENTRY_AT, CURRENT_AT,
)
from value_investment_agent.application.hotspot.simulated_lifecycle import (
    load_simulated_hotspot_lifecycle, run_simulated_hotspot_lifecycle, _digest,
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
    assert result["market_source_scope"] == "MIXED_OR_UNVERIFIED_SOURCES"
    assert result["market_evidence_scopes"][-1]["scope"] == "UNVERIFIED"


def _declare_bundle_scope(root, case, namespace):
    path = root / case["case_path"]
    payload = json.loads(path.read_bytes())
    quote = payload["current_reference_close"]
    bundle_path = root / quote["bundle_path"]
    bundle = json.loads(bundle_path.read_bytes())
    for key in ("test_only", "fixture_scope", "namespace"):
        bundle.pop(key, None)
    if namespace:
        bundle["namespace"] = namespace
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    quote["bundle_sha256"] = sha256(bundle_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    case["case_sha256"] = sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("namespace", ["TEST_ONLY", "SIMULATED"])
def test_declared_namespaces_are_not_public_source_attestations(tmp_path, namespace):
    root, entry, _, current = _history(tmp_path)
    for case in (entry, current):
        _declare_bundle_scope(root, case, namespace)
    result = _run(root, entry, current)
    assert result["market_source_scope"] == namespace


def test_unmarked_entry_and_test_followup_are_not_classified_as_public(tmp_path):
    root, entry, _, current = _history(tmp_path)
    _declare_bundle_scope(root, entry, None)
    result = _run(root, entry, current)
    assert result["market_source_scope"] == "MIXED_OR_UNVERIFIED_SOURCES"
    assert [row["scope"] for row in result["market_evidence_scopes"]] == ["ORIGIN_NOT_ATTESTED", "TEST_ONLY"]


def test_invalid_official_binding_never_claims_reverification_success(tmp_path):
    root, entry, _, current = _history(tmp_path)
    result = _run(root, entry, current,
        official_event_observation_binding=dict(path="runtime/missing-official.json", sha256="a" * 64))
    assert result["assumptions"]["event_coverage"] == "SEE_PER_CUTOFF_NATIVE_REVIEWS"
    assert {row["official_publication_coverage"] for row in result["official_event_reviews"]} == {
        "INVALID_OR_UNAVAILABLE"}
    assert {row["corporate_action_coverage"] for row in result["official_event_reviews"]} == {"UNKNOWN"}
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


def _seal(root):
    root, entry, _, current = _history(root)
    report = _run(root, entry, current)
    folder = (root / report["journal_receipt"]["path"]).parent
    result_path = folder / "lifecycle-simulation.json"
    result_path.write_text(json.dumps(report), encoding="utf-8")
    sources = {}
    for case in (entry, current):
        path = case["case_path"]
        sources[path] = sha256((root / path).read_bytes()).hexdigest()
        quote = case["current_reference_close"]
        for binding in (*case["source_bindings"].values(),
                dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])):
            sources[binding["path"]] = binding["sha256"]
    receipt = dict(namespace="SIMULATED", action="no_order", strategy_validation="NOT_PROVEN",
        generated_at=datetime.now().astimezone().isoformat(), source_root="NEVER_FOLLOW_THIS_METADATA",
        source_bindings=[dict(path=path, sha256=digest) for path, digest in sources.items()],
        actual_owned_entries=0, actual_accounts_used=0, real_shadow_credit=0, followup_fill_count=0,
        historical_pit_proven=False, independent_oos_proven=False,
        outputs={"lifecycle-simulation.json": sha256(result_path.read_bytes()).hexdigest(),
            "SIMULATED-journal.jsonl": report["journal_receipt"]["sha256"]})
    path = folder / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def _reseal_report(root, binding, mutate):
    receipt_path = root / binding["path"]
    receipt = json.loads(receipt_path.read_bytes())
    result_path = receipt_path.parent / "lifecycle-simulation.json"
    report = json.loads(result_path.read_bytes())
    mutate(report)
    result_path.write_text(json.dumps(report), encoding="utf-8")
    receipt["outputs"]["lifecycle-simulation.json"] = sha256(result_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return dict(path=binding["path"], sha256=sha256(receipt_path.read_bytes()).hexdigest())


def test_reader_recomputes_native_results_and_is_strictly_read_only(tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal
    binding = _seal(tmp_path)
    folder = (tmp_path / binding["path"]).parent
    (folder / "SIMULATED-journal.jsonl.lock").unlink()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Reader must not transact, create or reread journal through service")

    for name in ("read", "append", "transaction"):
        monkeypatch.setattr(PrivateJournal, name, forbidden)
    result = load_simulated_hotspot_lifecycle(tmp_path, binding, datetime.now().astimezone())
    assert result["verified"] is True and result["historical_only"] is True
    assert result["source_file_count"] == 8
    assert result["current_signal"] is result["current_pit"] is False
    assert result["formal_eligibility"] is result["trade_eligible"] is False
    assert result["report"]["market_source_scope"] == "TEST_ONLY"
    assert result["report"]["official_event_reviews"][0]["official_publication_coverage"] == "MISSING"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("field", ["protection", "native_review", "source_scope", "cash", "permission",
    "missing_permission", "currentized", "extra_current_signal", "assumption_claim", "unadmitted_official",
    "future_cutoff", "final_case_at_entry"])
def test_reader_rejects_resealed_semantic_tampering(tmp_path, field):
    binding = _seal(tmp_path)

    def mutate(report):
        if field == "protection":
            report["entry_reference"]["original_protection_price"] = "1"
            report["entry_freeze_sha256"] = _digest(report["entry_reference"])
        elif field == "native_review":
            report["steps"][0]["lifecycle_review"]["observed_review"] = "ADD_STRUCTURE_REVIEW"
        elif field == "source_scope":
            report["market_source_scope"] = "ORIGIN_NOT_ATTESTED"
        elif field == "cash":
            report["simulated_accounting"]["cash_cny"] = "1000000"
        elif field == "permission":
            report["formal_eligibility"] = True
        elif field == "missing_permission":
            del report["broker_execution_permission"]
        elif field == "currentized":
            report["scope"] = "CURRENT_LIVE_SIGNAL"
        elif field == "extra_current_signal":
            report["current_signal"] = True
        elif field == "assumption_claim":
            report["assumptions"]["event_coverage"] = "OFFICIAL_EVENT_VERIFIED"
        elif field == "unadmitted_official":
            report["official_event_reviews"][0]["supplied_binding"] = dict(
                path="config/DO_NOT_READ.json", sha256="a" * 64)
        elif field == "future_cutoff":
            report["steps"][0]["lifecycle_review"]["evaluated_at"] = "2099-01-01T12:00:00+08:00"
        else:
            report["entry_reference"]["entry_case_binding"] = report["steps"][0]["lifecycle_review"]["current_case_binding"]
            report["entry_freeze_sha256"] = _digest(report["entry_reference"])

    changed = _reseal_report(tmp_path, binding, mutate)
    with pytest.raises(ValueError):
        load_simulated_hotspot_lifecycle(tmp_path, changed, datetime.now().astimezone())


@pytest.mark.parametrize("target", ["receipt", "source", "journal", "outside_runtime"])
def test_reader_rejects_bad_bytes_and_paths_without_using_source_root(tmp_path, target):
    binding = _seal(tmp_path)
    receipt_path = tmp_path / binding["path"]
    receipt = json.loads(receipt_path.read_bytes())
    if target == "receipt":
        binding["sha256"] = "a" * 64
    elif target == "source":
        (tmp_path / receipt["source_bindings"][0]["path"]).write_bytes(b"TEST_ONLY tamper")
    elif target == "journal":
        (receipt_path.parent / "SIMULATED-journal.jsonl").write_bytes(b"TEST_ONLY tamper")
    else:
        binding["path"] = "config/receipt.json"
    with pytest.raises(ValueError):
        load_simulated_hotspot_lifecycle(tmp_path, binding, datetime.now().astimezone())


def test_reader_rejects_runtime_junction_to_non_runtime_inside_root(tmp_path):
    binding = _seal(tmp_path)
    folder = (tmp_path / binding["path"]).parent
    target = tmp_path / "config/relocated-simulation"
    target.parent.mkdir()
    assert folder.resolve().is_relative_to(tmp_path.resolve())
    assert target.resolve().is_relative_to(tmp_path.resolve())
    folder.rename(target)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(folder))
    else:
        folder.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes runtime"):
        load_simulated_hotspot_lifecycle(tmp_path, binding, datetime.now().astimezone())


@pytest.mark.parametrize("change", ["backdated", "reversed", "future"])
def test_reader_rejects_rehashed_journal_time_forgery(tmp_path, change):
    from value_investment_agent.application.portfolio.private_portfolio_service import canonical_bytes
    binding = _seal(tmp_path)
    receipt_path = tmp_path / binding["path"]
    receipt = json.loads(receipt_path.read_bytes())
    journal_path = receipt_path.parent / "SIMULATED-journal.jsonl"
    records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    times = [row["recorded_at"] for row in records]
    if change == "backdated":
        times = [ENTRY_AT.isoformat()] * 3
    elif change == "reversed":
        times.reverse()
    else:
        times[-1] = "2099-01-01T12:00:00+08:00"
    previous = None
    for index, row in enumerate(records):
        row["recorded_at"] = times[index]
        row["previous_record_sha256"] = previous
        if index == 2:
            row["body"]["prepared_record_sha256"] = previous
        payload = {key: value for key, value in row.items() if key != "record_sha256"}
        row["record_sha256"] = sha256(canonical_bytes(payload)).hexdigest()
        previous = row["record_sha256"]
    journal_path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    digest = sha256(journal_path.read_bytes()).hexdigest()
    receipt["outputs"]["SIMULATED-journal.jsonl"] = digest
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    changed = _reseal_report(tmp_path, binding,
        lambda report: report["journal_receipt"].update(sha256=digest))
    with pytest.raises(ValueError):
        load_simulated_hotspot_lifecycle(tmp_path, changed, datetime.now().astimezone())


@pytest.mark.skipif(not os.environ.get("HOTSPOT_SIMULATED_SEAL_ROOT") or
    not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Optional existing sealed consumer pack")
def test_reader_consumes_existing_sealed_300750_without_new_journal(tmp_path):
    sealed_root = Path(os.environ["HOTSPOT_SIMULATED_SEAL_ROOT"])
    source_root = Path(os.environ["HOTSPOT_RETAINED_ROOT"])
    folder = Path("runtime/swing-simulated-lifecycle/74bb1ed2e7944ea08d484464293409a6")
    receipt_path = folder / "receipt.json"
    raw = (sealed_root / receipt_path).read_bytes()
    assert sha256(raw).hexdigest() == "677f5ae729ae9962b01caa3c00949f683838a98f197fc04b029649c4cc2d195a"
    receipt = json.loads(raw)
    for relative in (receipt_path, folder / "lifecycle-simulation.json", folder / "SIMULATED-journal.jsonl"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((sealed_root / relative).read_bytes())
    for binding in receipt["source_bindings"]:
        target = tmp_path / binding["path"]
        source = source_root / binding["path"]
        assert sha256(source.read_bytes()).hexdigest() == binding["sha256"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = load_simulated_hotspot_lifecycle(tmp_path,
        dict(path=receipt_path.as_posix(), sha256=sha256(raw).hexdigest()), datetime.now().astimezone())
    assert result["verified"] is True and result["current_signal"] is False
    assert result["source_file_count"] == 8
    assert result["report"]["market_source_scope"] == "ORIGIN_NOT_ATTESTED"
    assert result["report"]["entry_reference"]["original_protection_price"] == "218.450"
    review = result["report"]["steps"][0]["lifecycle_review"]
    assert review["observed_review"] == "UNKNOWN"
    assert result["report"]["followup_fill_count"] == 0
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


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
    assert result["market_source_scope"] == "ORIGIN_NOT_ATTESTED"
    review = result["steps"][0]["lifecycle_review"]
    assert review["original_entry_comparison"]["coverage"] == "COMPLETE"
    assert review["original_entry_comparison"]["inspected_bar_count"] == 4
    assert review["original_entry_comparison"]["current_rolling_protection_price"] == "216.510"
    assert review["unadjusted_structural_observation"]["observed_review"] == "REDUCE_STRUCTURE_REVIEW"
    assert review["observed_review"] == "UNKNOWN"
    assert result["followup_fill_count"] == 0
