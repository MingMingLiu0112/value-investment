import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = path.resolve('D:/GPTProject/value-investment');
const out = path.join(root, 'runtime/frontend-stage-design');
await fs.mkdir(out, { recursive: true });

if (process.argv.includes('--inspect')) {
  const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(out, 'original-preview.xlsx')));
  console.log((await wb.inspect({ kind: 'sheet', include: 'id,name', maxChars: 4000 })).ndjson);
  for (const name of ['00_首页Dashboard', '00_公司总览', '21_决策验证', '05_仓位管理', '04_估值跟踪']) {
    console.log((await wb.inspect({ kind: 'table', range: `'${name}'!A1:H12`, tableMaxRows: 12, tableMaxCols: 8, tableMaxCellChars: 100, maxChars: 5000 })).ndjson);
    const img = await wb.render({ sheetName: name, range: 'A1:H15', scale: 1, format: 'png' });
    await fs.writeFile(path.join(out, `before-${name}.png`), new Uint8Array(await img.arrayBuffer()));
  }
  process.exit(0);
}

const hash = data => crypto.createHash('sha256').update(data).digest('hex');
async function pin(relative, filename = 'evidence.json') {
  const pointer = JSON.parse(await fs.readFile(path.join(root, relative), 'utf8'));
  const target = path.resolve(root, pointer.path, filename);
  if (!target.startsWith(root + path.sep)) throw new Error('Evidence escapes root');
  const raw = await fs.readFile(target);
  if (hash(raw) !== (pointer.sha256 || pointer.summary_sha256)) throw new Error(`Hash mismatch: ${relative}`);
  return { data: JSON.parse(raw), sha256: hash(raw), path: target };
}
const casesPin = await pin('runtime/excel-mvp-research-cases-latest.json');
const reviewPin = await pin('runtime/fixed-sample-admission-review-latest.json');
const records = casesPin.data.records;
const valuationPaths = {
  '600519': 'runtime/valuation-results/600519-current-equity-stage-b-latest.json',
  '000333': 'runtime/valuation-results/000333-fcff-stage-b-latest.json',
  '601088': 'runtime/valuation-results/601088-cyclical-stage-b-latest.json',
};
const valuations = {};
for (const [symbol, pointer] of Object.entries(valuationPaths)) valuations[symbol] = await pin(pointer);
const workbook = Workbook.create();
const names = ['00_投资工作台', '00_研究看板', '00_研究逻辑卡', '00_决策复核', '00_组合与股息', '00_跟踪与数据'];
const sheets = names.map(name => workbook.worksheets.add(name));
const [home, research, logic, decision, portfolio, tracking] = sheets;
const ink = '#243A35', green = '#176D56', blue = '#245D83', amber = '#FFF0CA', pale = '#EFF5F2', muted = '#52635D', border = '#D4DFD8';
const stamp = '2026-09-22';
const published = new Date().toLocaleDateString('en-CA', {timeZone: 'Asia/Shanghai'});
const links = [];
const comments = [];
function merge(ws, range, value, options = {}) {
  const r = ws.getRange(range); r.merge(); r.values = [[value]];
  r.format = { wrapText: true, verticalAlignment: 'center', ...options };
}
function band(ws, row, title) {
  merge(ws, `A${row}:L${row}`, title, { fill: green, font: { bold: true, color: '#FFFFFF', size: 12 } });
  ws.getRange(`A${row}:L${row}`).format.rowHeight = 29;
}
function line(ws, row, title, body, height = 49) {
  merge(ws, `A${row}:C${row}`, title, { fill: pale, font: { bold: true, color: ink } });
  merge(ws, `D${row}:L${row}`, body, { fill: '#FFFFFF' });
  ws.getRange(`A${row}:L${row}`).format.rowHeight = height;
}
function link(ws, range, title, target, cell = 'A1') {
  merge(ws, range, title, { fill: pale, font: { color: green, underline: 'single', bold: true } });
  links.push({ sheet: ws.name, ref: range.split(':')[0], location: `'${target}'!${cell}`, display: title });
}
function note(ws, cell, text) { comments.push({ sheet: ws.name, cell, text }); }
function table(ws, row, headers, rows, widths) {
  const end = String.fromCharCode(64 + headers.length);
  ws.getRange(`A${row}:${end}${row + rows.length}`).values = [headers, ...rows];
  ws.getRange(`A${row}:${end}${row}`).format = { fill: ink, font: { color: '#FFFFFF', bold: true }, rowHeight: 34, wrapText: true };
  ws.getRange(`A${row+1}:${end}${row + rows.length}`).format = { rowHeight: 74, wrapText: true, verticalAlignment: 'center' };
  rows.forEach((_, i) => { if (i % 2 === 0) ws.getRange(`A${row+i+1}:${end}${row+i+1}`).format.fill = pale; });
  if (rows.length) { const t = ws.tables.add(`A${row}:${end}${row + rows.length}`, true, 'StageTable' + sheets.indexOf(ws) + '_' + row); t.showFilterButton = true; }
  if (widths) widths.forEach((w, i) => { ws.getRange(`${String.fromCharCode(65+i)}:${String.fromCharCode(65+i)}`).format.columnWidth = w; });
}
for (const [i, ws] of sheets.entries()) {
  ws.showGridLines = false;
  ws.getRange('A1:L110').format = { font: { name: 'Microsoft YaHei', size: 11, color: ink }, columnWidth: 11, rowHeight: 24, verticalAlignment: 'center' };
  merge(ws, 'A1:L2', ['价值投资 | 研究与决策工作台', '研究看板 | 候选与重点关注', '研究逻辑卡 | 理解企业与反证', '决策复核 | 买入理由与买卖一致性', '组合与股息 | 现金回报与风险', '变化跟踪 | 数据与能力状态'][i], { fill: ink, font: { size: 19, bold: true, color: '#FFFFFF' } });
  merge(ws, 'A3:L3', `页面发布 ${published} | 研究快照 ${stamp}，非今日结论 | 自动监控尚未接入`, { font: { size: 10, color: muted } });
  names.forEach((name, j) => link(ws, `${String.fromCharCode(65+j*2)}4:${String.fromCharCode(66+j*2)}4`, ['工作台','研究看板','研究逻辑','决策复核','组合股息','变化数据'][j], name));
  ws.freezePanes.freezeRows(4);
}

band(home, 6, '现在可读：三家公司研究快照；正式决策与组合建议尚未接入');
const tiles = [['A7:C7','A8:C9','研究样本',records.length],['D7:F7','D8:F9','有条件三情景',1],['G7:I7','G8:I9','正式决策复核','未接入'],['J7:L7','J8:L9','个人组合核验','未接入']];
for(const [labelRange,valueRange,label,value] of tiles){merge(home,labelRange,label,{fill:pale,horizontalAlignment:'center',font:{color:muted}});merge(home,valueRange,value,{fill:pale,horizontalAlignment:'center',font:{size:22,bold:true,color:typeof value==='number'?green:muted}});}
home.getRange('A8').formulas=[["=COUNTA('00_跟踪与数据'!A30:A32)"]];
home.getRange('D8').formulas=[["=COUNTIF('00_跟踪与数据'!B30:B32,\"conditional_research_only\")"]];
note(home,'A8',`样本来自 ${casesPin.path}\nSHA256 ${casesPin.sha256}`);
note(home,'D8','仅统计已封存的条件研究情景，不代表生产估值或买入准入。');
band(home, 11, '研究注意力 | 尚未形成正式重点关注名单');
line(home,12,'贵州茅台 / 600519','有条件三情景；低置信度。优先复核量价、现金归属及优势持续期，尚未证明市场低估。',52);
line(home,13,'美的集团 / 000333','工业经营与财务公司口径尚未解决；FCFF暂不可用。先明确模型输入，不按低估值推断机会。',52);
line(home,14,'中国神华 / 601088','周期正常化输入未就绪；高当期股息不等于可持续股息。先研究中周期现金和必要资本开支。',52);
band(home,16,'阶段入口 | 尚未接入不等于没有风险或没有机会');
line(home,17,'买入 / 加仓复核','未接入决策前置条件与组合容量。当前不产生 BUY_REVIEW / ADD_REVIEW。',42);
line(home,18,'持有 / 减仓 / 退出','未接入个人持仓与原始买入论点。当前无法判断你的持仓应继续持有或退出。',42);
line(home,19,'今日重要变化','未接入持续事件扫描；不能把未扫描显示为“今日无变化”。',42);
link(home,'A21:D21','原始研究与证据','00_公司总览');
link(home,'E21:H21','人工持仓记录','05_仓位管理');
link(home,'I21:L21','人工交易记录','08_交易记录');
band(home,23,'已有样本的估值状态 | 条件估值不是买入资格');
home.getRange('A24:B26').values=[['状态','家数'],['有条件情景',1],['估值未就绪',2]];
home.getRange('B25').formulas=[['=D8']];
home.getRange('B26').formulas=[["=COUNTIF('00_跟踪与数据'!B30:B32,\"not_ready\")"]];
const chart=home.charts.add('bar',home.getRange('A24:B26'));chart.title='三家公司估值研究状态';chart.hasLegend=false;chart.setPosition('D24','L35');
chart.yAxis={numberFormatCode:'0.0'};
merge(home,'A28:C32','3家均未通过生产估值验收；正式重点关注名单尚未计算。',{fill:amber});

band(research,6,'已有研究样本 | 不是买入排行榜');
const modelLabel={'600519':'权益剩余收益','000333':'FCFF','601088':'周期正常化'};
const rowMap={};
// This table supports company/status filtering. Narrative evidence stays below it.
research.getRange('A9:A11').format.numberFormat='@';
table(research,8,['代码','公司','研究路径','估值状态','置信度','资料日期'],records.map(({case:c})=>[
  c.symbol,c.name,modelLabel[c.symbol],valuations[c.symbol].data.result.status==='conditional_research_only'?'条件研究':'未就绪',
  valuations[c.symbol].data.result.status==='conditional_research_only'?'低':'不适用',c.as_of]),[11,14,18,15,11,15]);
research.getRange('A9:F11').format.rowHeight=44;
research.freezePanes.freezeRows(8);
for(const [i,{case:c}] of records.entries()) {
  links.push({sheet:research.name,ref:`A${9+i}`,location:`'00_研究逻辑卡'!A${8+i*24}`,display:c.symbol});
  research.getRange(`A${9+i}`).format.font={color:green,underline:'single',bold:true};
}
merge(research,'G8:L11','当前连接3家封存研究样本。尚未运行正式关注池，不代表全市场只有这3家公司。',{fill:amber});
let r=14;
for(const record of records){const c=record.case;const v=valuations[c.symbol].data;rowMap[c.symbol]=r;
  merge(research,`A${r}:C${r}`,`${c.symbol} ${c.name}`,{fill:ink,font:{bold:true,color:'#FFFFFF'}});
  merge(research,`D${r}:L${r}`,c.investment_path,{fill:pale});
  line(research,r+1,'为什么研究',c.thesis,59);
  line(research,r+2,'估值能否参考',`模型：${modelLabel[c.symbol]}；${v.result.status==='conditional_research_only'?'条件研究，低置信度，非正式合理价':'估值未就绪，无可用三情景'}。研究门禁尚未通过。`,48);
  line(research,r+3,'最强反证',c.counter_evidence[0].text,67);
  line(research,r+4,'缺口 / 下一事件',`${c.blockers.slice(0,2).join('；')}\n${c.next_events.map(x=>x.text).slice(0,1).join('')}`,95);
  line(research,r+5,'信息时点',`研究日 ${c.as_of}；财务期 ${c.financial_period || c.financial_summary.period_end}；估值日 ${v.result.valuation_date}；报价日 ${v.price_bridge?.quote_date || '未接入'}。`,43);
  link(research,`A${r+6}:F${r+6}`,'完整论点、情景及失效条件','00_研究逻辑卡',`A${8+records.indexOf(record)*24}`);
  link(research,`G${r+6}:L${r+6}`,'原始公司研究','09_公司研究');
  note(research,`A${r}`,`ResearchCase ${c.research_version}; evidence SHA256 ${casesPin.sha256}; valuation SHA256 ${valuations[c.symbol].sha256}`);
  r+=9;
}
band(research,r,'全市场候选与重点关注 | M2待接入');
line(research,r+1,'四个研究通道','Quality / Dividend & Cash Return / Value / Cyclical。当前旧PE/PB初筛仅为历史baseline，不代表多通道已运行。',57);
line(research,r+2,'正式重点关注','未计算。未来允许0家公司，不为每日荐股降低标准。当前三家为研究样本，不自动进入重点关注。',52);
link(research,`A${r+4}:F${r+4}`,'旧候选与研究缺口（历史基线）','00_待完成公司');

band(logic,6,'研究论点可读；买入理由尚需正式决策与个人约束复核');
records.forEach(({case:c},i)=>link(logic,`${String.fromCharCode(65+i*4)}7:${String.fromCharCode(68+i*4)}7`,c.name,logic.name,`A${8+i*24}`));
for (const [index,record] of records.entries()) {
  const c=record.case,v=valuations[c.symbol].data.result,b=valuations[c.symbol].data.price_bridge; const start=8+index*24;
  band(logic,start,`${c.symbol} ${c.name} | ${modelLabel[c.symbol]} | ${c.as_of}`);
  line(logic,start+1,'生意 / 核心论点',c.thesis,63);
  line(logic,start+2,'主要回报来源',c.return_driver,51);
  line(logic,start+3,'市场可能错在哪里',c.mispricing_hypothesis,55);
  line(logic,start+4,'支持证据',c.positives.slice(0,2).map(x=>x.text).join('\n'),101);
  line(logic,start+5,'最强反证',c.counter_evidence.slice(0,2).map(x=>x.text).join('\n'),115);
  line(logic,start+6,'什么事实证明我错了',c.thesis_breakers.slice(0,2).map(x=>x.text).join('\n'),105);
  line(logic,start+7,'下一个复核事件',c.next_events.map(x=>x.text).slice(0,2).join('\n'),73);
  line(logic,start+8,'估值口径',`${v.valuation_date}；${modelLabel[c.symbol]}；${v.confidence}置信度。${v.status==='conditional_research_only'?'仅条件研究，不是正式合理价或交易区间。':'输入尚未就绪；不填0、不制造目标价。'}`,57);
  for(const [j,key] of ['bear_value','base_value','bull_value'].entries()) {
    const a=String.fromCharCode(65+j*4),e=String.fromCharCode(68+j*4);
    merge(logic,`${a}${start+9}:${e}${start+9}`,['Bear 悲观 / 元每股','Base 基准 / 元每股','Bull 乐观 / 元每股'][j],{fill:pale,font:{bold:true}});
    merge(logic,`${a}${start+10}:${e}${start+10}`,v[key]===null?'未就绪':Number(v[key]),{fill:v[key]===null?amber:pale,horizontalAlignment:'center',font:{size:17,color:blue,bold:true},numberFormat:'#,##0.00'});
    note(logic,`${a}${start+10}`,`后台估值结果，不是Excel重算。${valuations[c.symbol].path}\nSHA256 ${valuations[c.symbol].sha256}`);
  }
  line(logic,start+11,'价格 / 有效性',`归档报价 ${b?.current_price || '未接入'} ${b?.current_price?'元/股':''}；报价日 ${b?.quote_date || '未接入'}；桥接 ${b?.bridge_status || '未接入'}。本页不提供今日报价或买入结论。`,60);
  line(logic,start+12,'分红与资本回报','历史派息材料部分具备；可持续性尚未完成。当前股息率与正常化股息率、特别分红与经常分红不得混同。',58);
  line(logic,start+13,'为何现在买 / 加仓','尚未形成：研究结论未通过正式决策复核，个人组合容量与入场论点未接入。不能仅因看起来便宜而买入或加仓。',58);
  line(logic,start+14,'为何持有 / 减仓 / 退出','尚未形成个性化判断。需要原始买入论点、当前证据、估值变化和组合风险逐项比较。',56);
  line(logic,start+15,'原件追溯',`研究版本 ${c.research_version}\n研究证据 SHA256 ${casesPin.sha256}`,65);
  link(logic,`A${start+17}:F${start+17}`,'原研究卡和原件引用','00_公司总览');
  link(logic,`G${start+17}:L${start+17}`,'返回研究看板','00_研究看板',`A${rowMap[c.symbol]}`);
}

band(decision,6,'决策引擎未接入 | 不把研究样本转换成交易提醒');
line(decision,7,'BUY / ADD REVIEW','未接入；缺正式研究准入、价格判断和个人组合容量。不是当前没有机会。',49);
line(decision,8,'HOLD / REDUCE / EXIT','未接入；缺个人持仓、原始买入论点和新证据比较。不是默认继续持有。',49);
band(decision,10,'买入逻辑卡 | 正式输出前必须解释的内容');
for(const [i,[a,b]] of [['为何现在关注','生意、回报来源、可核验证据、市场预期差，而非一个总分。'],['价格与价值','三情景、假设、敏感性、报价时点、置信度；不把精确数字当确定性。'],['股息与风险','正常化分配、现金覆盖、资本投入、债务、最强反证与论点失效条件。'],['持有与跟踪','持有逻辑、下一事件、加仓/不加仓条件、组合容量与退出条件。']].entries()) line(decision,11+i,a,b,47);
band(decision,16,'买卖一致性 | 原始论点尚未接入，不伪造入场记录');
const consistency=[['原始核心论点','未接入','未比较'],['原始估值与置信度','未接入','未比较'],['原始股息论点','未接入','未比较'],['反证 / Thesis Breaker','未接入','未比较'],['组合与机会成本','未接入','未比较']];
for(const [i,[a,b,c]] of consistency.entries()){line(decision,17+i,a,`${b}；当前状态：${c}。`,37);}
line(decision,23,'卖出复核分类','论点破坏 / 永久价值损害 / 极端高估 / 组合与机会成本。每次指出哪条原始理由发生变化，涨跌幅不能单独触发。',59);
link(decision,'A25:F25','人工交易与补充理由','08_交易记录');
link(decision,'G25:L25','旧决策验证（历史实验）','21_决策验证');
line(decision,27,'人工确认与系统建议','人工成交仍记原交易记录。此页目前不捕获成交、不冻结Entry、不产生仓位；M3接入正式版本与审计后启用。',55);

band(portfolio,6,'个人组合未核验 | 未知不等于空仓或零风险');
for(const [i,[a,b]] of [['资产 / 现金 / 持仓','未接入经人工确认的组合快照。'],['单股 / 行业 / 共同风险','未评估；不得用默认仓位或样例本金代替你的实际情况。'],['Starter / Normal / Max','未启用；须结合置信度、下行风险、现金与集中度约束。'],['新增 / 停止加仓 / 减仓','未启用；股价下跌不是自动加仓理由，安全边际不等于仓位。']].entries())line(portfolio,7+i,a,b,48);
band(portfolio,12,'股息现金流 | 四种口径分别展示');
line(portfolio,13,'已到账股息','未接入真实到账记录；不是0元。',37);
line(portfolio,14,'已宣告未到账','未接入权益登记日与实际持股；不等同现金到账。',43);
line(portfolio,15,'Forward预测收入','未评估；须披露预测派息、持股和税费口径。',43);
line(portfolio,16,'Normalized可持续收入','未评估；须先研究中周期盈利、必要投入、债务与分配约束。',43);
line(portfolio,17,'股息集中度 / 可持续性','未评估；高当期股息不代表组合现金流稳定。成本股息率仅反映持有成本。',48);
link(portfolio,'A19:F19','核对原人工持仓记录','05_仓位管理');
link(portfolio,'G19:L19','查看原人工交易记录','08_交易记录');
band(portfolio,21,'后续准入所需的个人信息 | 不在此填入默认值');
line(portfolio,22,'账户与投资约束','可投资资产范围、现金、持仓、收入目标、流动性需要、期限、风险承受能力，由你确认后进入私有Portfolio。',58);
line(portfolio,23,'人工区与隐私','原持仓、交易、月度记录完整保留。此页仅展示未接入状态，不读取模板中的虚拟本金作为你的资产。',55);

band(tracking,6,'每日运行状态 | 自动监控未接入');
line(tracking,7,'今日重要变化','未知：没有完成事件扫描。不得解释为今日无变化。',44);
line(tracking,8,'今日新进 / 退出关注','未计算：全市场多通道候选和关注池尚未接入。',44);
line(tracking,9,'论点 / 股息 / 组合警报','未评估：未来重要变化提醒，无实质变化静默；源失联必须单独报警。',51);
band(tracking,11,'研究数据快照 | 快照Hash已核对，不代表重新核验了财报原件');
for(const [i,record]of records.entries()){const c=record.case,b=valuations[c.symbol].data.price_bridge;line(tracking,12+i,c.symbol+' '+c.name,`研究日 ${c.as_of}；估值日 ${valuations[c.symbol].data.result.valuation_date}；报价日 ${b?.quote_date||'未接入'}；股息研究 PARTIAL；未来日更尚未接入本前台。`,60);}
band(tracking,16,'能力阶段 | 页面已准备，不代表后台已实现');
for(const [i,[a,b]]of [['M1 真实研究工作台','本前台连接3家封存案例；新增M1研究成果尚未接入此页。'],['M2 全市场多通道','未接入：Quality、Dividend、Value、Cyclical，保留旧筛选基线。'],['M3 决策与买卖一致性','未接入：Logic Card、人工Entry、Journal、Consistency。'],['M4 组合与股息','未接入：个人组合容量、仓位复核与可持续股息收入。'],['M5 每日事件跟踪','未接入：新证据、依赖重算、静默与重要变化通知。'],['M6 真实使用验收','未通过：真实运行、用户理解、恢复能力与准入共同验收。']].entries())line(tracking,17+i,a,b,43);
link(tracking,'A24:F24','旧数据与证据索引','00_使用说明');
link(tracking,'G24:L24','原始证据明细','18_指标证据');
line(tracking,26,'发布边界',`本次是前端分阶段改版，展示快照 ${stamp}；不改估值参数、不新增决策信号、不连接生产服务。`,52);
note(tracking,'D12',`Research SHA256 ${casesPin.sha256}\nAdmission SHA256 ${reviewPin.sha256}`);
tracking.getRange('A29:D32').values=[['样本代码','后台估值状态','研究版本','展示批次'],...records.map(({case:c})=>[c.symbol,valuations[c.symbol].data.result.status,c.research_version,stamp])];
tracking.getRange('A30:A32').format.numberFormat='000000';
tracking.getRange('A29:D29').format={fill:ink,font:{color:'#FFFFFF',bold:true},wrapText:true,rowHeight:40};
tracking.getRange('A30:D32').format={wrapText:true,rowHeight:58};

// All links become native internal locations during package merge, avoiding external-file prompts in WPS.
await fs.writeFile(path.join(out, 'frontend-links.json'), JSON.stringify(links, null, 2));
workbook.comments.setSelf({displayName:'研究证据'});
for(const c of comments)workbook.comments.addThread({cell:workbook.worksheets.getItem(c.sheet).getRange(c.cell)},c.text);
const file=await SpreadsheetFile.exportXlsx(workbook);await file.save(path.join(out,'frontend-addon.xlsx'));
for(const ws of sheets){
  const last=ws===logic?26:ws===research?21:ws===home?35:28;
  const img=await workbook.render({sheetName:ws.name,range:`A1:L${last}`,scale:1.4,format:'png'});
  await fs.writeFile(path.join(out,`after-${ws.name}.png`),new Uint8Array(await img.arrayBuffer()));
}
for(const start of [32,56]) {
  const img=await workbook.render({sheetName:logic.name,range:`A${start}:L${start+18}`,scale:1.4,format:'png'});
  await fs.writeFile(path.join(out,`after-logic-${start}.png`),new Uint8Array(await img.arrayBuffer()));
}
console.log((await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
console.log(JSON.stringify({output:'frontend-addon.xlsx',sheets:names,records:records.length,links:links.length,sourceHashes:{research:casesPin.sha256,review:reviewPin.sha256}},null,2));
