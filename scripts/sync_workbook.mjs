import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const [workbookPath, payloadPath, outputPath] = process.argv.slice(2);
if (!workbookPath || !payloadPath || !outputPath) {
  throw new Error('Usage: node sync_workbook.mjs <workbook.xlsx> <payload.json> <temporary-output.xlsx>');
}
// XLSX is XML-based and rejects C0 controls sometimes present in PDF extracts.
// Strip only non-displayable controls at the presentation boundary; the raw
// original remains archived with its source hash in PostgreSQL.
function spreadsheetSafe(value) {
  if (typeof value === 'string') return value.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');
  if (Array.isArray(value)) return value.map(spreadsheetSafe);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, spreadsheetSafe(item)]));
  }
  return value;
}

// PostgreSQL exports are UTF-8, but archived/manual payloads can carry a
// UTF-8 BOM.  Normalize only that transport marker before strict JSON parse.
const payloadText = (await fs.readFile(payloadPath, 'utf8')).replace(/^\uFEFF/, '');
const payload = spreadsheetSafe(JSON.parse(payloadText));
await fs.mkdir(path.dirname(outputPath), { recursive: true });

function assertCompleteMarketPayload(value) {
  const candidates = value.market_candidates;
  if (!Array.isArray(candidates)) throw new Error('Payload is missing market_candidates');
  // The daily workbook is a full-market research queue.  Do not allow a
  // transient provider failure to replace it with a partial response.  Local
  // fixture work can opt in explicitly without weakening scheduled runs.
  if (candidates.length < 500 && process.env.ALLOW_PARTIAL_MARKET_PAYLOAD !== '1') {
    throw new Error(`Refusing incomplete all-market payload: ${candidates.length} candidates (minimum 500)`);
  }
  const seen = new Set();
  for (const candidate of candidates) {
    const symbol = symbolKey(candidate.symbol);
    if (!/^\d{6}$/.test(symbol) || seen.has(symbol)) {
      throw new Error(`Invalid or duplicate market candidate symbol: ${candidate.symbol}`);
    }
    if (!candidate.board || candidate.board === '待板块映射' || !candidate.sector || candidate.sector === '待行业映射') {
      throw new Error(`Incomplete board or industry mapping for ${symbol}`);
    }
    if (!candidate.source_id) throw new Error(`Missing market source audit ID for ${symbol}`);
    seen.add(symbol);
  }
}

assertCompleteMarketPayload(payload);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const dashboardSheet = workbook.worksheets.getItem('00_首页Dashboard');
const verificationSummary = payload.filing_verification_summary ?? {};
const latestMarketSource = payload.market_candidates?.[0]?.market_source ?? '待采集';
dashboardSheet.getRange('I4:J7').values = [
  ['全市场初筛候选', (payload.market_candidates ?? []).length],
  ['自动验证通过', Number(verificationSummary.automatically_verified ?? 0)],
  ['自动补证队列', Number(verificationSummary.candidate_pending_automated_verification ?? 0)],
  ['当前行情来源', latestMarketSource],
];
const valuationBySymbol = new Map(payload.valuations.map((row) => [row.symbol, row]));
const financialQualityBySymbol = new Map((payload.financial_quality ?? []).map((row) => [row.symbol, row]));
const pointBySymbol = new Map();
for (const point of payload.points) {
  const values = pointBySymbol.get(point.symbol) ?? {};
  const existing = values[point.field_name];
  // Retain an official cross-source fact when a later pending provider value
  // exists for the same field.
  if (!existing || (point.validation_status === 'verified' && existing.validation_status !== 'verified')) {
    values[point.field_name] = point;
  }
  pointBySymbol.set(point.symbol, values);
}

function symbolKey(value) {
  return String(value ?? '').padStart(6, '0');
}

function cellValue(value) {
  return value === null || value === undefined ? null : Number.isFinite(Number(value)) ? Number(value) : value;
}

function positiveRatio(numerator, denominator) {
  const top = Number(numerator);
  const bottom = Number(denominator);
  return Number.isFinite(top) && Number.isFinite(bottom) && bottom > 0 ? top / bottom : null;
}

function displayPeriod(periodLabel) {
  const match = String(periodLabel ?? '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return periodLabel ?? null;
  const [, year, month, day] = match;
  if (month === '12' && day === '31') return `${year}A`;
  if (month === '06' && day === '30') return `${year}H1`;
  return `${year}Q${Math.ceil(Number(month) / 3)}`;
}

function financialSummary(points, fieldNames = financialFields) {
  const relevantPoints = Object.values(points).filter((point) => fieldNames.includes(point.field_name));
  const verified = relevantPoints.filter((point) => point.validation_status === 'verified').length;
  const pending = relevantPoints.filter((point) => point.validation_status !== 'verified').length;
  if (!relevantPoints.length) return '\u5f85\u5f52\u6863\u5b98\u65b9\u8d22\u62a5';
  if (!pending) return `\u5df2\u5b98\u65b9\u53cc\u6e90\u9a8c\u8bc1 ${verified} \u9879`;
  if (!verified) return `\u5f85\u5b98\u65b9\u53cc\u6e90\u9a8c\u8bc1 ${pending} \u9879`;
  return `\u5df2\u9a8c\u8bc1 ${verified} \u9879\uff0c\u5f85\u9a8c\u8bc1 ${pending} \u9879`;
}

function syncRows(sheetName, firstDataRow, writeRow) {
  const sheet = workbook.worksheets.getItem(sheetName);
  for (let row = firstDataRow; row <= 200; row += 1) {
    const symbol = sheet.getRange(`A${row}`).values?.[0]?.[0];
    if (!symbol) break;
    writeRow(sheet, row, symbolKey(symbol));
  }
}

syncRows('01_观察名单', 4, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  if (!v) return;
  sheet.getRange(`F${row}:I${row}`).values = [[cellValue(v.current_price), cellValue(v.fair_value), cellValue(v.safety_margin), v.valuation_status]];
  sheet.getRange(`K${row}:L${row}`).values = [[v.build_signal, cellValue(v.target_weight)]];
  sheet.getRange(`N${row}:P${row}`).values = [[v.build_signal === '待数据' ? '等待数据' : 'Agent 自动验证', payload.generated_at, v.data_status]];
});

syncRows('04_估值跟踪', 4, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  const p = pointBySymbol.get(symbol) ?? {};
  if (!v) return;
  sheet.getRange(`K3:R3`).values = [['PE \u76ee\u6807\u500d\u6570', 'PB \u76ee\u6807\u500d\u6570', 'PE \u6a21\u578b\u5408\u7406\u4ef7(\u5143)', 'PB \u6a21\u578b\u5408\u7406\u4ef7(\u5143)', '\u7efc\u5408\u5408\u7406\u4ef7(\u5143)', '\u5b89\u5168\u8fb9\u9645', '\u4f30\u503c\u72b6\u6001', '\u6a21\u578b/\u590d\u6838\u8bf4\u660e']];
  sheet.getRange(`C${row}:U${row}`).values = [[cellValue(v.current_price), cellValue(p.eps_ttm?.value), cellValue(p.bvps?.value), cellValue(p.fcf_per_share?.value), cellValue(p.dps_ttm?.value), positiveRatio(v.current_price, p.eps_ttm?.value), positiveRatio(v.current_price, p.bvps?.value), null, cellValue(p.model_target_pe?.value), cellValue(p.model_target_pb?.value), cellValue(p.model_pe_fair_value?.value), cellValue(p.model_pb_fair_value?.value), cellValue(v.fair_value), cellValue(v.safety_margin), v.valuation_status, 'PE/PB \u89c4\u5219\u6a21\u578b\uff1b\u5f85\u590d\u6838', p.model_fair_value?.source_id ?? p.current_price?.source_id ?? null, payload.generated_at, v.data_status]];
});

syncRows('05_仓位管理', 10, (sheet, row, symbol) => {
  const v = valuationBySymbol.get(symbol);
  if (!v) return;
  sheet.getRange(`C${row}:D${row}`).values = [[v.build_signal, cellValue(v.target_weight)]];
  sheet.getRange(`F${row}`).values = [[cellValue(v.current_price)]];
  sheet.getRange(`K${row}`).values = [[v.build_signal === '待数据' ? '等待数据' : 'Agent 自动验证']];
});

const financialFields = ['revenue', 'revenue_yoy', 'net_income', 'net_income_yoy', 'roe', 'roic', 'gross_margin', 'net_margin', 'operating_cash_flow', 'free_cash_flow', 'operating_cash_flow_to_net_income', 'debt_ratio', 'cash', 'interest_bearing_debt', 'eps_ttm', 'dps_ttm', 'payout_ratio'];
// This is the evidence-facing coverage tab, so keep both the decision ratios
// and their official-statement inputs visible.  Users can trace a debt ratio
// or gross margin back to the actual verified asset, liability and cost facts.
const coverageFinancialFields = [
  ...financialFields,
  'operating_cost', 'total_assets', 'total_liabilities',
  'short_term_borrowings', 'current_portion_long_term_debt',
  'long_term_borrowings', 'bonds_payable', 'capital_expenditure',
  'eps_annual', 'eps_reported', 'bvps',
];
const bankOnlyInapplicableFields = new Set(['revenue_yoy', 'roic', 'net_margin', 'free_cash_flow']);
const bankSymbols = new Set(['600036', '601288']);
syncRows('03_财务指标', 4, (sheet, row, symbol) => {
  const p = pointBySymbol.get(symbol) ?? {};
  const values = financialFields.map((field) => {
    if (bankSymbols.has(symbol) && bankOnlyInapplicableFields.has(field)) return '\u4e0d\u9002\u7528\uff08\u94f6\u884c\u53e3\u5f84\uff09';
    if (field === 'eps_ttm') return cellValue((p.eps_ttm ?? p.eps_annual ?? p.eps_reported)?.value);
    return cellValue(p[field]?.value);
  });
  const source = financialFields.map((field) => p[field]?.source_id).find(Boolean) ?? null;
  const period = financialFields.map((field) => p[field]?.period_label).find(Boolean) ?? null;
  sheet.getRange(`C${row}:V${row}`).values = [[displayPeriod(period), ...values, source, financialSummary(p)]];
});

const observationSheet = workbook.worksheets.getItem('01_观察名单');
const disclosureBySymbol = new Map((payload.disclosures ?? []).map((row) => [row.symbol, row]));
const annualReportSheet = workbook.worksheets.getItem('10_\u5e74\u62a5\u8ddf\u8e2a');
for (let row = 4; row <= 200; row += 1) {
  const symbol = annualReportSheet.getRange(`A${row}`).values?.[0]?.[0];
  if (!symbol) break;
  const disclosure = disclosureBySymbol.get(symbolKey(symbol));
  if (!disclosure) continue;
  const reportStatus = disclosure.review_status === 'verified'
    ? '\u5b98\u65b9\u539f\u4ef6\u5df2\u590d\u6838'
    : '\u5b98\u65b9\u539f\u4ef6\u5f85\u590d\u6838';
  annualReportSheet.getRange(`C${row}:E${row}`).values = [[
    displayPeriod(disclosure.report_period),
    `${reportStatus}: ${disclosure.title}`,
    disclosure.published_at,
  ]];
  annualReportSheet.getRange(`M${row}`).values = [[disclosure.source_url]];
}

const qualityBySymbol = new Map();
for (let row = 4; row <= 200; row += 1) {
  const symbol = observationSheet.getRange(`A${row}`).values?.[0]?.[0];
  if (!symbol) break;
  qualityBySymbol.set(symbolKey(symbol), observationSheet.getRange(`J${row}`).values?.[0]?.[0] ?? null);
}
const positionSheet = workbook.worksheets.getItem('05_仓位管理');
const positionBySymbol = new Map();
for (let row = 10; row <= 200; row += 1) {
  const symbol = positionSheet.getRange(`A${row}`).values?.[0]?.[0];
  if (!symbol) break;
  positionBySymbol.set(symbolKey(symbol), positionSheet.getRange(`H${row}`).values?.[0]?.[0] ?? null);
}

const monthlySheet = workbook.worksheets.getItem('06_月度跟踪');
const monthlyRowByKey = new Map();
let nextMonthlyRow = 4;
for (; nextMonthlyRow <= 500; nextMonthlyRow += 1) {
  const month = monthlySheet.getRange(`A${nextMonthlyRow}`).values?.[0]?.[0];
  if (!month) break;
  const symbol = monthlySheet.getRange(`B${nextMonthlyRow}`).values?.[0]?.[0];
  if (symbol) monthlyRowByKey.set(`${month}|${symbolKey(symbol)}`, nextMonthlyRow);
}
for (const snapshot of payload.monthly_snapshots ?? []) {
  const symbol = symbolKey(snapshot.symbol);
  const key = `${snapshot.snapshot_month}|${symbol}`;
  let row = monthlyRowByKey.get(key);
  if (!row) {
    row = nextMonthlyRow;
    nextMonthlyRow += 1;
    monthlyRowByKey.set(key, row);
    monthlySheet.getRange(`A${row}:C${row}`).values = [[snapshot.snapshot_month, symbol, snapshot.name]];
  }
  const snapshotAt = monthlySheet.getRange(`P${row}`).values?.[0]?.[0];
  if (snapshotAt) continue;
  monthlySheet.getRange(`D${row}:M${row}`).values = [[
    cellValue(snapshot.current_price),
    cellValue(qualityBySymbol.get(symbol)),
    cellValue(snapshot.safety_margin),
    snapshot.valuation_status,
    snapshot.build_signal,
    cellValue(positionBySymbol.get(symbol)),
    cellValue(snapshot.revenue_yoy),
    cellValue(snapshot.net_income_yoy),
    cellValue(snapshot.roe),
    null,
  ]];
  monthlySheet.getRange(`O${row}:P${row}`).values = [[snapshot.data_status, snapshot.snapshot_at]];
}

const auditSheet = workbook.worksheets.getItem('11_数据源审计');
let auditRow = 4;
const existingAuditKeys = new Set();
for (let row = 4; row <= 1000; row += 1) {
  const values = auditSheet.getRange(`A${row}:D${row}`).values?.[0] ?? [];
  if (!values[0]) continue;
  if (String(values[0]).startsWith('EXAMPLE-')) {
    auditSheet.getRange(`A${row}:R${row}`).values = [Array(18).fill(null)];
    continue;
  }
  existingAuditKeys.add(values.map((value) => String(value ?? '')).join('|'));
  auditRow = row + 1;
}
for (const audit of payload.audits) {
  const auditKey = [audit.source_id, audit.symbol, audit.field_name, audit.period_label]
    .map((value) => String(value ?? '')).join('|');
  if (existingAuditKeys.has(auditKey)) continue;
  auditSheet.getRange(`A${auditRow}:R${auditRow}`).values = [[audit.source_id, audit.symbol, audit.field_name, audit.period_label, cellValue(audit.value), audit.unit, audit.source_name, audit.source_url, null, null, audit.fetched_at, audit.published_at, audit.parser_version, audit.sha256, null, audit.validation_status, audit.human_reviewed ? '是' : '否', '由本地 Agent 同步']];
  existingAuditKeys.add(auditKey);
  auditRow += 1;
}

function columnLabel(columnNumber) {
  let value = columnNumber;
  let label = '';
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

function replaceSheetRows(sheet, headers, rows) {
  // Clear enough rows to remove stale entries when a later screen contains
  // fewer candidates than the prior all-market run.
  const rowCount = Math.max(2001, rows.length + 1);
  const lastColumn = columnLabel(headers.length);
  sheet.getRange(`A1:${lastColumn}${rowCount}`).values = Array.from(
    { length: rowCount },
    (_, index) => index === 0 ? headers : Array(headers.length).fill(null),
  );
  if (rows.length) sheet.getRange(`A2:${lastColumn}${rows.length + 1}`).values = rows;
}

const reminderSheet = workbook.worksheets.getOrAdd('12_提醒');
function enrichmentStatusLabel(status) {
  return {
    pending_official_filings: '待归档官方财报',
    processing: '正在归档官方财报',
    official_filings_archived: '官方原件已归档，待Agent自动验证',
    retry: '归档异常，待重试',
    manual_review_required: '归档连续失败，Agent将自动重试',
  }[status] ?? '待归档官方财报';
}

function auditSummary(value) {
  if (!value) return null;
  const text = String(value);
  if (text.includes('ProxyError')) return 'ProxyError: primary market source unavailable; see source_id for full audit.';
  if (text.includes('ConnectionError')) return 'ConnectionError: primary market source unavailable; see source_id for full audit.';
  return text.length > 240 ? `${text.slice(0, 237)}...` : text;
}

const reminders = (payload.reminders ?? []).map((row) => [
  // Financial quality is a research-ranking layer. It never overrides the
  // independent valuation and evidence gates that control build signals.
  ...(() => {
    const q = financialQualityBySymbol.get(row.symbol) ?? {};
    return [
  row.priority, row.action, row.symbol, row.name, row.board, row.sector, row.reason,
  cellValue(row.current_price), cellValue(row.pe), cellValue(row.pb), enrichmentStatusLabel(row.enrichment_status),
  row.valuation_signal, row.valuation_status, cellValue(row.safety_margin), row.valuation_data_status,
  cellValue(q.total_score), q.quality_status ?? '待补证', cellValue(q.coverage_ratio),
  row.market_source, auditSummary(row.market_fallback_reason), row.industry_mapping_count, row.source_id, row.as_of,
    ];
  })(),
]);
replaceSheetRows(reminderSheet,
  ['优先级', '建议动作', '股票代码', '公司名称', '上市板块', '行业', '原因', '当前价(元)', 'PE', 'PB', '财报补全状态', '估值信号', '估值状态', '安全边际', '估值数据状态', '财务质量分', '财务质量状态', '质量覆盖率', '行情来源', '行情异常', '行业映射数量', 'source_id', '数据时点'],
  reminders,
);

const marketSheet = workbook.worksheets.getOrAdd('13_全市场初筛');
const candidates = (payload.market_candidates ?? []).map((row) => [
  // Keep the market screen and the financial-quality result adjacent for
  // sorting, while retaining separate status fields for missing evidence.
  ...(() => {
    const q = financialQualityBySymbol.get(row.symbol) ?? {};
    return [
  row.symbol, row.name, row.board, row.sector, cellValue(row.current_price), cellValue(row.pe), cellValue(row.pb),
  cellValue(Number(row.market_cap) / 100000000), cellValue(row.initial_score), row.status,
  cellValue(q.total_score), q.quality_status ?? '待补证', cellValue(q.coverage_ratio),
  row.market_source, auditSummary(row.market_fallback_reason), row.industry_mapping_count, row.source_id, row.screen_date,
    ];
  })(),
]);
replaceSheetRows(marketSheet,
  ['股票代码', '公司名称', '上市板块', '行业', '当前价(元)', 'PE', 'PB', '总市值(亿元)', '初筛评分', '状态', '财务质量分', '财务质量状态', '质量覆盖率', '行情来源', '行情异常', '行业映射数量', 'source_id', '筛选日期'],
  candidates,
);

const financialCoverageSheet = workbook.worksheets.getOrAdd('15_公司财务覆盖');
const financialCoverageRows = (payload.market_candidates ?? []).map((candidate) => {
  const quality = financialQualityBySymbol.get(candidate.symbol) ?? {};
  const points = pointBySymbol.get(candidate.symbol) ?? {};
  const financialPoints = Object.values(points).filter((point) => coverageFinancialFields.includes(point.field_name));
  const sourceIds = [...new Set(financialPoints.map((point) => point.source_id).filter(Boolean))];
  const periods = financialPoints.map((point) => point.period_label).filter(Boolean);
  const verified = financialPoints.filter((point) => point.validation_status === 'verified').length;
  const pending = financialPoints.filter((point) => point.validation_status !== 'verified').length;
  return [
    candidate.symbol, candidate.name, candidate.board, candidate.sector, candidate.screen_date,
    candidate.enrichment_status, displayPeriod(periods[0]), verified, pending, financialSummary(points, coverageFinancialFields),
    quality.model_type ?? 'general_enterprise', quality.quality_status ?? '待补证', cellValue(quality.total_score), cellValue(quality.coverage_ratio),
    sourceIds.join(', '), ...coverageFinancialFields.map((field) => cellValue(points[field]?.value)),
  ];
});
replaceSheetRows(financialCoverageSheet,
  [
    '股票代码', '公司名称', '上市板块', '行业', '初筛日期', '财报队列状态', '最新财报期',
    '已验证字段数', '待验证字段数', '数据状态', '质量模型', '财务质量状态', '财务质量分', '质量覆盖率', '源证据ID', ...coverageFinancialFields,
  ],
  financialCoverageRows,
);

const sectorSummarySheet = workbook.worksheets.getOrAdd('16_板块行业汇总');
const sectorSummary = new Map();
for (const candidate of payload.market_candidates ?? []) {
  const key = `${candidate.board}|${candidate.sector}`;
  const points = pointBySymbol.get(candidate.symbol) ?? {};
  const verifiedFields = Object.values(points)
    .filter((point) => financialFields.includes(point.field_name) && point.validation_status === 'verified');
  const row = sectorSummary.get(key) ?? {
    board: candidate.board, sector: candidate.sector, candidates: 0, focus: 0,
    scoreTotal: 0, verifiedCompanies: 0, verifiedFields: 0,
  };
  row.candidates += 1;
  row.focus += Number(candidate.initial_score) >= 55 ? 1 : 0;
  row.scoreTotal += Number(candidate.initial_score);
  row.verifiedCompanies += verifiedFields.length ? 1 : 0;
  row.verifiedFields += verifiedFields.length;
  sectorSummary.set(key, row);
}
const sectorSummaryRows = [...sectorSummary.values()]
  .sort((left, right) => right.focus - left.focus || right.candidates - left.candidates || left.board.localeCompare(right.board) || left.sector.localeCompare(right.sector))
  .map((row) => [
    row.board, row.sector, row.candidates, row.focus,
    Number((row.scoreTotal / row.candidates).toFixed(2)), row.verifiedCompanies, row.verifiedFields,
  ]);
replaceSheetRows(sectorSummarySheet,
  ['上市板块', '行业', '初筛候选数', '重点观察数', '平均初筛分', '有已验证财报公司数', '已验证字段数'],
  sectorSummaryRows,
);

const financialQualitySheet = workbook.worksheets.getOrAdd('17_财务质量评分');
const financialQualityRows = (payload.market_candidates ?? []).map((candidate) => {
  const quality = financialQualityBySymbol.get(candidate.symbol) ?? {};
  return [
    candidate.symbol, candidate.name, candidate.board, candidate.sector,
    quality.model_type ?? 'general_enterprise', quality.quality_status ?? '待补证',
    cellValue(quality.total_score), cellValue(quality.coverage_ratio),
    cellValue(quality.profitability_score), cellValue(quality.cash_flow_score),
    cellValue(quality.balance_sheet_score), cellValue(quality.growth_score),
    (quality.reasons ?? []).join('；').slice(0, 1000), JSON.stringify(quality.calculation_details ?? {}).slice(0, 2000),
  ];
});
replaceSheetRows(financialQualitySheet,
  ['股票代码', '公司名称', '上市板块', '行业', '质量模型', '质量状态', '财务质量分', '质量覆盖率', '盈利能力分', '现金流分', '资产负债表分', '成长分', '阻断原因', '计算与证据'],
  financialQualityRows,
);

const filingCandidateSheet = workbook.worksheets.getOrAdd('14_财报候选');
// Excel is the research front door, not the archive. Keep a bounded recent
// evidence queue here; PostgreSQL and the local cold archive retain every PDF.
const filingCandidates = (payload.filing_candidates ?? []).slice(0, 2500).map((row) => [
  row.candidate_id, row.symbol, row.name, row.report_period, row.report_kind, row.field_name,
  cellValue(row.value), row.unit, cellValue(row.page_number), row.source_label,
  row.status, row.source_url, row.sha256, String(row.excerpt ?? '').slice(0, 1000),
]);
replaceSheetRows(filingCandidateSheet,
  ['candidate_id', '股票代码', '公司名称', '报告期', '报告类型', '字段', '候选值', '单位', '页码', '原始标签', 'Agent验证状态', '官方URL', '文件SHA-256', '原文摘录'],
  filingCandidates,
);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
