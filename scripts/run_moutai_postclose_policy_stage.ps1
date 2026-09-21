[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'runtime\venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = Join-Path $root 'runtime\test-venv\Scripts\python.exe' }
$receipt = Get-ChildItem (Join-Path $root 'runtime\company-research') -Directory -Filter '600519-preclose-capital-receipt-*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $receipt) { throw 'No pre-close receipt exists; refusing to stage policy.' }
$now = (Get-Date).ToString('o')
& $python -X utf8 scripts\stage_moutai_postclose_policy.py --receipt (Join-Path $receipt.FullName 'evidence.json') --registered-at $now
if ($LASTEXITCODE -ne 0) { throw "Policy staging failed: $LASTEXITCODE" }
