"""TEST_ONLY mechanisms; real-source replay has a separately retained receipt."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.application.research import operating_cash_consumption_v2 as subject


def earnings():
    point = dict(group_pbt_cny="100", income_tax_cny="20", signed_nci_cny="5",
                 parent_profit_cny="75")
    return dict(action="no_order", formal_eligibility=False, symbol="TEST_ONLY",
        task_id="TEST_ONLY_TASK", scenarios={name: dict(period_basis="FY",
            period_start="2027-01-01", period_end="2027-12-31",
            anchor_evidence=[dict(evidence_id="TEST_ONLY", available_at="2026-01-01T00:00:00+00:00")],
            witnesses={"margin_lower": deepcopy(point), "margin_upper": deepcopy(point)})
            for name in ("bear", "base", "bull")})


def compile(value):
    return subject.compile_verified_annual_candidates(consumed=value, opening_date="2025-12-31",
                                                       asof="2026-11-05T00:00:00+00:00")


def test_full_year_compiles_without_inventing_intervening_year_or_cash():
    original = earnings()
    result = compile(original)
    for row in result["scenarios"].values():
        assert row["model_year"] == 2
        assert row["missing_calendar_years"] == [2026, *range(2028, 2036)]
        assert row["selected_witness"] is None
        for item in row["candidates"].values():
            assert item["annual_row"]["year"] == 2
            assert Decimal(item["parent_bridge"]["parent_profit_cny"]) == 75
            assert "cash_policy" not in item["annual_row"]
            assert item["contains_forecast_assumptions"]
    assert result["cash_model_ready"] is False
    assert result["selected_annual_rows"] is None
    assert original == earnings()


def test_half_year_is_not_multiplied_into_full_year():
    value = earnings()
    for row in value["scenarios"].values():
        row.update(period_basis="H1", period_end="2027-06-30")
    result = compile(value)
    assert all(not row["candidates"] for row in result["scenarios"].values())
    assert all(len(row["missing_calendar_years"]) == 10 for row in result["scenarios"].values())


@pytest.mark.parametrize("mutation,error", [
    (lambda v: v["scenarios"]["base"].update(period_end="2027-06-30"), "FY_LABEL"),
    (lambda v: v["scenarios"]["base"].update(period_start="2025-01-01"), "HORIZON"),
    (lambda v: v["scenarios"]["base"]["anchor_evidence"][0].update(available_at="2027-01-01T00:00:00+00:00"), "SOURCE_AFTER"),
    (lambda v: v["scenarios"]["base"]["witnesses"]["margin_lower"].update(parent_profit_cny="80"), "RECONCILIATION"),
    (lambda v: v.update(formal_eligibility=True), "UNAPPROVED"),
])
def test_invalid_annual_input_is_rejected(mutation, error):
    value = earnings()
    mutation(value)
    with pytest.raises(ValueError, match=error):
        compile(value)


def test_consumer_reuses_source_validation_and_keeps_old_result(monkeypatch, tmp_path):
    value = earnings()
    value.update(consumption_fingerprint="old", condition_price=None, current_blockers=[
        dict(code="COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED", stage="valuation", explanation="old H1")])
    monkeypatch.setattr(subject.previous, "read_operating_cash_consumption", lambda **kw: deepcopy(value))
    monkeypatch.setattr(subject.previous, "build_operating_source_context", lambda **kw:
        dict(financial_basis="2025-12-31", snapshot_fingerprint="verified"))
    task = dict(symbol="TEST_ONLY", research_as_of="2026-11-05T00:00:00+00:00",
                source_binding={}, context_fingerprint="verified")
    result = subject.read_operating_cash_consumption(root=tmp_path, task=task,
                                                     now=datetime.now(timezone.utc))
    assert result["previous_consumption_fingerprint"] == "old"
    assert result["current_blockers"][0]["code"] == "COMPLETE_TEN_YEAR_OPERATING_PATH_REQUIRED"
    assert result["condition_price"] is None
    assert value["current_blockers"][0]["explanation"] == "old H1"
    task["context_fingerprint"] = "changed"
    with pytest.raises(ValueError, match="CONTEXT_CHANGED"):
        subject.read_operating_cash_consumption(root=tmp_path, task=task, now=datetime.now(timezone.utc))


def test_half_year_keeps_existing_adapter_and_failure_has_precise_blocker(monkeypatch, tmp_path):
    value = earnings()
    value.update(consumption_fingerprint="old", current_blockers=[
        dict(code="COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED")])
    monkeypatch.setattr(subject.previous, "read_operating_cash_consumption", lambda **kw: deepcopy(value))
    monkeypatch.setattr(subject.previous, "build_operating_source_context", lambda **kw:
        dict(financial_basis="2026-06-30", snapshot_fingerprint="verified"))
    task = dict(symbol="TEST_ONLY", research_as_of="2026-11-05T00:00:00+00:00",
                source_binding={}, context_fingerprint="verified")
    result = subject.read_operating_cash_consumption(root=tmp_path, task=task, now=datetime.now(timezone.utc))
    assert result["earnings_input_compilation"]["reason"] == "ANNUAL_OPENING_BASIS_REQUIRED"
    assert result["current_blockers"] == [dict(code="ANNUAL_INPUT_COMPILATION_REJECTED",
        stage="valuation", explanation="ANNUAL_OPENING_BASIS_REQUIRED")]
    for row in value["scenarios"].values():
        row.update(period_basis="H1", period_end="2027-06-30")
    result = subject.read_operating_cash_consumption(root=tmp_path, task=task, now=datetime.now(timezone.utc))
    assert result["earnings_input_compilation"]["status"] == "DELEGATED_TO_EXISTING_PERIOD_ADAPTER"


def test_high_precision_tax_keeps_explicit_rounding_delta():
    value = earnings()
    for scenario in value["scenarios"].values():
        for point in scenario["witnesses"].values():
            point.update(income_tax_cny="20.123456789012345678901234567890123456789",
                parent_profit_cny="74.876543210987654321098765432109876543211")
    result = compile(value)
    candidate = result["scenarios"]["base"]["candidates"]["margin_lower"]
    assert candidate["annual_row"]["tax_assumption"]["value"] == "20.12"
    assert candidate["input_rounding"]["parent_profit_delta_cny"] != "0"
