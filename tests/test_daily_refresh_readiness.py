from datetime import datetime, timezone
import json
import hashlib
import pytest

from value_investment_agent.application.product import daily_refresh as module


def test_current_scan_summary_is_pinned_and_never_promoted_to_trade_eligibility(tmp_path):
    path = tmp_path / 'runtime/daily-marketwide/run/manifest.json'
    path.parent.mkdir(parents=True)
    value = {'summary': {'action': 'no_order', 'input_mode': 'LIVE_COLLECTION',
        'rule_version': 'm2-evidence-screen-v3', 'as_of': '2026-10-20',
        'quote_date_verification': 'UNVERIFIED_PROVIDER_TRADE_DATE',
        'data_health': {'universe_count': 5575, 'status': 'PARTIAL'},
        'channel_counts': {'quality': 0, 'value': 50},
        'legacy_comparison': {'new_candidate_count': 111}, 'secret': 'DO_NOT_EXPOSE'}}
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    pin = {'manifest_path': path.relative_to(tmp_path).as_posix(),
           'manifest_sha256': hashlib.sha256(raw).hexdigest()}
    result = module._screening_summary(tmp_path, pin)
    assert result['universe_count'] == 5575 and result['lead_count'] == 111
    assert result['scope'] == 'RESEARCH_LEADS_NOT_ACTIONS'
    assert result['formal_eligibility'] is False
    assert 'DO_NOT_EXPOSE' not in repr(result)
    path.write_bytes(raw + b' ')
    assert module._screening_summary(tmp_path, pin)['status'] == 'UNVERIFIED'
    assert module._screening_summary(tmp_path, {'manifest_path': '../manifest.json',
        'manifest_sha256': pin['manifest_sha256']})['status'] == 'UNVERIFIED'


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
    assert not check()['continuity_ready']
    monkeypatch.setattr(module, 'read_observation_changes', lambda *a, **k: {'status': 'SOURCE_REVALIDATED'})
    assert check()['continuity_ready']
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


def test_single_selected_candidate_and_quote_failure_are_independent(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/current-price-conditions.json').write_text(
        json.dumps({'items': [{'symbol': '300059'}], 'selected_symbols': ['300059']}),
        encoding='utf-8')
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {
        'items': [{'symbol': '300059', 'price_action_plan': {
            'market_trade_date': '2026-10-14', 'daily_selection': {'rank': 1}}}]})
    def bridge(root, symbol, **kwargs):
        if symbol == '600519':
            raise ValueError('private source details must not be exposed')
        return {'status': 'QUOTE_VERIFIED_BUT_RESEARCH_STALE', 'quote': {
            'quote_date': '2026-10-14', 'latest_completed_session': '2026-10-14'}}
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', bridge)
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc),
                                      symbols=['600519', '600887'])
    assert result['prices_ready'] and result['publication_ready']
    assert not result['quotes_ready']
    assert result['quotes']['600519']['status'] == 'QUOTE_READ_FAILED'
    assert result['quote_securities'][1]['status'] == 'VERIFIED'
    assert 'private source' not in json.dumps(result)


def test_verified_empty_selection_publishes_without_value_quotes_only_on_selection_day(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/current-price-conditions.json').write_text(
        json.dumps({'items': [], 'selected_symbols': []}), encoding='utf-8')
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {
        'status': 'CURRENT_EMPTY_SELECTION', 'selection_trade_date': '2026-10-15',
        'items': [], 'blockers': []})
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k: {
        'status': 'NOT_ADMITTED', 'quote': None})
    current = module.refresh_readiness(tmp_path,
        now=datetime.fromisoformat('2026-10-15T17:00:00+08:00'), symbols=['600887'])
    assert current['publication_ready'] and current['prices_ready']
    assert not current['quotes_ready']
    assert current['quote_securities'][0]['status'] == 'MISSING_OR_INVALID'
    later = module.refresh_readiness(tmp_path,
        now=datetime.fromisoformat('2026-10-16T17:00:00+08:00'), symbols=['600887'])
    assert not later['publication_ready'] and not later['prices_ready']


def test_pending_incremental_model_does_not_hide_independently_verified_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {'items': [], 'blockers': []})
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k: {
        'status': 'INCREMENTAL_VALIDITY_BLOCKED',
        'quote_verification_status': 'QUOTE_VERIFIED_BUT_RESEARCH_STALE',
        'quote': {'quote_date': '2026-10-15', 'latest_completed_session': '2026-10-15'},
        'price_admitted': False})
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['600887'])
    assert result['quotes_ready'] and result['publication_ready']
    assert result['quote_securities'][0]['status'] == 'VERIFIED'
    assert result['quotes']['600887']['price_admitted'] is False


def test_quote_only_observation_ready_without_promoting_research_or_old_close(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'load_price_conditions', lambda *a, **k: {'items': [], 'blockers': []})
    quote = {'status': 'QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY',
             'quote': {'quote_date': '2026-10-15', 'latest_completed_session': '2026-10-15'},
             'price_admitted': False, 'research_case': None}
    monkeypatch.setattr(module, 'execute_quote_bridge_for_symbol', lambda *a, **k: quote)
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['000333'])
    assert result['quotes_ready'] and result['publication_ready']
    assert result['quotes']['000333']['price_admitted'] is False
    assert result['quotes']['000333']['research_case'] is None
    quote['quote']['latest_completed_session'] = '2026-10-16'
    result = module.refresh_readiness(tmp_path, now=datetime.now(timezone.utc), symbols=['000333'])
    assert not result['quotes_ready'] and not result['publication_ready']


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


def _node_receipt():
    return {'schema_version': 'daily-workbench-run-v1', 'action': 'no_order',
        'status': 'PARTIAL', 'published': True, 'notes': [],
        'node_receipt_scope': 'COMMAND_EXECUTION_ONLY_NOT_DATA_ADMISSION',
        'nodes': [{'sequence': 1, 'command': 'scripts/run_m2_opportunity_discovery.py',
            'operation': 'RUN', 'started_at': '2026-10-22T09:00:00+00:00',
            'finished_at': '2026-10-22T09:00:01+00:00', 'execution_status': 'FAILED',
            'exit_code': 2, 'output_status': 'INVALID_JSON',
            'raw_output': 'secret private/account.json', 'argv': ['private/account.json']}]}


def test_node_receipts_are_execution_only_and_do_not_expose_raw_diagnostics(tmp_path):
    (tmp_path / '.tmp').mkdir()
    (tmp_path / '.tmp/daily-workbench-latest-run.json').write_text(
        json.dumps(_node_receipt()), encoding='utf-8')
    result = module.read_latest_run(tmp_path)
    assert result['node_receipt_scope'] == 'COMMAND_EXECUTION_ONLY_NOT_DATA_ADMISSION'
    assert result['nodes'][0]['execution_status'] == 'FAILED'
    assert result['nodes'][0]['exit_code'] == 2
    assert not {'raw_output', 'argv', 'formal_eligibility'} & result['nodes'][0].keys()
    assert 'private/' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [
    ('sequence', True), ('sequence', 2), ('command', 'private/account.json'),
    ('operation', 'TRADE'), ('execution_status', 'SUCCEEDED'), ('exit_code', False),
    ('finished_at', '2026-10-22T08:59:59+00:00'), ('started_at', '2026-10-22T09:00:00'),
    ('output_status', 'PENDING'), ('output_status', 'secret'),
])
def test_untrusted_node_metadata_fails_closed(field, value):
    receipt = _node_receipt()
    receipt['nodes'][0][field] = value
    assert module._node_execution_summary(receipt) == {}


def test_running_node_receipt_is_not_a_success():
    receipt = _node_receipt()
    receipt['nodes'][0].update(execution_status='RUNNING', exit_code=None,
        finished_at=None, output_status='PENDING')
    result = module._node_execution_summary(receipt)
    assert result['nodes'][0]['execution_status'] == 'RUNNING'
    assert result['nodes'][0]['exit_code'] is None
    receipt['nodes'].append({**receipt['nodes'][0], 'sequence': 2})
    assert module._node_execution_summary(receipt) == {}


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


def test_priority_summary_is_bound_and_not_an_investment_rank(tmp_path):
    import hashlib
    from value_investment_agent.application.research.value_research_queue import _canonical_hash
    path = tmp_path / 'runtime/daily-marketwide/test/research-priority-v2.json'
    path.parent.mkdir(parents=True)
    queue = {'schema_version': 'value-research-priority-v2', 'action': 'no_order',
        'admission': 'RESEARCH_QUEUE_ONLY', 'as_of': '2026-10-20',
        'deep_research_priority': [], 'evidence_enrichment_work_queue': [{'symbol': '600519'}],
        'selected_deep_research_count': 0, 'selected_enrichment_count': 1}
    queue['content_sha256'] = _canonical_hash(queue)
    path.write_text(json.dumps(queue), encoding='utf-8')
    binding = {'path': path.relative_to(tmp_path).as_posix(),
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    result = module._priority_summary(tmp_path, binding)
    assert result['status'] == 'VERIFIED_RESEARCH_PRIORITY'
    assert result['enrichment_count'] == 1 and result['formal_eligibility'] is False
    assert 'symbol' not in json.dumps(result)
    path.write_text('{}', encoding='utf-8')
    assert module._priority_summary(tmp_path, binding)['status'] == 'UNVERIFIED'
    binding['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert module._priority_summary(tmp_path, binding)['status'] == 'UNVERIFIED'
    binding['path'] = '../../private.json'
    assert module._priority_summary(tmp_path, binding)['status'] == 'UNVERIFIED'


def test_enrichment_summary_cannot_promote_or_misbind_execution(tmp_path):
    import hashlib
    folder = tmp_path / 'runtime/run'
    folder.mkdir(parents=True)
    path = folder / 'execution.json'
    queue = {'content_sha256': 'a' * 64, 'evidence_enrichment_work_queue': [
        {'symbol': '600519', 'company_name': 'TEST_ONLY'}]}
    body = {'schema_version': 'value-enrichment-execution-v1', 'action': 'no_order',
        'queue_content_sha256': 'a' * 64, 'formal_eligibility': False, 'new_fact_approvals': 0,
        'attempted_count': 1, 'items': [{'symbol': '600519', 'state': 'DATA_UNAVAILABLE',
            'formal_eligibility': False, 'transitions': ['QUALITY_REEVALUATED'],
            'extracted_candidates': 10, 'matched_candidates': 8}]}
    def read():
        path.write_text(json.dumps(body), encoding='utf-8')
        binding = {'path': path.relative_to(tmp_path).as_posix(),
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        return module._enrichment_execution_summary(tmp_path, folder, binding, queue)
    result = read()
    assert result['attempted_count'] == result['reevaluated_count'] == result['data_gap_count'] == 1
    assert result['formal_eligibility'] is False
    body['new_fact_approvals'] = 1
    assert read()['status'] == 'UNVERIFIED'
    body['new_fact_approvals'] = 0
    body['queue_content_sha256'] = 'b' * 64
    assert read()['status'] == 'UNVERIFIED'
