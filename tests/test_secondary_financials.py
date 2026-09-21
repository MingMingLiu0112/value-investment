from pathlib import Path
import pytest


def test_secondary_financial_collection_is_part_of_scheduled_filing_pipeline() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_collect_filings.source.sh').read_text(encoding='utf-8')

    assert 'collect-secondary-financials --limit 120' in script
    assert script.index('collect-secondary-financials --limit 120') < script.index('auto-verify-filings --limit 300')
    assert '--add-host="money.finance.sina.com.cn:116.133.8.236"' in script


def test_secondary_abstract_uses_selected_official_report_period():
    from value_investment_agent import cli
    import inspect
    source = inspect.getsource(cli.collect_secondary_financials)
    assert 'o.symbol, o.report_period' in source
    assert 'DISTINCT ON (o.symbol, o.report_period)' in source
    assert "abstract_adapter.fetch([row['symbol']], report_period=row['report_period'])" in source
    assert "statements_adapter.fetch([row['symbol']], report_period=row['report_period'])" in source
    assert "'operating_cost','revenue','net_income'" in source


@pytest.mark.parametrize('fail_all', [False, True])
def test_secondary_network_has_no_open_transaction_and_failures_are_isolated(monkeypatch, fail_all):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from value_investment_agent import cli

    class Connection:
        active = True
        committed = []
        pending = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            return SimpleNamespace(fetchall=lambda: [dict(symbol=s, report_period='2025-12-31')
                                                    for s in ['000001','000002','000003']])

        def commit(self):
            self.active = False

        @contextmanager
        def transaction(self):
            assert not self.active
            self.active = True
            self.pending = []
            try:
                yield
                self.committed.extend(self.pending)
            finally:
                self.active = False

    db = Connection()

    class Adapter:
        def fetch(self, symbols, **kwargs):
            assert not db.active, 'Network call must not hold a transaction'
            if fail_all or symbols == ['000002']:
                raise RuntimeError('fixture provider failure')
            return symbols

    class PeriodBoundStatements(Adapter):
        def fetch(self, symbols, **kwargs):
            assert kwargs == {'report_period': '2025-12-31'}
            return super().fetch(symbols, **kwargs)

    def store(connection, record, status):
        assert connection.active
        connection.pending.append(record)

    results, statuses = [], []
    monkeypatch.setattr(cli,'get_settings',lambda: SimpleNamespace(database_url='unused', evidence_directory='unused'))
    monkeypatch.setattr(cli, 'archive_financial_records', lambda records, _: records)
    monkeypatch.setattr(cli,'connect',lambda _: db)
    monkeypatch.setattr(cli,'begin_run',lambda *args: 'run')
    monkeypatch.setattr(cli,'end_run',lambda *args: (statuses.append(args[-2]), results.append(args[-1])))
    monkeypatch.setattr(cli,'store_record',store)
    for name in ['SinaFinancialAdapter','AkshareFinancialAbstractAdapter','SinaFinancialStatementsAdapter']:
        monkeypatch.setattr(cli,name,Adapter)
    monkeypatch.setattr(cli, 'SinaFinancialStatementsAdapter', PeriodBoundStatements)
    with pytest.raises(SystemExit) as exit_info:
        cli.collect_secondary_financials(3)
    assert exit_info.value.code == 1
    assert statuses == ['failed']
    assert db.committed == ([] if fail_all else ['000001'] * 3 + ['000003'] * 3)
    assert results[0]['records_stored'] == (0 if fail_all else 6)
    assert len(results[0]['failed_symbols']) == (3 if fail_all else 1)
