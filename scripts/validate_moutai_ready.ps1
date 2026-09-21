param(
    [Parameter(Mandatory = $true)][string]$Snapshot,
    [Parameter(Mandatory = $true)][string]$Ready
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = 'D:\GPTProject\value-investment'
Set-Location -LiteralPath $root
$python = Join-Path $root 'runtime\venv\Scripts\python.exe'
& $python (Join-Path $root 'scripts\validate_workbook_output.py') $Snapshot (Join-Path $root 'runtime\server-export-payload.json') $Ready
exit $LASTEXITCODE
