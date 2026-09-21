param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = 'D:\GPTProject\value-investment'
$python = Join-Path $root 'runtime\venv\Scripts\python.exe'
$workbook = 'C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx'
Set-Location -LiteralPath $root
$arguments = @('scripts\publish_moutai_case_workbook.py', $workbook)
if ($DryRun) { $arguments += '--dry-run' }
& $python @arguments
exit $LASTEXITCODE
