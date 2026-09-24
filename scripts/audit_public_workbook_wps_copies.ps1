param(
    [Parameter(Mandatory = $false)]
    [string]$WpsRoot = 'C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪',
    [Parameter(Mandatory = $false)]
    [string]$ReceiptPath = ''
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $WpsRoot -PathType Container)) {
    throw "WPS root is not a directory: $WpsRoot"
}

$tracked = @(& git -C $projectRoot -c core.quotepath=false ls-files -- '*.xlsx')
if ($LASTEXITCODE -ne 0) {
    throw "Git could not list tracked workbooks. Exit code: $LASTEXITCODE"
}
if ($tracked.Count -eq 0) {
    throw 'No tracked public workbooks were returned by Git.'
}

$files = @()
$mismatches = @()
foreach ($relative in $tracked) {
    $repoPath = Join-Path $projectRoot $relative
    if (-not (Test-Path -LiteralPath $repoPath -PathType Leaf)) {
        $mismatches += [pscustomobject]@{
            name = $relative
            problem = 'repo file missing'
        }
        continue
    }
    $repoHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $repoPath).Hash.ToLowerInvariant()
    $wpsPath = Join-Path $WpsRoot (Split-Path -Leaf $relative)
    $wpsHash = $null
    $match = $false
    if (Test-Path -LiteralPath $wpsPath -PathType Leaf) {
        $wpsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wpsPath).Hash.ToLowerInvariant()
        $match = $repoHash -eq $wpsHash
    }
    $files += [pscustomobject]@{
        name = $relative
        repo_sha256 = $repoHash
        wps_sha256 = $wpsHash
        match = $match
    }
    if (-not $match) {
        $mismatches += [pscustomobject]@{
            name = $relative
            problem = if ($null -eq $wpsHash) { 'WPS copy missing' } else { 'hash mismatch' }
        }
    }
}

$receipt = @{
    status = if ($mismatches.Count -eq 0) { 'passed' } else { 'failed' }
    checked_at = [DateTimeOffset]::UtcNow.ToString('o')
    project_root = $projectRoot
    wps_root = $WpsRoot
    total = $tracked.Count
    matched = @($files | Where-Object match).Count
    mismatch_count = $mismatches.Count
    files = @($files)
    mismatches = @($mismatches)
}

$receiptPath = $ReceiptPath
if ([string]::IsNullOrWhiteSpace($receiptPath)) {
    $stamp = [DateTimeOffset]::Now.ToString('yyyyMMdd-HHmmss')
    $receiptPath = Join-Path $projectRoot "runtime\public-workbook-wps-audit-$stamp\receipt.json"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $receiptPath) | Out-Null
$receipt | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $receiptPath -Encoding utf8

$receipt | ConvertTo-Json -Depth 8 -Compress
if ($mismatches.Count -gt 0) {
    throw "Public workbook WPS copy audit failed: $($mismatches.Count) mismatches."
}
