from datetime import date, datetime, timezone

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.fcff import FCFFValuationModel, FinancialFacts


def test_unverified_facts_fail_closed_into_a_unified_valuation_result():
    case = ResearchCase(
        symbol="000333", name="美的集团", as_of=date(2026, 9, 12), run_id="test",
        generated_at=datetime(2026, 9, 12, tzinfo=timezone.utc), research_version="test",
        industry="家电", investment_path="成长价值", thesis="测试", return_driver="测试",
        mispricing_hypothesis="未证明", financial_summary={"period_end": "2025-09-30"},
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="partial", valuation_status="not_ready", research_status="financial_scope_blocked",
        blockers=[], evidence_refs=[{"id": "case", "path": "case.json", "sha256": "x"}],
        quote_date=None, financial_period=date(2025, 9, 30),
        missing_date_reasons={"quote_date": "not used"},
    )
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 9, 30), verified=False,
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=["ordinary_shares_not_verified"],
    )

    result = FCFFValuationModel().value(facts, case)

    assert result.model_type == "FCFF"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert result.status == "not_ready"
    assert "financial_facts_not_verified" in result.blockers
