$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = 'D:\GPTProject\value-investment'
Set-Location -LiteralPath $root
$python = Join-Path $root 'runtime\venv\Scripts\python.exe'
& $python -m pytest tests\test_moutai_historical_admission.py tests\test_moutai_paper_decisions.py tests\test_excel_report.py -q --basetemp runtime\pytest-admission-audit-v2
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $root 'scripts\audit_moutai_historical_admission.py')
exit $LASTEXITCODE
