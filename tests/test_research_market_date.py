"""A-share research dates use China days; availability instants stay exact."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from test_research_application import case, residual_facts
from value_investment_agent.domain.research.research_run_contract import ResearchPitFrame
from value_investment_agent.research_application import ResearchRunSpec
from value_investment_agent.application.product.research_draft import (
    BOUND_DRAFT_SCHEMA, DRAFT_STATUS, _validate_draft,
)


@pytest.mark.parametrize('hour,minute,market_day', [(15, 59, 21), (16, 0, 22), (23, 59, 22)])
@pytest.mark.parametrize('offset', [timezone.utc, ZoneInfo('Asia/Shanghai'), timezone(timedelta(hours=-4))])
def test_research_dates_are_invariant_for_same_instant(hour, minute, market_day, offset):
    instant = datetime(2026, 10, 21, hour, minute, tzinfo=timezone.utc).astimezone(offset)
    day = date(2026, 10, market_day)
    facts = residual_facts()
    research = replace(case('600519'), as_of=day)
    frame = ResearchPitFrame(report_period=facts.as_of, research_as_of=day,
        valuation_date=day, available_at=instant, computed_at=instant)
    assert frame.available_at == instant
    ResearchRunSpec(run_id='TEST_ONLY-market-date', symbol='600519',
        profile_id='quality_compounder', research_case=research, facts=facts, available_at=instant)
    tomorrow = day + timedelta(days=1)
    with pytest.raises(ValueError, match='availability cannot precede'):
        replace(frame, research_as_of=tomorrow)
    with pytest.raises(ValueError, match='availability cannot precede'):
        ResearchRunSpec(run_id='TEST_ONLY-future-date', symbol='600519',
            profile_id='quality_compounder', research_case=replace(research, as_of=tomorrow),
            facts=facts, available_at=instant)
    with pytest.raises(ValueError, match='availability cannot follow computation'):
        replace(frame, available_at=instant + timedelta(microseconds=1))

    draft = dict(schema_version=BOUND_DRAFT_SCHEMA, status=DRAFT_STATUS,
        action='no_order', symbol='600519', available_at=instant.isoformat(),
        research_as_of=day.isoformat(), valuation={'status': 'not_ready'})
    # Passing the date check never makes this unvalued case a conditional draft.
    with pytest.raises(ValueError, match='valuation is not conditional'):
        _validate_draft(draft, '600519', instant)
    with pytest.raises(ValueError, match='research_as_of is in the future'):
        _validate_draft(dict(draft, research_as_of=tomorrow.isoformat()), '600519', instant)
    with pytest.raises(ValueError, match='not yet available'):
        _validate_draft(dict(draft, available_at=(instant + timedelta(microseconds=1)).isoformat()),
            '600519', instant)
