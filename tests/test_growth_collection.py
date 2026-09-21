from dataclasses import replace
from contextlib import nullcontext
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from value_investment_agent import growth_collection as module
from value_investment_agent.models import SourceRecord


def record(period, **changes):
    base = SourceRecord('000581', 'revenue', period, Decimal(100), 'CNY',
                        module.SOURCES['revenue'], 'https://example.invalid/source',
                        None, datetime.now(timezone.utc), 'test', b'raw')
    return replace(base, **changes)


def test_collection_requests_exact_consecutive_periods_and_source(monkeypatch):
    calls = []
    def fetch(self, symbols, report_period):
        calls.append((symbols, report_period))
        return [record(report_period), record(report_period, field_name='total_revenue', value=Decimal(999))]
    monkeypatch.setattr(module.SinaFinancialStatementsAdapter, 'fetch', fetch)
    pairs = module.collect_inputs('000581', '2025-12-31', {'revenue'})
    assert calls == [(['000581'], '2025-12-31'), (['000581'], '2024-12-31')]
    assert pairs['revenue'][0].value == 100


@pytest.mark.parametrize('change', [dict(source_name='wrong'), dict(period_label='2024-06-30'),
                                   dict(symbol='000001'), dict(unit='CNY 10K')])
def test_collection_rejects_wrong_scope(monkeypatch, change):
    monkeypatch.setattr(module.SinaFinancialStatementsAdapter, 'fetch',
                        lambda self, symbols, report_period: [replace(record(report_period), **change)])
    with pytest.raises(ValueError, match='Missing or conflicting'):
        module.collect_inputs('000581', '2025-12-31', {'revenue'})


def test_collection_rejects_conflicting_duplicate_values(monkeypatch):
    monkeypatch.setattr(module.SinaFinancialStatementsAdapter, 'fetch',
                        lambda self, symbols, report_period: [record(report_period), record(report_period, value=Decimal(99))])
    with pytest.raises(ValueError, match='conflicting'):
        module.collect_inputs('000581', '2025-12-31', {'revenue'})


def test_selector_limit_is_companies_and_rejects_wrong_year():
    base = dict(disclosure_id='a', symbol='000581', report_period='2025-12-31',
                field_name='revenue_yoy', excerpt='2025 \u5e74 2024 \u5e74 \u672c\u5e74\u6bd4\u4e0a\u5e74\u589e\u51cf')
    rows = [dict(base, disclosure_id='wrong', excerpt='2024 \u5e74 2023 \u5e74 \u672c\u5e74\u6bd4\u4e0a\u5e74\u589e\u51cf'),
            base, dict(base, field_name='net_income_yoy'), dict(base, disclosure_id='b')]
    class DB:
        def execute(self, sql, params):
            assert 'interval \'6 hours\'' in sql
            assert params == (module.TASK,)
            return SimpleNamespace(fetchall=lambda: rows)
    selected = module.select_reports(DB(), 1)
    assert len(selected) == 1
    assert selected[0]['fields'] == {'revenue', 'net_income'}


@pytest.mark.parametrize('limit', [0, 21])
def test_batch_rejects_unbounded_limit(limit):
    with pytest.raises(ValueError):
        module.collect_growth_evidence(limit)


def test_busy_batch_does_not_select_or_fetch(monkeypatch):
    class DB:
        def execute(self, sql, params=None):
            return SimpleNamespace(fetchone=lambda: {'acquired': False})
    monkeypatch.setattr(module, 'connect', lambda _: nullcontext(DB()))
    monkeypatch.setattr(module, 'get_settings', lambda: SimpleNamespace(database_url='unused'))
    monkeypatch.setattr(module, 'select_reports', lambda *args: pytest.fail('Busy batch selected work'))
    assert module.collect_growth_evidence(1)['status'] == 'already_running'


@pytest.mark.parametrize('failure', ['hash', 'build'])
def test_issuer_failure_rolls_back_and_next_issuer_completes(monkeypatch, tmp_path, failure):
    path = tmp_path / 'official.pdf'
    path.write_bytes(b'official fixture')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reports = [dict(symbol=symbol, report_period='2025-12-31', local_path=str(path),
                    sha256='bad' if failure == 'hash' and index == 0 else digest, fields={'revenue'})
               for index, symbol in enumerate(['000581', '000623'])]

    class DB:
        def __init__(self):
            self.pending = []
            self.persisted = []
            self.sql = []
            self.rollbacks = 0

        def execute(self, sql, params=None):
            self.sql.append(sql)
            return SimpleNamespace(fetchone=lambda: {'acquired': True})

        def commit(self):
            self.persisted.extend(self.pending)
            self.pending.clear()

        def rollback(self):
            self.rollbacks += 1
            self.pending.clear()

    db = DB()
    monkeypatch.setattr(module, 'connect', lambda _: nullcontext(db))
    monkeypatch.setattr(module, 'get_settings', lambda: SimpleNamespace(database_url='unused'))
    monkeypatch.setattr(module, 'select_reports', lambda *args: reports)
    monkeypatch.setattr(module, 'collect_inputs', lambda symbol, period, fields: {
        'revenue': (record(period, symbol=symbol, value=Decimal(120)),
                    record('2024-12-31', symbol=symbol))})
    original_builder = module.build_growth_evidence
    def build(current, previous, current_id, previous_id):
        if failure == 'build' and current.symbol == '000581':
            raise ValueError('Synthetic invalid growth input')
        return original_builder(current, previous, current_id, previous_id)
    monkeypatch.setattr(module, 'build_growth_evidence', build)
    def store(connection, point, status):
        assert status == 'pending'
        connection.pending.append(point)
        return str(len(connection.pending))
    monkeypatch.setattr(module, 'store_record', store)

    result = module.collect_growth_evidence(2)
    assert result['requested'] == 2 and result['growth_records'] == 1
    assert [row['symbol'] for row in result['failures']] == ['000581']
    assert len(db.persisted) == 3
    assert {point.symbol for point in db.persisted} == {'000623'}
    assert not any((point.point_metadata or {}).get('automatic_cross_source_verification')
                   for point in db.persisted)
    assert db.rollbacks >= 1
    assert any('pg_advisory_unlock' in sql for sql in db.sql)
