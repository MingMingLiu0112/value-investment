param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash
$app = $null
$book = $null
$initialCount = -1
$checks = [Collections.Generic.List[object]]::new()
try {
    # Document-object API only: no UI Automation, focus, visibility or window changes.
    $app = New-Object -ComObject ket.Application
    $applicationPath = [string]$app.Path
    if ($applicationPath -notmatch 'WPS') { throw "Unexpected document engine: $applicationPath" }
    $initialCount = $app.Workbooks.Count
    foreach ($existing in $app.Workbooks) {
        if ([string]$existing.FullName -eq $path) { throw 'Candidate already open; do not reuse or close it.' }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) { $book = $null; throw 'Candidate must open read-only.' }
    if ($book.Worksheets.Count -ne 36) { throw 'Unexpected worksheet count.' }
    $fronts = @('00_投资工作台','00_研究看板','00_研究逻辑卡','00_决策复核','00_组合与股息','00_跟踪与数据')
    $linkCount = 0
    for ($i=0; $i -lt $fronts.Count; $i++) {
        $sheet = $book.Worksheets.Item($i+1)
        if ($sheet.Name -ne $fronts[$i]) { throw 'Front sheet order differs.' }
        if ($sheet.Visible -ne -1) { throw 'Front sheet hidden.' }
        $sheet.Calculate()
        foreach ($link in $sheet.Hyperlinks) {
            if ($link.Address) { throw 'Frontend link has an external address.' }
            $location = [string]$link.SubAddress
            if ($location -notmatch "^'(.+)'!([A-Z]+[0-9]+)$") { throw "Invalid target $location" }
            $target = $book.Worksheets.Item($Matches[1])
            if ($target.Visible -ne -1 -or $null -eq $target.Range($Matches[2]).Value2) {
                throw "Missing/hidden target $location"
            }
            $linkCount++
        }
        $values = $sheet.UsedRange.Value2
        foreach ($value in $values) {
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
    }
    if ($linkCount -ne 64) { throw "Unexpected link count $linkCount" }
    $dashboardSheet = $book.Worksheets.Item($fronts[0])
    foreach ($pair in @(@('A8',3),@('D8',1),@('B25',1),@('B26',2))) {
        $value = $dashboardSheet.Range($pair[0]).Value2
        if ($value -ne $pair[1]) { throw "Formula result mismatch $($pair[0]) = $value" }
        $checks.Add(@{cell=$pair[0]; value=$value})
    }
    $research = $book.Worksheets.Item($fronts[1])
    if ([string]$research.Range('A10').Text -ne '000333') { throw 'Leading zero lost.' }
    if ($research.ListObjects.Count -ne 1) { throw 'Research filter table missing.' }
    $logic = $book.Worksheets.Item($fronts[2])
    if ($logic.Range('A42').Value2 -ne '未就绪' -or $logic.Range('A66').Value2 -ne '未就绪') {
        throw 'Fail-closed valuation state changed.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash -ne $before) { throw 'Read-only check changed candidate.' }
    $receipt = @{
        status='passed'; workbook=$path; sha256=$before.ToLowerInvariant(); read_only=$true
        application=[string]$app.Name; checked_at=[DateTimeOffset]::UtcNow.ToString('o')
        application_path=$applicationPath; automation_progid='ket.Application'
        internal_links=$linkCount; formula_checks=$checks; source_unchanged=$true
        check_scope='WPS document engine open/read/calculate and internal link targets; no visual click verification'
    }
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 5 -Compress
}
finally {
    if ($null -ne $book) { $book.Close($false) }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) { $app.Quit() }
}
