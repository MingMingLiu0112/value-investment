import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows sync entry points')
HELPER = Path(__file__).resolve().parents[1] / 'scripts' / 'workbook_path.ps1'


def resolve(root, override=None):
    env = dict(os.environ, TEST_PROJECT=str(root), TEST_HELPER=str(HELPER))
    env.pop('WORKBOOK_PATH', None)
    if override is not None:
        env['WORKBOOK_PATH'] = str(override)
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         "$ErrorActionPreference='Stop'; . $env:TEST_HELPER; "
         '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; '
         '(Get-AgentWorkbook -ProjectRoot $env:TEST_PROJECT).FullName'],
        env=env, capture_output=True, text=True, encoding='utf-8',
    )


def test_external_workbook_from_dotenv(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    workbook = tmp_path / '\u4e91\u76d8 workbook.xlsx'
    workbook.touch()
    (project / '.env').write_text(f'WORKBOOK_PATH={workbook}\n', encoding='utf-8')
    result = resolve(project)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(workbook)


def test_environment_override_and_relative_fallback(tmp_path):
    workbook = tmp_path / 'research.xlsx'
    workbook.touch()
    (tmp_path / '.env').write_text('WORKBOOK_PATH=missing.xlsx\n', encoding='utf-8')
    result = resolve(tmp_path, 'research.xlsx')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(workbook)
    assert resolve(tmp_path).returncode != 0


def test_ambiguous_root_is_rejected(tmp_path):
    (tmp_path / 'a.xlsx').touch()
    (tmp_path / 'b.xlsx').touch()
    assert resolve(tmp_path).returncode != 0


def test_sync_uses_full_path_and_same_volume_replacement():
    script = (HELPER.parent / 'run_server_excel_sync.ps1').read_text(encoding='utf-8')
    assert 'scripts\\sync_workbook.py $workbook.FullName' in script
    assert 'Join-Path $workbook.DirectoryName' in script
    assert '[System.IO.File]::Replace($publishPath, $workbook.FullName, [NullString]::Value)' in script


def test_powershell_atomic_replace_with_no_backup_path(tmp_path):
    source = tmp_path / 'staged.tmp'
    target = tmp_path / 'canonical.xlsx'
    source.write_bytes(b'new workbook')
    target.write_bytes(b'old workbook')
    env = dict(os.environ, TEST_SOURCE=str(source), TEST_TARGET=str(target))
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         "$ErrorActionPreference='Stop'; "
         '[System.IO.File]::Replace($env:TEST_SOURCE, $env:TEST_TARGET, [NullString]::Value)'],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == b'new workbook'
    assert not source.exists()
def test_sync_validates_before_staging_and_replacing_workbook():
    script = (HELPER.parent / 'run_server_excel_sync.ps1').read_text(encoding='utf-8')
    generation = script.index('& $python scripts\\sync_workbook.py')
    validation = script.index('& $python scripts\\validate_workbook_output.py')
    gate = script.index('Workbook validation failed; refusing publication.')
    staging = script.index('Copy-Item -LiteralPath $temporaryWorkbook')
    publication = script.index('[System.IO.File]::Replace')
    assert generation < validation < gate < staging < publication
