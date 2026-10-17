"""Real Windows CLI acceptance in an isolated project with retained public bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_safe_refresh_failure_keeps_previous_snapshot_bytes(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = tmp_path / 'isolated-project'
    project.mkdir()
    for directory in ('src', 'scripts'):
        shutil.copytree(ROOT / directory, project / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (project / 'config').mkdir()
    # No workbook/private data is copied or consulted. Missing active inputs
    # and the unavailable network must never republish the retained snapshot.
    for name in ('current-daily-public-snapshot.json', 'current-quote-bridge.json'):
        shutil.copy2(ROOT / 'config' / name, project / 'config' / name)
    pointer = project / 'config/current-daily-public-snapshot.json'
    old = json.loads(pointer.read_bytes())
    artifact = project / old['packet_path']
    artifact.parent.mkdir(parents=True)
    shutil.copy2(ROOT / old['packet_path'], artifact)
    shutil.copy2(ROOT / 'tests/fixtures/p6_network_unavailable/sitecustomize.py',
                 project / 'src/sitecustomize.py')
    original_pointer_sha = digest(ROOT / 'config/current-daily-public-snapshot.json')
    before, artifact_before = digest(pointer), digest(artifact)
    command = [str(PWSH), '-NoProfile', '-File',
               str(project / 'scripts/current/run_daily_workbench.ps1'),
               '-Mode', 'SAFE_REFRESH', '-NoServer']
    completed = subprocess.run(command, cwd=project, capture_output=True, text=True,
                               encoding='utf-8', timeout=180)
    receipt = json.loads((project / '.tmp/daily-workbench-latest-run.json').read_text(encoding='utf-8-sig'))
    output = completed.stdout + completed.stderr
    failures = [failure for path in (project / 'runtime/quote-sessions').glob('*/bundle.json')
                for failure in json.loads(path.read_bytes()).get('request_failures', [])]
    result = dict(schema_version='p6-refresh-failure-e2e-v1', action='no_order',
        execution='ACTUAL_WINDOWS_PWSH_SAME_SAFE_REFRESH_NOSERVER',
        injection=['missing_public_input_registry', 'network_connect_denied_in_isolated_python'],
        exit_code=completed.returncode, status=receipt['status'], published=receipt['published'],
        retained_publication_id=receipt['retained_publication_id'],
        finished_at=receipt['finished_at'], pointer_sha_before=before, pointer_sha_after=digest(pointer),
        packet_sha_before=artifact_before, packet_sha_after=digest(artifact),
        original_pointer_unchanged=digest(ROOT / 'config/current-daily-public-snapshot.json') == original_pointer_sha,
        network_failure_observed=bool(failures) and all(
            'P6_ISOLATED_NETWORK_UNAVAILABLE' in failure.get('error', '') for failure in failures),
        network_failed_request_count=len(failures),
        no_server_observed='-NoServer' in output,
        excel_or_private_copied=False,
        script_sha256=digest(project / 'scripts/current/run_daily_workbench.ps1'))
    destination = os.environ.get('P6_FAILURE_RECEIPT')
    if destination:
        target = Path(destination).resolve()
        assert target.is_relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert completed.returncode != 0, output
    assert receipt['status'] != 'SUCCESS' and receipt['published'] is False
    assert result['pointer_sha_before'] == result['pointer_sha_after']
    assert result['packet_sha_before'] == result['packet_sha_after']
    assert result['original_pointer_unchanged']
    assert result['network_failure_observed'] and result['no_server_observed'], output


@pytest.mark.parametrize('scenario,expected_exit,expected_status,published', [
    ('complete', 0, 'SUCCESS', True),
    ('partial', 3, 'PARTIAL', True),
    ('incremental_unavailable', 3, 'PARTIAL', True),
    ('unavailable', 2, 'BLOCKED', False),
    ('core_conflict', 2, 'BLOCKED', False),
    ('core_unavailable', 2, 'BLOCKED', False),
    ('core_recovered', 0, 'SUCCESS', True),
    ('post_integrity_loss', 2, 'BLOCKED', False),
    ('post_unreadable', 2, 'BLOCKED', False),
])
def test_windows_entry_distinguishes_partial_from_core_failure(tmp_path, scenario,
                                                             expected_exit, expected_status, published):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = tmp_path / scenario
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    (project / 'src/value_investment_agent').mkdir(parents=True)
    (project / 'src/value_investment_agent/__init__.py').write_text('', encoding='utf-8')
    (project / 'config').mkdir()
    pointer = project / 'config/current-daily-public-snapshot.json'
    pointer.write_text(json.dumps({'publication_id': 'retained'}), encoding='utf-8')
    (project / 'config/current-quote-bridge.json').write_text(
        json.dumps({'quotes': {'600887': {}}}), encoding='utf-8')
    shutil.copy2(ROOT / 'scripts/current/run_daily_workbench.ps1', current)
    packet = dict(action='no_order', publication_id='verified', source_bindings_verified=True)
    # Stub only child adapters in the isolated project; execute the real PS entry.
    build_exit = 4 if scenario == 'core_conflict' else 2 if scenario == 'core_unavailable' else 0
    (current / 'build_daily_public_packet.py').write_text(
        'import json,sys\nfrom pathlib import Path\n'
        f'packet=json.loads({json.dumps(packet)!r})\n'
        'counter=Path(".tmp/build-calls")\n'
        'count=int(counter.read_text())+1 if counter.exists() else 1\n'
        'counter.write_text(str(count))\n'
        f'scenario={scenario!r}\n'
        'if scenario == "post_integrity_loss" and count > 1:\n'
        '    packet["source_bindings_verified"]=False\n'
        'if scenario == "post_unreadable" and count > 1:\n'
        '    print("invalid packet output")\n'
        '    raise SystemExit(0)\n'
        'if "--no-publish" not in sys.argv:\n'
        '    packet["snapshot"]={"publication_id":"verified","status":"VERIFIED"}\n'
        '    Path("config/current-daily-public-snapshot.json").write_text(json.dumps(packet))\n'
        f'print(json.dumps(packet))\nraise SystemExit(2 if scenario == "core_recovered" and count == 1 else {build_exit})\n', encoding='utf-8')
    readiness = dict(prices_ready=scenario in {'complete', 'core_recovered', 'incremental_unavailable'}, quotes_ready=True,
        publication_ready=scenario != 'unavailable', core_integrity_ok=True,
        market_trade_dates=['2026-10-14'], price_securities=[], quote_securities=[])
    refresh = dict(status='WRITTEN', items=[], failures=[] if scenario in {'complete', 'incremental_unavailable'} else [
        dict(symbol='300001', reason='missing 15m')])
    (current / 'refresh_current_price_conditions.py').write_text(
        'import json,sys\n'
        f'value=json.loads({json.dumps(readiness)!r}) if "--check-reuse" in sys.argv else json.loads({json.dumps(refresh)!r})\n'
        'print(json.dumps(value))\n', encoding='utf-8')
    (current / 'collect_registered_validity_scan.py').write_text(
        'import json,sys\n'
        f'failed={scenario == "incremental_unavailable"!r}\n'
        'print(json.dumps({"binding_ref":{"path":"runtime/TEST_ONLY-scan.json","sha256":"a"*64}}))\n'
        'raise SystemExit(2 if failed else 0)\n', encoding='utf-8')
    (current / 'review_registered_research_validity.py').write_text(
        'import json\nprint(json.dumps({"reviews":[{"symbol":"600887",'
        '"model_validity_status":"UNKNOWN","status":"REQUIRES_MATERIALITY_REVIEW"}]}))\n',
        encoding='utf-8')
    before = pointer.read_bytes()
    completed = subprocess.run([str(PWSH), '-NoProfile', '-File',
        str(current / 'run_daily_workbench.ps1'), '-Mode', 'SAFE_REFRESH', '-NoServer'],
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60)
    receipt = json.loads((project / '.tmp/daily-workbench-latest-run.json').read_text(encoding='utf-8-sig'))
    assert completed.returncode == expected_exit, completed.stdout + completed.stderr
    assert receipt['status'] == expected_status and receipt['published'] is published
    assert receipt['finished_at']
    assert int((project / '.tmp/build-calls').read_text()) == (3 if published else 2)
    if not published:
        assert pointer.read_bytes() == before
        assert receipt['retained_publication_id'] == 'retained'
    else:
        assert json.loads(pointer.read_bytes())['publication_id'] == 'verified'
