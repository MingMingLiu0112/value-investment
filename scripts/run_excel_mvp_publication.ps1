[CmdletBinding()]
param(
    [switch]$Publish,
    [string]$Workbook = 'C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx'
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime'
$backups = Join-Path $runtime 'workbook-backups'

function Get-ProjectPython {
    foreach ($candidate in @(
        (Join-Path $runtime 'venv\Scripts\python.exe'),
        (Join-Path $runtime 'test-venv\Scripts\python.exe')
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Project Python runtime is missing.'
}

function Invoke-ProjectPython([string]$Python, [string[]]$Arguments, [string]$Name) {
    & $Python -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
}

try {
    Set-Location $root
    $source = (Resolve-Path -LiteralPath $Workbook).Path
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $python = Get-ProjectPython

    Invoke-ProjectPython $python @('scripts\preview_workbook_frontdoor.py', '--workbook', $source, '--skip-render') 'Workbook candidate build'
    $candidateDirectory = Get-ChildItem -LiteralPath $backups -Directory -Filter 'frontdoor-*' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $candidateDirectory) { throw 'Workbook candidate directory is missing.' }
    $verificationPath = Join-Path $candidateDirectory.FullName 'verification.json'
    if (-not (Test-Path -LiteralPath $verificationPath)) { throw 'Workbook candidate verification receipt is missing.' }
    $verification = Get-Content -LiteralPath $verificationPath -Raw | ConvertFrom-Json
    $candidate = [string]$verification.staged
    if ($verification.status -ne 'verified_ready_for_atomic_publication' -or
        $verification.original_sha256 -ne $sourceHash -or
        -not (Test-Path -LiteralPath $candidate)) {
        throw 'Workbook candidate is not bound to the verified canonical source.'
    }

    $wpsReceipt = Join-Path $candidateDirectory.FullName 'wps-verification.json'
    & (Join-Path $PSScriptRoot 'verify_wps_navigation.ps1') -WorkbookPath $candidate -ReceiptPath $wpsReceipt
    if ($LASTEXITCODE -ne 0) { throw 'WPS candidate verification failed.' }
    $wps = Get-Content -LiteralPath $wpsReceipt -Raw | ConvertFrom-Json
    if ($wps.status -ne 'passed' -or $wps.read_only -ne $true) { throw 'WPS candidate verification is incomplete.' }

    if (-not $Publish) {
        [PSCustomObject]@{
            status = 'verified_not_published'; candidate = $candidate; source_sha256 = $sourceHash
            candidate_sha256 = $verification.staged_sha256; wps_receipt = $wpsReceipt
            trade_approved = $false
        } | ConvertTo-Json -Compress
        exit 0
    }

    Invoke-ProjectPython $python @(
        'scripts\publish_workbook_candidate.py', '--candidate', $candidate, '--destination', $source,
        '--backup-dir', (Join-Path $candidateDirectory.FullName 'publish-backup'),
        '--expected-destination-sha256', $sourceHash
    ) 'Workbook atomic publication'
    $publishedHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($publishedHash -ne ([string]$verification.staged_sha256).ToLowerInvariant()) {
        throw 'Published workbook hash does not match the WPS-verified candidate.'
    }
    [PSCustomObject]@{
        status = 'published'; workbook = $source; published_sha256 = $publishedHash
        backup = (Join-Path $candidateDirectory.FullName 'publish-backup\canonical-before-publish.xlsx')
        trade_approved = $false
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{ status = 'failed'; error = $_.Exception.Message; trade_approved = $false } |
        ConvertTo-Json -Compress
    exit 1
}
