"""Offline ledger invariants, without granting live-session credit."""
import json
import sys
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.operations import personal_shadow_observation as observation


def _candidate(root, day, run_id):
    receipt = root / f'{run_id}.json'
    receipt.write_text(json.dumps({'run_id': run_id}), encoding='utf-8')
    manifest = root / f'{run_id}-manifest.json'
    manifest.write_text(json.dumps({'bindings': {'run_receipt': {
        'path': receipt.name, 'sha256': sha256_file(receipt)}},
        'session_date': day}), encoding='utf-8')
    return manifest


def _append(monkeypatch, root, day, run_id, expected_head_sha256=observation.GENESIS):
    monkeypatch.setattr(observation, 'audit_shadow_daily_input',
        lambda **kwargs: {'session_date': day,
                          'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
                          'blockers': ['REAL_PROSPECTIVE_EVENT_INPUT_REQUIRED']})
    manifest = _candidate(root, day, run_id)
    return observation.append_offline_observation(root=root, ledger=root / 'ledger',
        manifest=manifest, expected_manifest_sha256=sha256_file(manifest),
        expected_head_sha256=expected_head_sha256,
        now=datetime(2026, 10, 3, tzinfo=timezone.utc))


def test_chain_duplicate_and_offline_credit(monkeypatch, tmp_path):
    first = _append(monkeypatch, tmp_path, '2026-10-01', 'run-1')
    second = _append(monkeypatch, tmp_path, '2026-10-02', 'run-2', first['record_sha256'])
    assert second['record']['predecessor_sha256'] == first['record_sha256']
    state = observation.verify_offline_observation_ledger(root=tmp_path,
        ledger=tmp_path / 'ledger', expected_head_sha256=second['record_sha256'])
    assert state['record_count'] == 2
    assert state['verified_real_session_count'] == 0
    with pytest.raises(ValueError, match='duplicate day/run'):
        _append(monkeypatch, tmp_path, '2026-10-02', 'run-3', second['record_sha256'])
    with pytest.raises(ValueError, match='duplicate day/run'):
        _append(monkeypatch, tmp_path, '2026-10-03', 'run-2', second['record_sha256'])
    with pytest.raises(ValueError, match='rollback'):
        _append(monkeypatch, tmp_path, '2026-09-30', 'run-4', second['record_sha256'])


def test_tamper_tail_and_missing_middle_fail(monkeypatch, tmp_path):
    first = _append(monkeypatch, tmp_path, '2026-10-01', 'run-1')
    second = _append(monkeypatch, tmp_path, '2026-10-02', 'run-2', first['record_sha256'])
    path = tmp_path / 'ledger' / '000001.json'
    path.write_bytes(path.read_bytes().replace(b'run-1', b'run-x'))
    with pytest.raises(ValueError, match='integrity'):
        observation.verify_offline_observation_ledger(root=tmp_path, ledger=tmp_path / 'ledger')
    path.write_bytes(observation.encode_json_bytes(first['record']))
    (tmp_path / 'ledger' / '000002.json').unlink()
    with pytest.raises(ValueError, match='external head'):
        observation.verify_offline_observation_ledger(root=tmp_path,
            ledger=tmp_path / 'ledger', expected_head_sha256=second['record_sha256'])
    with pytest.raises(ValueError, match='external head'):
        _append(monkeypatch, tmp_path, '2026-10-03', 'run-3', second['record_sha256'])
    (tmp_path / 'ledger' / '000003.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='gap'):
        observation.verify_offline_observation_ledger(root=tmp_path, ledger=tmp_path / 'ledger')


def test_existing_lock_is_not_removed(monkeypatch, tmp_path):
    ledger = tmp_path / 'ledger'
    ledger.mkdir()
    lock = ledger / '.append.lock'
    lock.write_text('other writer', encoding='utf-8')
    manifest = _candidate(tmp_path, '2026-10-01', 'run-1')
    with pytest.raises(FileExistsError):
        observation.append_offline_observation(root=tmp_path, ledger=ledger,
            manifest=manifest, expected_manifest_sha256=sha256_file(manifest),
            expected_head_sha256=observation.GENESIS,
            now=datetime.now(timezone.utc))
    assert lock.read_text(encoding='utf-8') == 'other writer'


def test_existing_cli_appends_offline_only_and_rejects_extra_inputs(monkeypatch, tmp_path, capsys):
    from scripts.current import audit_m6_start_criteria as cli

    (tmp_path / 'runtime').mkdir()
    manifest = _candidate(tmp_path, '2026-10-01', 'cli-run')
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(observation, 'audit_shadow_daily_input', lambda **kwargs: {
        'session_date': '2026-10-01', 'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
        'blockers': ['TEST_ONLY_MISSING_QUOTE'],
    })
    args = ['audit_m6_start_criteria.py', '--governance-profile', 'personal-observation-v1',
            '--daily-input', manifest.name, '--daily-input-sha256', sha256_file(manifest),
            '--offline-observation-ledger', 'runtime/ledger',
            '--expected-ledger-head-sha256', observation.GENESIS]
    monkeypatch.setattr(sys, 'argv', args)
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['record']['verified_real_session_count'] == 0
    assert result['record']['blockers'] == ['TEST_ONLY_MISSING_QUOTE']
    assert len(list((tmp_path / 'runtime/ledger').glob('*.json'))) == 1
    with pytest.raises(ValueError, match='external head'):
        cli.main()
    monkeypatch.setattr(sys, 'argv', args + ['--quote-input', 'ignored.json'])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
