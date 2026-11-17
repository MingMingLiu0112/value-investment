"""Real candidate generation across China midnight preserves exact PIT instants."""
from datetime import date, datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from test_pending_research_candidate import candidate_inputs, run
from value_investment_agent.application.product import pending_research_candidate as candidate
from value_investment_agent.domain.research.research_run_contract import ResearchPitFrame


@pytest.mark.parametrize('instant', [
    '2026-10-10T15:59:59+00:00',
    '2026-10-10T16:00:00+00:00',
    '2026-10-10T23:59:59+00:00',
    '2026-10-11T00:00:00+00:00',
])
def test_legacy_candidate_actual_behavior_at_shanghai_boundary(tmp_path, monkeypatch, instant):
    fixed = datetime.fromisoformat(instant)

    class BoundaryClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=None) if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(candidate, 'datetime', BoundaryClock)
    package, policy, request = candidate_inputs(tmp_path)
    original_valuation_date = json.loads(package.read_text(encoding='utf-8'))['point_in_time']['valuation_date']
    local = fixed.astimezone(ZoneInfo('Asia/Shanghai'))
    result = run(tmp_path, package, policy, request)
    pit = json.loads((tmp_path / 'runtime/pending/package.json').read_text(encoding='utf-8'))['point_in_time']
    available = datetime.fromisoformat(pit['available_at'])
    computed = datetime.fromisoformat(pit['computed_at'])
    assert pit['research_as_of'] == local.date().isoformat()
    assert pit['valuation_date'] == original_valuation_date
    assert available == computed == fixed
    assert available.utcoffset() == timedelta(0)
    assert available.astimezone(ZoneInfo('Asia/Shanghai')).date() == local.date()
    assert result['price_admitted'] is result['approval_changed'] is False
    assert result['registered_current_case_changed'] is False


@pytest.mark.parametrize('fault', ['prior-local-day', 'future-availability'])
def test_strict_pit_still_rejects_real_date_or_instant_violation(fault):
    computed = datetime(2026, 10, 12, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    available = computed - timedelta(seconds=1) if fault == 'prior-local-day' else computed + timedelta(seconds=1)
    with pytest.raises(ValueError, match='availability cannot'):
        ResearchPitFrame(report_period=date(2026, 6, 30), research_as_of=date(2026, 10, 12),
            valuation_date=date(2026, 10, 12), available_at=available, computed_at=computed)
