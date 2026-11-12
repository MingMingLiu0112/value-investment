"""TEST_ONLY dividend-policy transport; real source replay is a separate check."""
from value_investment_agent.application.research.agent_review.dividend_policy_anchor_v1 import (
    disclosed_per_share_growth_anchor,
    disclosed_attributable_profit_payout_anchor,
)


def _context():
    common = dict(period="2025-12-31", unit="TEXT", source_id="TEST_ONLY:filing",
                  pdf_sha256="a" * 64)
    return dict(evidence=[
        dict(common, id="TEST_ONLY:distribution", text=(
            "2025 年度累计每股分红 1.05 元，现金分红总额占归母净利润的 43.39%。")),
        dict(common, id="TEST_ONLY:policy", text=(
            "股东回报规划（2024 年-2026 年）明确2024-2026 年度，每股派发的现金股利，"
            "较上一年度同比增长不低于 10%。")),
    ])


def test_source_bound_conditional_dps_floor_not_cash_capacity():
    result = disclosed_per_share_growth_anchor(_context())
    assert result["conditional_minimum_dps_cny"] == "1.155"
    assert result["target_year"] == 2026
    assert result["evidence_ids"] == ["TEST_ONLY:distribution", "TEST_ONLY:policy"]
    assert result["action"] == "no_order" and "does not establish" in result["limitation"]


def test_distinct_original_or_missing_policy_cannot_be_spliced():
    context = _context()
    context["evidence"][1]["source_id"] = "OTHER_REPORT"
    assert disclosed_per_share_growth_anchor(context) is None
    context = _context()
    context["evidence"][1]["text"] = "We hope to increase dividends."
    assert disclosed_per_share_growth_anchor(context) is None


def test_real_attributable_profit_target_and_wrong_denominator_rejection():
    import json
    import os
    from datetime import datetime, timezone
    from pathlib import Path
    import pytest
    from test_operating_horizon_draft_v3 import payload
    from value_investment_agent.application.research.agent_review import operating_task_v2 as live
    from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v1 as draft
    from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
        build_operating_horizon_source_context,
    )

    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    context = build_operating_horizon_source_context(root=Path(os.environ["VALUE_REAL_SOURCE_ROOT"]),
        symbol="000568", now=datetime.now(timezone.utc))
    anchor = disclosed_attributable_profit_payout_anchor(context)
    assert anchor["fiscal_years"] == [2024, 2025, 2026]
    assert anchor["minimum_ratios"] == ["0.65", "0.7", "0.75"]
    assert anchor["minimum_annual_cash_cny"] == "8500000000"
    assert anchor["profit_basis"] == "consolidated_parent_attributable"
    assert anchor["action"] == "no_order"
    research_context = live.research_context(context, drivers=True)
    request = draft.build_request(research_context, [2026])
    assert "consolidated_parent_attributable" in request.user
    assert "SOURCE_BOUND_PARENT_CASH_CONVERSION_HISTORY" in request.user
    assert "-3795473694.17" in request.user
    assert "do not label that difference working capital" in request.system
    assert "no material commitments at its balance-sheet date" in request.system
    assert "does not prove zero future growth capex" in request.system
    paths = payload()["years"]["2026"]["shareholder_cash_paths"]
    for path in paths.values():
        for term in path.values():
            if isinstance(term, dict) and "evidence_ids" in term:
                term["evidence_ids"] = anchor["evidence_ids"]
    paths["bear"]["target_payout_ratio"]["rationale"] = "75% of parent net profit under the disclosed plan"
    response = json.dumps({"years": {"2026": {"shareholder_cash_paths": paths}}})
    with pytest.raises(ValueError, match="SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT"):
        draft.validate_response(response, research_context, [2026], datetime.now(timezone.utc))
    paths["bear"]["target_payout_ratio"]["rationale"] = "Conditional 75% of consolidated attributable profit; parent cash capacity remains separately unknown."
    accepted = draft.validate_response(json.dumps({"years": {"2026": {"shareholder_cash_paths": paths}}}),
        research_context, [2026], datetime.now(timezone.utc))
    assert accepted["action"] == "no_order" and accepted["formal_eligibility"] is False
