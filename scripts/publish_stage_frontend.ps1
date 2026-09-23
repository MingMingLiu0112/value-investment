param(
    [Parameter(Mandatory)][string]$OriginalPath,
    [Parameter(Mandatory)][string]$CandidatePath,
    [Parameter(Mandatory)][string]$WpsReceiptPath,
    [Parameter(Mandatory=$false)][string]$ExpectedOriginalSha256,
    [Parameter(Mandatory=$false)][int]$NewFrontendSheetCount = 6
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$original = (Resolve-Path -LiteralPath $OriginalPath).Path
$candidate = (Resolve-Path -LiteralPath $CandidatePath).Path
if ($original -eq $candidate) { throw 'Candidate must be separate from original.' }
$package = Get-Content -Raw -LiteralPath ([IO.Path]::ChangeExtension($candidate,'receipt.json')) | ConvertFrom-Json
$checks = Get-Content -Raw -LiteralPath ([IO.Path]::ChangeExtension($candidate,'checks.json')) | ConvertFrom-Json
$wps = Get-Content -Raw -LiteralPath $WpsReceiptPath | ConvertFrom-Json
$candidateHash = (Get-FileHash -LiteralPath $candidate).Hash.ToLowerInvariant()
$expectedOriginalHash = if ([string]::IsNullOrWhiteSpace($ExpectedOriginalSha256)) {
    $package.source_sha256
} else {
    $ExpectedOriginalSha256.ToLowerInvariant()
}
if ($checks.status -ne 'passed' -or $wps.status -ne 'passed' -or -not $wps.read_only) {
    throw 'Candidate has not passed package and WPS checks.'
}
if ($candidateHash -ne $package.candidate_sha256 -or $candidateHash -ne $checks.candidate_sha256 -or $candidateHash -ne $wps.sha256) {
    throw 'Candidate changed after verification.'
}
$id = [Guid]::NewGuid().ToString('N')
$repo = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $repo ('runtime/workbook-backups/stage-frontend-' + $id)
New-Item -ItemType Directory -Path $backupDir | Out-Null
$backup = Join-Path $backupDir 'before.xlsx'
$staged = Join-Path (Split-Path -Parent $original) ('.frontend-' + $id + '.xlsx')
Copy-Item -LiteralPath $candidate -Destination $staged
$stream = $null
try {
    # Deny concurrent writes while allowing the atomic replacement itself.
    $stream = [IO.File]::Open($original,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::Read -bor [IO.FileShare]::Delete))
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant()
    if ($hash -ne $expectedOriginalHash) { throw 'Original changed; publication refused.' }
    $stream.Position = 0
    $backupStream = [IO.File]::Open($backup,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.CopyTo($backupStream) } finally { $backupStream.Dispose() }
    if ((Get-FileHash -LiteralPath $backup).Hash.ToLowerInvariant() -ne $hash) { throw 'Backup verification failed.' }
    [IO.File]::Replace($staged,$original,[NullString]::Value)
}
finally {
    if ($null -ne $stream) { $stream.Dispose() }
}
if ((Get-FileHash -LiteralPath $original).Hash.ToLowerInvariant() -ne $candidateHash) { throw 'Published hash mismatch.' }
$receipt = @{
    status='published'; original=$original; backup=$backup; candidate=$candidate
    original_sha256=$expectedOriginalHash; base_source_sha256=$package.source_sha256
    published_sha256=$candidateHash
    checked_at=[DateTimeOffset]::UtcNow.ToString('o'); preserved_original_sheets=$package.original_sheets_preserved
    new_frontend_sheets=$NewFrontendSheetCount; production_or_scheduler_changed=$false
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupDir 'publication.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 4 -Compress
