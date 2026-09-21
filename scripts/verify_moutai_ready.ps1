param([Parameter(Mandatory = $true)][string]$Workbook)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = 'D:\GPTProject\value-investment'
Set-Location -LiteralPath $root
& (Join-Path $root 'runtime\venv\Scripts\python.exe') (Join-Path $root 'scripts\verify_moutai_workbook_case.py') $Workbook
exit $LASTEXITCODE
