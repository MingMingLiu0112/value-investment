from contextlib import nullcontext
from types import SimpleNamespace

from value_investment_agent import cli


def test_update_evaluates_existing_points_outside_seed_universe(monkeypatch):
    connection = object()
    point = {'symbol': '000001', 'field_name': 'current_price', 'value': '10'}
    evaluated = {}
    completed = []
    monkeypatch.setattr(cli, 'get_settings', lambda: SimpleNamespace(
        database_url='unused', data_max_age_hours=30, price_conflict_tolerance='0.02'))
    monkeypatch.setattr(cli, 'connect', lambda _: nullcontext(connection))
    monkeypatch.setattr(cli, 'begin_run', lambda *args: 'run')
    monkeypatch.setattr(cli, 'UNIVERSE', [('600519',)])
    monkeypatch.setattr(cli, 'latest_points', lambda _: [point])
    monkeypatch.setattr(cli, 'build_reference_records', lambda *args: [])
    def evaluate(symbol, rows, *args):
        evaluated[symbol] = rows
        return symbol
    monkeypatch.setattr(cli, 'evaluate', evaluate)
    monkeypatch.setattr(cli, 'as_valuation_row', lambda result: result)
    monkeypatch.setattr(cli, 'upsert_valuation', lambda *args: None)
    monkeypatch.setattr(cli, '_refresh_financial_quality', lambda _: None)
    monkeypatch.setattr(cli, 'end_run', lambda *args: completed.append(args))
    cli.run_update(False, False, False)
    assert evaluated == {'600519': [], '000001': [point]}
    assert completed[0][2] == 'succeeded'
