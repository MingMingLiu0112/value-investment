[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$HostName,
    [string]$ContainerName = 'value-investment-postgres',
    [string]$Database = 'value_agent',
    [string]$DatabaseUser = 'value_agent_admin',
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

# This exports definitions only.  It never requests table rows, credentials,
# backups, or container filesystem contents.
$remoteCommand = "podman exec $ContainerName pg_dump -U $DatabaseUser -d $Database --schema-only --no-owner --no-privileges"
$schema = & ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "root@$HostName" $remoteCommand
if ($LASTEXITCODE -ne 0 -or -not $schema) {
    throw 'Server schema export failed; no output file was written.'
}
if (($schema -join "`n") -notmatch 'CREATE TABLE') {
    throw 'Schema export did not contain any table definitions.'
}

$destination = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
$header = @(
    '-- Server schema snapshot for value-investment-agent.',
    '-- Generated from pg_dump --schema-only; contains no table data, secrets, or backups.',
    "-- Generated at UTC: $([DateTime]::UtcNow.ToString('o'))",
    ''
) -join "`n"
$sanitized = $schema | Where-Object { $_ -notmatch '^\\(un)?restrict\b' }
[IO.File]::WriteAllText($destination, $header + ($sanitized -join "`n") + "`n", [System.Text.UTF8Encoding]::new($false))
Get-FileHash -LiteralPath $destination -Algorithm SHA256 | Select-Object Path, Hash, Length
