param(
    [ValidateRange(1024, 65535)][int]$Port = 8001,
    [switch]$Open
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    & 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File $PSCommandPath -Port $Port -Open:$Open
    exit $LASTEXITCODE
}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$env:PYTHONPATH = Join-Path $root 'src'
$env:PYTHONIOENCODING = 'utf-8'
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
$unlockUrl = "http://127.0.0.1:$Port/#unlock=$($env:VALUE_INVESTMENT_WEB_BOOTSTRAP)"
Write-Host ''
Write-Host 'Workbench unlock link (one-time for this run, invalid after restart):'
Write-Host $unlockUrl
Write-Host ''
if ($Open) { Start-Process $unlockUrl }
& python -m uvicorn value_investment_agent.presentation.web_api.app:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
