$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location -LiteralPath 'D:\GPTProject\value-investment'
Get-Content 'docs\historical-corporate-actions.md' -Encoding utf8 -TotalCount 180
Get-Content 'docs\moutai-model-scope-decision-20260909.md' -Encoding utf8 -TotalCount 180
Get-Content 'scripts\replay_moutai_distributions.py' -Encoding utf8 -TotalCount 240
rg --files scripts runtime\strategy-validation runtime\company-research | Select-String -Pattern 'moutai.*(share|repurchase|cancel)|share.*moutai'
