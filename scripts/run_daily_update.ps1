[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$logDirectory = Join-Path $runtimeDirectory 'logs'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $logDirectory "daily-update-$timestamp.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Transcript -Path $logPath -Append | Out-Null

function Get-AgentPython {
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }

    $codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $codexPython) { return $codexPython }

    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) { return $systemPython.Source }
    throw 'Python was not found. Create .venv and install project dependencies.'
}

try {
    Set-Location $projectRoot
    $python = Get-AgentPython

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
        Write-Warning 'No .env found. Using the project defaults; configure .env before storing non-demo credentials.'
    }

    & $python -m value_investment_agent sync-excel
    if ($LASTEXITCODE -ne 0) { throw "Central database read or Excel sync failed. Exit code: $LASTEXITCODE" }

    Write-Host "Complete. Excel output: $(Join-Path $projectRoot 'runtime')"
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
