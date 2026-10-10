[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Destination,
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$Source = (Get-Item -LiteralPath $Source).FullName.TrimEnd('\')
$Destination = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ($Source -eq $Destination -or $Destination.StartsWith($Source + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must be outside the original workspace.'
}
$workbooks = @(Get-ChildItem -LiteralPath $Source -File -Filter '*.xlsx' | Where-Object { -not $_.Name.StartsWith('~$') })
if ($workbooks.Count -ne 1) { throw 'Expected exactly one canonical workbook to retain.' }
$workbook = $workbooks[0]
$excludedNames = @('.pytest_cache', '__pycache__', 'node_modules')

function Get-ProjectFiles([string]$Directory) {
    foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($item.PSIsContainer) {
            if ($item.Name -in $excludedNames -or $item.Name -like 'pytest-*') { continue }
            if ($item.LinkType) { throw "Unexpected directory link: $($item.FullName)" }
            Get-ProjectFiles $item.FullName
        }
        elseif ($item.FullName -ne $workbook.FullName) { $item }
    }
}

if (-not $VerifyOnly) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $existing = @(Get-ChildItem -LiteralPath $Destination -Force)
    if ($existing.Count) { throw 'Destination is not empty. Review existing files before copying.' }
    & robocopy.exe $Source $Destination /E /COPY:DAT /DCOPY:DAT /XJ /R:1 /W:1 /NFL /NDL /NP /XD '.pytest_cache' '__pycache__' 'node_modules' 'pytest-*' /XF $workbook.FullName
    if ($LASTEXITCODE -lt 0 -or $LASTEXITCODE -ge 8) { throw "Project copy failed: $LASTEXITCODE" }
}
$manifest = [System.Collections.Generic.List[object]]::new()
foreach ($file in Get-ProjectFiles $Source) {
    $relative = $file.FullName.Substring($Source.Length + 1)
    $target = Join-Path $Destination $relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing destination file: $relative" }
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    if ($hash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) { throw "File mismatch: $relative" }
    $manifest.Add(@{path = $relative; sha256 = $hash; bytes = $file.Length})
}
$manifestDirectory = Join-Path $Destination 'runtime\migration'
New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
$snapshot = Join-Path $manifestDirectory $workbook.Name
if (-not $VerifyOnly) { Copy-Item -LiteralPath $workbook.FullName -Destination $snapshot }
if ((Get-FileHash -LiteralPath $snapshot).Hash -ne (Get-FileHash -LiteralPath $workbook.FullName).Hash) {
    throw 'Workbook changed during migration; do not clean the source.'
}
@{
    source = $Source; destination = $Destination; workbook = $workbook.FullName
    verified_at = (Get-Date -Format o); files = @($manifest.ToArray())
    excluded_regenerable_directories = @('.pytest_cache', '__pycache__', 'node_modules', 'pytest-*')
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $manifestDirectory 'copy-manifest.json') -Encoding UTF8
Write-Host "Verified $($manifest.Count) files by SHA-256. Source retained; cleanup is a separate step."
