param([ValidateSet('menu','view','update','hotspots','portfolio','review')][string]$Mode='menu')
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    & 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File $PSCommandPath -Mode $Mode
    exit $LASTEXITCODE
}
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$OutputEncoding=[System.Text.UTF8Encoding]::new()
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH=Join-Path $projectRoot 'src'
$env:PYTHONIOENCODING='utf-8'
$env:TEMP=Join-Path $projectRoot '.tmp'
$env:TMP=$env:TEMP
$pythonPath='D:\APP\Python313\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python runtime is missing.' }
if ($Mode -eq 'menu') {
    Write-Host '1 打开工作台  2 更新并发布  3 扫描热点  4 查看组合状态  5 研究审核  0 退出'
    $selection=Read-Host '请选择'
    $Mode=switch ($selection) { '1' {'view'} '2' {'update'} '3' {'hotspots'} '4' {'portfolio'} '5' {'review'} default {exit 0} }
}
switch ($Mode) {
    'view' { & $pythonPath -X utf8 scripts/current/use_trade_assistant.py --mode view --open }
    'update' { & $pythonPath -X utf8 scripts/current/use_trade_assistant.py --mode update }
    'hotspots' {
        $runName=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
        & $pythonPath -X utf8 scripts/current/scan_market_hotspots.py --output-dir "runtime/hotspot-observations/$runName"
    }
    'portfolio' { & $pythonPath -X utf8 scripts/current/review_dual_sleeve_risk.py }
    'review' {
        $symbol=Read-Host '股票代码（600519 或 600887）'
        if ($symbol -notin @('600519','600887')) { throw 'Choose a registered company.' }
        & $pythonPath -X utf8 scripts/current/use_trade_assistant.py --mode review --symbol $symbol
    }
}
exit $LASTEXITCODE
