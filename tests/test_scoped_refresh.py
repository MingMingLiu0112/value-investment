from types import SimpleNamespace

from value_investment_agent import cli, db


def test_latest_points_binds_scope_without_changing_latest_order():
    calls = []
    connection = SimpleNamespace(execute=lambda sql, args: (
        calls.append((sql, args)) or SimpleNamespace(fetchall=lambda: [])))
    for scope in (None, [], ['601088']):
        assert db.latest_points(connection, symbols=scope) == []
        sql, args = calls[-1]
        assert args == (False, scope, scope)
        assert 'p.symbol = ANY(%s::text[])' in sql
        assert 'p.period_label DESC, p.created_at DESC' in sql


def test_quality_refresh_loads_one_company_at_a_time(monkeypatch):
    symbols = ['601088', '600519']
    calls, evaluated, stored = [], [], []
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: [
        {'symbol': s, 'name': s, 'sector': 'test'} for s in symbols]))

    def points(connection, *, symbols, annual_only=False):
        assert len(symbols) == 1
        calls.append((symbols[0], annual_only))
        return [{'symbol': symbols[0], 'annual': annual_only}]

    def evaluate(symbol, name, sector, rows):
        assert all(r['symbol'] == symbol for r in rows)
        assert [r['annual'] for r in rows] == [False, True]
        evaluated.append(symbol)
        return symbol

    monkeypatch.setattr(cli, 'latest_points', points)
    monkeypatch.setattr(cli, 'build_verified_derivations', lambda rows, symbols: [])
    monkeypatch.setattr(cli, 'evaluate_financial_quality', evaluate)
    monkeypatch.setattr(cli, 'upsert_financial_quality', lambda connection, result: stored.append(result))
    assert cli._refresh_financial_quality(connection, symbols) == 2
    assert evaluated == stored == symbols
    assert calls == [(s, annual) for s in symbols for annual in (False, True, False, True)]
