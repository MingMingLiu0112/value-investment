"""Synthetic explicit supplemental bindings; no real approval or research edits."""
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import runpy
import sys
from pathlib import Path

import pytest

from test_research_validity_review import _registered_fixture, _write, CUTOFF, TODAY
from value_investment_agent.application.product.incremental_validity import (
    BINDING_SCHEMA, BINDING_SCHEMA_V2, collect_registered_validity_scan, resolve_incremental_model_validity,
    load_incremental_scan_binding, register_incremental_validity_binding,
    incremental_scan_start,
)
from value_investment_agent.application.product.research_validity_review import review_registered_research_validity
from value_investment_agent.price_bridge import bridge_with_quote
from value_investment_agent.quote_snapshot import QuoteSnapshot, QUOTE_STATUS_VERIFIED_CLOSE
from value_investment_agent.valuation_models.base import ValuationResult


def _supplement(root):
    fixture = _registered_fixture(root)
    scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
    scan_ref = {"path": fixture["scan"].relative_to(root).as_posix(), "sha256": fixture["scan_sha256"]}
    observation_path = root / "runtime/events/observation.json"
    observation = {"schema_version": "daily-event-observation-v1", "symbol": "600887",
        "scan_binding": scan_ref, "scan_from": "2026-10-11", "scan_to": CUTOFF.isoformat(),
        "pagination_complete": True, "collection_status": "OFFICIAL_QUERY_ARCHIVED",
        "announcement_count": 0, "source_bindings": scan["evidence_refs"],
        "full_calendar_window_elapsed": True, "acquired_at": scan["retrieved_at"]}
    observation_sha = _write(observation_path, observation)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    binding = {"schema_version": BINDING_SCHEMA, "symbol": "600887", "action": "no_order",
        "package_ref": {"path": fixture["package"].relative_to(root).as_posix(),
                        "sha256": fixture["package_sha256"]},
        "research_as_of": "2026-10-11", "review_cutoff": CUTOFF.isoformat(),
        "model_id": package["model_validity_input"]["model_id"],
        "observation_ref": {"path": observation_path.relative_to(root).as_posix(), "sha256": observation_sha},
        "scan_ref": scan_ref}
    path = root / "runtime/events/incremental-binding.json"
    digest = _write(path, binding)
    return fixture, {"path": path.relative_to(root).as_posix(), "sha256": digest}, binding


def _resolve(root, ref):
    return resolve_incremental_model_validity(root=root, symbol="600887", binding_ref=ref,
        review_cutoff=CUTOFF, today=TODAY)


def test_explicit_supplement_reaches_shared_model_validity_and_real_price_bridge(tmp_path):
    fixture, ref, _ = _supplement(tmp_path)
    before = fixture["package"].read_bytes()
    validity = _resolve(tmp_path, ref)
    assert validity.status == "VALID"  # Synthetic pre-reviewed input only.
    valuation = ValuationResult(symbol="600887", model_type="TEST_ONLY", valuation_date=date(2026, 10, 11),
        bear_value=Decimal("20"), base_value=Decimal("30"), bull_value=Decimal("40"),
        confidence="低", assumptions={}, sensitivities=[], evidence_refs=[{"id": "TEST_ONLY-value"}],
        blockers=[], status="conditional_research_only", model_version=validity.model_id)
    quote = QuoteSnapshot(symbol="600887", quote_date=CUTOFF, current_price=Decimal("18"),
        status=QUOTE_STATUS_VERIFIED_CLOSE, evidence_refs=[{"id": "TEST_ONLY-quote", "sha256": "a" * 64}])
    bridge = bridge_with_quote(valuation, validity, quote)
    assert bridge.bridge_status == "READY"
    assert bridge.margin_to_base == Decimal("0.4")
    assert any(row["path"] == ref["path"] for row in bridge.evidence_refs if "path" in row)
    assert valuation.status == "conditional_research_only"
    assert fixture["package"].read_bytes() == before
    assert bridge_with_quote(valuation, validity, replace(quote, quote_date=date(2026, 10, 13))).bridge_status == "INVALID"
    assert bridge_with_quote(replace(valuation, model_version="wrong-model"), validity, quote).bridge_status == "INVALID"
    # Replaying evidence, not trusting a previously produced VALID label.
    (tmp_path / "runtime/events/index.json").write_text("tampered", encoding="utf-8")
    changed = _resolve(tmp_path, ref)
    assert changed.status == "UNKNOWN"
    assert bridge_with_quote(valuation, changed, quote).bridge_status != "READY"


def test_batch_uses_only_explicit_supplement_and_preserves_prior_blockers(tmp_path):
    fixture, ref, binding = _supplement(tmp_path)
    # A sidecar may supplement a package with no embedded scan reference.
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    package["model_validity_input"].pop("event_scan_ref")
    package["model_validity_input"]["blockers"] = ["TEST_ONLY_prior_review_missing"]
    sha = _write(fixture["package"], package)
    pointer = tmp_path / "config/current-quote-bridge.json"
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["quotes"]["600887"]["research_package_sha256"] = sha
    _write(pointer, payload)
    binding["package_ref"]["sha256"] = sha
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    args = dict(root=tmp_path, review_cutoff=CUTOFF, today=TODAY, symbols=["600887"])
    without = review_registered_research_validity(**args, output_path=tmp_path / "runtime/without.json")
    assert without["reviews"][0]["status"] == "PENDING"
    result = review_registered_research_validity(**args, output_path=tmp_path / "runtime/with.json",
        incremental_bindings=[ref])
    row = result["reviews"][0]
    assert row["status"] == "BLOCKED_ON_MODEL_VALIDITY"
    assert "TEST_ONLY_prior_review_missing" in row["review"]["model_validity_review"]["current"]["blockers"]
    assert row["incremental_binding_ref"] == ref
    assert row["formal_eligibility"] is False
    assert _resolve(tmp_path, ref).status == "UNKNOWN"


@pytest.mark.parametrize("failure", ["package", "model", "observation", "future", "window", "snapshot"])
def test_supplement_mismatch_cannot_be_consumed(tmp_path, failure):
    _, ref, binding = _supplement(tmp_path)
    if failure == "package":
        binding["package_ref"]["sha256"] = "0" * 64
    elif failure == "model":
        binding["model_id"] = "wrong-model"
    elif failure == "window":
        binding["review_cutoff"] = "2026-10-14"
    else:
        obs_ref = binding["observation_ref"]
        path = tmp_path / obs_ref["path"]
        observation = json.loads(path.read_text(encoding="utf-8"))
        if failure == "observation":
            observation["announcement_count"] = 99
        elif failure == "future":
            observation["acquired_at"] = "2099-01-01T00:00:00+00:00"
        else:
            observation["full_calendar_window_elapsed"] = False
        obs_ref["sha256"] = _write(path, observation)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve(tmp_path, ref)


def test_collector_reuses_existing_service_and_binds_immutable_package(tmp_path, monkeypatch):
    ref, binding, package_path, now = _v2_supplement(tmp_path, monkeypatch)
    from value_investment_agent.application.product import daily_event_observation
    output = tmp_path / "runtime/new-acquisition"
    seen = {}

    def acquire(**kwargs):
        seen.update(kwargs)
        output.mkdir()
        observation = json.loads((tmp_path / binding["observation_ref"]["path"]).read_text(encoding="utf-8"))
        _write(output / "observation.json", observation)
        return observation

    monkeypatch.setattr(daily_event_observation, "collect_daily_event_observation", acquire)
    result = collect_registered_validity_scan(root=tmp_path, symbol="600519", review_cutoff=date(2020, 1, 2),
                                             output_dir=output)
    assert seen["retain_raw_index"] is True
    assert seen["start"] == date(2020, 1, 1)
    assert seen["end"] == date(2020, 1, 2)
    bound = json.loads((tmp_path / result["binding_ref"]["path"]).read_text(encoding="utf-8"))
    assert bound["package_ref"] == binding["package_ref"]
    assert bound["schema_version"] == BINDING_SCHEMA_V2
    assert bound["research_as_of"] == "2020-01-02"
    assert bound["scan_from"] == bound["model_valid_from"] == bound["valuation_date"] == "2020-01-01"
    assert bound["g3_approval_granted"] is bound["materiality_approved"] is False
    repeated = collect_registered_validity_scan(root=tmp_path, symbol="600519", review_cutoff=date(2020, 1, 2),
                                                output_dir=output)
    assert repeated == result
    with pytest.raises(ValueError, match="31 days"):
        collect_registered_validity_scan(root=tmp_path, symbol="600519", review_cutoff=date(2020, 2, 2),
            output_dir=tmp_path / "runtime/not-created")


def test_collection_cli_registers_through_service(tmp_path, monkeypatch, capsys):
    _, ref, _ = _supplement(tmp_path)
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/current/collect_registered_validity_scan.py"))
    main = namespace["main"]
    main.__globals__["ROOT"] = tmp_path
    main.__globals__["collect_registered_validity_scan"] = lambda **kwargs: {"binding_ref": ref, "action": "no_order"}
    monkeypatch.setattr(sys, "argv", ["collect", "--symbol", "600887", "--review-cutoff", CUTOFF.isoformat(),
        "--output-dir", "runtime/TEST_ONLY", "--register"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["registration"]["binding_ref"] == ref
    pointer = json.loads((tmp_path / "config/current-quote-bridge.json").read_text(encoding="utf-8"))
    assert pointer["quotes"]["600887"]["incremental_validity_binding"] == ref


def _v2_supplement(root, monkeypatch, *, populated=False):
    from test_retained_event_coverage import archive
    observation = archive(root, monkeypatch, populated=populated)
    package_path = root / "runtime/package.json"
    package = {"symbol": "600519", "name": "TEST_ONLY", "point_in_time": {
        "research_as_of": "2020-01-02", "valuation_date": "2020-01-01",
        "available_at": "2020-01-02T00:00:00+00:00"},
        "model_validity_input": {"model_id": "TEST_ONLY", "valid_from": "2020-01-01",
            "events": [], "blockers": ["pending_complete_event_materiality_review"]}}
    package_ref = {"path": "runtime/package.json", "sha256": _write(package_path, package)}
    _write(root / "config/current-quote-bridge.json", {"schema_version": "current-quote-bridge-v1",
        "action": "no_order", "quotes": {"600519": {"research_package": package_ref["path"],
            "research_package_sha256": package_ref["sha256"]}}})
    binding = {"schema_version": BINDING_SCHEMA_V2, "symbol": "600519", "action": "no_order",
        "package_ref": package_ref, "research_as_of": "2020-01-02", "valuation_date": "2020-01-01",
        "model_valid_from": "2020-01-01", "scan_from": "2020-01-01", "review_cutoff": "2020-01-02",
        "model_id": "TEST_ONLY", "observation_ref": {"path": "runtime/events/observation.json",
            "sha256": _write(root / "runtime/events/observation.json", observation)},
        "scan_ref": observation["scan_binding"], "materiality_approved": False,
        "g3_approval_granted": False, "research_cutoff_changed": False,
        "coverage_mode": "FULL_ELAPSED_WINDOW" if observation["full_calendar_window_elapsed"] else "PARTIAL_INTRADAY_SNAPSHOT"}
    ref = {"path": "runtime/events/incremental-binding.json",
           "sha256": _write(root / "runtime/events/incremental-binding.json", binding)}
    return ref, binding, package_path, datetime.now(timezone.utc)


def _resolve_v2(root, ref, now):
    return resolve_incremental_model_validity(root=root, symbol="600519", binding_ref=ref,
        review_cutoff=date(2020, 1, 2), today=now)


@pytest.mark.parametrize("populated", [False, True])
def test_v2_raw_coverage_does_not_approve_materiality_and_registers_only_pending(tmp_path, monkeypatch, populated):
    ref, binding, package, now = _v2_supplement(tmp_path, monkeypatch, populated=populated)
    before = package.read_bytes()
    validity = _resolve_v2(tmp_path, ref, now)
    assert validity.status == "UNKNOWN"
    assert validity.model_as_of == validity.valid_from == date(2020, 1, 1)
    assert "pending_complete_event_materiality_review" in validity.blockers
    assert "event scan is pending human review" in validity.blockers
    result = register_incremental_validity_binding(tmp_path, "600519", ref, date(2020, 1, 2), now)
    pointer = tmp_path / "config/current-quote-bridge.json"
    pinned = pointer.read_bytes()
    assert result["model_validity_status"] == "UNKNOWN"
    assert result["g3_approval_granted"] is False and result["action"] == "no_order"
    assert register_incremental_validity_binding(tmp_path, "600519", ref, date(2020, 1, 2), now) == result
    assert package.read_bytes() == before and pointer.read_bytes() == pinned


@pytest.mark.parametrize("field,value", [("valuation_date", "2020-01-02"),
    ("model_valid_from", "2020-01-02"), ("scan_from", "2020-01-02"),
    ("research_as_of", "2020-01-01"), ("scan_from", None),
    ("scan_from", "20200101"), ("scan_from", "2099-01-01"),
    ("schema_version", "incremental-validity-binding-v3"), ("materiality_approved", True)])
def test_v2_resealed_binding_cannot_relabel_model_window(tmp_path, monkeypatch, field, value):
    ref, binding, _, now = _v2_supplement(tmp_path, monkeypatch)
    binding[field] = value
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve_v2(tmp_path, ref, now)


@pytest.mark.parametrize("failure", ["wrong_window", "missing_raw", "future_raw", "incomplete",
    "scan_start", "scan_end", "validity_start", "validity_end", "future_observation", "naive_observation"])
def test_v2_resealed_observation_cannot_fake_original_coverage(tmp_path, monkeypatch, failure):
    from test_retained_event_coverage import rebind, read
    ref, binding, _, now = _v2_supplement(tmp_path, monkeypatch)
    folder = tmp_path / "runtime/events"
    observation = read(folder / "observation.json")
    scan = read(folder / "event-scan.json")
    if failure == "wrong_window":
        index = read(folder / "cninfo-index.json")
        index["parameters"]["seDate"] = "2020-01-02~2020-01-02"
        _write(folder / "cninfo-index.json", index)
    elif failure == "missing_raw":
        (folder / "raw-index/response-0001.bin").unlink()
    elif failure == "future_raw":
        manifest = read(folder / "raw-index-manifest.json")
        manifest["responses"][0]["acquired_at"] = "2099-01-01T00:00:00+00:00"
        _write(folder / "raw-index-manifest.json", manifest)
    elif failure == "incomplete":
        observation["pagination_complete"] = False
    elif failure in {"future_observation", "naive_observation"}:
        observation["acquired_at"] = "2099-01-01T00:00:00+00:00" if failure == "future_observation" else "2020-01-03T00:00:00"
    else:
        key = {"scan_start": "scan_from", "scan_end": "scan_to", "validity_start": "validity_from",
               "validity_end": "validity_to"}[failure]
        scan[key] = "2020-01-02" if "start" in failure else "2020-01-03"
        _write(folder / "event-scan.json", scan)
    if failure != "missing_raw":
        rebind(tmp_path, observation)
    binding["scan_ref"] = observation["scan_binding"]
    binding["observation_ref"]["sha256"] = _write(folder / "observation.json", observation)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises((ValueError, OSError)):
        _resolve_v2(tmp_path, ref, now)


@pytest.mark.parametrize("failure", ["missing_date", "future_available", "naive_available", "late_available", "reversed", "long_window"])
def test_v2_model_window_rejects_missing_and_unavailable_package(tmp_path, monkeypatch, failure):
    ref, binding, package_path, now = _v2_supplement(tmp_path, monkeypatch)
    package = json.loads(package_path.read_bytes())
    if failure == "missing_date":
        package["point_in_time"].pop("valuation_date")
    elif failure in {"future_available", "naive_available", "late_available"}:
        package["point_in_time"]["available_at"] = {"future_available": "2099-01-01T00:00:00+00:00",
            "naive_available": "2020-01-02T00:00:00", "late_available": "2020-01-03T00:00:00+00:00"}[failure]
    else:
        start = "2020-01-03" if failure == "reversed" else "2019-11-01"
        package["point_in_time"]["valuation_date"] = start
        package["model_validity_input"]["valid_from"] = start
        binding.update(valuation_date=start, model_valid_from=start, scan_from=start)
    binding["package_ref"]["sha256"] = _write(package_path, package)
    pointer = json.loads((tmp_path / "config/current-quote-bridge.json").read_bytes())
    pointer["quotes"]["600519"]["research_package_sha256"] = binding["package_ref"]["sha256"]
    _write(tmp_path / "config/current-quote-bridge.json", pointer)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve_v2(tmp_path, ref, now)


def test_v1_different_basis_stays_incomplete_and_cannot_be_reused_as_full_model_scan(tmp_path):
    fixture, ref, binding = _supplement(tmp_path)
    package = json.loads(fixture["package"].read_bytes())
    package["point_in_time"]["valuation_date"] = "2026-10-10"
    package["model_validity_input"]["valid_from"] = "2026-10-10"
    package_sha = _write(fixture["package"], package)
    pointer_path = tmp_path / "config/current-quote-bridge.json"
    pointer = json.loads(pointer_path.read_bytes())
    pointer["quotes"]["600887"]["research_package_sha256"] = package_sha
    _write(pointer_path, pointer)
    binding["package_ref"]["sha256"] = package_sha
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    before = (tmp_path / ref["path"]).read_bytes()
    assert incremental_scan_start(binding) == date(2026, 10, 11)
    validity = _resolve(tmp_path, ref)
    assert validity.status == "UNKNOWN"
    assert "event scan validity window starts on a different date" in validity.blockers
    with pytest.raises(ValueError, match="cannot reuse"):
        collect_registered_validity_scan(root=tmp_path, symbol="600887", review_cutoff=CUTOFF,
            output_dir=tmp_path / "runtime/events")
    assert (tmp_path / ref["path"]).read_bytes() == before


@pytest.mark.parametrize("failure", ["bytes", "future", "naive", "after_research", "retrieved_before_available"])
def test_v2_resealed_package_cannot_hide_invalid_source_provenance(tmp_path, monkeypatch, failure):
    ref, binding, package_path, now = _v2_supplement(tmp_path, monkeypatch)
    source_path = tmp_path / "runtime/source.json"
    source = {"id": "TEST_ONLY-facts", "local_path": "runtime/source.json",
        "sha256": _write(source_path, {"TEST_ONLY": True}),
        "source_available_at": "2020-01-01T00:00:00+00:00",
        "retrieved_at": "2020-01-01T00:00:00+00:00"}
    if failure == "bytes":
        source_path.write_text("changed", encoding="utf-8")
    elif failure == "retrieved_before_available":
        source["retrieved_at"] = "2019-12-31T00:00:00+00:00"
    else:
        source["source_available_at"] = {"future": "2099-01-01T00:00:00+00:00",
            "naive": "2020-01-01T00:00:00", "after_research": "2020-01-03T00:00:00+00:00"}[failure]
    package = json.loads(package_path.read_bytes())
    package["sources"] = [source]
    binding["package_ref"]["sha256"] = _write(package_path, package)
    pointer_path = tmp_path / "config/current-quote-bridge.json"
    pointer = json.loads(pointer_path.read_bytes())
    pointer["quotes"]["600519"]["research_package_sha256"] = binding["package_ref"]["sha256"]
    _write(pointer_path, pointer)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve_v2(tmp_path, ref, now)


def test_v2_registered_original_pending_context_is_never_erased(tmp_path, monkeypatch):
    ref, binding, package_path, now = _v2_supplement(tmp_path, monkeypatch)
    scan_path = tmp_path / binding["scan_ref"]["path"]
    original_scan = json.loads(scan_path.read_bytes())
    original_ref = {"path": "runtime/prior-scan.json",
                    "sha256": _write(tmp_path / "runtime/prior-scan.json", original_scan)}
    package = json.loads(package_path.read_bytes())
    package["model_validity_input"].update(blockers=[], event_scan_ref=original_ref)
    binding["package_ref"]["sha256"] = _write(package_path, package)
    pointer_path = tmp_path / "config/current-quote-bridge.json"
    pointer = json.loads(pointer_path.read_bytes())
    pointer["quotes"]["600519"]["research_package_sha256"] = binding["package_ref"]["sha256"]
    _write(pointer_path, pointer)
    # Explicitly synthetic completed later scan; raw coverage is unchanged.
    original_scan.update(status="COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW", blockers=[])
    binding["scan_ref"]["sha256"] = _write(scan_path, original_scan)
    observation_path = tmp_path / binding["observation_ref"]["path"]
    observation = json.loads(observation_path.read_bytes())
    observation["scan_binding"] = binding["scan_ref"]
    binding["observation_ref"]["sha256"] = _write(observation_path, observation)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    validity = _resolve_v2(tmp_path, ref, now)
    assert validity.status == "UNKNOWN"
    assert "ORIGINAL_EVENT_REVIEW_UNRESOLVED" in validity.blockers


def test_versioned_start_has_no_v2_fallback():
    assert incremental_scan_start({"schema_version": BINDING_SCHEMA,
        "research_as_of": "2020-01-02"}) == date(2020, 1, 2)
    for payload in ({"model_valid_from": "2020-01-01"}, {"scan_from": "2020-01-01"},
                    {"scan_from": "2020-01-01", "model_valid_from": "2020-01-02"}):
        with pytest.raises(ValueError):
            incremental_scan_start({"schema_version": BINDING_SCHEMA_V2,
                "research_as_of": "2020-01-02", **payload})


def _partial_v2(root, monkeypatch):
    import test_retained_event_coverage as retained
    from value_investment_agent.application.product import daily_event_observation
    clock = datetime(2020, 1, 2, 10, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz) if tz else clock.replace(tzinfo=None)

    monkeypatch.setattr(retained, "datetime", Clock)
    monkeypatch.setattr(daily_event_observation, "datetime", Clock)
    return _v2_supplement(root, monkeypatch)


def test_v2_same_day_snapshot_is_archivable_and_registers_only_unknown(tmp_path, monkeypatch):
    from value_investment_agent.application.product import daily_event_observation
    ref, binding, package, now = _partial_v2(tmp_path, monkeypatch)
    assert binding["coverage_mode"] == "PARTIAL_INTRADAY_SNAPSHOT"
    assert binding["research_as_of"] != binding["model_valid_from"]
    validity = _resolve_v2(tmp_path, ref, now)
    assert validity.status == "UNKNOWN"
    assert "INTRADAY_SNAPSHOT_NOT_FULL_WINDOW" in validity.blockers
    result = register_incremental_validity_binding(tmp_path, "600519", ref, date(2020, 1, 2), now)
    assert result["model_validity_status"] == "UNKNOWN" and result["g3_approval_granted"] is False
    # Reuse stays explicit partial V2, never silently falls back to V1.
    result = collect_registered_validity_scan(root=tmp_path, symbol="600519", review_cutoff=date(2020, 1, 2),
        output_dir=tmp_path / "runtime/events")
    assert result["binding_ref"] == ref
    assert json.loads((tmp_path / ref["path"]).read_bytes())["schema_version"] == BINDING_SCHEMA_V2
    output = tmp_path / "runtime/new-partial"
    observation = json.loads((tmp_path / binding["observation_ref"]["path"]).read_bytes())

    def acquire(**kwargs):
        assert kwargs["start"] == date(2020, 1, 1)
        output.mkdir()
        _write(output / "observation.json", observation)
        return observation

    monkeypatch.setattr(daily_event_observation, "collect_daily_event_observation", acquire)
    collected = collect_registered_validity_scan(root=tmp_path, symbol="600519", review_cutoff=date(2020, 1, 2),
        output_dir=output)
    new_binding = json.loads((tmp_path / collected["binding_ref"]["path"]).read_bytes())
    assert new_binding["coverage_mode"] == "PARTIAL_INTRADAY_SNAPSHOT"
    assert _resolve_v2(tmp_path, collected["binding_ref"], now).status == "UNKNOWN"


@pytest.mark.parametrize("failure", ["promote_full", "missing_mode", "elapsed", "reviewed", "future_raw", "wrong_request"])
def test_partial_snapshot_cannot_be_resealed_as_full_or_reviewed(tmp_path, monkeypatch, failure):
    from test_retained_event_coverage import read, rebind
    ref, binding, _, now = _partial_v2(tmp_path, monkeypatch)
    folder = tmp_path / "runtime/events"
    observation = read(folder / "observation.json")
    if failure == "promote_full":
        binding["coverage_mode"] = "FULL_ELAPSED_WINDOW"
    elif failure == "missing_mode":
        binding.pop("coverage_mode")
    elif failure == "elapsed":
        observation["full_calendar_window_elapsed"] = True
    elif failure == "reviewed":
        scan = read(folder / "event-scan.json")
        scan.update(status="COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW", blockers=[])
        _write(folder / "event-scan.json", scan)
    elif failure == "future_raw":
        manifest = read(folder / "raw-index-manifest.json")
        manifest["responses"][0]["acquired_at"] = "2099-01-01T00:00:00+00:00"
        _write(folder / "raw-index-manifest.json", manifest)
    else:
        index = read(folder / "cninfo-index.json")
        index["parameters"]["seDate"] = "2020-01-02~2020-01-02"
        _write(folder / "cninfo-index.json", index)
    rebind(tmp_path, observation)
    binding["scan_ref"] = observation["scan_binding"]
    binding["observation_ref"]["sha256"] = _write(folder / "observation.json", observation)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve_v2(tmp_path, ref, now)
