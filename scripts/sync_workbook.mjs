import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const [templatePath, payloadPath, outputPath] = process.argv.slice(2);
if (!templatePath || !payloadPath || !outputPath) {
  throw new Error('Usage: node sync_workbook.mjs <template.xlsx> <payload.json> <output.xlsx>');
}
const payload = JSON.parse(await fs.readFile(payloadPath, 'utf8'));
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const valuationBySymbol = new Map(payload.valuations.map((row) => [row.symbol, row]));
const pointBySymbol = new Map();
for (const point of payload.points) {
  const values = pointBySymbol.get(point.symbol) ?? {};
  values[point.field_name] = point;
  pointBySymbol.set(point.symbol, values);
}

function cellValue(value) {
  return value === null || value === undefined ? null : Number.isFinite(Number(value)) ? Number(value) : value;
}

function syncRows(sheetName, firstDataRow, writeRow) {
  const sheet = workbook.worksheets.getItem(sheetName);
  for (let row = firstDataRow; row <= 200; row += 1) {
    const symbol = sheet.getRange(`A${row}`).values?.[0]?.[0];
    if (!symbol) break;
    writeRow(sheet, row, String(symbol).padStart(6, '0'));
  }
}

syncRows('01_观察名单', 4, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  if (!v) return;
  sheet.getRange(`F${row}:I${row}`).values = [[cellValue(v.current_price), cellValue(v.fair_value), cellValue(v.safety_margin), v.valuation_status]];
  sheet.getRange(`K${row}:L${row}`).values = [[v.build_signal, cellValue(v.target_weight)]];
  sheet.getRange(`N${row}:P${row}`).values = [[v.build_signal === '待数据' ? '等待数据' : '人工确认', payload.generated_at, v.data_status]];
});

syncRows('04_估值跟踪', 4, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  const p = pointBySymbol.get(symbol) ?? {};
  if (!v) return;
  sheet.getRange(`C${row}:U${row}`).values = [[cellValue(v.current_price), cellValue(p.eps_ttm?.value), cellValue(p.bvps?.value), cellValue(p.fcf_per_share?.value), cellValue(p.dps_ttm?.value), null, null, null, null, null, cellValue(v.fair_value), null, cellValue(v.fair_value), cellValue(v.safety_margin), v.valuation_status, null, p.current_price?.source_id ?? null, payload.generated_at, v.data_status]];
});

syncRows('05_仓位管理', 10, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  if (!v) return;
  sheet.getRange(`C${row}:D${row}`).values = [[v.build_signal, cellValue(v.target_weight)]];
  sheet.getRange(`F${row}`).values = [[cellValue(v.current_price)]];
  sheet.getRange(`K${row}`).values = [[v.build_signal === '待数据' ? '等待数据' : '人工确认']];
});

const financialFields = ['revenue', 'revenue_yoy', 'net_income', 'net_income_yoy', 'roe', 'roic', 'gross_margin', 'net_margin', 'operating_cash_flow', 'free_cash_flow', 'operating_cash_flow_to_net_income', 'debt_ratio', 'cash', 'interest_bearing_debt', 'eps_ttm', 'dps_ttm', 'payout_ratio'];
syncRows('03_财务指标', 4, (sheet, row, symbol) => {
  const p = pointBySymbol.get(symbol) ?? {};
  const values = financialFields.map((field) => cellValue(p[field]?.value));
  const source = financialFields.map((field) => p[field]?.source_id).find(Boolean) ?? null;
  sheet.getRange(`D${row}:V${row}`).values = [[...values, source, source ? '待人工复核' : '待Agent写入']];
});

const auditSheet = workbook.worksheets.getItem('11_数据源审计');
let auditRow = 4;
while (auditSheet.getRange(`A${auditRow}`).values?.[0]?.[0]) auditRow += 1;
for (const audit of payload.audits) {
  auditSheet.getRange(`A${auditRow}:R${auditRow}`).values = [[audit.source_id, audit.symbol, audit.field_name, audit.period_label, cellValue(audit.value), audit.unit, audit.source_name, audit.source_url, null, null, audit.fetched_at, audit.published_at, audit.parser_version, audit.sha256, null, audit.validation_status, audit.human_reviewed ? '是' : '否', '由本地 Agent 同步']];
  auditRow += 1;
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
