"""Exercise the PowerShell readiness function without starting any server/browser."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe')
SCRIPT = ROOT / 'scripts/current/start_web_workbench.ps1'


@pytest.mark.parametrize('scenario, expected', [('ready', True), ('wrong_owner', False),
    ('exited', False), ('failed_http', False)])
def test_bounded_health_confirmation(scenario, expected):
    if not PWSH.is_file():
        pytest.skip('PowerShell 7 unavailable')
    source = SCRIPT.read_text(encoding='utf-8')
    function = source[source.index('function Wait-WorkbenchReady'):source.index('if (Test-Path -LiteralPath $statePath)')]
    process = '$null' if scenario == 'exited' else '@{Id=123}'
    owner = 456 if scenario == 'wrong_owner' else 123
    response = "throw 'HTTP unavailable'" if scenario == 'failed_http' else "[pscustomobject]@{paths=[pscustomobject]@{'/api/v1/daily-public-packet'=@{}}}"
    harness = function + f'''
function Get-Process {{ param($Id, $ErrorAction); {process} }}
function Get-NetTCPConnection {{ param($LocalPort,$State,$ErrorAction); [pscustomobject]@{{OwningProcess={owner}; LocalAddress='127.0.0.1'}} }}
function Invoke-RestMethod {{ param($Uri,$TimeoutSec); {response} }}
Wait-WorkbenchReady -ServerPid 123 -ServerPort 54321 -TimeoutSeconds 1
'''
    result = subprocess.run([str(PWSH), '-NoProfile', '-Command', harness],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(expected)


def test_browser_open_follows_backend_health_and_reauthorization_is_explicit():
    source = SCRIPT.read_text(encoding='utf-8')
    new_server = source[source.index('$server = Start-Process'):]
    assert new_server.index('Wait-WorkbenchReady') < new_server.index('Start-Process $unlockUrl')
    assert new_server.index('exit 4') < new_server.index('Write-Host $unlockUrl')
    assert 'if ($Reauthorize)' in source
    assert source.index('$owned.StartTime') < source.index('$owned.Kill()')
    entry = (ROOT / 'scripts/current/run_daily_workbench.ps1').read_text(encoding='utf-8')
    assert '-Reauthorize:$Reauthorize' in entry


@pytest.mark.parametrize('typed_date', [False, True])
def test_identity_accepts_json_date_types_and_normalized_root(typed_date):
    if not PWSH.is_file():
        pytest.skip('PowerShell 7 unavailable')
    source = SCRIPT.read_text(encoding='utf-8')
    function = source[source.index('function Test-WorkbenchIdentity'):source.index('function Wait-WorkbenchReady')]
    stamp = "[datetime]'2026-10-14T14:56:56.4536700Z'" if typed_date else "'2026-10-14T14:56:56.4536700Z'"
    harness = function + f'''
$state = [pscustomobject]@{{root='d:/GPTProject/value-investment/'; pid=123; port=8001; created_at={stamp}}}
$process = [pscustomobject]@{{ProcessId=123; CreationDate=[datetime]'2026-10-14T14:56:56.4536700Z'; ExecutablePath='D:\\APP\\Python313\\python.exe'; CommandLine='python -m uvicorn value_investment_agent.presentation.web_api.app:app'}}
$listeners = @([pscustomobject]@{{OwningProcess=123; LocalAddress='127.0.0.1'; LocalPort=8001}})
Test-WorkbenchIdentity $state $process $listeners 'D:\\GPTProject\\value-investment' 'D:\\APP\\Python313\\python.exe'
$state.created_at = [datetime]'2026-10-14T14:56:57Z'
Test-WorkbenchIdentity $state $process $listeners 'D:\\GPTProject\\value-investment' 'D:\\APP\\Python313\\python.exe'
'''
    result = subprocess.run([str(PWSH), '-NoProfile', '-Command', harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ['True', 'False']


@pytest.mark.parametrize('record', ['current', 'prior_8001'])
def test_actual_windows_starter_reuses_existing_process_without_mutation(record):
    if os.environ.get('P6_PROCESS_REUSE_QA') != '1' or not PWSH.is_file():
        pytest.skip('Explicit read-only live Windows acceptance required')
    state_path = ROOT / '.tmp/workbench-process.json'
    state_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    state = json.loads(state_path.read_bytes()) if record == 'current' else dict(
        root=str(ROOT), pid=37756, port=8001, created_at='2026-10-14T14:56:56.4536700Z')
    literal = json.dumps(state).replace("'", "''")
    # Fail closed if the actual starter tries to spawn anything. Override only
    # its state read for the overwritten prior record; query real CIM/TCP/HTTP.
    harness = f'''
function Start-Process {{ throw 'P6_PROCESS_CREATION_FORBIDDEN_DURING_READONLY_QA' }}
function Get-Content {{ param($LiteralPath,[switch]$Raw,$Encoding)
    if ($LiteralPath -like '*workbench-process.json') {{ return '{literal}' }}
    Microsoft.PowerShell.Management\\Get-Content @PSBoundParameters
}}
& '{str(SCRIPT)}' -Port 8001
'''
    result = subprocess.run([str(PWSH), '-NoProfile', '-Command', harness], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8', timeout=45)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f'http://127.0.0.1:{state["port"]}' in result.stdout
    assert '#unlock=' not in result.stdout
    assert hashlib.sha256(state_path.read_bytes()).hexdigest() == state_before
