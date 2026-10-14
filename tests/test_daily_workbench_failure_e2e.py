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
