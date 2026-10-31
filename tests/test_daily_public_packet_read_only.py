"""Read the retained public bytes, never build/repair or acquire data."""
from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def seed_snapshot(root, state='valid'):
    if state == 'missing':
        return
    from value_investment_agent.application.product.daily_public_packet import packet_content_sha256
    config, runtime = root / 'config', root / 'runtime'
    config.mkdir(exist_ok=True)
    runtime.mkdir(exist_ok=True)
    packet = dict(action='no_order', publication_id='pub-TEST_ONLY', packet_status='CURRENT')
    packet['content_sha256'] = packet_content_sha256(packet)
    raw = json.dumps(packet).encode('utf-8')
    (runtime / 'packet.json').write_bytes(raw)
    pointer = dict(schema_version='current-daily-public-snapshot-v1', action='no_order',
        status='VERIFIED', packet_path='runtime/packet.json',
        packet_sha256=hashlib.sha256(raw).hexdigest(),
        content_sha256=packet['content_sha256'], publication_id=packet['publication_id'])
    (config / 'current-daily-public-snapshot.json').write_text(
        '{bad' if state == 'malformed' else json.dumps(pointer), encoding='utf-8')
    if state == 'tampered':
        (runtime / 'packet.json').write_bytes(raw + b' ')


@pytest.fixture
def cli(monkeypatch):
    module = runpy.run_path(str(ROOT / 'scripts/current/build_daily_public_packet.py'))
    main = module['main']
    def forbidden(*args, **kwargs):
        raise AssertionError('READ_ONLY attempted build/write/network/process')
    for name in ('build_daily_public_packet', 'write_new_json', 'publish_snapshot', '_publish'):
        monkeypatch.setitem(main.__globals__, name, forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    return main


@pytest.mark.parametrize('state,code', [('valid', 0), ('missing', 2), ('malformed', 2), ('tampered', 2)])
def test_read_only_uses_native_snapshot_verifier_without_mutation(cli, monkeypatch, tmp_path, capsys, state, code):
    from test_daily_workbench_entry import _tree
    seed_snapshot(tmp_path, state)
    before = _tree(tmp_path)
    monkeypatch.setitem(cli.__globals__, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['build_daily_public_packet.py', '--read-only'])
    native_open = builtins.open
    def read_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), 'file write'
        return native_open(file, mode, *args, **kwargs)
    with monkeypatch.context() as guard:
        guard.setattr(builtins, 'open', read_open)
        guard.setattr(Path, 'write_bytes', lambda *args, **kwargs: pytest.fail('write'))
        guard.setattr(Path, 'write_text', lambda *args, **kwargs: pytest.fail('write'))
        guard.setattr(Path, 'mkdir', lambda *args, **kwargs: pytest.fail('mkdir'))
        assert cli() == code
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == ('VERIFIED_READ_ONLY' if code == 0 else 'BLOCKED')
    assert result['published'] is False
    assert result['action'] == 'no_order'
    assert _tree(tmp_path) == before


@pytest.mark.parametrize('extra', [['--no-publish'], ['--output-dir', 'runtime/new'],
    ['--generated-at', '2026-10-25'], ['--excel', 'NEVER_READ.xlsx'], ['--unknown']])
def test_read_only_rejects_build_parameters_before_loading(cli, monkeypatch, tmp_path, extra):
    monkeypatch.setitem(cli.__globals__, 'load_current_packet', lambda *args: pytest.fail('read before rejection'))
    monkeypatch.setattr(sys, 'argv', ['build_daily_public_packet.py', '--read-only', *extra])
    with pytest.raises(SystemExit) as error:
        cli()
    assert error.value.code == 2
