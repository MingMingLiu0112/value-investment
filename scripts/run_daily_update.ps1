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
    $workbooks = @(Get-ChildItem -LiteralPath $projectRoot -File -Filter '*.xlsx')
    if ($workbooks.Count -ne 1) {
        throw 'Expected exactly one canonical .xlsx workbook in the project root.'
    }
    for ($attempt = 1; $attempt -le 30; $attempt += 1) {
        try {
            $stream = [System.IO.File]::Open($workbooks[0].FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
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
