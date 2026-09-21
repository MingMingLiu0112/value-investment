function Get-AgentWorkbook {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $path = $env:WORKBOOK_PATH
    $envFile = Join-Path $ProjectRoot '.env'
    if (-not $path -and (Test-Path -LiteralPath $envFile)) {
        foreach ($line in [System.IO.File]::ReadAllLines($envFile, [System.Text.Encoding]::UTF8)) {
            if ($line.Trim() -match '^WORKBOOK_PATH\s*=(.*)$') {
                $path = $Matches[1].Trim()
                break
            }
        }
    }
    if ($path) {
        if (-not [System.IO.Path]::IsPathRooted($path)) { $path = Join-Path $ProjectRoot $path }
        $file = Get-Item -LiteralPath $path -ErrorAction Stop
        if ($file.PSIsContainer -or $file.Extension -ne '.xlsx' -or $file.Name.StartsWith('~$')) {
            throw 'WORKBOOK_PATH must identify the canonical .xlsx file.'
        }
        return $file
    }
    $files = @(Get-ChildItem -LiteralPath $ProjectRoot -File -Filter '*.xlsx' | Where-Object { -not $_.Name.StartsWith('~$') })
    if ($files.Count -ne 1) { throw 'Set WORKBOOK_PATH in .env to the canonical Excel full path.' }
    return $files[0]
}
