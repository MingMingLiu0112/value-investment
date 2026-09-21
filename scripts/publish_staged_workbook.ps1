[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$StagedPath,
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
    [string]$ExpectedOriginalSha256,
    [string]$ExpectedStagedSha256
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $StagedPath)) { throw "Staged workbook missing: $StagedPath" }
if ($ExpectedOriginalSha256 -and (Get-FileHash -LiteralPath $WorkbookPath -Algorithm SHA256).Hash -ne $ExpectedOriginalSha256) {
    throw 'Original workbook changed since staging; refusing publication.'
}
if ($ExpectedStagedSha256 -and (Get-FileHash -LiteralPath $StagedPath -Algorithm SHA256).Hash -ne $ExpectedStagedSha256) {
    throw 'Staged workbook changed since verification; refusing publication.'
}
$stream = [System.IO.File]::Open($WorkbookPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
$stream.Close()
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$backup = Join-Path $BackupDirectory ("{0}-pre-{1}{2}" -f [IO.Path]::GetFileNameWithoutExtension($WorkbookPath), (Get-Date -Format 'yyyyMMdd-HHmmss'), [IO.Path]::GetExtension($WorkbookPath))
$temporary = Join-Path (Split-Path -Parent $WorkbookPath) (".~agent-publish-{0}.xlsx" -f [guid]::NewGuid().ToString('N'))
Copy-Item -LiteralPath $WorkbookPath -Destination $backup -Force
Copy-Item -LiteralPath $StagedPath -Destination $temporary -Force
if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $StagedPath -Algorithm SHA256).Hash) {
    throw 'Publication copy checksum mismatch.'
}
if ($ExpectedOriginalSha256 -and (Get-FileHash -LiteralPath $WorkbookPath -Algorithm SHA256).Hash -ne $ExpectedOriginalSha256) {
    throw 'Original workbook changed during staging; refusing publication.'
}
[System.IO.File]::Replace($temporary, $WorkbookPath, [NullString]::Value)
$item = Get-Item -LiteralPath $WorkbookPath
[PSCustomObject]@{ workbook = $item.FullName; bytes = $item.Length; backup = $backup; sha256 = (Get-FileHash -LiteralPath $WorkbookPath -Algorithm SHA256).Hash } | ConvertTo-Json -Compress
