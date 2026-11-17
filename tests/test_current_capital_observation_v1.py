"""TEST_ONLY original bytes and parser doubles, not actual PDF acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest

from value_investment_agent.application.research import current_capital_observation_v1 as mod

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []
    def forbidden(*args, **kwargs): pytest.fail('Network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    sources = []
    for index in range(2):
        path = tmp_path / f'TEST_ONLY_{index}.pdf'
        path.write_bytes(f'TEST_ONLY_NOT_A_REAL_PDF_{index}'.encode())
        sources.append(dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_url=f'https://static.cninfo.com.cn/finalpage/2026-10-30/{1000+index}.PDF',
            available_at='2026-10-30T09:00:00+08:00', report_period='2026-09-30', kind='q3'))
    registry = tmp_path / mod.REGISTRY
    registry.parent.mkdir(parents=True)
    def save():
        registry.write_text(json.dumps(dict(schema_version=mod.VERSION, action='no_order',
            cases={'123456': dict(sources=sources)})), encoding='utf-8')
    save()
    monkeypatch.setattr(mod, 'validate_pdf_original', lambda path: calls.append(('pdf', path.name)))
    monkeypatch.setattr(mod, 'extract_pages', lambda path: [path.name])
    def parse(pages, *, symbol):
        calls.append(('parse', pages[0]))
        return dict(status='VERIFIED', symbol=symbol, report_period='2026-09-30', kind='q3',
                    observations=[dict(field='TEST_ONLY_cash', value='12', unit='CNY')])
    monkeypatch.setattr(mod, 'parse_native_capital_observation', parse)
    return tmp_path, sources, registry, save, calls


def read(env): return mod.read_current_capital_observation(env[0], '123456', NOW)


def test_read_only_source_bound_success_without_current_continuity(env, monkeypatch):
    from pathlib import Path
    before = {str(p): p.read_bytes() for p in env[0].rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs): pytest.fail('Consumer attempted file write')
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    result = read(env)
    assert result['status'] == 'VERIFIED' and len(result['source_bound_observations']) == 2
    assert result['current_capital_continuity'] == 'NOT_PROVEN'
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert result['current_financial_coverage']['complete_current_coverage'] is False
    assert result['source_bound_observations'][0]['source']['sha256'] == env[1][0]['sha256']
    assert {str(p): p.read_bytes() for p in env[0].rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('damage', ['hash', 'future', 'naive', 'wronghost', 'http', 'query', 'bad_url_date',
    'future_report', 'absolute', 'traversal', 'missing_pdf', 'bad_pdf', 'parser_reject', 'symbol', 'period'])
def test_failed_source_preserves_other_and_reports_partial(env, monkeypatch, damage):
    root, sources, registry, save, calls = env
    source = sources[0]
    if damage == 'hash': source['sha256'] = 'a' * 64
    elif damage == 'future': source['available_at'] = '2027-01-01T00:00:00+08:00'
    elif damage == 'naive': source['available_at'] = '2026-10-30T09:00:00'
    elif damage == 'wronghost': source['source_url'] = source['source_url'].replace('static.cninfo.com.cn', 'example.com')
    elif damage == 'http': source['source_url'] = source['source_url'].replace('https:', 'http:')
    elif damage == 'query': source['source_url'] += '?x=1'
    elif damage == 'bad_url_date': source['source_url'] = source['source_url'].replace('2026-10-30', '2026-02-30')
    elif damage == 'future_report': source['report_period'] = '2026-12-31'
    elif damage == 'absolute': source['path'] = str(root / source['path'])
    elif damage == 'traversal': source['path'] = '../outside.pdf'
    elif damage == 'missing_pdf': (root / source['path']).unlink()
    elif damage == 'bad_pdf':
        def check(path):
            if path.name == source['path']: raise ValueError('TEST_ONLY_BAD_PDF')
        monkeypatch.setattr(mod, 'validate_pdf_original', check)
    else:
        original = mod.parse_native_capital_observation
        def changed(pages, *, symbol):
            result = original(pages, symbol=symbol)
            if pages[0] == source['path']:
                result.update(**({'status': 'PARTIAL'} if damage == 'parser_reject' else
                                 {'symbol': '654321'} if damage == 'symbol' else {'report_period': '2025-12-31'}))
            return result
        monkeypatch.setattr(mod, 'parse_native_capital_observation', changed)
    save()
    result = read(env)
    assert result['status'] == 'PARTIAL'
    assert len(result['source_bound_observations']) == 1
    assert result['source_bound_observations'][0]['source'] == sources[1]
    assert result['source_results'][0]['status'] == 'UNASSESSABLE'
    assert result['current_capital_continuity'] == 'NOT_PROVEN'


def test_duplicate_sources_all_rejected_not_first_wins(env):
    env[1].append(deepcopy(env[1][0])); env[3]()
    result = read(env)
    assert result['status'] == 'PARTIAL' and len(result['source_bound_observations']) == 1
    assert result['source_results'][0]['error_code'] == result['source_results'][2]['error_code'] == 'DUPLICATE_SOURCE'


@pytest.mark.parametrize('damage', ['json', 'duplicate_key', 'schema', 'case'])
def test_registry_corruption_unassessable(env, damage):
    root, sources, registry, save, calls = env
    if damage == 'json': registry.write_text('{', encoding='utf-8')
    elif damage == 'duplicate_key': registry.write_text('{"cases":{},"cases":{}}', encoding='utf-8')
    else:
        doc = json.loads(registry.read_bytes())
        if damage == 'schema': doc['schema_version'] = 'other'
        else: doc['cases']['123456']['sources'] = None
        registry.write_text(json.dumps(doc), encoding='utf-8')
    result = read(env)
    assert result['status'] == 'UNASSESSABLE' and calls == []
    assert result['source_bound_observations'] == []
    assert result['current_financial_coverage']['latest_report_period'] is None


def test_unregistered_not_started_and_no_sources_means_unknown(env):
    assert mod.read_current_capital_observation(env[0], '654321', NOW)['status'] == 'NOT_STARTED'
    env[2].unlink()
    assert read(env)['status'] == 'NOT_STARTED' and env[4] == []


@pytest.mark.parametrize('target', ['original', 'registry'])
def test_mutation_during_parse_cannot_publish_changed_evidence(env, monkeypatch, target):
    original = mod.parse_native_capital_observation
    def changing(pages, *, symbol):
        result = original(pages, symbol=symbol)
        if pages[0] == env[1][1]['path']:
            if target == 'original': (env[0] / env[1][0]['path']).write_bytes(b'TEST_ONLY_CHANGED')
            else: env[2].write_bytes(env[2].read_bytes() + b' ')
        return result
    monkeypatch.setattr(mod, 'parse_native_capital_observation', changing)
    result = read(env)
    if target == 'registry':
        assert result['status'] == 'UNASSESSABLE' and result['source_bound_observations'] == []
    else:
        assert result['status'] == 'PARTIAL' and len(result['source_bound_observations']) == 1
        assert result['source_results'][0]['error_code'] == 'ORIGINAL_CHANGED_DURING_READ'


@pytest.mark.parametrize('declared,parsed', [('annual', 'dividend_implementation'),
    ('q3', 'dividend_implementation'), ('dividend_implementation', 'annual')])
def test_report_and_implementation_kind_mismatch_not_admitted(env, monkeypatch, declared, parsed):
    env[1][0]['kind'] = declared
    env[3]()
    original = mod.parse_native_capital_observation
    def parse(pages, *, symbol):
        result = original(pages, symbol=symbol)
        if pages[0] == env[1][0]['path']: result['kind'] = parsed
        return result
    monkeypatch.setattr(mod, 'parse_native_capital_observation', parse)
    result = read(env)
    assert result['status'] == 'PARTIAL'
    assert result['source_results'][0]['error_code'] == 'NATIVE_OBSERVATION_KIND_MISMATCH'
    assert len(result['source_bound_observations']) == 1


@pytest.mark.parametrize('only_notice', [False, True])
def test_dividend_notice_preserves_policy_but_never_advances_financial_coverage(env, monkeypatch, only_notice):
    env[1][0].update(kind='dividend_implementation', report_period='2026-10-01')
    if only_notice: env[1].pop()
    env[3]()
    policy = dict(status='VERIFIED', policies=[dict(fiscal_year=2026, minimum_payout_ratio='0.5',
        minimum_distribution_cny=None, currency='CNY', scope='consolidated_parent')], evidence_pages=[1])
    original = mod.parse_native_capital_observation
    def parse(pages, *, symbol):
        result = original(pages, symbol=symbol)
        if pages[0] == env[1][0]['path']:
            result.update(kind='dividend_implementation', report_period='2026-10-01', dividend_policy=deepcopy(policy))
        return result
    monkeypatch.setattr(mod, 'parse_native_capital_observation', parse)
    result = read(env)
    assert result['status'] == 'VERIFIED'
    assert result['source_bound_observations'][0]['observation']['dividend_policy'] == policy
    coverage = result['current_financial_coverage']
    assert coverage['latest_report_period'] == (None if only_notice else '2026-09-30')
    assert coverage['report_periods'] == ([] if only_notice else ['2026-09-30'])
    assert coverage['status'] == ('UNKNOWN' if only_notice else 'REGISTERED_SOURCES_ONLY')
    assert result['current_capital_continuity'] == 'NOT_PROVEN'


def test_real_registered_four_sources_native_parser_contract(monkeypatch):
    real_root = os.environ.get('CAPITAL_OBSERVATION_REAL_ROOT')
    if not real_root:
        if os.environ.get('CAPITAL_OBSERVATION_REAL_REQUIRED') == '1':
            pytest.fail('CAPITAL_OBSERVATION_REAL_ROOT required')
        pytest.skip('Explicit opt-in retained public originals required')
    root = Path(real_root).resolve()
    registry = root / mod.REGISTRY
    assert registry.is_file(), 'Required retained registry missing'
    sources = json.loads(registry.read_bytes())['cases']['000568']['sources']
    assert len(sources) == 4
    paths = [registry] + [root / row['path'] for row in sources]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    def forbidden(*args, **kwargs): pytest.fail('Real replay is offline and read-only')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    result = mod.read_current_capital_observation(root, '000568', datetime.now(timezone.utc))
    assert result['status'] == 'VERIFIED', result['source_results']
    assert len(result['source_bound_observations']) == 4
    assert {r['observation']['kind'] for r in result['source_bound_observations']} == {
        'q3', 'interim', 'share_unlock_notice', 'dividend_implementation'}
    for row in result['source_bound_observations']:
        observed = row['observation']
        assert observed['kind'] == observed['report_kind'] == row['source']['kind']
        assert observed['report_period'] == row['source']['report_period']
        assert observed['status'] == 'VERIFIED'
    assert result['current_financial_coverage']['report_periods'] == ['2026-06-30', '2026-09-30']
    assert result['current_financial_coverage']['latest_report_period'] == '2026-09-30'
    assert result['current_capital_continuity'] == 'NOT_PROVEN'
    assert result['formal_eligibility'] is False
    assert {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths} == before


@pytest.mark.parametrize('field', ['observation_date', 'report_approved_date'])
@pytest.mark.parametrize('formed', ['2026-08-20', '2026-08-02'])
def test_native_formation_date_rejects_backdated_source(env, monkeypatch, field, formed):
    source = env[1][0]
    source.update(source_url=source['source_url'].replace('2026-10-30', '2026-08-01'),
                  available_at='2026-08-01T12:00:00+08:00', report_period='2026-06-30')
    env[3]()
    original = mod.parse_native_capital_observation
    def parse(pages, *, symbol):
        result = original(pages, symbol=symbol)
        if pages[0] == source['path']:
            result.update(report_period='2026-06-30', **{field: formed})
        return result
    monkeypatch.setattr(mod, 'parse_native_capital_observation', parse)
    result = mod.read_current_capital_observation(env[0], '123456', datetime(2026, 8, 2, tzinfo=timezone.utc))
    assert result['status'] == 'PARTIAL'
    assert result['source_results'][0]['error_code'] == 'NATIVE_FORMATION_DATE_AFTER_SOURCE_AVAILABILITY'
    assert result['source_bound_observations'] == []
    # Same original/hash remains rejected even after the native formation date passes:
    # the claimed URL publication and available_at are still too early.
    later = read(env)
    assert later['source_results'][0]['error_code'] == 'NATIVE_FORMATION_DATE_AFTER_SOURCE_AVAILABILITY'
    assert len(later['source_bound_observations']) == 1


@pytest.mark.parametrize('formed', ['2026-10-30', 'UNKNOWN', None])
def test_future_planned_action_dates_not_treated_as_future_source(env, monkeypatch, formed):
    original = mod.parse_native_capital_observation
    def parse(pages, *, symbol):
        result = original(pages, symbol=symbol)
        result.update(observation_date=formed, report_approved_date=formed,
                      record_date='2027-01-01', ex_date='2027-01-02',
                      payment_date='2027-01-03', effective_date='2027-01-04')
        return result
    monkeypatch.setattr(mod, 'parse_native_capital_observation', parse)
    result = read(env)
    assert result['status'] == 'VERIFIED'
    assert result['source_bound_observations'][0]['observation']['observation_date'] == formed
    assert result['source_bound_observations'][0]['observation']['payment_date'] == '2027-01-03'
    assert set(result['implementation_sha256']) == {'source_consumer', 'native_parser'}
