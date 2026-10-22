"""Exercise registered CLIs with isolated provider snapshots, never publication."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from test_m2_opportunity_discovery import (
    RUN_M2, _official_payload, _tencent_payload, _sina_payload,
    _dividend_payload, _financial_points,
)


@pytest.mark.parametrize('financial_mode', ['available', 'missing', 'empty', 'undated_points'])
def test_registered_fresh_cli_adopts_annual_and_replays_its_own_version(tmp_path, monkeypatch, capsys, financial_mode):
    root = tmp_path
    runtime = root / 'runtime'
    runtime.mkdir()
    output = runtime / 'new-scan'
    annual = [dict(p, data_point_id=f'annual-{i}') for i, p in enumerate(_financial_points())]
    export = {'points': [dict(p, period_label='2026-06-30') for p in _financial_points()],
              'annual_points': annual, 'generated_at': '2026-09-23T08:00:00+00:00'}
    if financial_mode == 'empty':
        export = {'points': []}
    elif financial_mode == 'undated_points':
        export = {'points': [{k: v for k, v in p.items() if k not in {'fetched_at', 'created_at'}}
                             for p in _financial_points()]}
    if financial_mode != 'missing':
        (runtime / 'server-export-payload.json').write_text(json.dumps(export), encoding='utf-8')
    calls = []

    def official(directory, project):
        calls.append('official')
        payload = _official_payload()
        path = RUN_M2._write(directory, 'official-universe.json', RUN_M2._json_bytes(payload))
        return payload, RUN_M2._reference('official', path, root=project,
            source_name='isolated fixture', source_url='https://example.test',
            fetched_at=RUN_M2._payload_fetched_at(payload, 'official'))

    def source(payload):
        payload = dict(payload, fetched_at='2026-09-23T08:00:00+00:00')
        return RUN_M2._json_bytes(payload), payload

    monkeypatch.setattr(RUN_M2, 'ROOT', root)
    monkeypatch.setattr(RUN_M2, '_collect_official', official)
    monkeypatch.setattr(RUN_M2, 'fetch_tencent_board_rank', lambda: source(_tencent_payload()))
    monkeypatch.setattr(RUN_M2, 'fetch_sina_industry_quotes', lambda: source(_sina_payload()))
    monkeypatch.setattr(RUN_M2, 'fetch_eastmoney_dividends', lambda **_: source(_dividend_payload()))
    monkeypatch.setattr(RUN_M2, 'write_discovery_workbook', lambda *a, **k: pytest.fail('Excel-frozen'))
    monkeypatch.setattr(sys, 'argv', ['run_m2_opportunity_discovery.py', '--no-wps',
                                    '--no-workbook', '--output-dir', str(output)])
    if financial_mode == 'undated_points':
        with pytest.raises(RuntimeError, match='no generated_at or point timestamp'):
            RUN_M2.main()
        assert not (output / 'manifest.json').exists()
        return
    assert RUN_M2.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['rule_version'] == 'm2-evidence-screen-v3'
    assert summary['input_mode'] == 'LIVE_COLLECTION'
    assert summary['current_publication_eligible'] is False
    assert summary['replay']['raw_inputs_match']
    financial = json.loads((output / 'retained-financial-points.json').read_text(encoding='utf-8'))
    if financial_mode == 'available':
        assert summary['financial_input']['annual_evidence_adoption']['added_rows'] == 9
        assert len(financial['points']) == 18
        assert financial['points'][-9:] == annual
    else:
        assert financial['points'] == [] and financial['retained_generated_at'] is None
        assert summary['financial_input']['status'] == 'NOT_AVAILABLE'
        assert summary['data_health']['financial_evidence_count'] == 0
        assert summary['channel_counts']['quality'] == 0
        receipt = json.loads((output / 'receipt.json').read_text(encoding='utf-8'))
        assert all(ref['id'] != 'financial' for ref in receipt['evidence_refs'])
        assert sum(summary['channel_counts'][key] for key in ('value', 'cyclical')) > 0
        assert summary['quote_date_verification'] == 'UNVERIFIED_PROVIDER_TRADE_DATE'
    assert not (output / 'm2-opportunity-discovery.xlsx').exists()
    assert not (root / 'config/current-daily-public-snapshot.json').exists()

    with pytest.raises(ValueError, match='new input directory'):
        RUN_M2.run_once(root=root, output_dir=output, wps_dir=None, max_per_channel=50,
                        skip_dividend=False, reuse_inputs=False, skip_workbook=True)
    assert calls == ['official']
    replay = RUN_M2.run_once(root=root, output_dir=output, wps_dir=None, max_per_channel=50,
        skip_dividend=False, reuse_inputs=True, skip_workbook=True)
    assert replay['rule_version'] == 'm2-evidence-screen-v3'
    assert replay['input_mode'] == 'HISTORICAL_REPLAY'
    assert replay['generated_at'] == summary['generated_at']
    assert replay['current_publication_eligible'] is False
    assert all(replay['replay'].values())
    assert replay['financial_input'] == summary['financial_input']
    assert calls == ['official']


def test_existing_publication_cli_blocks_historical_m2_publication(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/current/run_update_and_publish.py'
    spec = importlib.util.spec_from_file_location('m2_update_integration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, 'argv', [str(path), '--auto-marketwide',
        '--marketwide-replay-manifest', 'runtime/historical/manifest.json',
        '--marketwide-replay-manifest-sha256', 'a' * 64])
    monkeypatch.setattr(module, 'get_settings', lambda: pytest.fail('must reject before publication setup'))
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


def test_daily_safe_refresh_calls_registered_m2_without_replay_or_publication():
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / 'config/current-cli-entrypoints-v2.json').read_text(encoding='utf-8'))
    assert 'scripts/run_m2_opportunity_discovery.py' in registry['SUPPORTED_ENGINEERING_CLI']
    text = (root / 'scripts/current/run_daily_workbench.ps1').read_text(encoding='utf-8')
    start = text.index("if ($Mode -eq 'SAFE_REFRESH') {", text.index('$marketwideScreen = $null'))
    end = text.index('$reuse = Invoke-PythonJson', start)
    call = text[start:end]
    assert "'scripts/run_m2_opportunity_discovery.py'" in call
    assert "'--no-workbook'" in call
    assert '--reuse-inputs' not in call
    assert '--auto-marketwide' not in call
    assert 'receipt.marketwide_screen = $marketwideScreen' in text
