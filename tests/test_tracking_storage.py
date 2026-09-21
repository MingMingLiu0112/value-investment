import json
from types import SimpleNamespace
import pytest
from value_investment_agent.candidate_tracking import store_tracking_observations


class Connection:
    def __init__(self):
        self.rows = {}
    def execute(self, sql, params):
        if sql.lstrip().startswith('INSERT'):
            run, symbol, source, _, _, _, payload = params
            self.rows.setdefault((run, symbol), {'source_id':source,'observation':json.loads(payload)})
        return SimpleNamespace(fetchone=lambda: self.rows.get(tuple(params)))


def observation():
    return {'symbol':'000333','membership':{'symbol':'000333','initial_score':'60'},
            'quote_as_of':'2026-09-08T16:00:00+08:00','quote_status':'missing_quote',
            'signal_blocked':True,'current_price':None}


def test_identical_retry_is_idempotent_and_new_run_appends():
    db = Connection()
    for run in ('run1','run1','run2'):
        assert store_tracking_observations(db,run,'source',[observation()]) == 1
    assert len(db.rows) == 2


def test_changed_retry_rejected_without_overwriting_history():
    db = Connection()
    store_tracking_observations(db,'run','source',[observation()])
    revised = {**observation(),'quote_status':'stale_quote'}
    with pytest.raises(ValueError, match='differs'):
        store_tracking_observations(db,'run','source',[revised])
    assert db.rows[('run','000333')]['observation']['quote_status'] == 'missing_quote'


def test_duplicate_batch_rejected_before_writes():
    db = Connection()
    with pytest.raises(ValueError, match='Duplicate'):
        store_tracking_observations(db,'run','source',[observation(),observation()])
    assert not db.rows
