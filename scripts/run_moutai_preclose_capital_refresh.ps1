[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot 'runtime\logs'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Transcript -Path (Join-Path $logDirectory "moutai-preclose-capital-$timestamp.log") -Append | Out-Null
try {
    Set-Location $projectRoot
    $python = Join-Path $projectRoot 'runtime\venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $projectRoot 'runtime\test-venv\Scripts\python.exe' }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Project Python runtime is missing.' }
    $env:PYTHONUTF8 = '1'
    $env:VALUE_INVESTMENT_PYTHON = $python
    & $python -X utf8 scripts\prepare_moutai_preclose_capital_refresh.py
    if ($LASTEXITCODE -ne 0) { throw "Pre-close capital refresh failed. Exit code: $LASTEXITCODE" }
}
finally {
    Stop-Transcript | Out-Null
}
