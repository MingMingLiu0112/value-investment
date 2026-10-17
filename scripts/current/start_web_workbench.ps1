param(
    [ValidateRange(1024, 65535)][int]$Port = 8001,
    [switch]$Open,
    [switch]$Reauthorize
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    & 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File $PSCommandPath -Port $Port -Open:$Open -Reauthorize:$Reauthorize
    exit $LASTEXITCODE
}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$env:PYTHONPATH = Join-Path $root 'src'
$env:PYTHONIOENCODING = 'utf-8'
$python = 'D:\APP\Python313\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw '未找到工作台 Python 解释器。' }
$requestedPort = $Port
$statePath = Join-Path $root '.tmp/workbench-process.json'
function Test-WorkbenchIdentity {
    param($State, $Process, $Listeners, [string]$ExpectedRoot, [string]$ExpectedPython)
    try {
        $recordedRoot = [System.IO.Path]::GetFullPath([string]$State.root).TrimEnd('\', '/')
        $canonicalRoot = [System.IO.Path]::GetFullPath($ExpectedRoot).TrimEnd('\', '/')
        $recordedCreation = [DateTimeOffset]$State.created_at
        $actualCreation = [DateTimeOffset]$Process.CreationDate
        # ConvertFrom-Json may return DateTime rather than a string on PS 7.5+.
        # Compare UTC instants, never a formatted string against a typed date.
        return ($Process -and
            [string]::Equals($recordedRoot, $canonicalRoot, [StringComparison]::OrdinalIgnoreCase) -and
            [string]::Equals($Process.ExecutablePath, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase) -and
            $Process.ProcessId -eq $State.pid -and
            $actualCreation.UtcTicks -eq $recordedCreation.UtcTicks -and
            $Process.CommandLine -match 'value_investment_agent.presentation.web_api.app:app' -and
            @($Listeners | Where-Object { $_.OwningProcess -eq $State.pid -and
                $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq $State.port }).Count -gt 0)
    } catch { return $false }
}
function Wait-WorkbenchReady {
    param([int]$ServerPid, [int]$ServerPort, [int]$TimeoutSeconds = 30)
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if (-not (Get-Process -Id $ServerPid -ErrorAction SilentlyContinue)) { return $false }
        try {
            $listener = Get-NetTCPConnection -LocalPort $ServerPort -State Listen -ErrorAction SilentlyContinue
            if ($listener.OwningProcess -contains $ServerPid -and $listener.LocalAddress -contains '127.0.0.1') {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ServerPort/openapi.json" -TimeoutSec 2
                if ($health.paths.PSObject.Properties.Name -contains '/api/v1/daily-public-packet') { return $true }
            }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    return $false
}
if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.pid)"
        $listener = Get-NetTCPConnection -LocalPort $state.port -State Listen -ErrorAction SilentlyContinue
        if (Test-WorkbenchIdentity -State $state -Process $process -Listeners $listener -ExpectedRoot $root -ExpectedPython $python) {
            $url = "http://127.0.0.1:$($state.port)"
            if ($Reauthorize) {
                # Bind the process handle to the recorded creation time before terminating it.
                $owned = Get-Process -Id $state.pid -ErrorAction Stop
                if ([Math]::Abs((([DateTimeOffset]$owned.StartTime).UtcDateTime - ([DateTimeOffset]$state.created_at).UtcDateTime).TotalMilliseconds) -ge 1) {
                    throw '进程身份已变化；拒绝停止。'
                }
                $owned.Kill()
                if (-not $owned.WaitForExit(5000)) { throw '本入口进程未在限时内退出。' }
                $Port = [int]$state.port
                Write-Host '已停止核验通过的本入口进程；本次启动生成新本机授权链接。'
            } else {
                Write-Host "已核验本入口工作台进程，复用 $url 。"
                Write-Host '若授权过期或丢失链接，请运行唯一日常入口：pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode READ_ONLY -Reauthorize -Open'
                if (-not (Wait-WorkbenchReady -ServerPid $state.pid -ServerPort $state.port)) {
                    Write-Host '工作台健康检查未在30秒内通过；未打开页面。'; exit 4
                }
                if ($Open) { Start-Process $url }
                exit 0
            }
        } else {
            Write-Host '原启动记录的路径、进程创建时间或监听归属不匹配；保留现有进程。'
        }
    } catch { Write-Host '原启动记录无法核验，保留现有进程。' }
}
while ($Port -le 65535) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $probe.Start(); break } catch { $Port++ } finally { $probe.Stop() }
}
if ($Port -gt 65535) { throw '没有可用的本机回环端口。' }
if ($Port -ne $requestedPort) { Write-Host "端口 $requestedPort 已占用，未停止任何进程；改用 http://127.0.0.1:$Port 。" }
$env:VALUE_INVESTMENT_WEB_PORT = "$Port"
# WEB-D3 P0.2: the private API starts locked. This per-run secret is the only
# way to unlock it; it is handed to the browser through the URL fragment (never
# sent to the server) and printed here as the controlled local handoff. It is
# never written to disk, Git or the research packages.
$env:VALUE_INVESTMENT_WEB_BOOTSTRAP = [System.Security.Cryptography.RandomNumberGenerator]::GetHexString(32)
$env:TEMP = Join-Path $root '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $root 'web/dist/index.html'))) {
    throw 'Web build missing. Run npm ci --prefix web, then npm run build --prefix web.'
}
$unlockUrl = "http://127.0.0.1:$Port/daily#unlock=$($env:VALUE_INVESTMENT_WEB_BOOTSTRAP)"
$server = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'value_investment_agent.presentation.web_api.app:app', '--host', '127.0.0.1', '--port', "$Port") -WorkingDirectory $root -WindowStyle Hidden -PassThru
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $($server.Id)"
if (-not $process) {
    Write-Host '工作台启动进程已退出；未打开页面或提供授权链接。'
    exit 4
}
@{ root = $root; pid = $server.Id; port = $Port; created_at = $process.CreationDate.ToUniversalTime().ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
if (-not (Wait-WorkbenchReady -ServerPid $server.Id -ServerPort $Port)) {
    Write-Host '工作台健康检查未在30秒内通过；未打开页面，也未提供不可用授权链接。'
    Write-Host '如需重新启动本入口进程：pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode READ_ONLY -Reauthorize -Open'
    exit 4
}
Write-Host "工作台已就绪：http://127.0.0.1:$Port"
Write-Host '本机授权链接（仅用于此次启动，重启后失效；请勿分享）：'
Write-Host $unlockUrl
if ($Open) { Start-Process $unlockUrl }
$server.WaitForExit()
exit $server.ExitCode
