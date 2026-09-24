param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $false)][string]$ManifestPath
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$manifestPath = if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    Join-Path (Split-Path -Parent $path) 'manifest.json'
} else {
    (Resolve-Path -LiteralPath $ManifestPath).Path
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Reconstructed evidence manifest missing: $manifestPath"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M3 reconstructed evidence candidate changed before WPS verification: $before"
}
if ($manifest.workbook.workbook_sha256 -ne $expected) {
    throw 'M3 reconstructed evidence manifest does not bind the candidate hash.'
}
if ($manifest.strict_contemporaneous_rule_pit -ne 'NOT_PROVEN') {
    throw 'M3 reconstructed evidence manifest claims strict PIT is proven.'
}
if ($manifest.action -ne 'no_order') {
    throw "M3 reconstructed evidence manifest action is not no_order: $($manifest.action)"
}

$expectedSheets = @(
    '00_重建边界'
    '01_历史基准'
    '02_官方披露演变'
    '03_一致性观察'
    '04_阻断与结论'
    '05_来源哈希'
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
            throw 'M3 reconstructed evidence candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw 'M3 reconstructed evidence candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    $checks = @{}
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M3 reconstructed evidence sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M3 reconstructed evidence sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $checks = @{
                title = [string]$sheet.Range('A1').Text
                subtitle = [string]$sheet.Range('A2').Text
                symbol = [string]$sheet.Range('B6').Text
                namespace = [string]$sheet.Range('B7').Text
                baseline_date = [string]$sheet.Range('B9').Text
                rule_status = [string]$sheet.Range('B10').Text
                strict_pit = [string]$sheet.Range('B11').Text
                actual_entry = [string]$sheet.Range('B12').Text
                human_decision = [string]$sheet.Range('B13').Text
                conclusion = [string]$sheet.Range('B14').Text
                human_review = [string]$sheet.Range('B15').Text
                action = [string]$sheet.Range('B16').Text
            }
        }
        if ($i -eq 1) {
            $checks.baseline_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.disclosure_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.comparison_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 5) {
            $checks.source_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }

    if ($checks.title -ne 'M3 重建证据连续性边界') {
        throw "Unexpected M3 reconstructed evidence title: $($checks.title)"
    }
    if ($checks.subtitle -notmatch '不含真实账户') {
        throw 'M3 reconstructed evidence subtitle does not preserve the private-data boundary.'
    }
    if ($checks.symbol -ne '600519' -or $checks.namespace -ne 'RECONSTRUCTED_EVIDENCE_CONTINUITY') {
        throw 'Unexpected M3 reconstructed evidence namespace or symbol.'
    }
    if ($checks.baseline_date -ne '2024-06-21') {
        throw "Unexpected reconstructed evidence baseline: $($checks.baseline_date)"
    }
    if ($checks.rule_status -ne 'RETROSPECTIVE_RESEARCH_EXTENSION') {
        throw "Unexpected rule registration status: $($checks.rule_status)"
    }
    if ($checks.strict_pit -ne '否') {
        throw "Strict PIT is not marked unproven: $($checks.strict_pit)"
    }
    if ($checks.actual_entry -ne '否' -or $checks.human_decision -ne '无') {
        throw 'M3 reconstructed evidence contains private Entry or decision fields.'
    }
    if ($checks.conclusion -ne 'RECONSTRUCTED_EVIDENCE_ONLY') {
        throw "Unexpected reconstructed evidence conclusion: $($checks.conclusion)"
    }
    if ($checks.human_review -ne '是') {
        throw "Reconstructed evidence is not marked for human review: $($checks.human_review)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M3 reconstructed evidence action is not no_order: $($checks.action)"
    }
    if ($checks.baseline_rows -ne 6) {
        throw "Unexpected baseline fact row count: $($checks.baseline_rows)"
    }
    if ($checks.disclosure_rows -ne 7) {
        throw "Unexpected disclosure metric row count: $($checks.disclosure_rows)"
    }
    if ($checks.comparison_rows -ne 8) {
        throw "Unexpected comparison row count: $($checks.comparison_rows)"
    }
    if ($checks.source_rows -ne 10) {
        throw "Unexpected source row count: $($checks.source_rows)"
    }

    $allText = ''
    foreach ($name in $expectedSheets) {
        foreach ($value in $book.Worksheets.Item($name).UsedRange.Value2) {
            $allText += [string]$value
        }
    }
    if ([string]::IsNullOrWhiteSpace($allText)) {
        throw 'M3 reconstructed evidence text could not be materialized.'
    }
    foreach ($forbidden in @('目标仓位', '下单', '自动卖出', '买入', '加仓')) {
        if ($allText -match $forbidden) {
            throw "Forbidden presentation text on M3 reconstructed evidence pages: $forbidden"
        }
    }

    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M3 reconstructed evidence candidate.'
    }

    $receipt = @{
        status = 'passed'
        mode = 'standalone_reconstructed_evidence_continuity_candidate'
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        strict_contemporaneous_rule_pit = 'NOT_PROVEN'
        action = 'no_order'
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, disclosure counts, evidence boundary and forbidden-signal scan; no visual click verification'
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
