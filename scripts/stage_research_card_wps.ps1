[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$StagedPath
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$source = (Resolve-Path -LiteralPath $WorkbookPath).Path
$targetDirectory = Split-Path -Parent $StagedPath
New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
if (Test-Path -LiteralPath $StagedPath) { throw "Staged path already exists: $StagedPath" }

$application = $null
$sourceBook = $null
$stagedBook = $null
try {
    $application = New-Object -ComObject 'ket.Application'
    $application.DisplayAlerts = $false
    $sourceBook = $application.Workbooks.Open($source, 0, $true)
    if (-not $sourceBook.ReadOnly) { throw 'Source workbook must be opened read-only for staging.' }
    $sourceBook.SaveCopyAs($StagedPath)
    $sourceBook.Close($false)
    $sourceBook = $null

    $stagedBook = $application.Workbooks.Open($StagedPath, 0, $false)
    $sheet = $stagedBook.Worksheets.Item('00_公司总览')
    $priceRow = $null
    for ($row = 1; $row -le $sheet.UsedRange.Rows.Count; $row++) {
        if ([string]$sheet.Cells.Item($row, 1).Value2 -eq '价格如何理解') {
            $priceRow = $row
            break
        }
    }
    if ($null -eq $priceRow) { throw 'Research-card price row is missing.' }
    $sheet.Cells.Item($priceRow, 1).Value2 = '主模型 / 价格要求'
    $sheet.Cells.Item($priceRow, 3).Value2 = (
        '主模型：归母权益剩余收益/分配能力模型，以2026-06-30归母权益和扣非TTM为起点，检验未来五年利润-5%/0/+5%、75%研究性分配、优势回报五年衰减及不同折现率。' +
        '市场对价格的要求：2026-09-16归档价1,277.96元高于0年、5年、10年优势衰减且利润增长-5%至+5%的注册组合上限，因此利润、分配、优势持续期或资本成本中至少一项需显著更强。' +
        '变量有多解，这不是唯一市场预测、合理价或卖出信号；正式估值仍待指定日期审查。'
    )
    $sheet.Rows.Item($priceRow).RowHeight = 90
    $stagedBook.Save()
    $stagedBook.Close($true)
    $stagedBook = $null
    [PSCustomObject]@{
        status = 'staged'
        source = $source
        staged = (Resolve-Path -LiteralPath $StagedPath).Path
        sha256 = (Get-FileHash -LiteralPath $StagedPath -Algorithm SHA256).Hash
        changed_sheet = '00_公司总览'
        changed_row = $priceRow
    } | ConvertTo-Json -Compress
}
finally {
    if ($null -ne $stagedBook) { $stagedBook.Close($false) }
    if ($null -ne $sourceBook) { $sourceBook.Close($false) }
    if ($null -ne $application) { $application.Quit() }
}
