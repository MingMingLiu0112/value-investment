$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location -LiteralPath 'D:\GPTProject\value-investment'
Get-Content 'runtime\strategy-validation\moutai-warmup-20260909T062823719664Z\annual-inputs.json' -Encoding utf8 -TotalCount 260
Get-Content 'runtime\strategy-validation\moutai-daily-research-inputs-20260909T161900156334Z\daily-inputs.json' -Encoding utf8 -TotalCount 180
Get-Content 'scripts\build_moutai_annual_inputs.py' -Encoding utf8 -TotalCount 340
