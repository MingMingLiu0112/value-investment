param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$Server
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Text.UTF8Encoding]::new()

$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$plan = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($plan.mode -ne 'copy_and_verify_only' -or $plan.deletion_permitted -or !$plan.candidates) {
    throw 'Manifest is not a non-empty copy-and-verify-only cold-archive plan.'
}

$destinationRoot = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null
$batch = New-TemporaryFile
try {
    $commands = [Collections.Generic.List[string]]::new()
    foreach ($candidate in $plan.candidates) {
        $relative = [string]$candidate.relative_path
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') {
            throw "Unsafe archive relative path: $relative"
        }
        $target = [IO.Path]::GetFullPath((Join-Path $destinationRoot $relative))
        if (!$target.StartsWith($destinationRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Archive target escapes destination: $relative"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        $commands.Add("reget $($candidate.server_path) $relative")
    }
    [IO.File]::WriteAllLines($batch, $commands, [Text.UTF8Encoding]::new($false))
    Push-Location $destinationRoot
    try {
        & "$env:WINDIR\System32\OpenSSH\sftp.exe" -b $batch $Server
        if ($LASTEXITCODE -ne 0) { throw "sftp exited with code $LASTEXITCODE" }
    }
    finally { Pop-Location }

    foreach ($candidate in $plan.candidates) {
        $target = Join-Path $destinationRoot ([string]$candidate.relative_path)
        if (!(Test-Path -LiteralPath $target) -or (Get-Item -LiteralPath $target).Length -ne [int64]$candidate.bytes) {
            throw "Archive size mismatch: $($candidate.relative_path)"
        }
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidate.sha256) {
            throw "Archive SHA-256 mismatch: $($candidate.relative_path)"
        }
    }
    [pscustomobject]@{ status = 'copied_and_verified'; files = $plan.candidate_count; bytes = $plan.candidate_bytes }
        | ConvertTo-Json -Compress
}
finally {
    Remove-Item -LiteralPath $batch -Force -ErrorAction SilentlyContinue
}
