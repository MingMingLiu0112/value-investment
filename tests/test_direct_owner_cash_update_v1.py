"""TEST_ONLY immutable E1 link through the real shared owner-cash kernel."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from test_direct_owner_cash_compilation_v1 import NOW, sample
from value_investment_agent.application.research import direct_owner_cash_research_v1 as runner
from value_investment_agent.application.research import direct_owner_cash_update_v1 as update


def seal(root, name, value):
    path = root / "runtime" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(raw)
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())


def pair(tmp_path, monkeypatch, change="economic", successor_time=None,
         successor_day=None, review_at=None):
    spec = sample(monkeypatch)
    (tmp_path / "runtime").mkdir()
    source = seal(tmp_path, "TEST_ONLY.json", {"TEST_ONLY": True})
    spec["operating_sources"][0]["sha256"] = source["sha256"]
    old_pin = seal(tmp_path, "old-spec.json", spec)
    old = runner.build_direct_owner_cash_receipt(
        root=tmp_path, spec_binding=old_pin, output_dir=tmp_path / "runtime/old", now=NOW)
    next_spec = deepcopy(spec)
    next_spec["run_id"] = "TEST_ONLY_new_run"
    next_spec["computed_at"] = (successor_time or NOW + timedelta(hours=1)).isoformat()
    next_spec["research_as_of"] = successor_day or NOW.date().isoformat()
    if change == "economic":
        next_spec["scenarios"]["bear"]["years"][0]["operating_forecast"]["other_operating_cash"]["value"] = "-30"
    elif change == "format":
        next_spec["scenarios"]["bear"]["years"][0]["policy"]["maintenance_capex"]["value"] = "20.0"
    new_pin = seal(tmp_path, "new-spec.json", next_spec)
    new = runner.build_direct_owner_cash_receipt(
        root=tmp_path, spec_binding=new_pin, output_dir=tmp_path / "runtime/new",
        now=review_at or NOW + timedelta(days=2))
    rationale = dict(schema_version=update.RATIONALE_SCHEMA, action="no_order",
        symbol=spec["symbol"], predecessor_binding=old["receipt_binding"],
        successor_binding=new["receipt_binding"],
        change_rationale="TEST_ONLY lower bear cash conversion",
        countercase="TEST_ONLY cash conversion may recover",
        source_bindings=[source])
    reason_pin = seal(tmp_path, "reason.json", rationale)
    return old, new, reason_pin, rationale


def build(tmp_path, old, new, reason_pin):
    return update.build_direct_owner_cash_update(
        root=tmp_path, predecessor_binding=old["receipt_binding"],
        successor_binding=new["receipt_binding"], change_binding=reason_pin,
        output_dir=tmp_path / "runtime/update", now=NOW + timedelta(days=2))


def test_real_shared_kernel_economic_successor_and_replay(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch)
    built = build(tmp_path, old, new, reason_pin)
    replayed = update.replay_direct_owner_cash_update(
        tmp_path, built["update_binding"], NOW + timedelta(days=2))
    assert replayed == built["update"]
    assert replayed["schema_version"] == update.SCHEMA
    assert replayed["status"] == update.STATUS
    assert "scenarios.bear.years" in replayed["changed_input_fields"]
    assert "scenarios.base.years" not in replayed["changed_input_fields"]
    changed, = replayed["changed_assumptions"]
    assert changed["spec_path"] == "scenarios.bear.years.0.operating_forecast.other_operating_cash"
    assert changed["predecessor"]["value"] == "0"
    assert changed["successor"]["value"] == "-30"
    assert changed["evidence_anchors"] == {"profit": runner._read(
        tmp_path, runner._read(tmp_path, new["receipt_binding"])["spec_binding"]
    )["fact_anchors"]["profit"]}
    assert changed["anchor_validation"] == "REPLAYED_BY_DIRECT_OWNER_CASH_COMPILER"
    assert list(replayed["yearly_changes"]) == ["bear"]
    assert replayed["predecessor_valuation"] != replayed["successor_valuation"]
    assert replayed["action"] == "no_order" and replayed["formal_eligibility"] is False
    assert replayed["condition_price"] is None and replayed["price_admitted"] is False


def test_source_damage_rejected(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch)
    built = build(tmp_path, old, new, reason_pin)
    (tmp_path / "runtime/TEST_ONLY.json").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        update.replay_direct_owner_cash_update(tmp_path, built["update_binding"],
                                               NOW + timedelta(days=2))


def test_metadata_only_change_rejected(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch, change="metadata")
    with pytest.raises(ValueError, match="ECONOMIC_INPUT_UNCHANGED"):
        build(tmp_path, old, new, reason_pin)


def test_decimal_format_only_change_rejected(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch, change="format")
    with pytest.raises(ValueError, match="ECONOMIC_INPUT_UNCHANGED"):
        build(tmp_path, old, new, reason_pin)


def test_decimal_comparison_preserves_high_precision_and_raw_rows():
    left = {"cash": "1.00000000000000000000000000001", "rows": [{"value": "0E-37"}]}
    right = {"cash": "1.0000000000000000000000000001", "rows": [{"value": "0.00"}]}
    assert not update._same_economics(left, right)
    assert update._same_economics({"cash": "1", "rows": [{"value": "0E-37"}]},
                                  {"cash": "1.0", "rows": [{"value": "0.00"}]})
    assert left["cash"] == "1.00000000000000000000000000001"


def test_changed_assumption_ignores_only_prose_and_rejects_missing_anchor(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch)
    new_receipt = runner._read(tmp_path, new["receipt_binding"])
    old_spec = runner._read(tmp_path, runner._read(tmp_path, old["receipt_binding"])["spec_binding"])
    new_spec = runner._read(tmp_path, new_receipt["spec_binding"])
    prose = deepcopy(old_spec)
    prose["scenarios"]["bear"]["years"][0]["operating_forecast"]["other_operating_cash"]["rationale"] = "TEST_ONLY revised wording"
    assert update._assumption_changes(old_spec, prose) == []
    missing = deepcopy(new_spec)
    missing["scenarios"]["bear"]["years"][0]["operating_forecast"]["other_operating_cash"]["evidence_anchors"] = ["absent"]
    with pytest.raises(ValueError, match="CHANGED_ASSUMPTION_ANCHOR_MISSING"):
        update._assumption_changes(old_spec, missing)


def test_cross_company_and_time_rejected(tmp_path, monkeypatch):
    old, new, reason_pin, _ = pair(tmp_path, monkeypatch)
    receipt = runner._read(tmp_path, new["receipt_binding"])
    spec = runner._read(tmp_path, receipt["spec_binding"])
    original_read = update._read
    for key, value, reason in (("symbol", "600887", "ISSUER_SCOPE"),
                               ("computed_at", (NOW - timedelta(hours=1)).isoformat(), "TIME_MOVES_BACKWARD"),
                               ("computed_at", (NOW + timedelta(days=3)).isoformat(), "FUTURE_OR_NAIVE")):
        changed = deepcopy(spec)
        changed[key] = value
        monkeypatch.setattr(update, "_read", lambda root, binding, changed=changed:
                            changed if binding == receipt["spec_binding"]
                            else original_read(root, binding))
        with pytest.raises(ValueError, match=reason):
            update._expected(root=tmp_path,
                predecessor_binding=old["receipt_binding"],
                successor_binding=new["receipt_binding"],
                change_binding=reason_pin, now=NOW + timedelta(days=2))
    monkeypatch.setattr(update, "_read", original_read)


def test_shanghai_day_crosses_utc_midnight_without_false_rejection(tmp_path, monkeypatch):
    # UTC November 16 evening is already November 17 in Shanghai.
    computed = datetime(2026, 11, 16, 16, 30, tzinfo=timezone.utc)
    reviewed = datetime(2026, 11, 16, 16, 40, tzinfo=timezone.utc)
    old, new, reason_pin, _ = pair(
        tmp_path, monkeypatch, successor_time=computed,
        successor_day="2026-11-17", review_at=reviewed)
    built = update.build_direct_owner_cash_update(
        root=tmp_path, predecessor_binding=old["receipt_binding"],
        successor_binding=new["receipt_binding"], change_binding=reason_pin,
        output_dir=tmp_path / "runtime/update", now=reviewed)
    assert update.replay_direct_owner_cash_update(
        tmp_path, built["update_binding"], reviewed)["research_as_of"] == "2026-11-17"

    # A research day after the local computation day is invalid even if the
    # later review clock has reached that day.
    receipt = runner._read(tmp_path, new["receipt_binding"])
    spec = runner._read(tmp_path, receipt["spec_binding"])
    changed = deepcopy(spec)
    changed["research_as_of"] = "2026-11-18"
    original_read = update._read
    monkeypatch.setattr(update, "_read", lambda root, binding:
                        changed if binding == receipt["spec_binding"]
                        else original_read(root, binding))
    with pytest.raises(ValueError, match="TIME_MOVES_BACKWARD_OR_FUTURE"):
        update.replay_direct_owner_cash_update(tmp_path, built["update_binding"],
                                               reviewed + timedelta(days=2))


def test_forged_reason_and_resealed_update_fields_rejected(tmp_path, monkeypatch):
    old, new, reason_pin, rationale = pair(tmp_path, monkeypatch)
    built = build(tmp_path, old, new, reason_pin)
    rationale["source_bindings"] = [dict(path="runtime/other.json", sha256="0" * 64)]
    bad_reason = seal(tmp_path, "bad-reason.json", rationale)
    with pytest.raises(ValueError, match="BOUND_RATIONALE"):
        update.build_direct_owner_cash_update(
            root=tmp_path, predecessor_binding=old["receipt_binding"],
            successor_binding=new["receipt_binding"], change_binding=bad_reason,
            output_dir=tmp_path / "runtime/bad-update", now=NOW + timedelta(days=2))
    forged = deepcopy(built["update"])
    forged["yearly_changes"]["bear"]["successor"][0]["conditional_distribution_cny"] = "999999"
    forged_pin = seal(tmp_path, "forged-update.json", forged)
    with pytest.raises(ValueError, match="FIELDS_OR_YEARLY_PATH_CHANGED"):
        update.replay_direct_owner_cash_update(tmp_path, forged_pin, NOW + timedelta(days=2))
    for field, replacement in (("spec_path", "scenarios.base.years.0.policy.parent_profit"),
                               ("successor", {"classification": "FORECAST_ASSUMPTION", "value": "999"}),
                               ("evidence_anchors", {})):
        forged = deepcopy(built["update"])
        forged["changed_assumptions"][0][field] = replacement
        forged_pin = seal(tmp_path, "forged-assumption-" + field + ".json", forged)
        with pytest.raises(ValueError, match="FIELDS_OR_YEARLY_PATH_CHANGED"):
            update.replay_direct_owner_cash_update(tmp_path, forged_pin, NOW + timedelta(days=2))
