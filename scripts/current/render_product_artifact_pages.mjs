import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(import.meta.dirname, '../..');
const argument = flag => {
  const index = process.argv.indexOf(flag);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Required argument: ${flag}`);
  return process.argv[index + 1];
};
const runtimePath = value => {
  const resolved = path.resolve(root, value);
  if (!resolved.startsWith(path.join(root, 'runtime') + path.sep)) throw new Error('Artifact must remain under runtime');
  return resolved;
};
const inputPath = runtimePath(argument('--publication-input'));
const output = runtimePath(argument('--output'));
const raw = await fs.readFile(inputPath);
const publication = JSON.parse(raw);
if (crypto.createHash('sha256').update(raw).digest('hex') !== argument('--sha256')) throw new Error('Publication input drift');
if (publication.action !== 'no_order' || publication.publication_approved !== false || publication.canonical_written !== false) throw new Error('Unsupported publication boundary');
for (const binding of publication.source_bindings) {
  const source = path.resolve(root, binding.path);
  if (!source.startsWith(root + path.sep)) throw new Error('Source escapes project');
  const hash = crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex');
  if (hash !== binding.sha256) throw new Error('Source hash drift: ' + binding.path);
}
const snapshot = publication.snapshot;
const displayPath = runtimePath(argument('--display-input'));
const displayRaw = await fs.readFile(displayPath);
const display = JSON.parse(displayRaw);
if (display.input_sha256 !== crypto.createHash('sha256').update(raw).digest('hex')) throw new Error('Display input drift');
if (display.policy_binding.sha256 !== crypto.createHash('sha256').update(await fs.readFile(path.join(root, display.policy_binding.path))).digest('hex')) throw new Error('Display policy drift');
const publicText = value => typeof value === 'string' ? display.strings[value] ?? value : value;
const readModel = JSON.parse(await fs.readFile(path.join(root, publication.read_model_binding.path)));
const decisionBinding = readModel.decision_workbench_binding;
const decision = decisionBinding ? JSON.parse(await fs.readFile(path.join(root, decisionBinding.path))) : null;
const wb = Workbook.create();
const layouts = new Map();
const label = value => typeof value === 'object' ? value?.user_label ?? '' : value ?? '';
const assessment = value => value.available ? value.value_text : value.unavailable_reason;
const reviews = company => Object.fromEntries(company.decision_review);
const mainReason = company => {
  const review = reviews(company);
  for (const key of ['为什么未进入更高状态', '尚缺证据', '最强反证']) {
    if (review[key]) return review[key];
  }
  const blocker = company.decision_process.find(step => step.key === 'decision_gate' && step.status === 'BLOCKED')
    ?? company.decision_process.find(step => step.status === 'BLOCKED');
  return blocker?.reason ?? '未记录当前原因';
};
const steps = { financial_facts: '财务事实', business_quality: '商业质量', model_applicability: '模型适用性', valuation: '估值', price_bridge: '价格与估值', research_gate: '研究复核', portfolio_gate: '组合风险', decision_gate: '建议结论' };
const states = { PASS: '通过', CONDITIONAL: '条件性结果', BLOCKED: '未通过' };
const sections = {business_quality:'商业质量', financial_quality:'财务质量', capital_allocation:'资本配置', valuation:'估值', dividend:'分红', risks_counterevidence:'风险与反证'};
const names = ['01_今日', '02_机会', '决策过程', '03_公司', '04_我的组合', '05_事件', '06_系统与审计'];
for (const name of names) wb.worksheets.add(name);
function chunks(value, width) {
  const text = String(value ?? '');
  const result = [];
  let start = 0, lines = 1, used = 0;
  for (let index = 0; index < text.length; index++) {
    const size = text.charCodeAt(index) >= 0x2e80 ? 2 : 1;
    if (text[index] === '\n' || used + size > width - 1) {
      if (++lines > 13) {
        result.push(text.slice(start,index));
        start = index; lines = 1;
      }
      used = 0;
    }
    if (text[index] !== '\n') used += size;
  }
  result.push(text.slice(start));
  return result;
}
function table(name, title, headers, rows, widths) {
  const ws = wb.worksheets.getItem(name);
  if (name !== names[6]) rows = rows.map(row => row.map(publicText));
  rows = rows.flatMap(row => {
    const pieces = row.map((value,index)=>chunks(value,widths[index]));
    return Array.from({length:Math.max(...pieces.map(parts=>parts.length))},(_,page)=>
      row.map((value,index)=>pieces[index].length===1 && page===0 ? value : pieces[index][page] ?? (index<2?value:'')));
  });
  layouts.set(name, rows);
  ws.showGridLines = false;
  const last = String.fromCharCode(64 + headers.length);
  const extent = `A1:${last}${rows.length + 6}`;
  ws.getRange(extent).format.font = {name:'Microsoft YaHei', size:11, color:'#202828'};
  ws.getRange(extent).format.wrapText = true;
  ws.getRange(extent).format.verticalAlignment = 'center';
  for (let i = 0; i < widths.length; i++) ws.getRange(`${String.fromCharCode(65+i)}1:${String.fromCharCode(65+i)}${rows.length+6}`).format.columnWidth = widths[i];
  ws.getRange(`A2:${last}2`).merge();
  ws.getRange('A2').values = [[title]];
  ws.getRange('A2').format.font = {name:'Microsoft YaHei', size:17, bold:true, color:'#202828'};
  ws.getRange(`A2:${last}2`).format.rowHeight = 35;
  ws.getRange(`A3:${last}3`).merge();
  ws.getRange('A3').values = [[`展示日期 ${snapshot.as_of}；工程预览，正式工作簿未替换。各公司的证据和估值日期分别保留。`]];
  ws.getRange(`A3:${last}3`).format.rowHeight = 32;
  ws.getRange('A1').formulas = [[`=HYPERLINK("#'01_今日'!A1","返回今日")`]];
  ws.getRange(`A1:${last}1`).format = {wrapText:false, rowHeight:24};
  ws.getRange(`A5:${last}${rows.length+5}`).values = [headers,...rows];
  ws.getRange(`A5:${last}5`).format = {fill:'#255C50',font:{bold:true,color:'#FFFFFF'},rowHeight:34,wrapText:true};
  for (let i=0; i<rows.length; i++) {
    const height = Math.max(42,...rows[i].map((value,col)=> 22*(String(value??'').split('\n').reduce((sum,line)=>sum+Math.max(1,Math.ceil(line.length/(widths[col]*0.44))),0)+1)));
    ws.getRange(`A${i+6}:${last}${i+6}`).format.rowHeight = height;
    if (i%2===1) ws.getRange(`A${i+6}:${last}${i+6}`).format.fill='#F2F5F4';
  }
  ws.freezePanes.freezeRows(5);
  return ws;
}
const reviewRows = snapshot.companies.map(c=>{
  const r=reviews(c);
  return [`${c.company_name}\n${c.symbol}`,label(c.research_status),r['当前决策状态']??'待研究复核',mainReason(c),r['下一触发']??c.next_trigger];
});
// Keep independently verified dated observations visible without admitting a decision price.
const marketObservations = (snapshot.today_items ?? []).filter(item=>item.category?.code === 'MARKET_DATA');
reviewRows.push(...marketObservations.map(item=>[
  `${item.company}\n${item.symbol}`, '独立行情观察', item.current_status,
  `${item.what_happened}\n${item.why_it_matters}`, item.next_step,
]));
table(names[0],'今日研究与待处理事项',['公司','研究状态','当前结论','主要原因','下一触发'],reviewRows,[19,22,30,65,58]);
table(names[1],'研究机会',['公司','研究状态','行情观察','估值状态','价格评估','当前结论'],snapshot.companies.map(c=>{
  const r=reviews(c); const observation=marketObservations.findLast(item=>item.symbol === c.symbol);
  const legacyObservation=r['已核验收盘行情（未桥接估值）'];
  return [`${c.company_name}\n${c.symbol}`,label(c.research_status),observation?.what_happened??legacyObservation?.split('；')[0]??assessment(c.price),assessment(c.valuation),r['价格区域']??'尚未完成当前价格评估',r['当前决策状态']??'待研究复核'];
}),[19,22,33,65,30,32]);
table(names[2],'决策过程',['公司','检查步骤','状态','原因','下一步'],snapshot.companies.flatMap(c=>c.decision_process.map(s=>[`${c.company_name}\n${c.symbol}`,steps[s.key],states[s.status],s.reason,s.next_action])),[19,20,16,74,55]);
const companyRows=snapshot.companies.flatMap(c=>[
  [`${c.company_name}\n${c.symbol}`,'原始投资逻辑',c.original_thesis],
  ...c.sections.map(s=>[c.symbol,sections[s.key],s.summary]),
  ...c.decision_review.filter(([key])=>!key.startsWith('估值敏感性 ')).map(([key,value])=>[c.symbol,publicText(key),publicText(value)]),
  [c.symbol,'估值情景（非买入价）',assessment(c.valuation)],
  [c.symbol,'下一触发',c.next_trigger],
]);
const companySheet=table(names[3],'公司研究',['公司','内容','研究结果'],companyRows,[19,28,125]);
const shownCompanyRows = layouts.get(names[3]);
const valueRow=shownCompanyRows.length+9;
if (decision) {
  companySheet.getRange(`A${valueRow}:C${valueRow}`).values=[['公司代码','压力情景','条件情景值（元/股，非合理价）']];
  for (const [i,key] of ['bear','base','bull'].entries()) companySheet.getRange(`A${valueRow+i+1}:C${valueRow+i+1}`).values=[[decision.symbol,['低值压力情景','中值压力情景','高值压力情景'][i],decision.valuation[`${key}_value`] == null ? null : Number(decision.valuation[`${key}_value`])]];
  companySheet.getRange(`C${valueRow+1}:C${valueRow+3}`).setNumberFormat('0.00');
  // Four rows fit within the space previously taken by three 30pt rows.
  companySheet.getRange(`A${valueRow}:C${valueRow+3}`).format.rowHeight=22;
}
table(names[4],'我的组合',['状态','内容'],[[label(snapshot.portfolio.status),snapshot.portfolio.connection_hint],['个人仓位','尚未接入真实组合；仓位与金额为空。']],[30,100]);
table(names[5],'事件',['公司','事件','当前结论','下一步'],snapshot.events.length?snapshot.events.map(e=>[e.company_name,e.what_happened,e.current_conclusion,e.next_step]):[['','当前没有已分类的用户事件。','公告原件取得不代表事件影响已批准。','完成证据绑定的事件审查。']],[20,55,65,55]);
const auditRows = snapshot.audit_evidence.map(e=>[e.evidence_id,e.title,e.artifact_type,e.path,e.source_url??'',e.sha256,e.available_at??'']);
const auditSheet = table(names[6],'系统与审计',['证据编号','名称','类型','路径','原始来源网址','SHA-256','可用时间'],auditRows,[40,30,27,75,72,72,28]);
const shownAuditRows = layouts.get(names[6]);
for (let i = 0; i < shownAuditRows.length; i++) {
  const row = shownAuditRows[i];
  const evidence = snapshot.audit_evidence.find(e => e.evidence_id === row[0]);
  if (!evidence?.source_url || row[4] !== evidence.source_url) continue;
  const url = new URL(evidence.source_url);
  if (url.protocol !== 'https:' || url.username || url.password || /["\r\n]/.test(evidence.source_url)) throw new Error('Unsupported evidence URL');
  auditSheet.getRange(`E${i+6}`).formulas = [[`=HYPERLINK("${evidence.source_url}","${evidence.source_url}")`]];
}
const auditStart = shownAuditRows.length + 9;
const eventAudit = snapshot.event_audit_decisions ?? [];
auditSheet.getRange(`A${auditStart}:G${auditStart+eventAudit.length}`).values = [
  ['事件编号','审查状态','展示方式','是否用户可见','证据编号','观察时间','审查结论'],
  ...eventAudit.map(e=>[e.event_id,e.state,e.disposition,e.visible,e.evidence_refs.join('\n'),e.observed_at,e.corrected_conclusion??'']),
];
auditSheet.getRange(`A${auditStart}:G${auditStart+eventAudit.length}`).format={wrapText:true,rowHeight:92,verticalAlignment:'center'};
const companyStart = new Map(snapshot.companies.map(c=>[c.symbol,shownCompanyRows.findIndex(row=>String(row[0]).endsWith('\n'+c.symbol))+6]));
for (const name of names.slice(0,2)) {
  const ws = wb.worksheets.getItem(name);
  layouts.get(name).forEach((row,index)=>{
    const c = snapshot.companies.find(c=>String(row[0]).endsWith('\n'+c.symbol));
    if (!c) return;
    const title = `${c.company_name} ${c.symbol}`.replaceAll('"', '""');
    ws.getRange(`A${index+6}`).formulas=[[`=HYPERLINK("#'03_公司'!A${companyStart.get(c.symbol)}","${title}")`]];
  });
}
for (let i=0; i<shownCompanyRows.length; i++) if (String(shownCompanyRows[i][0]).includes('\n')) {
  const c = snapshot.companies.find(c=>String(shownCompanyRows[i][0]).endsWith('\n'+c.symbol));
  if (!c) continue;
  const auditIndex = shownAuditRows.findIndex(row=>c.evidence_refs.includes(row[0]));
  const title = `${shownCompanyRows[i][1]}（证据）`.replaceAll('"', '""');
  if (auditIndex >= 0) companySheet.getRange(`B${i+6}`).formulas=[[`=HYPERLINK("#'06_系统与审计'!A${auditIndex+6}","${title}")`]];
}
wb.recalculate();
if (await fs.stat(output).catch(()=>null)) throw new Error('Preview already exists');
await fs.mkdir(path.dirname(output), {recursive:true});
const exportFile=await SpreadsheetFile.exportXlsx(wb);
await exportFile.save(output);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!',options:{useRegex:true,maxResults:20}})).ndjson);
const receipt={schema_version:'d2-product-engineering-preview-v1',input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),workbook_sha256:crypto.createHash('sha256').update(await fs.readFile(output)).digest('hex'),sheets:names,source_count:publication.source_bindings.length,display_binding:{path:path.relative(root,displayPath).replaceAll('\\','/'),sha256:crypto.createHash('sha256').update(displayRaw).digest('hex')},scope:'ENGINEERING_PREVIEW_NOT_CANONICAL_OR_USER_ACCEPTANCE',canonical_written:false,action:'no_order'};
for (const binding of publication.source_bindings) {
  if (crypto.createHash('sha256').update(await fs.readFile(path.resolve(root, binding.path))).digest('hex') !== binding.sha256) throw new Error('Source changed during export');
}
await fs.writeFile(output.replace(/\.xlsx$/i,'-receipt.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
console.log(JSON.stringify(receipt));
