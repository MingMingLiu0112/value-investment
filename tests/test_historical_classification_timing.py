import importlib.util
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from build_moutai_daily_research_inputs import classification_at


def evidence():
    return {
        'prepayments_2013': {'source': {'source_id': 'annual2013', 'available_at': '2014-03-26T00:00:00+08:00'}},
        'revenue_standard_transition': {'effective_date': '2020-01-01', 'source': {'source_id': 'annual2020', 'available_at': '2021-04-01T00:00:00+08:00'}},
    }


def test_effective_date_does_not_leak_later_disclosure():
    assert classification_at(evidence(), '2020-12-31T15:00:00+08:00', 'annual2019') == {}
    assert 'revenue_standard_transition' in classification_at(evidence(), '2021-04-01T00:00:00+08:00', 'annual2020')


def test_old_project_balance_does_not_roll_into_later_year():
    assert 'prepayments_2013' in classification_at(evidence(), '2015-01-05T15:00:00+08:00', 'annual2013')
    assert 'prepayments_2013' not in classification_at(evidence(), '2015-05-05T15:00:00+08:00', 'annual2014')
    assert classification_at(evidence(), '2014-03-25T15:00:00+08:00', 'annual2013') == {}
