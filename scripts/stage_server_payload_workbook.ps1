[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PayloadPath,
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$node = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
if (-not (Test-Path -LiteralPath $node)) { throw "Codex Node runtime not found: $node" }
if (-not (Test-Path -LiteralPath $PayloadPath)) { throw "Payload not found: $PayloadPath" }
if (-not (Test-Path -LiteralPath $WorkbookPath)) { throw "Workbook not found: $WorkbookPath" }

$syncScript = Join-Path $PSScriptRoot 'sync_workbook.mjs'
$logDirectory = Join-Path $projectRoot 'runtime\logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$stdout = Join-Path $logDirectory 'workbook-stage.stdout.log'
$stderr = Join-Path $logDirectory 'workbook-stage.stderr.log'
Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath $node -ArgumentList @($syncScript, $WorkbookPath, $PayloadPath, $OutputPath) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
if ($process.ExitCode -ne 0) {
    $details = (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue).Trim()
    throw "Workbook staging failed with exit code $($process.ExitCode): $details"
}
if (-not (Test-Path -LiteralPath $OutputPath)) { throw 'Workbook staging produced no output file' }
if ((Get-Item -LiteralPath $OutputPath).Length -lt 1MB) { throw 'Workbook staging output is unexpectedly small' }
Write-Output (Get-Item -LiteralPath $OutputPath | Select-Object FullName, Length, LastWriteTime | ConvertTo-Json -Compress)
