[CmdletBinding()]
param(
    [string]$Server = $env:VALUE_AGENT_SERVER
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'workbook_path.ps1')
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$logDirectory = Join-Path $runtimeDirectory 'logs'
$keyPath = if ($env:VALUE_AGENT_SSH_KEY) { $env:VALUE_AGENT_SSH_KEY } else { Join-Path $env:USERPROFILE '.ssh\id_rsa' }
$payloadPath = Join-Path $runtimeDirectory 'server-export-payload.json'
$backupDirectory = Join-Path $runtimeDirectory 'workbook-backups'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$temporaryWorkbook = Join-Path $runtimeDirectory "workbook-preview-$timestamp.xlsx"
$downloadPath = Join-Path $runtimeDirectory "server-export-$timestamp.download.json"
$sshOptions = @('-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3')
$syncLock = $null
$publishPath = $null
$observationStatus = $null

if (-not $Server) { $Server = 'root@47.100.97.88' }
New-Item -ItemType Directory -Force -Path $logDirectory, $backupDirectory | Out-Null
Start-Transcript -Path (Join-Path $logDirectory "server-excel-sync-$timestamp.log") -Append | Out-Null

function Get-SharedFileHash([string]$Path) {
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '') }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function ConvertFrom-AgentJsonLine([string[]]$Output, [string]$Context) {
    $line = @($Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw "$Context did not produce a JSON result." }
    try { return $line[0] | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "$Context produced invalid final JSON: $($_.Exception.Message)" }
}

function Assert-MoutaiCurrentP1Ready([string]$ProjectRoot) {
    # The separately scheduled post-close task owns model construction. This
    # consumer only admits a same-date, already-audited P1 package.
    $researchDirectory = Join-Path $ProjectRoot 'runtime\company-research'
    $contractPointerPath = Join-Path $researchDirectory '600519-p1-model-contract-latest.json'
    $admissionPointerPath = Join-Path $researchDirectory '600519-current-valuation-admission-latest.json'
    foreach ($path in @($contractPointerPath, $admissionPointerPath)) {
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing post-close P1 pointer: $path" }
    }
    $contractPointer = Get-Content -LiteralPath $contractPointerPath -Raw | ConvertFrom-Json
    $contractPath = Join-Path $ProjectRoot ([string]$contractPointer.path)
    if (-not (Test-Path -LiteralPath $contractPath)) { throw 'Pinned P1 contract directory is missing.' }
    $contractEvidencePath = Join-Path $contractPath 'evidence.json'
    if ((Get-FileHash -LiteralPath $contractEvidencePath -Algorithm SHA256).Hash.ToLower() -ne ([string]$contractPointer.sha256).ToLower()) {
        throw 'Pinned P1 contract evidence hash changed.'
    }
    $contract = Get-Content -LiteralPath $contractEvidencePath -Raw | ConvertFrom-Json
    $modelReference = $contract.inputs.current_model
    if ($contract.symbol -ne '600519' -or -not $modelReference) { throw 'Latest P1 contract is outside the current Moutai scope.' }
    $modelPath = Join-Path $ProjectRoot ([string]$modelReference.path)
    if (-not (Test-Path -LiteralPath $modelPath)) { throw 'Pinned P1 current model is missing.' }
    if ((Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLower() -ne ([string]$modelReference.sha256).ToLower()) {
        throw 'Pinned P1 current model hash changed.'
    }
    $model = Get-Content -LiteralPath $modelPath -Raw | ConvertFrom-Json
    $today = (Get-Date).ToString('yyyy-MM-dd')
    if ([DateTimeOffset]::Parse([string]$model.valuation_at).ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd') -ne $today) {
        throw 'Current P1 model is stale for this quote session; refusing daily paper-account cycle.'
    }
    $admissionPointer = Get-Content -LiteralPath $admissionPointerPath -Raw | ConvertFrom-Json
    $admissionPath = Join-Path $ProjectRoot ([string]$admissionPointer.path)
    if (-not (Test-Path -LiteralPath $admissionPath)) { throw 'Pinned current P1 admission directory is missing.' }
    $admissionEvidencePath = Join-Path $admissionPath 'evidence.json'
    if ((Get-FileHash -LiteralPath $admissionEvidencePath -Algorithm SHA256).Hash.ToLower() -ne ([string]$admissionPointer.sha256).ToLower()) {
        throw 'Pinned current P1 admission evidence hash changed.'
    }
    $admission = Get-Content -LiteralPath $admissionEvidencePath -Raw | ConvertFrom-Json
    if ($admission.p1_current_model_admitted -ne $true -or $admission.trade_approved -ne $false) {
        throw 'Current P1 admission is not restricted to the permitted paper-research scope.'
    }
    return @{ contract = [string]$contractPointer.path; model = [string]$modelReference.path; admission = [string]$admissionPointer.path }
}

function Update-MoutaiCurrentObservation([string]$Python, [string]$ProjectRoot) {
    try {
        $p1 = Assert-MoutaiCurrentP1Ready -ProjectRoot $ProjectRoot
        $collectionText = [string[]](& $Python scripts\collect_quote_sessions.py --symbols 600519)
        if ($LASTEXITCODE -ne 0) { throw "Quote collection failed. Exit code: $LASTEXITCODE" }
        $collection = ConvertFrom-AgentJsonLine -Output $collectionText -Context 'Quote collection'
        $collectionPath = [IO.Path]::GetFullPath([string]$collection.path)
        $report = Join-Path $collectionPath 'report.json'
        if (-not (Test-Path -LiteralPath $report)) { throw "Archived quote report was not found: $report" }
        $executionText = [string[]](& $Python scripts\prepare_moutai_current_execution_contract.py --quote-report $report)
        if ($LASTEXITCODE -ne 0) { throw "Current execution-contract preparation failed. Exit code: $LASTEXITCODE" }
        $execution = ConvertFrom-AgentJsonLine -Output $executionText -Context 'Current execution-contract preparation'
        $contract = [string]$execution.contract.output
        $observationText = [string[]](& $Python scripts\run_moutai_simulation_closure.py --daily-paper --current-quote-report $report --execution-contract $contract)
        if ($LASTEXITCODE -ne 0) { throw "Daily paper-account cycle failed. Exit code: $LASTEXITCODE" }
        return @{ status = 'succeeded'; p1 = $p1; collection = $collection; execution = $execution; observation = (ConvertFrom-AgentJsonLine -Output $observationText -Context 'Daily paper-account cycle') }
    }
    catch {
        return @{ status = 'failed'; error = $_.Exception.Message }
    }
}

try {
    Set-Location $projectRoot
    $syncLock = [System.IO.File]::Open((Join-Path $runtimeDirectory 'excel-sync.lock'), [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    $env:PYTHONUTF8 = '1'
    $python = Join-Path $runtimeDirectory 'venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $runtimeDirectory 'test-venv\Scripts\python.exe' }
    if ($env:VALUE_AGENT_PYTHON) { $python = $env:VALUE_AGENT_PYTHON }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Set VALUE_AGENT_PYTHON to a Python environment with openpyxl installed.' }
    $workbook = Get-AgentWorkbook -ProjectRoot $projectRoot
    $templateHash = Get-SharedFileHash $workbook.FullName
    $observationStatus = Update-MoutaiCurrentObservation -Python $python -ProjectRoot $projectRoot
    if ($observationStatus.status -eq 'succeeded' -and $observationStatus.observation.status -ne 'unchanged') {
        $publishOutput = & $python scripts\publish_moutai_case_workbook.py $workbook.FullName 2>&1
        if ($LASTEXITCODE -ne 0) {
            $observationStatus.localWorkbookPublication = @{ status = 'failed'; output = [string]::Join([Environment]::NewLine, [string[]]$publishOutput) }
        }
        else {
            $observationStatus.localWorkbookPublication = @{ status = 'published'; output = [string]::Join([Environment]::NewLine, [string[]]$publishOutput) }
            $templateHash = Get-SharedFileHash $workbook.FullName
        }
    }
    elseif ($observationStatus.status -eq 'succeeded') {
        $observationStatus.localWorkbookPublication = @{ status = 'not_needed'; reason = 'decision_relevant_observation_unchanged' }
    }

    if (-not (Test-Path -LiteralPath $keyPath)) { throw "Sync SSH key was not found: $keyPath" }

    $remotePath = '/opt/value-investment-agent/exports/latest.json'
    $hashOutput = & ssh.exe -i $keyPath @sshOptions $Server "sha256sum $remotePath"
    if ($LASTEXITCODE -ne 0) { throw 'Server export checksum request failed.' }
    $remoteHash = ($hashOutput | Select-Object -First 1).Split()[0].ToLower()
    if ($remoteHash -notmatch '^[a-f0-9]{64}$') { throw 'Server export did not return a SHA-256 checksum.' }
    $localHash = if (Test-Path -LiteralPath $payloadPath) { (Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256).Hash.ToLower() } else { '' }
    if ($localHash -ne $remoteHash) {
        & scp.exe -C -O -i $keyPath @sshOptions "${Server}:$remotePath" $downloadPath
        if ($LASTEXITCODE -ne 0) { throw "Server payload download failed. Exit code: $LASTEXITCODE" }
        $localHash = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash.ToLower()
        if ($localHash -ne $remoteHash) { throw 'Server export checksum mismatch; refusing workbook update.' }
        Move-Item -LiteralPath $downloadPath -Destination $payloadPath -Force
    }
    else { Write-Host 'Server checksum matches the cached payload; no download needed.' }
    & $python scripts\sync_workbook.py $workbook.FullName $payloadPath $temporaryWorkbook
    if ($LASTEXITCODE -ne 0) { throw "Workbook generation failed. Exit code: $LASTEXITCODE" }
    & $python scripts\validate_workbook_output.py $workbook.FullName $payloadPath $temporaryWorkbook
    if ($LASTEXITCODE -ne 0) { throw "Workbook validation failed; refusing publication. Exit code: $LASTEXITCODE" }
    # Stage on the workbook's volume so final replacement stays atomic across C: and D:.
    $publishPath = Join-Path $workbook.DirectoryName ('.value-agent-' + [guid]::NewGuid().ToString('N') + '.tmp')
    Copy-Item -LiteralPath $temporaryWorkbook -Destination $publishPath
    if ((Get-SharedFileHash $publishPath) -ne (Get-SharedFileHash $temporaryWorkbook)) { throw 'Workbook staging checksum mismatch.' }
    $locked = $false
    try {
        $stream = [System.IO.File]::Open($workbook.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        $stream.Close()
    }
    catch { $locked = $true }
    $changed = (Get-SharedFileHash $workbook.FullName) -ne $templateHash
    if ($locked -or $changed) {
        @{ status = 'staged_not_published'; workbook = $temporaryWorkbook; canonicalLocked = $locked; templateChanged = $changed; payloadSha256 = $localHash; currentObservation = $observationStatus; at = (Get-Date -Format o) } |
            ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'excel-sync-status.json') -Encoding UTF8
        Write-Warning "Canonical workbook is locked or changed. Fresh report is available: $temporaryWorkbook"
        return
    }
    Copy-Item -LiteralPath $workbook.FullName -Destination (Join-Path $backupDirectory "$($workbook.BaseName)-$timestamp.xlsx")
    [System.IO.File]::Replace($publishPath, $workbook.FullName, [NullString]::Value)
    Remove-Item -LiteralPath $temporaryWorkbook
    @{ status = 'published'; workbook = $workbook.FullName; payloadSha256 = $localHash; currentObservation = $observationStatus; at = (Get-Date -Format o) } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'excel-sync-status.json') -Encoding UTF8
    if ($observationStatus.status -ne 'succeeded') {
        throw ('Current Moutai observation failed; remote payload synchronization does not count as a successful daily paper cycle: ' + $observationStatus.error)
    }
    Write-Host "Complete. Workbook updated from server export at $(Get-Date -Format o)."
}
catch {
    @{ status = 'failed'; preview = $temporaryWorkbook; error = $_.Exception.Message; currentObservation = $observationStatus; at = (Get-Date -Format o) } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'excel-sync-status.json') -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($publishPath -and (Test-Path -LiteralPath $publishPath)) { Remove-Item -LiteralPath $publishPath -ErrorAction SilentlyContinue }
    if ($syncLock) { $syncLock.Dispose() }
    Stop-Transcript | Out-Null
}
