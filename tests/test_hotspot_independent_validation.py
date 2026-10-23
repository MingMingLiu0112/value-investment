"""Independent review computes evidence limits, not a second admission policy."""
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot import independent_validation as subject
from value_investment_agent.application.hotspot.strategy_execution_replay import fingerprint

NOW = datetime(2026, 10, 23, 5, tzinfo=timezone.utc)


def _fixed_oct22_selection(root):
    """Retained historical inputs; never follow a later mutable current pointer."""
    watch = dict(path="runtime/hotspot-daily-selection/e9916940bfbd4f91bb05d0cecaf94363/report.json",
        sha256="c13be62b28412322ff4f5cc8e1e0968e26283df5c820e40e5ff5b0a62c351f73")
    originals = [
        ("600036-2026-10-22-8342287a809d44c69b8b32c964271f20", "91f115b86fa4f1efc9a3b6e78e9cc3b2dd5239c7f8d8a05763f7482bc83135fb"),
        ("601857-2026-10-22-fec18fe436fb48f4bdd05938e9f1c218", "cd36c137aeecda6879c21eb2a749cbb5f2751a2eb1ec2410593ac30e31ac269d"),
        ("003006-2026-10-22-f685210b247c4e579ecf31df36db376b", "32f5fed0561ab08f9fb142f7cd67709d1444f13c76a5ea1d5a6496c4d7a2909b"),
        ("601318-2026-10-22-d9b6599481424551a97a406e1d7dd931", "c6a9448ddd12da72f290f33d12e01e153496b23aef20d2ac56363a7f28dc46a7"),
        ("600176-2026-10-22-3e6a71dba43c4edda5d59d6b7b4c5bdf", "a7f7aa54d9c4199a9e7a4e9bfc7073d2d2d528da1bd18927a392e81e1f8e7bf0"),
        ("600019-2026-10-22-838d779909884a518cd6e4acfeda9f3c", "7aef643c44bcbf353205befb2cae0fcd87d667716337361539ce4cebfd36e4a2"),
        ("300750-2026-10-22-33fb0e21b19e42c298afea658cf277fe", "7403915e9a25adab62fadfc881c14d6ec24efa552aec7a3d66a3cc542d40d5fd"),
        ("002594-2026-10-22-aabe0beb73ce4d1f8ee9029278d4a9ea", "63e0314cefbaa3e776d80cba949f70211a127c1626b7e6018e01345798f56ff9"),
        ("002353-2026-10-22-0a012f12eaf44f1cb616ef11afcf9d43", "48da4ad206805955ddf63e6bad8088559c1b1186192c7a7dfd8be58b88f15d1f"),
        ("000333-2026-10-22-78fd9640ce1c4de5a1352f4bb2516a76", "484fb973edf75547f0ba42cb7c030f4718fad452e913aaafa97da299dc3e7874"),
    ]
    cases = {name[:6]: dict(path=f"runtime/hotspot-current-price-cases/{name}/case.json", sha256=digest)
             for name, digest in originals}
    if any(not (root / row["path"]).is_file() for row in [watch, *cases.values()]):
        pytest.skip("Fixed historical Oct22 raw evidence unavailable")
    return watch, cases


def execution():
    return dict(summary=dict(strict_closed_trade_count=0),
        symbols=["600519"],
        protocol=dict(registered_before_validation=False),
        decision_availability=dict(intention_count=2, source_acquired_after_decision=2),
        strict_rejection_counts=dict(MISSING_DATED_STOCK_STATUS=2),
        cost_fingerprint="a" * 64, costed_partitions=[])


def dependencies(monkeypatch):
    monkeypatch.setattr(subject, "_current_scope", lambda root, now: dict(symbols=["600519"], data_status="STALE"))
    monkeypatch.setattr(subject, "_historical_structure", lambda root, now, current: dict(matches_current_scope=False))
    monkeypatch.setattr(subject, "_execution_evidence", lambda root, now: execution())


def test_report_does_not_conflate_integrity_currentness_or_admission(tmp_path, monkeypatch):
    dependencies(monkeypatch)
    report = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    checks = {c["check"]: c for c in report["checks"]}
    assert checks["CURRENT_SOURCE_REPLAY"]["status"] == "PASS"
    assert report["current_scope"]["data_status"] == "STALE"
    assert checks["OLD_STRUCTURE_APPLICABILITY"]["status"] == "FAIL"
    assert checks["HISTORICAL_SOURCE_PIT"]["status"] == "FAIL"
    assert checks["PREDECLARED_UNTOUCHED_OOS"]["status"] == "FAIL"
    assert checks["STRICT_TRADABILITY_EXECUTION"]["status"] == "INSUFFICIENT_DATA"
    assert report["sample_comparison"]["overlapping_symbols"] == ["600519"]
    assert report["sample_comparison"]["applies_to_current_strategy"] is False
    assert report["elapsed_real_shadow_sessions"] is None
    assert report["session_credit_from_this_report"] == 0
    assert report["signed_gate_assessment"] is report["formal_eligibility"] is report["trade_eligible"] is False
    assert report["action"] == "no_order"
    content = dict(report)
    assert content.pop("content_sha256") == fingerprint(content)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("lane", ["_current_scope", "_historical_structure", "_execution_evidence"])
@pytest.mark.parametrize("error", [ValueError, FileNotFoundError])
def test_bad_dependency_fails_affected_checks_without_masking_other_evidence(tmp_path, monkeypatch, lane, error):
    dependencies(monkeypatch)

    def rejected(*args):
        raise error("private path must not leak")

    monkeypatch.setattr(subject, lane, rejected)
    report = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    checks = {c["check"]: c["status"] for c in report["checks"]}
    assert "private path" not in json.dumps(report)
    if lane == "_execution_evidence":
        assert checks["RETAINED_EXECUTION_REPLAY"] == "FAIL"
        assert checks["COST_ARITHMETIC_AND_SENSITIVITY"] == "NOT_ASSESSED"
        assert checks["CURRENT_SOURCE_REPLAY"] == "PASS"
    else:
        assert checks["COST_ARITHMETIC_AND_SENSITIVITY"] == "PASS"
    assert report["trade_eligible"] is False


def test_registration_and_no_late_acquisition_still_cannot_prove_pit_or_unbiased_oos(tmp_path, monkeypatch):
    dependencies(monkeypatch)
    data = execution()
    data["protocol"]["registered_before_validation"] = True
    data["decision_availability"]["source_acquired_after_decision"] = 0
    monkeypatch.setattr(subject, "_execution_evidence", lambda root, now: data)
    report = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    checks = {c["check"]: c["status"] for c in report["checks"]}
    assert checks["HISTORICAL_SOURCE_PIT"] == checks["PREDECLARED_UNTOUCHED_OOS"] == "INSUFFICIENT_DATA"


def bind(root, name, value):
    raw = json.dumps(value).encode()
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return dict(path=name, sha256=sha256(raw).hexdigest())


def historical_fixture(root):
    watch = dict(path="runtime/selection/report.json", sha256="b" * 64)
    validation = dict(action="no_order", evaluated_at=NOW.isoformat(),
        selection_trade_date="2026-10-22", rule_version="activity", replayed_rule_version="activity",
        structure_rule_version="structure")
    output = bind(root, "artifacts/validation.json", validation)
    manifest = bind(root, "artifacts/manifest.json", dict(action="no_order",
        outputs={"validation.json": output}, source_files={"selection_report": watch}))
    pointer = dict(schema_version="current-hotspot-structure-validation-v1", action="no_order",
        manifest_path=manifest["path"], manifest_sha256=manifest["sha256"])
    bind(root, subject.STRUCTURE_POINTER, pointer)
    current = dict(trade_date="2026-10-22", watch_binding=watch,
                   activity_rule_version="activity", structure_rule_version="structure")
    return current, output, validation, pointer


@pytest.mark.parametrize("change", ["date", "binding", "rule", "missing_structure"])
def test_old_verified_flag_does_not_replace_exact_scope_binding(tmp_path, change):
    current, output, validation, pointer = historical_fixture(tmp_path)
    assert subject._historical_structure(tmp_path, NOW, current)["matches_current_scope"] is True
    if change == "date":
        current["trade_date"] = "2026-10-23"
    elif change == "binding":
        current["watch_binding"] = dict(path="runtime/new/report.json", sha256="c" * 64)
    elif change == "rule":
        current["structure_rule_version"] = "new structure"
    else:
        current["structure_rule_version"] = None
    assert subject._historical_structure(tmp_path, NOW, current)["matches_current_scope"] is False


def test_tampered_and_future_old_report_rejected(tmp_path):
    current, output, validation, pointer = historical_fixture(tmp_path)
    (tmp_path / output["path"]).write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        subject._historical_structure(tmp_path, NOW, current)
    historical_fixture(tmp_path)
    with pytest.raises(ValueError, match="unavailable"):
        subject._historical_structure(tmp_path, datetime(2026, 10, 22, tzinfo=timezone.utc), current)


def test_unaware_cutoff_rejected_before_io(tmp_path):
    with pytest.raises(ValueError, match="Timezone-aware"):
        subject.validate_current_hotspot_strategy(root=tmp_path, now=datetime(2026, 10, 23))


def numeric_fixture(root):
    spec = dict(registered_at="2026-10-20T00:00:00+08:00", selection_scope="RETROSPECTIVE",
        rule_version="frozen", start_date="2026-04-13", development_end="2026-06-30",
        validation_start="2026-07-01", end_date="2026-10-15")
    protocol = bind(root / "archive/sources", "protocol.json", spec)
    manifest = bind(root, "archive/manifest.json", dict(historical_protocol_binding=protocol))
    fold = dict(fold="validation", fills=[dict(fee_components=dict(commission="5.00"))],
        total_fees_cny="5.00", same_fills_gross_return="0.01", net_return="0.00995",
        maximum_drawdown="0.02", total_slippage_cny="1.00", trade_count=1,
        right_censored_positions=0, rejection_counts={})
    return dict(manifest_binding=manifest, action="no_order", summary={},
        results=[dict(symbol="600519", case_binding=dict(case_path="case.json", case_sha256="a" * 64),
            source_available_at="2026-10-20T00:00:00+08:00",
            strict=dict(folds=[dict(rejection_counts=dict(MISSING_DATED_STOCK_STATUS=1),
                generated_intentions=[dict(decision_at="2026-07-01T15:00:00+08:00")])]),
            scenarios=[dict(cost_multiplier="1", folds=[fold])])],
        source_bindings=[], implementation_bindings=[], content_sha256="d" * 64,
        parameters={}, parameter_fingerprint="e" * 64, costs={}, cost_fingerprint="f" * 64)


@pytest.mark.parametrize("change", ["none", "fee", "gross", "future_source"])
def test_numeric_dependency_checks_are_computed_not_copied_flags(tmp_path, monkeypatch, change):
    replay = numeric_fixture(tmp_path)
    fold = replay["results"][0]["scenarios"][0]["folds"][0]
    if change == "fee":
        fold["total_fees_cny"] = "4"
    elif change == "gross":
        fold["net_return"] = "0.5"
    elif change == "future_source":
        replay["results"][0]["source_available_at"] = "2026-10-24T00:00:00+08:00"
    monkeypatch.setattr(subject, "build_strategy_execution_replay", lambda **kwargs: replay)
    if change != "none":
        with pytest.raises(ValueError):
            subject._execution_evidence(tmp_path, NOW)
    else:
        result = subject._execution_evidence(tmp_path, NOW)
        assert result["decision_availability"]["source_acquired_after_decision"] == 1
        assert result["protocol"]["registered_before_validation"] is False
        assert result["costed_partitions"][0]["total_fees_cny"] == "5.00"
        assert result["sample_bindings"][0]["dated_stock_state_binding"] is None


@pytest.mark.skipif(not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Explicit read-only real source root required")
def test_real_source_replay_refutes_current_independent_oos_without_mutation(monkeypatch):
    root = Path(os.environ["HOTSPOT_RETAINED_ROOT"])
    watch, cases = _fixed_oct22_selection(root)
    # Bind inputs only; all selector, price, timestamp and source checks remain
    # native. A missing registry means explicit inputs, not a fictional pointer.
    monkeypatch.setattr(subject, "select_current_hotspot_candidates", partial(
        subject.select_current_hotspot_candidates, watch_binding=watch, case_bindings=cases))
    paths = [root / "config/current-price-conditions.json", root / subject.STRUCTURE_POINTER,
             root / "config/hotspot-replay-review-v1.json"]
    before = {p: p.read_bytes() for p in paths}
    report = subject.validate_current_hotspot_strategy(root=root, now=NOW)
    assert {p: p.read_bytes() for p in paths} == before
    actual = report["execution"]
    assert actual["summary"]["signal_event_count"] == 161
    assert actual["summary"]["strict_closed_trade_count"] == 0
    assert actual["summary"]["assumed_state_closed_trade_count"] == 10
    assert actual["decision_availability"]["source_acquired_after_decision"] > 0
    assert len(actual["costed_partitions"]) == 30
    assert {r["cost_multiplier"] for r in actual["costed_partitions"]} == {"0", "1", "2"}
    assert report["current_scope"]["trade_date"] == "2026-10-22"
    assert report["current_scope"]["watch_binding"] == watch
    assert report["current_scope"]["registry_binding"] is None
    assert report["current_scope"]["coverage"]["candidate_pool"] == 10
    assert report["historical_structure"]["selection_trade_date"] == "2026-10-16"
    assert report["historical_structure"]["matches_current_scope"] is False
    assert report["strict_oos_admitted"] is False


@pytest.mark.skipif(not os.environ.get("HOTSPOT_RETAINED_ROOT"), reason="Explicit read-only real source root required")
def test_fixed_historical_selection_still_rejects_unavailable_at_cutoff():
    root = Path(os.environ["HOTSPOT_RETAINED_ROOT"])
    watch, cases = _fixed_oct22_selection(root)
    result = subject.select_current_hotspot_candidates(root=root, watch_binding=watch, case_bindings=cases,
        now=datetime(2026, 10, 22, 0, tzinfo=timezone.utc))
    assert result["status"] == "UNASSESSABLE" and result["data_status"] == "INVALID"
    assert result["items"] == [] and result["formal_eligibility"] is False
