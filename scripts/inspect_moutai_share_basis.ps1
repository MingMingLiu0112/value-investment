$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location -LiteralPath 'D:\GPTProject\value-investment'
Get-Content 'runtime\strategy-validation\moutai-daily-share-basis-20260909T094243932846Z\result.json' -Encoding utf8 -TotalCount 240
Get-Content 'runtime\strategy-validation\moutai-warmup-20260909T062823719664Z\share-bridge.json' -Encoding utf8 -TotalCount 240
Get-Content 'runtime\strategy-validation\moutai-repurchase-timeline-20260909T095306550689Z\evidence.json' -Encoding utf8 -TotalCount 240
Get-Content 'scripts\check_moutai_2026_share_scope.py' -Encoding utf8 -TotalCount 260
