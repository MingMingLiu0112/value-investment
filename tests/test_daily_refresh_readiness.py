from datetime import datetime, timezone
import json

from value_investment_agent.application.product import daily_refresh as module


def test_reuse_requires_all_active_cases_not_retired_survivors(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    symbols = [str(i) for i in range(5)]
    (tmp_path / 'config/current-price-conditions.json').write_text(
        json.dumps({'items': [{'symbol': s} for s in symbols]}), encoding='utf-8')
    rows = [{'symbol': s, 'price_action_plan': {'market_trade_date': '2026-10-14',
             'daily_selection': {'rank': i}}} for i, s in enumerate(symbols)]
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {'items': rows})
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k:
        {'status': 'QUOTE_VERIFIED_BUT_RESEARCH_STALE', 'quote': {
            'quote_date': '2026-10-14', 'latest_completed_session': '2026-10-14'}})
    check = lambda: module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['600887'])
    assert check()['prices_ready'] and check()['quotes_ready']
    rows.pop()
    assert not check()['prices_ready']
    rows.append({'symbol': symbols[-1], 'price_action_plan': {'candidate_lifecycle': 'PREVIOUS'}})
    assert not check()['prices_ready']


def test_stale_or_failed_quote_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {'items': []})
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k:
        {'status': 'NOT_ADMITTED', 'quote': None})
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['600887'])
    assert not result['quotes_ready'] and not result['prices_ready']


def test_latest_run_only_exposes_status_not_secret(tmp_path):
    (tmp_path / '.tmp').mkdir()
    path = tmp_path / '.tmp/daily-workbench-latest-run.json'
    assert module.read_latest_run(tmp_path) is None
    path.write_text(json.dumps({'schema_version': 'daily-workbench-run-v1', 'action': 'no_order',
        'status': 'BLOCKED', 'published': False, 'retained_publication_id': 'pub-old',
        'bootstrap': 'never-return-this', 'notes': ['secret private/account.json',
        '本次更新尚未完成；继续显示历史已验证快照。']}), encoding='utf-8')
    receipt = module.read_latest_run(tmp_path)
    assert receipt['retained_publication_id'] == 'pub-old' and not receipt['published']
    assert 'bootstrap' not in receipt
    assert 'secret' not in json.dumps(receipt) and 'private/' not in json.dumps(receipt)
    assert '本次更新尚未完成；继续显示历史已验证快照。' in receipt['notes']


def test_startup_preserves_unknown_listener_and_checks_identity():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / 'scripts/current/start_web_workbench.ps1').read_text(encoding='utf-8')
    assert 'Stop-Process' not in text
    for field in ('CreationDate', 'ExecutablePath', 'OwningProcess', '127.0.0.1', 'TcpListener'):
        assert field in text


def test_quote_reuse_independent_of_missing_price_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k:
        {'items': [], 'blockers': []})
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k:
        {'status': 'QUOTE_VERIFIED_BUT_RESEARCH_STALE', 'quote': {
            'quote_date': '2026-10-14', 'latest_completed_session': '2026-10-14'}})
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['600887'])
    assert result['quotes_ready'] and not result['prices_ready']
    assert result['publication_ready'] and result['quote_securities'][0]['missing'] == []
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k:
        {'items': [], 'blockers': ['CURRENT_PRICE_REGISTRY_UNAVAILABLE']})
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['600887'])
    assert not result['publication_ready'] and not result['core_integrity_ok']
