"""TL9 MVP-2: the one daily entry stays thin, registered and fail-closed."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/current/run_daily_workbench.ps1"


def _pwsh() -> str | None:
    for name in ("pwsh", "pwsh.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def test_daily_entry_is_registered_in_both_registries():
    v2 = json.loads(
        (ROOT / "config/current-cli-entrypoints-v2.json").read_text(encoding="utf-8")
    )
    assert "scripts/current/run_daily_workbench.ps1" in v2["SUPPORTED_PRODUCT_CLI"]
    inventory = json.loads(
        (ROOT / "docs/architecture/script-inventory-v1.json").read_text(encoding="utf-8")
    )
    entry = next(
        item for item in inventory["entries"]
        if item["path"] == "scripts/current/run_daily_workbench.ps1"
    )
    assert entry["category"] == "CURRENT_PRODUCT_CLI"
    assert "config/current-cli-entrypoints-v2.json" in entry["current_consumers"]


def test_daily_entry_orchestrates_existing_clis_without_new_side_doors():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ValidateSet('READ_ONLY', 'SAFE_REFRESH')" in text
    # The entry orchestrates the existing packet builder, collector and Web
    # starter instead of re-implementing any business calculation.
    assert "scripts/current/build_daily_public_packet.py" in text
    assert "scripts/collect_quote_sessions.py" in text
    assert "scripts/current/pin_current_quote_bridge.py" in text
    assert "start_web_workbench.ps1" in text
    assert "-AutoDiscoverResearchContexts" in text
    assert "--discover-contexts" in text
    assert "--test-only-retrospective" in text
    assert "--authorize-paid-api" not in text
    # It never orders, never publishes the canonical workbook and never signs
    # a human approval.
    assert "action=no_order" in text
    assert "publish_product_workbench_to_canonical" not in text
    assert "git " not in text
    assert '--no-publish' in text
    assert 'open_current_trial_workbook.py' not in text


def test_event_review_day_is_independent_from_quote_reuse_and_always_fresh():
    text = SCRIPT.read_text(encoding="utf-8")
    review = text[text.index("# Filings can change on non-trading days"):
                  text.index("# Recompute after incremental registration")]
    assert "[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))" in review
    assert "$reviewCutoff-$scanStamp" in review
    assert "collect_registered_validity_scan.py" in review
    assert "'--review-cutoff', $reviewCutoff" in review
    assert "'--output-dir', $scanDirectory" in review
    assert "market_trade_dates" not in review
    assert "expected_session" not in review
    assert "incremental_validity_binding" not in review


def _tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            if p.is_file() else 'DIRECTORY' for p in root.rglob('*')}


def _isolated_entry(tmp_path):
    project = tmp_path / 'isolated-entry'
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    shutil.copy2(SCRIPT, current / SCRIPT.name)
    shutil.copy2(ROOT / 'scripts/current/build_daily_public_packet.py', current)
    shutil.copytree(ROOT / 'src', project / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Runs in the actual Python child. Reads/imports are allowed, writes,
    # network and further process creation are forbidden, not just mocked APIs.
    (project / 'src/sitecustomize.py').write_text('''import sys, os
def guard(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec')) or event == 'os.system':
        raise RuntimeError('READ_ONLY forbidden network/process')
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise RuntimeError('READ_ONLY forbidden file write')
    if event in {'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod', 'os.utime', 'os.link', 'os.symlink'}:
        raise RuntimeError('READ_ONLY forbidden mutation')
sys.addaudithook(guard)
''', encoding='utf-8')
    return project, current / SCRIPT.name


def _run_entry(script, project, *args):
    pwsh = _pwsh()
    if pwsh is None:
        pytest.skip("PowerShell 7 is unavailable")
    guards = '\n'.join(f"function {name} {{ throw 'READ_ONLY forbidden operation' }}" for name in (
        'New-Item', 'Set-Content', 'Add-Content', 'Move-Item', 'Remove-Item',
        'Start-Process', 'Invoke-WebRequest', 'Invoke-RestMethod', 'Get-NetTCPConnection'))
    quoted = ' '.join(str(arg) if str(arg).startswith('-') else
        "'" + str(arg).replace("'", "''") + "'" for arg in (script, *args))
    return subprocess.run(
        [pwsh, '-NoProfile', '-Command', "$ErrorActionPreference='Stop'\n" + guards + '\n& ' + quoted + '\nexit $LASTEXITCODE'],
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60,
    )


@pytest.mark.parametrize('pointer', ['missing', 'malformed', 'valid', 'tampered'])
def test_daily_entry_runs_read_only_and_reports_plain_language(tmp_path, pointer):
    project, script = _isolated_entry(tmp_path)
    from test_daily_public_packet_read_only import seed_snapshot
    seed_snapshot(project, pointer)
    # READ_ONLY must not even parse invalid refresh settings.
    config = project / 'config'
    config.mkdir(exist_ok=True)
    (config / 'public-research-refresh-v1.json').write_text('INVALID', encoding='utf-8')
    before = _tree(project)
    args = [] if pointer == 'valid' else ['-Mode', 'READ_ONLY', '-NoServer']
    completed = _run_entry(script, project, *args)
    output = completed.stdout or ""
    assert completed.returncode == (0 if pointer == 'valid' else 2), (output, completed.stderr)
    assert "运行结果" in output
    assert "action=no_order" in output
    assert 'http://127.0.0.1:8001/daily' in output
    assert _tree(project) == before
    assert not (project / '.tmp').exists()


@pytest.mark.parametrize('extra', [
    ['-Open'], ['-Reauthorize'], ['-Symbols', '600519'],
    ['-AutoDiscoverResearchContexts'], ['-RegisterResearchDrafts'],
    ['-BuildValueResearchPriority'], ['-ExecuteValueEnrichment'],
    ['-ResearchMockPlan', 'dummy'], ['-ResearchMockPlanSha256', '0' * 64],
    ['-ResearchTestOnlyRetrospective', 'dummy'],
    ['-ResearchTestOnlyRetrospectiveSha256', '0' * 64],
    ['-RetainedMarketwideManifest', 'dummy'],
    ['-RetainedMarketwideManifestSha256', '0' * 64],
])
def test_read_only_rejects_mutating_parameters_before_io(tmp_path, extra):
    project = tmp_path / 'rejected-entry'
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    script = current / SCRIPT.name
    shutil.copy2(SCRIPT, script)
    before = _tree(project)
    result = _run_entry(script, project, '-Mode', 'READ_ONLY', *extra)
    assert result.returncode != 0
    assert 'READ_ONLY rejects' in result.stderr
    assert _tree(project) == before


@pytest.mark.parametrize('mutation', [None, {'enabled': False}, {'unknown': True},
    {'execution_budget': 4}, {'priority_budget': 0}, {'enrichment_budget': 51},
    {'execution_budget': True}, {'priority_budget': 10.0}, {'enabled': 'true'},
    {'schema_version': 'unknown'}, {'action': 'order'}, {'action': ['no_order']},
    {'schema_version': ['public-research-refresh-v1']},
    {'build_value_research_priority': False}])
def test_safe_refresh_settings_validate_and_apply_before_writes(tmp_path, mutation):
    pwsh = _pwsh()
    if pwsh is None:
        pytest.skip('PowerShell 7 is unavailable')
    project = tmp_path / 'settings'
    config = project / 'config'
    config.mkdir(parents=True)
    settings = json.loads((ROOT / 'config/public-research-refresh-v1.json').read_text(encoding='utf-8'))
    settings.update(mutation or {})
    (config / 'public-research-refresh-v1.json').write_text(json.dumps(settings), encoding='utf-8')
    text = SCRIPT.read_text(encoding='utf-8')
    section = text[text.index('$priorityBudget = 10'):text.index("$env:TEMP = Join-Path")]
    command = ("$ErrorActionPreference='Stop'; $Mode='SAFE_REFRESH'; "
        "$BuildValueResearchPriority=$false; $ExecuteValueEnrichment=$false; "
        "$root='" + str(project).replace("'", "''") + "';\n" + section +
        '\n@{build=[bool]$BuildValueResearchPriority; execute=[bool]$ExecuteValueEnrichment; '
        'priority=$priorityBudget; enrichment=$enrichmentBudget; execution=$executionBudget} | ConvertTo-Json -Compress')
    before = _tree(project)
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command], capture_output=True,
        encoding='utf-8', timeout=30)
    assert _tree(project) == before
    if mutation not in (None, {'enabled': False}):
        assert result.returncode != 0
    else:
        assert result.returncode == 0, result.stderr
        flags = mutation is None
        assert json.loads(result.stdout) == dict(build=flags, execute=flags,
            priority=10, enrichment=10, execution=2)


@pytest.mark.parametrize('enabled,explicit,budgets', [
    (True, False, (1, 50, 3)), (False, True, (10, 10, 2)),
])
def test_settings_feed_existing_queue_command_without_new_execution_path(tmp_path, enabled, explicit, budgets):
    pwsh = _pwsh()
    if pwsh is None:
        pytest.skip('PowerShell 7 is unavailable')
    config = tmp_path / 'config'
    config.mkdir()
    settings = json.loads((ROOT / 'config/public-research-refresh-v1.json').read_text(encoding='utf-8'))
    settings.update(enabled=enabled, priority_budget=1, enrichment_budget=50, execution_budget=3)
    (config / 'public-research-refresh-v1.json').write_text(json.dumps(settings), encoding='utf-8')
    text = SCRIPT.read_text(encoding='utf-8')
    section = text[text.index('$priorityBudget = 10'):text.index("$env:TEMP = Join-Path")]
    queue = text[text.index('            $executionArgs = if ($ExecuteValueEnrichment)'):
                 text.index('            if ($queue.ExitCode -ne 0')]
    truth = '$true' if explicit else '$false'
    command = ("$ErrorActionPreference='Stop'; $Mode='SAFE_REFRESH'; "
        f'$BuildValueResearchPriority={truth}; $ExecuteValueEnrichment={truth}; '
        "$root='" + str(tmp_path).replace("'", "''") + "';\n" + section + '''
$scanManifest = @{files=@{lead_report=@{path='TEST_ONLY-report';sha256='test'};
    receipt=@{path='TEST_ONLY-receipt';sha256='test'};financial=@{path='TEST_ONLY-export';sha256='test'}}}
$queuePath='TEST_ONLY-queue'
function Invoke-PythonJson { param([string[]]$PythonArgs) $script:captured=$PythonArgs }
''' + queue + '\nConvertTo-Json -InputObject @($captured) -Compress')
    before = _tree(tmp_path)
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command],
        capture_output=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert _tree(tmp_path) == before
    args = json.loads(result.stdout)
    assert args[0] == 'scripts/current/build_value_research_queue.py'
    for key, expected in zip(('--budget', '--enrichment-budget', '--execution-budget'), budgets):
        assert args[args.index(key) + 1] == str(expected)
    assert '--execute-enrichment' in args
    assert '--allow-public-evidence-downloads' in args
    assert not any('mock' in arg.lower() or 'paid' in arg.lower() for arg in args)


@pytest.mark.parametrize('mutation', [None, 'malformed', {'unexpected': True},
    {'execution_budget': 4}, {'priority_budget': 0}, {'enrichment_budget': True}])
def test_actual_safe_refresh_entry_validates_settings_before_first_write(tmp_path, mutation):
    pwsh = _pwsh()
    if pwsh is None:
        pytest.skip('PowerShell 7 is unavailable')
    project = tmp_path / 'safe-prefix'
    current = project / 'scripts/current'
    config = project / 'config'
    current.mkdir(parents=True)
    config.mkdir()
    script = current / SCRIPT.name
    shutil.copy2(SCRIPT, script)
    settings = json.loads((ROOT / 'config/public-research-refresh-v1.json').read_text(encoding='utf-8'))
    if isinstance(mutation, dict):
        settings.update(mutation)
    (config / 'public-research-refresh-v1.json').write_text(
        '{bad' if mutation == 'malformed' else json.dumps(settings), encoding='utf-8')
    # Stop at, not after, the first mutation in the actual entry. No Python,
    # collection, service or receipt is permitted in this prefix acceptance.
    command = '''$ErrorActionPreference='Stop'
function New-Item {
    [Console]::WriteLine((@{build=[bool]$BuildValueResearchPriority; execute=[bool]$ExecuteValueEnrichment;
      priority=$priorityBudget; enrichment=$enrichmentBudget; execution=$executionBudget} | ConvertTo-Json -Compress))
    throw 'TEST_ONLY_FIRST_WRITE_BOUNDARY'
}
function Start-Process { throw 'TEST_ONLY_FORBIDDEN_PROCESS' }
function Invoke-WebRequest { throw 'TEST_ONLY_FORBIDDEN_NETWORK' }
function Invoke-RestMethod { throw 'TEST_ONLY_FORBIDDEN_NETWORK' }
& ''' + "'" + str(script).replace("'", "''") + "' -Mode SAFE_REFRESH -NoServer"
    before = _tree(project)
    result = subprocess.run([pwsh, '-NoProfile', '-Command', command],
        capture_output=True, encoding='utf-8', timeout=30)
    assert result.returncode != 0
    assert _tree(project) == before
    assert not (project / '.tmp').exists()
    if mutation is None:
        assert 'TEST_ONLY_FIRST_WRITE_BOUNDARY' in result.stderr
        assert json.loads(result.stdout) == dict(build=True, execute=True,
            priority=10, enrichment=10, execution=2)
    else:
        assert 'TEST_ONLY_FIRST_WRITE_BOUNDARY' not in result.stderr
        assert result.stdout.strip() == ''


def test_daily_entry_keeps_update_and_web_results_separate():
    """TL10-RC: a Web failure must never mask a failed update."""
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in ("运行结果", "公开快照", "Web 服务", "整体结果"):
        assert marker in text
    # The header documents the four update-first outcomes, including exit 4.
    assert "4  Web failed to start while the update itself succeeded" in text
    # Both Web-failure paths fall back to 4 only when the update reported 0.
    assert "} else { 4 }" in text
    assert "} elseif ($webExit -ne 0) { 4 } else { 0 }" in text
    assert "数据更新优先" in text
    # Still no shell-based repo mutation and no canonical workbook publish.
    assert "git " not in text
    assert "publish_product_workbench_to_canonical" not in text
    assert 'if (-not $coreBlocked)' in text
