import json
import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from value_investment_agent import db, evidence_dependencies, settings


def test_audit_loads_point_id_only_growth_dependencies(monkeypatch, capsys):
    queries = []
    rows = [dict(data_point_id='bad', symbol='000001', field_name='revenue',
                 period_label='2024-12-31', source_id='s', validation_status='failed', metadata={}),
            dict(data_point_id='growth', symbol='000001', field_name='revenue_growth',
                 period_label='2025-12-31', source_id='g', validation_status='verified',
                 metadata={'input_data_point_ids': ['bad']})]

    class Connection:
        def execute(self, sql, params=None):
            queries.append(sql)
            if 'SELECT p.data_point_id,p.symbol,p.period_label,p.value' in sql:
                result = [rows[0]]
            elif 'SELECT p.data_point_id,p.symbol,p.field_name' in sql:
                result = rows if "p.metadata ? 'input_data_point_ids'" in sql else rows[:1]
            else:
                result = []
            return SimpleNamespace(fetchall=lambda: result)

    @contextmanager
    def connect(_):
        yield Connection()

    monkeypatch.setattr(db, 'connect', connect)
    monkeypatch.setattr(settings, 'get_settings', lambda: SimpleNamespace(database_url='unused'))
    monkeypatch.setitem(sys.modules, 'evidence_dependencies', evidence_dependencies)
    runpy.run_path(str(Path(__file__).parents[1] / 'scripts/audit_revenue_scope.py'))
    result = json.loads(capsys.readouterr().out)
    assert result['total_affected'] == 2
    assert result['affected_verified'] == 1
    assert any('SET TRANSACTION READ ONLY' in sql for sql in queries)
