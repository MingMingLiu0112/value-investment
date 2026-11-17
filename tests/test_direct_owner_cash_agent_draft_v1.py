"""TEST_ONLY draft validation and legacy compiler handoff, no AI claim."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_agent_draft_v1 as target

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def _term(count):
    return dict(values=["1"] * count, evidence_anchors=["profit"],
        mechanism="TEST_ONLY explicit assumption anchored to profit",
        counter_evidence="TEST_ONLY financing or sales may differ",
        reopen_condition="TEST_ONLY reopen on dated source revision")


def _draft(name):
    return dict(schema_version=target.VERSION, scenario=name,
        source_fingerprint="f" * 64, years=list(range(2026, 2036)),
        annual_notes=[f"TEST_ONLY year {year} must be reviewed" for year in range(2026, 2036)],
        series={key: _term(10) for key in target.SERIES},
        terminal=dict(policy={key: _term(1) for key in target.TERMINAL_POLICY},
            remaining_scheduled_events=[], max_transition_years=10, financing=None,
            rationale="TEST_ONLY terminal policy needs economic review",
            counter_evidence="TEST_ONLY future obligations may continue",
            reopen_condition="TEST_ONLY new obligations require a revision"),
        cost_of_equity=_term(1),
        rationale="TEST_ONLY source-bound annual business path",
        counter_evidence="TEST_ONLY earnings conversion may weaken",
        reopen_condition="TEST_ONLY new filings require re-examination")


def _setup(monkeypatch):
    context = dict(symbol="600887", valuation_date="2025-12-31",
        input_fingerprint="f" * 64,
        facts={"revenue": {"period_end": "2025-12-31"}, "profit": {"period_end": "2025-12-31"}})
    old = dict(symbol="600887", scenarios={"old_approved": {"value": "999"}})
    seen = []
    monkeypatch.setattr(target, "read_parent_cash_agent_facts", lambda **kw: context)
    monkeypatch.setattr(target, "_load_spec", lambda *args: old)
    monkeypatch.setattr(target, "compile_source_bound_owner_cash",
                        lambda **kw: seen.append(deepcopy(kw["spec"])) or {"TEST_ONLY": True})
    return old, seen


def test_three_explicit_scenarios_replace_old_predictions_and_reach_compiler(monkeypatch, tmp_path):
    old, seen = _setup(monkeypatch)
    drafts = {name: _draft(name) for name in target.SCENARIOS}
    result = target.assemble_parent_cash_drafts(root=tmp_path,
        spec_binding={"path": "runtime/TEST_ONLY", "sha256": "a" * 64},
        drafts=drafts, generated_at=NOW)
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["main_range_adopted"] is False and result["compiled"] == {"TEST_ONLY": True}
    assert set(seen[0]["scenarios"]) == set(target.SCENARIOS)
    assert old["scenarios"] == {"old_approved": {"value": "999"}}
    assert len(seen[0]["scenarios"]["base"]["years"]) == 10
    assert seen[0]["scenarios"]["base"]["years"][0]["operating_forecast"]["revenue"]["classification"] == "FORECAST_ASSUMPTION"


@pytest.mark.parametrize("fault,code", [
    ("source", "SOURCE_OR_HORIZON"), ("year", "SOURCE_OR_HORIZON"),
    ("extra", "SOURCE_OR_HORIZON"), ("missing_term", "SOURCE_OR_HORIZON"),
    ("forged_anchor", "TERM_SOURCE_INVALID"),
    ("nan", "FINITE_REQUIRED"), ("missing_note", "ANNUAL_MECHANISM_REQUIRED"),
    ("terminal", "TERMINAL_CONTRACT_INVALID"),
])
def test_model_draft_failure_never_reaches_compiler(monkeypatch, tmp_path, fault, code):
    _, seen = _setup(monkeypatch)
    drafts = {name: _draft(name) for name in target.SCENARIOS}
    row = drafts["base"]
    if fault == "source": row["source_fingerprint"] = "0" * 64
    if fault == "year": row["years"][3] = 2028
    if fault == "extra": row["formally_approved"] = True
    if fault == "missing_term": del row["series"]["parent_profit"]
    if fault == "forged_anchor": row["series"]["parent_profit"]["evidence_anchors"] = ["fiction"]
    if fault == "nan": row["series"]["parent_profit"]["values"][0] = "NaN"
    if fault == "missing_note": row["annual_notes"][0] = ""
    if fault == "terminal": del row["terminal"]["remaining_scheduled_events"]
    with pytest.raises(ValueError, match=code):
        target.assemble_parent_cash_drafts(root=tmp_path,
            spec_binding={"path": "runtime/TEST_ONLY", "sha256": "a" * 64},
            drafts=drafts, generated_at=NOW)
    assert seen == []
