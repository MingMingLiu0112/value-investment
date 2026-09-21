[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'workbook_path.ps1')
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$logDirectory = Join-Path $runtimeDirectory 'logs'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $logDirectory "daily-update-$timestamp.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Transcript -Path $logPath -Append | Out-Null

function Get-AgentPython {
    $python = Join-Path $runtimeDirectory 'venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $python) { return $python }
    $reportPython = Join-Path $runtimeDirectory 'test-venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $reportPython) { return $reportPython }
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }

    $codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $codexPython) { return $codexPython }

    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) { return $systemPython.Source }
    throw 'Python was not found. Create .venv and install project dependencies.'
}

function Assert-CentralDatabaseReachable {
    $envFile = Join-Path $projectRoot '.env'
    $databaseLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
    if (-not $databaseLine) {
        throw 'DATABASE_URL is missing from .env.'
    }
    $uri = [Uri]($databaseLine.Substring('DATABASE_URL='.Length))
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.BeginConnect($uri.Host, $uri.Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne(10000)) {
            throw 'timeout'
        }
        $client.EndConnect($connection)
    }
    catch {
        throw 'Cannot reach the central database private endpoint. Sign in to Tailscale and retry.'
    }
    finally {
        $client.Dispose()
    }
}

function Assert-WorkbookUnlocked {
    $workbookPath = Join-Path $projectRoot 'A股价值投资_Agent前端智能跟踪模板.xlsx'
    try {
        $stream = [System.IO.File]::Open($workbookPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        $stream.Close()
    }
    catch {
        throw 'The canonical Excel workbook is open or locked. Close it in WPS, then retry the sync.'
    }
}

function Assert-CanonicalWorkbookUnlocked {
    $workbook = Get-AgentWorkbook -ProjectRoot $projectRoot
    $env:WORKBOOK_PATH = $workbook.FullName
    for ($attempt = 1; $attempt -le 30; $attempt += 1) {
        try {
            $stream = [System.IO.File]::Open($workbook.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $stream.Close()
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    throw 'The canonical Excel workbook stayed open or locked for 60 seconds. Close it in WPS, then retry the sync.'
}

try {
    Set-Location $projectRoot
    # Task Scheduler starts with a minimal environment. Pin the project source,
    # UTF-8 output, and the bundled Node runtime used by the workbook exporter.
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    $env:PYTHONUTF8 = '1'
    $nodeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node'
    if (Test-Path -LiteralPath (Join-Path $nodeRoot 'bin\node.exe')) {
        $env:PATH = "$(Join-Path $nodeRoot 'bin');$env:PATH"
        $env:NODE_PATH = Join-Path $nodeRoot 'node_modules'
    }
    $python = Get-AgentPython
    Assert-CentralDatabaseReachable
    Assert-CanonicalWorkbookUnlocked

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
        Write-Warning 'No .env found. Using the project defaults; configure .env before storing non-demo credentials.'
    }

    & $python -m value_investment_agent sync-excel
    if ($LASTEXITCODE -ne 0) { throw "Central database read or Excel sync failed. Exit code: $LASTEXITCODE" }

    Write-Host "Complete. Canonical Excel workbook updated in place. Technical backup: $(Join-Path $runtimeDirectory 'workbook-backups')"
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
