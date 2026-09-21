from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.research_case import ResearchCase


def case():
    return ResearchCase(
        symbol="600519", name="Fixture", as_of=date(2026, 9, 18),
        run_id="fixture", generated_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        research_version="v1", industry="fixture", investment_path="fixture",
        thesis="", return_driver="", mispricing_hypothesis="",
        financial_summary={"profit": Decimal("1.01")}, positives=[],
        counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="incomplete", valuation_status="not_ready",
        research_status="incomplete", blockers=[], evidence_refs=[],
        quote_date=None, financial_period=None,
        missing_date_reasons={"quote_date": "missing", "financial_period": "missing"})


def test_json_preserves_exact_amount_and_missing_dates():
    data = json.loads(case().to_json())
    assert data["financial_summary"]["profit"] == "1.01"
    assert data["quote_date"] is None
    assert data["as_of"] == "2026-09-18"


def test_future_date_and_unexplained_missing_date_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        replace(case(), quote_date=date(2026, 9, 21))
    with pytest.raises(ValueError, match="explanation"):
        replace(case(), missing_date_reasons={})


def test_unbacked_fact_and_unknown_reference_rejected():
    with pytest.raises(ValueError, match="require evidence"):
        replace(case(), positives=[{"kind": "fact", "text": "profitable"}])
    with pytest.raises(ValueError, match="unknown evidence"):
        replace(case(), positives=[{"kind": "fact", "evidence_refs": ["missing"]}])


def test_gap_is_preserved_without_manufacturing_evidence():
    record = replace(case(), counter_evidence=[{"kind": "gap", "text": "Unknown"}])
    assert json.loads(record.to_json())["evidence_refs"] == []
