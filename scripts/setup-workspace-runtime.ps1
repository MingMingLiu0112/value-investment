param(
    [string]$NodeModulesPath = 'C:\Users\we\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
)

$linkPath = Join-Path $PSScriptRoot 'node_modules'
if (-not (Test-Path -LiteralPath $NodeModulesPath)) {
    throw "未找到 Codex 工作区依赖：$NodeModulesPath"
}
if (Test-Path -LiteralPath $linkPath) {
    Write-Host "Excel 同步运行时已就绪：$linkPath"
    exit 0
}
New-Item -ItemType Junction -Path $linkPath -Target $NodeModulesPath | Out-Null
Write-Host "Excel 同步运行时已就绪：$linkPath"
