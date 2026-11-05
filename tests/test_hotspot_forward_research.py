from copy import deepcopy
from datetime import datetime
import base64
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot import forward_research as service
from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case
from value_investment_agent.infrastructure.hotspot.sina_price_case import decode_klines
from value_investment_agent.quote_sessions import CHINA
from test_hotspot_candidate_selection import _fixture
from test_hotspot_current_price_case import Response

FREEZE = datetime(2026, 9, 26, 17, tzinfo=CHINA)
OBSERVE = datetime(2026, 9, 28, 16, 15, tzinfo=CHINA)


def setup(root):
    watch, _, _, case = _fixture(root, count=1)
    pointer = root / 'config/current-price-conditions.json'
    original = pointer.read_bytes()
    binding = service.freeze_forward_research(root=root, candidate_binding=watch, test_only=True, now=FREEZE)
    bundle = json.loads((root / case['current_reference_close']['bundle_path']).read_bytes())
    return binding, bundle, pointer, original


def fresh_bundle(original, at=OBSERVE):
    bundle, mapping, documents = deepcopy(original), {}, {}
    for key, doc in bundle['documents'].items():
        raw = base64.b64decode(doc['raw_base64']).replace(b'20260924', at.strftime('%Y%m%d').encode()).replace(
            b'2026-09-24', at.date().isoformat().encode())
        doc.update(raw_base64=base64.b64encode(raw).decode(), sha256=hashlib.sha256(raw).hexdigest(),
                   fetched_at=at.isoformat())
        identity = hashlib.sha256((doc['source_url'] + '\n' + doc['fetched_at'] + '\n' + doc['sha256']).encode()).hexdigest()
        mapping[key], documents[identity] = identity, doc
    bundle['documents'] = documents
    for ref in bundle['references'].values():
        ids = ref['document_refs']
        for key in ('tencent', 'sina'):
            ids[key] = mapping[ids[key]]
        ids['calendar_documents'] = [mapping[item] for item in ids['calendar_documents']]
    bundle.update(started_at=at.isoformat(), finished_at=at.isoformat())
    return bundle


def capture(_drop_15m=False, **kwargs):
    def fetch(url, params, timeout):
        response = Response(params['scale'])
        rows = decode_klines(response.content)
        latest = [row for row in rows if row['day'].startswith('2026-09-24')]
        for day in range(28, kwargs['as_of'].day + 1):
            rows.extend(dict(row, day=row['day'].replace('2026-09-24', f'2026-09-{day}')) for row in latest)
        if _drop_15m and str(params['scale']) == '15':
            rows.pop(-2)
        response.content = ('=(' + json.dumps(rows) + ');').encode()
        return response
    return collect_current_price_case(**kwargs, fetch=fetch)


def test_forward_native_case_is_append_only_not_shadow_credit_or_current_update(tmp_path):
    binding, bundle, pointer, original = setup(tmp_path)
    receipt = service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
        now=OBSERVE, bundle_collector=lambda symbols: fresh_bundle(bundle), case_collector=capture)
    result = service._read(tmp_path, receipt)
    assert result['trade_date'] == '2026-09-28'
    assert result['elapsed_real_shadow_sessions'] == 0 and result['hypothetical_fills'] is None
    assert result['execution_status'] == 'UNASSESSABLE' and result['formal_eligibility'] is False
    assert result['observations'][0]['baseline']['elapsed_real_shadow_sessions'] == 0
    assert pointer.read_bytes() == original
    with pytest.raises(ValueError, match='Duplicate'):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=OBSERVE, bundle_collector=lambda symbols: pytest.fail('No duplicate collection'))


def test_missing_15m_path_rejected_by_native_loader_before_observation(tmp_path):
    binding, bundle, pointer, original = setup(tmp_path)
    with pytest.raises(ValueError, match='Complete frozen pool'):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=OBSERVE, bundle_collector=lambda symbols: fresh_bundle(bundle),
            case_collector=lambda **kwargs: capture(_drop_15m=True, **kwargs))
    failures = list((tmp_path / 'runtime/hotspot-forward-data').rglob('failure.json'))
    assert len(failures) == 1
    assert 'Incomplete 15m session' in json.loads(failures[0].read_bytes())['failures'][0]['reason']
    assert not list((tmp_path / 'runtime/hotspot-forward').rglob('receipt.json'))
    assert pointer.read_bytes() == original


def test_failure_retains_evidence_and_does_not_poison_retry_date(tmp_path):
    binding, bundle, pointer, original = setup(tmp_path)
    with pytest.raises(ValueError):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=OBSERVE, bundle_collector=lambda symbols: bundle, case_collector=capture)
    assert list((tmp_path / 'runtime/hotspot-forward-data').rglob('failure.json'))
    assert not list((tmp_path / 'runtime/hotspot-forward').rglob('receipt.json'))
    result = service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
        now=OBSERVE, bundle_collector=lambda symbols: fresh_bundle(bundle), case_collector=capture)
    assert service._read(tmp_path, result)['trade_date'] == '2026-09-28'
    assert pointer.read_bytes() == original


@pytest.mark.parametrize('clock', [FREEZE, datetime(2026, 9, 27, 16, tzinfo=CHINA),
                                   datetime(2026, 9, 28, 14, tzinfo=CHINA)])
def test_old_non_session_and_incomplete_dates_fail_before_network(tmp_path, clock):
    binding, _, _, _ = setup(tmp_path)
    with pytest.raises(ValueError):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=clock, bundle_collector=lambda symbols: pytest.fail('No collection'))


def test_code_drift_and_production_clock_injection_fail_closed(tmp_path, monkeypatch):
    binding, _, _, _ = setup(tmp_path)
    rules = service._rules()
    rules[0]['sha256'] = '0' * 64
    monkeypatch.setattr(service, '_rules', lambda: rules)
    with pytest.raises(ValueError, match='Frozen rules'):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=OBSERVE, bundle_collector=lambda symbols: pytest.fail('No collection'))
    with pytest.raises(ValueError, match='Clock injection'):
        service.freeze_forward_research(root=tmp_path, candidate_binding={}, now=FREEZE)


def test_prior_day_sources_are_replayed_before_next_collection(tmp_path):
    binding, bundle, pointer, original = setup(tmp_path)
    first = service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
        now=OBSERVE, bundle_collector=lambda symbols: fresh_bundle(bundle), case_collector=capture)
    first_result = service._read(tmp_path, first)
    following = datetime(2026, 9, 29, 16, 15, tzinfo=CHINA)
    second = service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
        now=following, bundle_collector=lambda symbols: fresh_bundle(bundle, following), case_collector=capture)
    second_result = service._read(tmp_path, second)
    assert second_result['elapsed_real_shadow_sessions'] == 0
    assert second_result['prior_observation_binding'] == first
    comparison = second_result['observations'][0]['prior_condition_comparison']
    assert comparison['volume_confirmation'] == comparison['condition_path']['volume_confirmation']
    assert comparison['condition_path']['original_condition'] == first_result['observations'][0]['baseline']['frozen_price_condition']
    assert comparison['condition_path']['action'] == 'no_order'
    assert comparison['real_trade'] is False and comparison['profit'] is None
    case_path = tmp_path / first_result['session_root'] / first_result['cases']['600519']['path']
    case_path.write_bytes(case_path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='hash changed'):
        service.observe_forward_research(root=tmp_path, manifest_binding=binding, test_only=True,
            now=datetime(2026, 9, 30, 16, tzinfo=CHINA),
            bundle_collector=lambda symbols: pytest.fail('Prior tampering must fail before collection'))
    assert pointer.read_bytes() == original


@pytest.mark.parametrize('location', ['report', 'classification'])
@pytest.mark.parametrize('namespace', ['TEST_ONLY', 'SIMULATED'])
def test_resealed_simulated_sources_cannot_enter_actual_freeze(tmp_path, location, namespace):
    binding, _, report, _ = _fixture(tmp_path, count=1)
    if location == 'report':
        report['namespace'] = namespace
    else:
        source = report['source_bindings'][0]
        path = tmp_path / source['path']
        content = json.loads(path.read_bytes())
        content['namespace'] = namespace
        path.write_text(json.dumps(content), encoding='utf-8')
        source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = tmp_path / binding['path']
    path.write_text(json.dumps(report), encoding='utf-8')
    binding['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='cannot enter ACTUAL'):
        service._selection(tmp_path, binding, FREEZE, False)
    assert not list((tmp_path / 'runtime/hotspot-forward').glob('*/manifest.json'))


@pytest.mark.parametrize('scenario', ['clean', 'drift', 'preloaded', 'warm'])
def test_actual_execution_requires_cold_source_identity(tmp_path, scenario):
    import shutil
    import subprocess
    import sys
    source = tmp_path / 'src'
    shutil.copytree(service.CODE_ROOT / 'src', source,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    prefix = tmp_path / '.tmp' / 'fresh-cache'
    command = [sys.executable, '-B']
    if scenario != 'warm':
        command += ['-X', f'pycache_prefix={prefix}']
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
scenario = sys.argv[1]
target = Path('src/value_investment_agent/application/hotspot/strategy_execution_replay.py')
if scenario == 'preloaded':
    from value_investment_agent.application.hotspot import strategy_execution_replay
    before = target.read_bytes()
    target.write_bytes(before.replace(b'0.0003', b'0.1234'))
    assert target.read_bytes() != before
from value_investment_agent.application.hotspot import forward_research as service
assert service._costs()['commission_rate'] == '0.0003'
if scenario == 'drift':
    before = target.read_bytes()
    target.write_bytes(before.replace(b'0.0003', b'0.1234'))
    assert target.read_bytes() != before
if scenario == 'clean':
    service._require_cold_execution(False)
else:
    for operation in (
        lambda: service.freeze_forward_research(root=Path.cwd(), candidate_binding={}),
        lambda: service._verify_freeze(Path.cwd(), {}, False, None),
    ):
        try:
            operation()
        except ValueError as exc:
            assert 'cold process' in str(exc) or 'source changed' in str(exc), str(exc)
        else:
            raise AssertionError('Mixed execution version accepted')
'''
    result = subprocess.run(command + ['-c', script, scenario], cwd=tmp_path,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
