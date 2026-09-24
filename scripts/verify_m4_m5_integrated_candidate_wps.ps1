param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ReceiptPath,
    [Parameter(Mandatory)][string]$ExpectedSha256
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M4/M5 joint candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_总览'
    '01_M4组合基线'
    '02_M5事件批'
    '03_依赖失效映射'
    '04_联合产品状态'
    '05_输入与边界'
)
$app = $null
$book = $null
$initialCount = -1
try {
    $app = New-Object -ComObject ket.Application
    $applicationPath = [string]$app.Path
    if ($applicationPath -notmatch 'WPS') {
        throw "Unexpected document engine: $applicationPath"
    }
    $initialCount = $app.Workbooks.Count
    foreach ($existing in $app.Workbooks) {
        if ([string]$existing.FullName -eq $path) {
            throw 'M4/M5 joint candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M4/M5 joint candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M4/M5 joint sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M4/M5 joint sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            $allText += [string]$value
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $checks = @{
                title = [string]$sheet.Range('A1').Text
                subtitle = [string]$sheet.Range('A2').Text
                namespace = [string]$sheet.Range('B5').Text
                joint_status = [string]$sheet.Range('B6').Text
                risk_status = [string]$sheet.Range('B7').Text
                guidance_status = [string]$sheet.Range('B8').Text
                dividend_status = [string]$sheet.Range('B9').Text
                event_count = [string]$sheet.Range('B10').Text
                affected_count = [string]$sheet.Range('B11').Text
                action = [string]$sheet.Range('B13').Text
            }
        }
        if ($i -eq 1) {
            $checks.m4_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.event_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.invalidation_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $checks.artifact_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 5) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }

    if ($checks.title -ne 'M4/M5 联合检查点（模拟演示）') {
        throw "Unexpected M4/M5 joint title: $($checks.title)"
    }
    if ($checks.namespace -ne 'SIMULATED') {
        throw "M4/M5 joint candidate is not simulated: $($checks.namespace)"
    }
    if ($checks.joint_status -ne 'NEGATIVE') {
        throw "Unexpected joint status: $($checks.joint_status)"
    }
    if ($checks.risk_status -ne 'VIOLATION') {
        throw "Unexpected risk baseline: $($checks.risk_status)"
    }
    if ($checks.guidance_status -ne 'BUDGET_CONFLICT') {
        throw "Unexpected guidance baseline: $($checks.guidance_status)"
    }
    if ($checks.dividend_status -ne 'READY') {
        throw "Unexpected dividend baseline: $($checks.dividend_status)"
    }
    if ($checks.event_count -ne '4') {
        throw "Unexpected event count: $($checks.event_count)"
    }
    if ($checks.affected_count -ne '10') {
        throw "Unexpected affected artifact count: $($checks.affected_count)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M4/M5 joint action is not no_order: $($checks.action)"
    }
    if ($checks.m4_rows -ne 3) {
        throw "Unexpected M4 baseline row count: $($checks.m4_rows)"
    }
    if ($checks.event_rows -ne 4) {
        throw "Unexpected event row count: $($checks.event_rows)"
    }
    if ($checks.artifact_rows -ne 11) {
        throw "Unexpected artifact row count: $($checks.artifact_rows)"
    }
    if ($checks.boundary_rows -ne 6) {
        throw "Unexpected boundary row count: $($checks.boundary_rows)"
    }
    if ($allText -contains '目标仓位' -or $allText -contains '下单') {
        throw 'M4/M5 joint candidate contains forbidden position or order text.'
    }

    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M4/M5 joint candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_m4_m5_joint_candidate'
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, simulated labels, row counts, event precision and no-order boundary'
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 5 -Compress
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
