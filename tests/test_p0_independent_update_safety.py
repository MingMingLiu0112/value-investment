"""Independent pure classification and isolated recovery checks; no real Excel."""
from copy import deepcopy
import json

import pytest

from scripts.current import product_update_publication as adapter
from scripts.current import publish_product_workbench_to_canonical as protected
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.daily_product_update import semantic_digest
from value_investment_agent.presentation.daily_product_composition import classify_product_changes
from test_pending_review_response import signed  # noqa: F401 - shared pytest fixture


def _content():
    return {"layout_version": "v1", "companies": {
        "600519": {"quote": {"quote_date": "2026-10-09", "display_price": "100"},
                   "inputs": {"package_sha256": "a" * 64},
                   "event": {"announcements": []},
                   "decision": {"recommendation_type": "NO_ACTION", "counter_evidence": []}},
        "600887": {"quote": {"quote_date": "2026-10-09"}, "decision": {"blockers": ["pending"]}},
    }, "extensions": {"hotspot_report": {"generated_at": "old", "status": "OBSERVATION_ONLY"}}}


@pytest.mark.parametrize("section,value,category", [
    ("quote", {"quote_date": "2026-10-10", "display_price": "100"}, "QUOTE_CHANGE"),
    ("inputs", {"package_sha256": "b" * 64}, "RESEARCH_FACT_ASSUMPTION_OR_REVIEW_CHANGE"),
    ("event", {"announcements": [{"id": "new", "original_hashes": ["c" * 64]}]}, "OFFICIAL_EVENT_OBSERVATION_CHANGE"),
    ("decision", {"recommendation_type": "NO_ACTION", "counter_evidence": [{"text": "new countercase"}]}, "VALUATION_OR_DECISION_CHANGE"),
])
def test_each_actual_change_has_one_category_and_does_not_mutate(section, value, category):
    before = _content()
    after = deepcopy(before)
    after["companies"]["600519"][section] = value
    retained = deepcopy((before, after))
    assert classify_product_changes(before, after) == [category]
    assert (before, after) == retained
    assert after["companies"]["600887"] == before["companies"]["600887"]


def test_transport_only_extension_clock_is_not_economic_change():
    before = _content()
    after = deepcopy(before)
    after["extensions"]["hotspot_report"]["generated_at"] = "new"
    assert classify_product_changes(before, after) == []
    assert semantic_digest(before) == semantic_digest(after)
    after["extensions"]["hotspot_report"]["status"] = "DATA_UNAVAILABLE"
    assert classify_product_changes(before, after) == ["HOTSPOT_OBSERVATION_CHANGE"]


@pytest.fixture
def interrupted(tmp_path, monkeypatch, request):
    root = tmp_path
    folder = root / getattr(request, "param", "runtime/daily-trade-assistant/synthetic-interruption")
    folder.mkdir(parents=True)
    workbook = root / "canonical.xlsx"
    workbook.write_bytes(b"synthetic-before")
    before = sha256_file(workbook)
    prior = {"canonical_workbook_sha256": before, "synthetic_fixture": True}
    write_new_json(root / "config/current-trial-workbook.json", prior)
    write_new_json(folder / "previous-workbook-pointer.json", prior)
    backup = folder / "pre-publication-recovery.xlsx"
    backup.write_bytes(workbook.read_bytes())
    workbook.write_bytes(b"synthetic-candidate")
    intent = {"action": "no_order", "before_sha256": before,
              "candidate_sha256": sha256_file(workbook),
              "recovery_backup": {"path": backup.relative_to(root).as_posix(), "sha256": before}}
    write_new_json(folder / "publication-intent.json", intent)
    staging = root / ".tmp/staging"
    staging.mkdir(parents=True)
    calls = []

    def replace_exact(target, source, *, expected_source_sha256, staging_sha256, scratch_dir):
        assert target == workbook and scratch_dir == staging
        assert sha256_file(target) == expected_source_sha256
        assert sha256_file(source) == staging_sha256
        calls.append((expected_source_sha256, staging_sha256))
        target.write_bytes(source.read_bytes())
        source.unlink()

    monkeypatch.setattr(protected, "_project_staging_directory", lambda *a, **k: staging)
    monkeypatch.setattr(protected, "_replace_canonical_staging", replace_exact)
    return root, folder, workbook, backup, intent, prior, calls


def test_exact_unregistered_candidate_recovers_once_without_pointer_change(interrupted):
    root, folder, workbook, backup, intent, prior, calls = interrupted
    result = adapter.recover_interrupted_product_publications(root=root, workbook=workbook)
    assert result[0]["status"] == "ROLLED_BACK_INTERRUPTED_UNREGISTERED_PUBLICATION"
    assert workbook.read_bytes() == backup.read_bytes()
    assert json.loads((root / "config/current-trial-workbook.json").read_text()) == prior
    assert len(calls) == 1
    assert adapter.recover_interrupted_product_publications(root=root, workbook=workbook) == []
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["user_edit", "backup_drift", "pointer_conflict"])
def test_recovery_refuses_to_overwrite_conflicting_bytes(interrupted, fault):
    root, folder, workbook, backup, intent, prior, calls = interrupted
    if fault == "user_edit":
        workbook.write_bytes(b"synthetic-user-edit")
    elif fault == "backup_drift":
        backup.write_bytes(b"synthetic-backup-drift")
    else:
        path = root / "config/current-trial-workbook.json"
        value = {**prior, "canonical_workbook_sha256": "0" * 64}
        path.write_text(json.dumps(value), encoding="utf-8")
    retained = workbook.read_bytes()
    with pytest.raises(ValueError):
        adapter.recover_interrupted_product_publications(root=root, workbook=workbook)
    assert workbook.read_bytes() == retained and not calls
    assert not (folder / "publication-rollback.json").exists()


def test_verified_successor_is_never_rolled_back(interrupted, monkeypatch):
    root, folder, workbook, backup, intent, prior, calls = interrupted
    successor = {**prior, "canonical_workbook_sha256": sha256_file(workbook)}
    (root / "config/current-trial-workbook.json").write_text(json.dumps(successor), encoding="utf-8")
    verified = []
    monkeypatch.setattr(adapter, "verify_workbook_publication", lambda r, p: verified.append(p))
    retained = workbook.read_bytes()
    result = adapter.recover_interrupted_product_publications(root=root, workbook=workbook)
    assert result[0]["status"] == "SUCCESSOR_ALREADY_REGISTERED"
    assert verified == [successor] and not calls
    assert workbook.read_bytes() == retained


def test_recovery_before_hash_must_equal_prior_pointer(interrupted):
    root, folder, workbook, backup, intent, prior, calls = interrupted
    backup.write_bytes(b"synthetic-wrong-old-version")
    intent["before_sha256"] = sha256_file(backup)
    intent["recovery_backup"]["sha256"] = sha256_file(backup)
    (folder / "publication-intent.json").write_text(json.dumps(intent), encoding="utf-8")
    retained = workbook.read_bytes()
    with pytest.raises(ValueError):
        adapter.recover_interrupted_product_publications(root=root, workbook=workbook)
    assert workbook.read_bytes() == retained and not calls


@pytest.mark.parametrize("interrupted", ["runtime/custom-product-run"], indirect=True)
def test_authorized_runtime_output_directory_is_not_silently_skipped(interrupted):
    root, folder, workbook, backup, intent, prior, calls = interrupted
    result = adapter.recover_interrupted_product_publications(root=root, workbook=workbook)
    assert len(result) == 1
    assert result[0]["status"] == "ROLLED_BACK_INTERRUPTED_UNREGISTERED_PUBLICATION"
    assert workbook.read_bytes() == backup.read_bytes() and len(calls) == 1


def test_signed_candidate_fixture_uses_one_fixed_utc_calendar_day(signed):
    package = json.loads((signed["path"].parent / "package.json").read_text(encoding="utf-8"))
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    pit = package["point_in_time"]
    available = datetime.fromisoformat(pit["available_at"])
    computed = datetime.fromisoformat(pit["computed_at"])
    assert available == computed == datetime(2026, 10, 11, 4, tzinfo=timezone.utc)
    assert available.date().isoformat() == pit["research_as_of"]
    assert available.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() == pit["research_as_of"]


def test_daily_risk_report_binding_rejects_changed_bytes_and_private_path(tmp_path):
    from value_investment_agent.presentation.daily_product_composition import _load

    report = tmp_path / "runtime/dual-sleeve-risk.json"
    write_new_json(report, {"action": "no_order", "status": "BLOCKED_PRIVATE_INPUT"})
    binding = {"path": report.relative_to(tmp_path).as_posix(), "sha256": sha256_file(report)}
    assert _load(tmp_path, binding)["status"] == "BLOCKED_PRIVATE_INPUT"
    report.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        _load(tmp_path, binding)
    private = tmp_path / "private/risk.json"
    write_new_json(private, {"action": "no_order"})
    with pytest.raises(ValueError):
        _load(tmp_path, {"path": "private/risk.json", "sha256": sha256_file(private)})


def test_risk_source_changed_during_review_cannot_emit_report(tmp_path, monkeypatch):
    from value_investment_agent.application.product import dual_sleeve_risk as risk
    from test_dual_sleeve_risk import synthetic_input, GENERATED_AT

    source = tmp_path / ".tmp/input.json"
    output = tmp_path / ".tmp/report.json"
    write_new_json(source, synthetic_input())
    pin = sha256_file(source)
    original = risk.review_dual_sleeve_risk

    def mutate_source(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(risk, "review_dual_sleeve_risk", mutate_source)
    with pytest.raises(ValueError, match="changed during review"):
        risk.run_dual_sleeve_review(root=tmp_path, input_path=source,
            input_sha256=pin, output_path=output, synthetic=True, generated_at=GENERATED_AT)
    assert not output.exists()
