from value_investment_agent.db import begin_run, end_run
from value_investment_agent.db import record_failed_run
import json
import pytest


def test_run_boundaries_use_wall_clock_not_transaction_start():
    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((statement, params))

    connection = Connection()
    ident = begin_run(connection, 'research')
    end_run(connection, ident, 'succeeded', {'processed': 3})
    assert len(connection.calls) == 2
    assert all('clock_timestamp()' in sql and 'now()' not in sql
               for sql, _ in connection.calls)
    assert connection.calls[1][1][-1] == ident


@pytest.mark.parametrize('previous,reconstructed', [
    (None, True), ({'details': {}}, False),
    ({'details': {'start_time_reconstructed': True}}, True),
])
def test_failure_does_not_disguise_missing_start_time(previous, reconstructed):
    class Connection:
        def __init__(self):
            self.calls = []

        def rollback(self):
            self.calls.append(('rollback', None))

        def execute(self, sql, params):
            self.calls.append((sql, params))
            return self

        def fetchone(self):
            return previous

    connection = Connection()
    details = {'error': 'test'}
    record_failed_run(connection, 'run', 'task', details)
    assert connection.calls[0][0] == 'rollback'
    sql, params = connection.calls[-1]
    assert json.loads(params[-1])['start_time_reconstructed'] is reconstructed
    assert details == {'error': 'test'}
    assert 'clock_timestamp()' in sql and 'now()' not in sql
    assert 'started_at =' not in sql.split('DO UPDATE')[1]
