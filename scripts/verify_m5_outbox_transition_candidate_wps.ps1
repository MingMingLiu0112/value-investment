param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$manifestFile = (Resolve-Path -LiteralPath $ManifestPath).Path
if (Test-Path -LiteralPath $ReceiptPath) {
    throw "M5 outbox transition verification receipt already exists: $ReceiptPath"
}
$manifest = Get-Content -LiteralPath $manifestFile -Raw -Encoding utf8 | ConvertFrom-Json
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = ([string]$manifest.workbook_sha256).ToLowerInvariant()
if ($before -ne $expected) {
    throw "M5 outbox transition candidate differs from its manifest hash: $before"
}
if ([int]$manifest.outbox_revision -ne 7 -or [int]$manifest.outbox_transition_count -ne 7) {
    throw 'M5 outbox transition manifest does not contain seven transitions.'
}
if ([string]$manifest.schema_version -ne 'm5-outbox-transition-candidate-v2') {
    throw "Unexpected M5 outbox transition manifest schema: $($manifest.schema_version)"
}
if ([string]$manifest.producer.parent_v1_workbook.sha256 -ne '2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae') {
    throw 'M5 outbox transition manifest no longer binds the frozen v1 parent.'
}
if ([string]$manifest.action -ne 'no_order') {
    throw "M5 outbox transition manifest action is not no_order: $($manifest.action)"
}

$expectedSheets = @(
    '00_总览'
    '01_事件账'
    '02_水位与检查点'
    '03_依赖失效与重算'
    '04_Outbox'
    '05_Outbox迁移'
    '06_输入与边界'
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
            throw 'M5 outbox transition candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M5 outbox transition candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M5 outbox transition sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M5 outbox transition sheet hidden: $($sheet.Name)"
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
                namespace = [string]$sheet.Range('B5').Text
                health = [string]$sheet.Range('B6').Text
                input_count = [int]$sheet.Range('B7').Value2
                active_count = [int]$sheet.Range('B9').Value2
                outbox_revision = [int]$sheet.Range('B17').Value2
                transition_count = [int]$sheet.Range('B18').Value2
                action = [string]$sheet.Range('B19').Text
            }
        }
        if ($i -eq 1) {
            $checks.event_rows = [int]$sheet.UsedRange.Rows.Count - 4
            $checks.identity_header = [string]$sheet.Range('D4').Text
            $checks.source_header = [string]$sheet.Range('E4').Text
            $checks.first_identity = [string]$sheet.Range('D5').Text
            $checks.first_source_id = [string]$sheet.Range('E5').Text
        }
        if ($i -eq 2) {
            $checks.watermark_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.invalidation_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $checks.outbox_rows = [int]$sheet.UsedRange.Rows.Count - 4
            $checks.sent_at_header = [string]$sheet.Range('K4').Text
        }
        if ($i -eq 5) {
            $checks.transition_rows = [int]$sheet.UsedRange.Rows.Count - 4
            $checks.last_revision = [int]$sheet.Cells($sheet.UsedRange.Rows.Count, 1).Value2
            $checks.transition_headers = @(
                [string]$sheet.Range('A4').Text
                [string]$sheet.Range('B4').Text
                [string]$sheet.Range('C4').Text
                [string]$sheet.Range('D4').Text
                [string]$sheet.Range('E4').Text
                [string]$sheet.Range('F4').Text
                [string]$sheet.Range('K4').Text
                [string]$sheet.Range('M4').Text
            )
            $checks.first_transition_source_event = [string]$sheet.Range('D5').Text
            $checks.first_transition_source_id = [string]$sheet.Range('E5').Text
            $checks.first_transition_identity = [string]$sheet.Range('F5').Text
            $checks.last_transition_action = [string]$sheet.Range('M11').Text
            $transitionStatuses = @()
            for ($transitionRow = 5; $transitionRow -le 11; $transitionRow++) {
                $transitionStatuses += [string]$sheet.Cells($transitionRow, 10).Text
            }
            $checks.transition_status_counts = @{
                sent = @($transitionStatuses | Where-Object { $_ -eq 'SENT' }).Count
                acknowledged = @($transitionStatuses | Where-Object { $_ -eq 'ACKNOWLEDGED' }).Count
                failed_retryable = @($transitionStatuses | Where-Object { $_ -eq 'FAILED_RETRYABLE' }).Count
                failed_terminal = @($transitionStatuses | Where-Object { $_ -eq 'FAILED_TERMINAL' }).Count
            }
        }
        if ($i -eq 6) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne 'M5 事件监控基础设施（模拟演示）') {
        throw "Unexpected M5 event title: $($checks.title)"
    }
    if ($checks.namespace -ne 'SIMULATED' -or $checks.health -ne '需关注') {
        throw "Unexpected M5 event boundary: $($checks.namespace)/$($checks.health)"
    }
    if ($checks.input_count -ne 7 -or $checks.active_count -ne 5) {
        throw "Unexpected M5 event counts: $($checks.input_count)/$($checks.active_count)"
    }
    if ($checks.outbox_revision -ne 7 -or $checks.transition_count -ne 7) {
        throw "Unexpected M5 outbox counts: $($checks.outbox_revision)/$($checks.transition_count)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M5 event action is not no_order: $($checks.action)"
    }
    if ($checks.identity_header -ne '身份版本' -or $checks.source_header -ne '来源ID') {
        throw 'M5 event identity columns are missing.'
    }
    if ($checks.first_identity -ne '历史兼容（无来源ID）' -or $checks.first_source_id -ne 'unspecified-source') {
        throw 'M5 event identity values differ from the frozen legacy fixture.'
    }
    if ($checks.sent_at_header -ne '发送时间') {
        throw 'M5 outbox send-time column is missing.'
    }
    if ($checks.event_rows -ne 7 -or $checks.outbox_rows -ne 6 -or $checks.transition_rows -ne 7) {
        throw "Unexpected M5 event/outbox/transition rows: $($checks.event_rows)/$($checks.outbox_rows)/$($checks.transition_rows)"
    }
    if ($checks.watermark_rows -ne 10 -or $checks.invalidation_rows -ne 20 -or $checks.boundary_rows -ne 13) {
        throw "Unexpected M5 supporting row counts: $($checks.watermark_rows)/$($checks.invalidation_rows)/$($checks.boundary_rows)"
    }
    if ($checks.last_revision -ne 7) {
        throw "Unexpected final outbox revision: $($checks.last_revision)"
    }
    $expectedTransitionHeaders = @(
        '修订'
        '迁移ID'
        '提醒ID'
        '来源事件ID'
        '来源ID'
        '身份版本'
        '发生时间'
        '动作'
    )
    for ($headerIndex = 0; $headerIndex -lt $expectedTransitionHeaders.Count; $headerIndex++) {
        if ($checks.transition_headers[$headerIndex] -ne $expectedTransitionHeaders[$headerIndex]) {
            throw "Unexpected M5 transition header at index $headerIndex"
        }
    }
    if ($checks.first_transition_source_event -ne '600519-financial-report-001' -or
        $checks.first_transition_source_id -ne 'unspecified-source' -or
        $checks.first_transition_identity -ne '历史兼容（无来源ID）') {
        throw 'M5 transition source identity is not traceable to the frozen fixture.'
    }
    if ($checks.last_transition_action -ne 'no_order') {
        throw "Transition action is not no_order: $($checks.last_transition_action)"
    }
    if ($checks.transition_status_counts.sent -ne 3 -or
        $checks.transition_status_counts.acknowledged -ne 1 -or
        $checks.transition_status_counts.failed_retryable -ne 1 -or
        $checks.transition_status_counts.failed_terminal -ne 1) {
        throw 'M5 transition status counts differ from the frozen fixture.'
    }
    if ($allText -contains '自动交易' -or $allText -contains '下单' -or $allText -contains '目标仓位') {
        throw 'M5 outbox transition candidate contains forbidden trading or position text.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M5 outbox transition candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_m5_outbox_transition_candidate'
        workbook = $path
        manifest = $manifestFile
        sha256 = $before
        state_sha256 = [string]$manifest.state_sha256
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, manifest hash, identity columns, outbox send time, transition history, row counts, formula errors and no-order boundary'
    }
    $receipt | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 6 -Compress
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
