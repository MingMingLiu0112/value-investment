"""Explicit TEST_ONLY event fixtures plus source-bound retained-data checks."""
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import os

import pytest

from test_historical_execution_replay import _distribution_fixture
from test_hotspot_lifecycle_bound_history import (
    _history, _review, _assert_no_permission, _binding as case_binding, CURRENT_AT, ENTRY_AT,
)
from value_investment_agent.application.hotspot.lifecycle_review import build_hotspot_lifecycle_review
from value_investment_agent.application.hotspot.report_text import render_hotspot_lifecycle_markdown
from value_investment_agent.domain.hotspot.price_comparability import assess_price_comparability
from value_investment_agent.infrastructure.hotspot.price_comparability import inspect_price_comparability
from value_investment_agent.quote_sessions import CHINA


NOW = datetime(2026, 10, 23, 17, tzinfo=CHINA)


def _binding(path, root):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest(),
        available_at=NOW.isoformat())


def test_domain_requires_full_coverage_and_no_action_to_confirm():
    args = dict(start=date(2020, 6, 1), end=date(2020, 6, 3), events=[])
    assert assess_price_comparability(**args)["status"] == "UNKNOWN"
    # Synthetic coverage exercises the future domain contract, not source admission.
    assert assess_price_comparability(**args, coverage_complete=True)["status"] == "CONFIRMED"
    args["events"] = [dict(ex_date="2020-06-02")]
    result = assess_price_comparability(**args, coverage_complete=True)
    assert result["status"] == "INCOMPARABLE"
    assert result["adjusted_protection_price"] is None
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


@pytest.mark.parametrize("start,end,expected", [
    ("2020-06-01", "2020-06-03", "INCOMPARABLE"),
    ("2020-06-02", "2020-06-03", "UNKNOWN"),
    ("2020-06-01", "2020-06-01", "UNKNOWN"),
])
def test_bound_reviewed_distribution_crossing_and_empty_coverage(tmp_path, start, end, expected):
    path, _, _ = _distribution_fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    result = inspect_price_comparability(root=tmp_path, symbol="600519", start=date.fromisoformat(start),
        end=date.fromisoformat(end), now=NOW, registry_binding=_binding(path, tmp_path))
    assert result["status"] == expected
    assert result["source_status"] == "VERIFIED_RETAINED_CORRESPONDENCE"
    assert result["historical_availability_proven"] is False
    assert result["pdf_semantics_reverified"] is False
    assert result["complete_corporate_action_coverage"] is False
    assert result["adjusted_protection_price"] is None
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("damage", ["registry_hash", "original_hash", "missing_pdf", "future", "no_time", "naive", "amount", "escape", "malformed_event"])
def test_bad_binding_never_confirms_comparability(tmp_path, damage):
    path, _, _ = _distribution_fixture(tmp_path)
    binding = _binding(path, tmp_path)
    if damage == "registry_hash":
        binding["sha256"] = "0" * 64
    elif damage == "original_hash":
        (tmp_path / "distribution.pdf").write_bytes(b"changed")
    elif damage == "missing_pdf":
        (tmp_path / "distribution.pdf").unlink()
    elif damage == "future":
        binding["available_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif damage == "no_time":
        del binding["available_at"]
    elif damage == "naive":
        binding["available_at"] = "2026-10-23T17:00:00"
    elif damage == "amount":
        value = json.loads(path.read_bytes())
        value["events"][0]["cash_amount"] = "999"
        path.write_text(json.dumps(value), encoding="utf-8")
        binding = _binding(path, tmp_path)
    elif damage == "malformed_event":
        path.write_text(json.dumps(dict(events=["not an event"])), encoding="utf-8")
        binding = _binding(path, tmp_path)
    else:
        binding["path"] = "../outside.json"
    result = inspect_price_comparability(root=tmp_path, symbol="600519", start=date(2020, 6, 1),
        end=date(2020, 6, 3), now=NOW, registry_binding=binding)
    assert result["status"] == "UNKNOWN"
    assert result["source_status"] == "INVALID_OR_UNAVAILABLE"
    assert result["evidence_bindings"] == []


def test_registry_coverage_flags_cannot_approve_same_basis(tmp_path):
    path, _, _ = _distribution_fixture(tmp_path)
    raw = json.loads(path.read_bytes())
    raw.update(complete_historical_coverage_proven=True, complete_corporate_action_coverage=True,
        status="CONFIRMED", historical_availability_proven=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    result = inspect_price_comparability(root=tmp_path, symbol="600519", start=date(2026, 9, 1),
        end=date(2026, 9, 24), now=NOW, registry_binding=_binding(path, tmp_path))
    assert result["status"] == "UNKNOWN"
    assert result["complete_corporate_action_coverage"] is False
    assert result["historical_availability_proven"] is False


@pytest.mark.parametrize("breach,raw_review", [(False, "HOLD_STRUCTURE_OBSERVATION"), (True, "EXIT_STRUCTURE_REVIEW")])
def test_native_lifecycle_never_assumes_unadjusted_prices_comparable(tmp_path, breach, raw_review):
    result = _review(_history(tmp_path, breach=breach))
    assert result["observed_review"] == "UNKNOWN"
    assert result["unadjusted_structural_observation"]["observed_review"] == raw_review
    assert result["decision_explanation"]["basis_code"] == "PRICE_BASIS_UNKNOWN"
    assert result["price_comparability"]["status"] == "UNKNOWN"
    assert result["original_entry_comparison"]["first_breach_at"] == (
        "2026-09-22T11:30:00+08:00" if breach else None)
    _assert_no_permission(result)


def test_native_action_crossing_cannot_turn_mechanical_drop_into_admitted_exit(tmp_path):
    _, entry, _, current = _history(tmp_path, breach=True)
    registry, _, _ = _distribution_fixture(tmp_path)
    value = json.loads(registry.read_bytes())
    value["events"][0].update(record_date="2026-09-21", ex_date="2026-09-22",
        cash_payment_date="2026-09-22")
    registry.write_text(json.dumps(value), encoding="utf-8")
    binding = _binding(registry, tmp_path)
    binding["available_at"] = CURRENT_AT.isoformat()
    result = build_hotspot_lifecycle_review(root=tmp_path, symbol="600519",
        current_case_binding=case_binding(current), entry_case_binding=case_binding(entry),
        entry_at=ENTRY_AT, now=CURRENT_AT, corporate_action_registry_binding=binding)
    assert result["observed_review"] == "UNKNOWN"
    assert result["price_comparability"]["status"] == "INCOMPARABLE"
    assert result["unadjusted_structural_observation"]["observed_review"] == "EXIT_STRUCTURE_REVIEW"
    assert result["original_entry_comparison"]["original_protection_price"] == "11"
    assert result["original_entry_comparison"]["first_breach_close"] == "10"
    assert "PRICE_BASIS_INCOMPARABLE" in render_hotspot_lifecycle_markdown(result)
    assert result["price_comparability"]["adjusted_protection_price"] is None
    _assert_no_permission(result)


def test_retained_real_distribution_warns_without_claiming_pit_or_complete_coverage():
    configured = os.environ.get("HOTSPOT_RETAINED_ROOT")
    if not configured:
        pytest.skip("Retained public source root not supplied")
    root = Path(configured)
    registry = root / "docs/reviewed-cash-distributions.json"
    if not registry.exists():
        pytest.skip("Retained reviewed distribution registry missing")
    result = inspect_price_comparability(root=root, symbol="600519", start=date(2025, 12, 18),
        end=date(2025, 12, 22), now=NOW, registry_binding=_binding(registry, root))
    assert result["source_status"] == "VERIFIED_RETAINED_CORRESPONDENCE"
    assert result["status"] == "INCOMPARABLE"
    assert [row["ex_date"] for row in result["crossing_events"]] == ["2025-12-19"]
    assert result["historical_availability_proven"] is False
    assert result["complete_corporate_action_coverage"] is False
