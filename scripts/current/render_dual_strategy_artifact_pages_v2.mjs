import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

// The Windows renderer may fault while disposing native drawing resources after
// completing every awaited export/check. A clean supervisor verifies that receipt.
if (process.platform==='win32' && !process.argv.includes('--render-worker')) {
  const child=spawn(process.execPath,[process.argv[1],...process.argv.slice(2),'--render-worker'],{stdio:'inherit'});
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
  if (code===0) process.exit(0);
  if (![3221226505,-1073740791].includes(code)) process.exit(code??1);
  const taskRoot=path.resolve(import.meta.dirname,'../..');
  const args=process.argv;
  const arg=flag=>args[args.indexOf(flag)+1];
  const outputPath=path.resolve(taskRoot,arg('--output'));
  const receipt=JSON.parse(await fs.readFile(outputPath.replace(/\.xlsx$/i,'-receipt.json')));
  const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
  const inputBytes=await fs.readFile(path.resolve(taskRoot,arg('--publication-input')));
  if (receipt.action!=='no_order' || receipt.canonical_written!==false || receipt.input_sha256!==digest(inputBytes) || receipt.input_sha256!==arg('--sha256') || receipt.workbook_sha256!==digest(await fs.readFile(outputPath))) throw new Error('Native shutdown recovery receipt mismatch');
  const envelope=JSON.parse(inputBytes);
  for (const binding of [...envelope.source_bindings,...(receipt.extension_binding?.source_bindings??[])]) if (digest(await fs.readFile(path.resolve(taskRoot,binding.path)))!==binding.sha256) throw new Error('Native shutdown recovery source drift');
  if (receipt.manual_input_binding && digest(await fs.readFile(receipt.manual_input_binding.path))!==receipt.manual_input_binding.sha256) throw new Error('Native shutdown recovery manual input drift');
  if (args.includes('--render-review')) for (let i=1;i<=7;i++) if (!(await fs.stat(path.join(path.dirname(outputPath),`sheet-${i}.png`))).size) throw new Error('Native shutdown recovery preview missing');
  console.error('Native drawing runtime faulted at shutdown; completed export and all source hashes reverified.');
  process.exit(0);
}

// Resolve from the bundled Node runtime, never repository dependencies.
const bundledModules=path.resolve(path.dirname(process.execPath),'../node_modules');
const bundledRequire=createRequire(path.join(bundledModules,'../package.json'));
const artifactEntry=bundledRequire.resolve('@oai/artifact-tool');
if (!artifactEntry.startsWith(bundledModules+path.sep)) throw new Error('Bundled artifact runtime required');
const {Workbook,SpreadsheetFile,FileBlob}=await import(pathToFileURL(artifactEntry).href);

const root = path.resolve(import.meta.dirname, '../..');
const argument = flag => {
  const index = process.argv.indexOf(flag);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Required argument: ${flag}`);
  return process.argv[index + 1];
};
const runtimePath = value => {
  const resolved = path.resolve(root, value);
  if (!['runtime','.tmp'].some(directory=>resolved.startsWith(path.join(root, directory) + path.sep))) throw new Error('Artifact must remain under runtime or project .tmp');
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
const readModelRaw=await fs.readFile(runtimePath(publication.read_model_binding.path));
if (crypto.createHash('sha256').update(readModelRaw).digest('hex')!==publication.read_model_binding.sha256) throw new Error('Read model drift');
const readModel = JSON.parse(readModelRaw);
const inputHash = crypto.createHash('sha256').update(raw).digest('hex');
let extensions = null;
let extensionRaw = null;
let extensionPath = null;
const boundReports = [];
async function readBoundReport(binding, role) {
  const source = runtimePath(binding.path);
  const bytes = await fs.readFile(source);
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== binding.sha256) throw new Error(`${role} source drift`);
  const report = JSON.parse(bytes);
  if (report.action !== 'no_order') throw new Error(`${role} action mismatch`);
  boundReports.push(binding);
  return report;
}
const productExtensions=readModel.product_extensions??publication.product_extensions;
if (productExtensions) {
  extensions = {source_bindings:[]};
  for (const role of ['hotspot_report','dual_sleeve_report','value_discovery_report','value_research_queue','m2_pending_research']) {
    const binding=productExtensions[role];
    if (binding) extensions[role]=await readBoundReport(binding,role);
  }
  extensions.source_bindings=boundReports;
}
if (process.argv.includes('--extensions')) {
  extensionPath = runtimePath(argument('--extensions'));
  extensionRaw = await fs.readFile(extensionPath);
  if (crypto.createHash('sha256').update(extensionRaw).digest('hex') !== argument('--extensions-sha256')) throw new Error('Extension input drift');
  extensions = JSON.parse(extensionRaw);
  if (extensions.schema_version !== 'dual-product-surface-v1' || extensions.action !== 'no_order' || extensions.input_sha256 !== inputHash) throw new Error('Extension publication boundary mismatch');
  if (!Array.isArray(extensions.source_bindings) || !extensions.source_bindings.length) throw new Error('Extension sources missing');
  for (const binding of extensions.source_bindings) {
    const source = path.resolve(root, binding.path);
    if (!source.startsWith(root + path.sep)) throw new Error('Extension source escapes project');
    if (crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex') !== binding.sha256) throw new Error('Extension source drift');
  }
  for (const key of ['hotspot_report','dual_sleeve_report']) if (extensions[key] && extensions[key].action !== 'no_order') throw new Error('Extension report action mismatch');
}
const hotspotReport=extensions?.hotspot_report;
const riskReport=extensions?.dual_sleeve_report;
const discovery=extensions?.value_discovery_report;
const researchQueue=extensions?.value_research_queue;
const pendingResearch=extensions?.m2_pending_research;
if ((discovery==null)!==(researchQueue==null)) throw new Error('M2 discovery and queue must be bound together');
if (discovery) {
  if (discovery.schema_version!=='value-discovery-product-v1' || discovery.status!=='RESEARCH_LEADS_ONLY' ||
      discovery.quote_date_verification!=='UNVERIFIED_PROVIDER_TRADE_DATE' ||
      researchQueue.schema_version!=='value-research-queue-v1' || researchQueue.admission!=='RESEARCH_QUEUE_ONLY' ||
      researchQueue.run_id!==discovery.run_id || researchQueue.as_of!==discovery.as_of ||
      researchQueue.inputs?.report_sha256!==productExtensions.value_discovery_report.sha256 ||
      discovery.deduplicated_lead_count!==discovery.leads.length ||
      researchQueue.entries.length!==discovery.leads.length) throw new Error('M2 research-only contract mismatch');
  const leads=new Map(discovery.leads.map(item=>[item.symbol,item]));
  if (leads.size!==discovery.leads.length || researchQueue.entries.some(item=>!leads.has(item.symbol) ||
      !['DISCOVERED','DATA_CHECK'].includes(item.research_state) ||
      !['SELECTED_FOR_DATA_CHECK','BUDGET_DEFERRED'].includes(item.queue_status))) throw new Error('M2 queue admission or identity mismatch');
  if (pendingResearch && (pendingResearch.schema_version!=='m2-pending-research-intake-v1' ||
      pendingResearch.decision_admitted!==false || pendingResearch.quote_admitted!==false ||
      pendingResearch.m2_queue_binding?.sha256!==productExtensions.value_research_queue.sha256 ||
      !leads.has(pendingResearch.symbol))) throw new Error('Pending M2 case not bound to queue');
}
const hotspotRows = hotspotReport?.opportunities ?? (hotspotReport?.observation_list??[]).map(item=>({
  ...item, company_name:item.name, state:item.status, as_of:hotspotReport.observed_at,
  quote_date:item.confirmed_market_date??'UNKNOWN', scope:'历史快照观察，行情交易日未确认',
  basis:`${item.industry??'行业未核验'}。快照涨跌 ${item.snapshot_change_percent??'UNKNOWN'}%。主题持续性与催化未核验。`,
  risk:'行情日期、停牌和风险标识尚未核验。不能作为当前热点或交易依据。',
  next_trigger:'取得有日期的行情、主题催化，并完成独立价值与风险复核。',
}));
const seenHotspots = new Set();
for (const item of hotspotRows) {
  if (!item.symbol || seenHotspots.has(item.symbol)) throw new Error('Missing or duplicate hotspot symbol');
  seenHotspots.add(item.symbol);
  if (!['UNKNOWN','HOT_WATCH','SETUP_FORMING','ENTRY_REVIEW_CANDIDATE','POSITION_RISK_ALERT','EXIT_REVIEW_CANDIDATE','INVALIDATED','NO_SIGNAL'].includes(item.state??'UNKNOWN')) throw new Error('Unsupported hotspot research state');
  if (item.state === 'ENTRY_REVIEW_CANDIDATE' && ['core_value','risk','pit','oos','cost','shadow'].some(key=>item.gates?.[key] !== true)) throw new Error('Unqualified hotspot entry review');
}
const displayPath = runtimePath(argument('--display-input'));
const displayRaw = await fs.readFile(displayPath);
const display = JSON.parse(displayRaw);
if (display.input_sha256 !== crypto.createHash('sha256').update(raw).digest('hex')) throw new Error('Display input drift');
if (display.policy_binding.sha256 !== crypto.createHash('sha256').update(await fs.readFile(path.join(root, display.policy_binding.path))).digest('hex')) throw new Error('Display policy drift');
const enums = {UNKNOWN:'未核验', NOT_READY:'尚未形成', HOT_WATCH:'热点观察', SETUP_FORMING:'结构形成中', ENTRY_REVIEW_CANDIDATE:'入场人工复核候选', POSITION_RISK_ALERT:'持仓风险复核', EXIT_REVIEW_CANDIDATE:'退出人工复核候选', INVALIDATED:'逻辑失效', NO_SIGNAL:'无有效条件', CORE_VALUE:'核心价值', HOTSPOT_SATELLITE:'热点卫星', NOT_CONNECTED:'未接入', BLOCKED_PRIVATE_INPUT:'私人输入不完整', REVIEW_REQUIRED:'需风险复核', RISK_REVIEW_CALCULATED:'风险已计算，仍需人工复核', SIMULATED:'隔离模拟', ACTUAL:'本人输入', UP:'上行', DOWN:'下行', FLAT:'持平', OBSERVED_NOT_ADMITTED:'仅观察，未准入', QUANTITY_REVIEW_ONLY:'数量仅供人工复核', BLOCKED_BELOW_ONE_LOT:'不足一手', BLOCKED:'未通过', NOT_PROVEN:'未证明', SOURCE_UNVERIFIED:'来源单位未核验', UNADJUSTED:'未复权', RESEARCH_OBSERVATION_ONLY:'研究观察'};
const enumPattern = new RegExp(`\\b(${Object.keys(enums).join('|')})\\b`,'g');
const publicText = value => typeof value === 'string' ? (display.strings[value] ?? value).replace(enumPattern, token=>enums[token]) : value;
const decisionBinding = readModel.decision_workbench_binding;
const decision = decisionBinding ? JSON.parse(await fs.readFile(path.join(root, decisionBinding.path))) : null;
const supplements = [];
for (const binding of readModel.research_supplement_bindings ?? publication.research_supplement_bindings ?? []) {
  const source = runtimePath(binding.path);
  const bytes = await fs.readFile(source);
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== binding.sha256) throw new Error('Supplement drift');
  const data = JSON.parse(bytes);
  if (data.action !== 'no_order') throw new Error('Supplement action mismatch');
  supplements.push({role:binding.role, data});
}
const wb = Workbook.create();
const layouts = new Map();
const links=[];
function link(range, formula, text) {
  range.values=[[text]];
  links.push({range,formula});
}
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
const choiceNames = {A_PRESSURE_REFERENCE:'A 强侵蚀参照',B_CONTINUITY_ALTERNATIVE:'B 盈利持续假设',C_SLOW_EROSION_ALTERNATIVE:'C 慢侵蚀反例','short-advantage':'短优势期条件','medium-advantage':'中优势期条件'};
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
  const generated=new Date(String(snapshot.generated_at).replace(' ','T'));
  if (!Number.isFinite(generated.getTime())) throw new Error('Invalid snapshot update timestamp');
  const updated=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(generated);
  ws.getRange('A3').values = [[`更新时间 ${updated}（上海）。研究截止 ${snapshot.as_of}。研究展示，批准状态分别核验。`]];
  ws.getRange(`A3:${last}3`).format.rowHeight = 32;
  link(ws.getRange('A1'),`=HYPERLINK("#'01_今日'!A1","返回今日")`,'返回今日');
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
  return [`${c.company_name}\n${c.symbol}`,label(c.research_status),r['当前决策状态']??'待研究复核',r['本次重点']??mainReason(c),r['审核入口']??r['下一触发']??c.next_trigger];
});
// Keep independently verified dated observations visible without admitting a decision price.
const allMarketObservations = (snapshot.today_items ?? []).filter(item=>item.category?.code === 'MARKET_DATA');
const marketObservations = allMarketObservations.filter((item,index)=>
  !allMarketObservations.slice(index+1).some(later=>later.symbol === item.symbol));
reviewRows.push(...marketObservations.map(item=>[
  `${item.company}\n${item.symbol}`, '独立行情观察', item.current_status,
  `${item.what_happened}\n${item.why_it_matters}`, item.next_step,
]));
const band = title => [title,'','','','',''];
const concise = (value,limit=90) => {const text=publicText(String(value??''));return text.length>limit?`${text.slice(0,limit)}...（详见公司页）`:text;};
const riskScope=riskReport?.namespace==='SIMULATED'?'隔离模拟，不是本人组合':'本人组合风险';
const riskSummary=riskReport ? (riskReport.status==='NOT_CONNECTED'?'私人组合未接入':`${riskScope}：${publicText(riskReport.status)}`):'私人组合未接入';
const selectedSymbols=new Set(supplements.filter(item=>item.role==='pending_research_candidate').map(item=>item.data.symbol));
const homepageCompanies=snapshot.companies.filter(company=>selectedSymbols.has(company.symbol)).slice(0,2);
const coreToday = homepageCompanies.map(c=>{
  const r=reviews(c); const quote=marketObservations.findLast(item=>item.symbol===c.symbol);
  return [`${c.company_name}\n${c.symbol}`,`核心价值\n研究 ${snapshot.as_of}`,quote?.what_happened??assessment(c.price),
    `条件研究\n${concise(r['本次重点']??mainReason(c),60)}`,r['当前决策状态']??'待研究复核',`${concise(r['最强反证']??mainReason(c),50)}\n下一复核：${concise(r['下一触发']??c.next_trigger,40)}`];
});
const hotspotToday = hotspotRows.map(item=>[`${item.company_name??item.symbol}\n${item.symbol}`,`热点卫星\n研究 ${item.as_of??extensions.hotspot_report.as_of??'UNKNOWN'}`,
  `行情 ${item.quote_date??'UNKNOWN'}`,`${item.scope??'研究观察'}\n${item.basis??'UNKNOWN'}`,item.state??'UNKNOWN',`${item.risk??'UNKNOWN'}\n下一复核：${item.next_trigger??'UNKNOWN'}`]);
const selectedLeads=(researchQueue?.entries??[]).filter(item=>item.queue_status==='SELECTED_FOR_DATA_CHECK');
const leadBySymbol=new Map((discovery?.leads??[]).map(item=>[item.symbol,item]));
const channelNames={quality:'质量',dividend_cash_return:'股息现金回报',value:'低估线索',cyclical:'周期观察'};
const channelText=item=>item.channels.map(channel=>channelNames[channel]??'其他研究').join(' / ');
const leadNext=pending=>pending?'官方年报已留存；财务口径、身份与模型仍待核验':'待核官方财报、逐股交易日和模型适用性';
const discoverySummary=discovery ? [
  [`全市场研究线索 ${discovery.deduplicated_lead_count} 家`,`名单/抓取 ${discovery.as_of}`,
   '逐股交易日未核验',`质量 ${discovery.channel_counts.quality??0}；股息 ${discovery.channel_counts.dividend_cash_return??0}；价值 ${discovery.channel_counts.value??0}；周期 ${discovery.channel_counts.cyclical??0}`,
   '仅供研究',`数据健康 ${discovery.data_health.status}；本轮资料检查 ${selectedLeads.length} 家`],
  ...selectedLeads.slice(0,3).map(item=>[`${item.company_name}\n${item.symbol}`,'价值研究线索',
    '逐股交易日未核验',channelText(item),'资料检查',leadNext(pendingResearch?.symbol===item.symbol)]),
] : [];
const todayRows = [band('机会'),...(discoverySummary.length?[['全市场发现','','','','',''],...discoverySummary]:[]),['核心价值','','','','',''],...coreToday,['热点卫星','','','','',''],
  ...(hotspotToday.length?hotspotToday.slice(0,3):[['尚未接入热点报告','热点卫星','','研究观察','未形成候选','等待真实来源报告']]),
  ['更多见机会页','','','全部公司与热点观察保留在机会、公司页','',''],
  band('风险'),[riskSummary,'',riskReport?.generated_at?`报告时间 ${riskReport.generated_at}`:'',riskReport?.aggregate?'查看组合页的资金与重复敞口':'真实持仓、资金预算与风险限额尚不完整','风险结果不等于交易资格','查看组合页风险理由与输入准备'],
  ...(extensions?.dual_sleeve_report?.presentation_alerts??[]).map(item=>[
    item.title??'风险观察',item.strategy??'',item.as_of??'',item.scope??'研究观察',item.status??'UNKNOWN',`${item.reason??'UNKNOWN'}\n下一复核：${item.next_trigger??'UNKNOWN'}`]),
  band('变化'),...(snapshot.today_items?.length?snapshot.today_items.slice(0,3).map(item=>[item.company??'',concise(item.current_status,50),concise(item.what_happened,60),concise(item.why_it_matters,60), '观察',concise(item.next_step,60)]):[['没有已记录的研究变化','','','','','']]),
  band('待办'),...homepageCompanies.map(c=>{const r=reviews(c);return [c.company_name,'核心价值','','',concise(r['审核入口']??'待研究复核',60),concise(r['下一触发']??c.next_trigger,60)];})];
const todaySheet=table(names[0],'今日',['公司 / 分区','策略 / 研究日期','行情 / 日期','依据 / 用途','候选动作','风险 / 下一触发'],todayRows,[19,24,32,52,28,58]);
layouts.get(names[0]).forEach((row,index)=>{if (['机会','全市场发现','风险','变化','待办'].includes(row[0])) todaySheet.getRange(`A${index+6}:F${index+6}`).format={fill:'#DCE5EB',font:{name:'Microsoft YaHei',size:11,bold:true,color:'#202828'},rowHeight:28};});
const discoveryRows=(researchQueue?.entries??[]).map(item=>{
  const lead=leadBySymbol.get(item.symbol);
  const pending=pendingResearch?.symbol===item.symbol?pendingResearch:null;
  return [`${item.company_name}\n${item.symbol}`,
    pending?'待审研究':item.research_state==='DATA_CHECK'?'资料检查':'研究线索',
    `${discovery.as_of} 抓取；交易日未核验`,
    `${channelText(item)}\n${(lead?.screening_reasons??[])[0]??'待核筛选依据'}`,
    '未形成正式估值或买点',
    `${item.queue_status==='SELECTED_FOR_DATA_CHECK'?'本轮资料检查':'研究预算外继续观察'}；${leadNext(pending)}`];
});
table(names[1],'研究机会',['公司','研究状态','行情观察','估值状态','价格评估','当前结论'],snapshot.companies.map(c=>{
  const r=reviews(c); const observation=marketObservations.findLast(item=>item.symbol === c.symbol);
  const legacyObservation=r['已核验收盘行情（未桥接估值）'];
  return [`${c.company_name}\n${c.symbol}`,label(c.research_status),observation?.what_happened??legacyObservation?.split('；')[0]??assessment(c.price),assessment(c.valuation),r['价格区域']??'尚未完成当前价格评估',r['当前决策状态']??'待研究复核'];
}).concat(discoveryRows,hotspotRows.map(item=>[`${item.company_name??item.symbol}\n${item.symbol}`,'热点卫星',`行情 ${item.quote_date??'UNKNOWN'}`,
  `${item.scope??'研究观察'}\n${item.basis??'UNKNOWN'}`,item.state??'UNKNOWN',`${item.risk??'UNKNOWN'}\n${item.next_trigger??'UNKNOWN'}`])),[19,22,33,65,30,32]);
table(names[2],'决策过程',['公司','检查步骤','状态','原因','下一步'],snapshot.companies.flatMap(c=>c.decision_process.map(s=>[`${c.company_name}\n${c.symbol}`,steps[s.key],states[s.status],s.reason,s.next_action])),[19,20,16,74,55]);
const companyRows=snapshot.companies.flatMap(c=>{
  const r=reviews(c);
  const observation=marketObservations.findLast(item=>item.symbol === c.symbol);
  const reviewKeys=['最强反证','为什么未进入更高状态','人工买入复核条件','人工加仓复核条件',
    '人工减仓复核条件','人工退出复核条件','已满足的研究前置','尚缺证据',
    '条件研究备选','研究假设重开条件','本次财务研究补充','Agent问题独立复核','本次研究版本比较','本次官方事件窗口'];
  const candidates=supplements.filter(item=>item.role==='pending_research_candidate' && item.data.symbol===c.symbol && item.data.model_context_scope==='ACTUALLY_CONSUMED' && item.data.candidate_valuation?.status==='conditional_research_only').map(item=>item.data);
  const current=candidates.length>1?candidates.filter(item=>item.is_current===true):candidates;
  if (candidates.length && current.length!==1) throw new Error('Ambiguous current company candidate');
  const candidate=current[0];
  if (candidate && ['bear','base','bull'].some(key=>candidate.candidate_valuation[`${key}_value`]!=null && !Number.isFinite(Number(candidate.candidate_valuation[`${key}_value`])))) throw new Error('Invalid candidate valuation value');
  const candidateRows=candidate ? [
    [`${c.company_name}\n${c.symbol}`,'当前选定待审研究记录',`${choiceNames[candidate.selected_choice]??'当前选定假设'}。研究日 ${candidate.candidate_research_as_of}。选定历史记录用于当前展示，尚待审批。`],
    ...['bear','base','bull'].map(key=>[c.symbol,`当前候选 ${{bear:'悲观',base:'基准',bull:'乐观'}[key]}（元/股）`,candidate.candidate_valuation[`${key}_value`]==null?'未形成':Number(candidate.candidate_valuation[`${key}_value`])]),
  ] : [];
  return [
    ...candidateRows,
    [`${c.company_name}\n${c.symbol}`,'当前结论',r['当前决策状态']||label(c.decision_status)||'待研究复核'],
    [c.symbol,'为什么关注',c.sections.find(s=>s.key === 'business_quality')?.summary||'经营论点尚未形成；先核对公司研究证据。'],
    [c.symbol,'现在能否买入',mainReason(c)],
    [c.symbol,'最新价格观察',observation?.what_happened??assessment(c.price)],
    [c.symbol,'公司已保存估值说明（独立参考）',assessment(c.valuation)],
    ...['事实与估计','当前正式准入','审核入口','事件复核重点','研究变化归因'].filter(key=>r[key]).map(key=>[c.symbol,key,r[key]]),
    ...Object.keys(r).filter(key=>key.startsWith('经济审核：')).map(key=>[c.symbol,key,r[key]]),
    ...c.sections.map(s=>[c.symbol,sections[s.key],s.summary]),
    ...reviewKeys.filter(key=>r[key]).map(key=>[c.symbol,key,publicText(r[key])]),
    ...Object.keys(r).filter(key=>key.startsWith('模型待审：') || ['完整主估值候选待审','主估值候选最强反证'].includes(key)).map(key=>[c.symbol,key,r[key]]),
    [c.symbol,'下一次关注',r['下一触发']??c.next_trigger],
  ];
});
const periodNames={daily:'日线','60m':'60 分钟','15m':'15 分钟'};
const behaviorRows=[];
function appendPeriods(symbol, periods, scope) {
  for (const period of ['daily','60m','15m']) {
    const data=periods?.[period];
    behaviorRows.push(['热点证券观察',`${symbol} 热点 ${periodNames[period]}`,!data || data.status==='UNKNOWN'
      ? `${scope}。本周期缺少已绑定行情，趋势、价位与量价均未核验。`
      : `${scope}。观察日期 ${data.first_date??'未核验'} 至 ${data.last_date??'未核验'}。${publicText(data.direction??'UNKNOWN')}。支撑 ${data.prior_five_bar_support??'未核验'} 元，压力 ${data.prior_five_bar_resistance??'未核验'} 元。量比 ${data.volume_ratio??'未核验'}，成交量确认 ${publicText(data.volume_confirmation??'UNKNOWN')}。未复权，除权事件待核验。后续收盘跌破支撑时重新观察。`]);
  }
}
for (const item of hotspotRows) {
  behaviorRows.push(['热点证券观察',`${item.company_name??''} ${item.symbol} 热点研究观察`,`${publicText(item.state??'UNKNOWN')}。${item.basis??'依据未核验'}。${item.risk??'风险未核验'}。下一观察：${item.next_trigger??'未核验'}`]);
  appendPeriods(item.symbol,item.periods,'证券观察周期');
}
if (hotspotReport?.price_behavior) {
  const behavior=hotspotReport.price_behavior;
  behaviorRows.push(['热点证券观察',`${behavior.symbol} 独立历史价格行为`,'该历史行情与市场快照并非同一观察时点，不能拼接成当前入场信号。']);
  appendPeriods(behavior.symbol,behavior.periods,'独立历史价格行为');
}
companyRows.push(...behaviorRows);
companyRows.push(...selectedLeads.map(item=>{
  const pending=pendingResearch?.symbol===item.symbol?pendingResearch:null;
  return [`${item.company_name}\n${item.symbol}`,'全市场候选资料检查',
    `通道：${channelText(item)}。${item.screening_reasons.slice(0,2).join('；')}\n`+
    `阶段：${pending?'待审研究':'资料检查'}；正式估值：未批准；交易资格：无。\n`+
    `待补：${leadNext(pending)}。原始出处见系统与审计。`];
}));
companyRows.push(...(snapshot.today_items??[]).map(item=>[item.symbol??item.company??'研究观察','本次变化（完整记录）',`${item.what_happened??''}\n${item.why_it_matters??''}\n下一复核：${item.next_step??''}`]));
const companySheet=table(names[3],'公司研究',['公司','内容','研究结果'],companyRows,[19,28,125]);
const shownCompanyRows = layouts.get(names[3]);
shownCompanyRows.forEach((row,index)=>{if (String(row[1]).startsWith('当前候选 ') && typeof row[2]==='number') companySheet.getRange(`C${index+6}`).setNumberFormat('0.00;[Red](0.00);"-"');});
const valueRow=shownCompanyRows.length+9;
if (decision) {
  companySheet.getRange(`A${valueRow}:C${valueRow}`).values=[['公司代码','父模型情景（独立参考）','父模型条件值（元/股，非选定待审记录）']];
  for (const [i,key] of ['bear','base','bull'].entries()) companySheet.getRange(`A${valueRow+i+1}:C${valueRow+i+1}`).values=[[decision.symbol,['低值压力情景','中值压力情景','高值压力情景'][i],decision.valuation[`${key}_value`] == null ? null : Number(decision.valuation[`${key}_value`])]];
  companySheet.getRange(`C${valueRow+1}:C${valueRow+3}`).setNumberFormat('0.00');
  // Four rows fit within the space previously taken by three 30pt rows.
  companySheet.getRange(`A${valueRow}:C${valueRow+3}`).format.rowHeight=22;
}
let proposalRow=valueRow+6;
for (const {role,data} of supplements) if (role === 'valuation_proposal') {
  proposalRow += 2;
  companySheet.getRange(`A${proposalRow}:C${proposalRow}`).values=[['公司代码',`原估值日期 ${data.original_valuation_date}（待审）`,'条件研究值（元/股，非买点）']];
  companySheet.getRange(`A${proposalRow}:C${proposalRow}`).format={rowHeight:42,wrapText:true,font:{name:'Microsoft YaHei',size:11,bold:true}};
  for (const choice of data.choices) {
    for (const key of ['bear','base','bull']) {
      proposalRow++;
      const choiceTitle = choiceNames[choice.id] ?? choice.id;
      companySheet.getRange(`A${proposalRow}:C${proposalRow}`).values=[[data.symbol,`${choiceTitle} ${ {bear:'低档',base:'中档',bull:'高档'}[key]}`,Number(choice.valuation[`${key}_value`])]];
      companySheet.getRange(`A${proposalRow}:C${proposalRow}`).format={rowHeight:38,wrapText:true,font:{name:'Microsoft YaHei',size:11}};
      companySheet.getRange(`C${proposalRow}`).setNumberFormat('0.00');
    }
  }
}
const portfolioRows = riskReport ? [
  [riskSummary,`报告时间 ${riskReport.generated_at??'未核验'}。${riskReport.namespace==='SIMULATED'?'以下金额属于隔离模拟，不代表本人持仓或收益。':'风险报告反映已提供输入，不代表交易批准。'}`],
  ['输入准备','由本人核验两个资金池预算、现金、持仓数量与成本、风险限额、行业与主题归属。缺项保持未形成，不填估计金额。'],
  ...((riskReport.blockers??[]).map(reason=>['风险 / 缺项',publicRiskReason(reason)])),
] : [[label(snapshot.portfolio.status),snapshot.portfolio.connection_hint],['输入准备','尚未接入来源绑定的风险报告。请准备本人核验的资金池预算、现金、持仓、成本与风险限额。']];
function publicRiskReason(reason) {
  const labels={'portfolio.private_input_missing':'尚未提供私人组合','sleeve_policy.private_input_missing':'两个资金池的预算与风险规则尚不完整','security_attributes.missing':'证券行业、流动性与风险属性缺失','holding.cost_basis_missing':'持仓成本缺失','portfolio.nonpositive_equity':'组合权益无有效正值','hotspot.user_risk_policy_missing':'热点单笔风险规则缺失',budget_exceeded:'资金预算超限',risk_unknown:'已占用风险未核验',risk_budget_exhausted:'风险预算用尽',cash_floor_violation:'现金低于保留限额',single_security_cap:'单票集中度超限',industry_cap:'行业集中度超限',single_security_concentration:'单票集中度超限',industry_concentration:'行业集中度超限',factor_concentration:'主题集中度超限',liquidity_review:'需流动性复核',financing_or_risk_tools_not_supported:'融资或风险工具不在当前支持范围'};
  if (labels[reason]) return labels[reason];
  const parts=String(reason).split(':');
  return `${enums[parts[0]]??'组合'}：${labels[parts[1]]??'风险条件待复核'}${parts.length>2?`（${parts.slice(2).join('：')}）`:''}。具体来源见系统与审计。`;
}
for (const [sleeve,data] of Object.entries(riskReport?.sleeves??{})) {
  portfolioRows.push([publicText(sleeve),'资金池独立，不自动转移现金或风险预算。']);
  for (const [key,title] of Object.entries({budget_cny:'预算（元）',equity_cny:'权益（元）',used_funds_cny:'已用资金（元）',cash_cny:'现金（元）',available_funds_cny:'可用资金（元）',risk_budget_cny:'风险预算（元）',committed_risk_cny:'已占用风险（元）',available_risk_cny:'可用风险（元）',unrealized_pnl_cny:'未实现损益（元）',realized_pnl_cny:'已实现损益（元）'})) portfolioRows.push([`${publicText(sleeve)} ${title}`,data[key]==null?'未形成':Number(data[key])]);
  for (const holding of data.holdings??[]) portfolioRows.push([`${publicText(sleeve)} ${holding.symbol}`,`数量 ${holding.quantity??'未形成'}。市值 ${holding.market_value_cny??'未形成'} 元。归属独立记录。`]);
}
for (const [symbol,parts] of Object.entries(riskReport?.aggregate?.duplicated_security_exposure??{})) portfolioRows.push(['跨策略重复敞口',`${symbol}：${parts.map(item=>`${publicText(item.sleeve)} ${item.quantity} 股`).join('；')}。资产按原报告汇总，不重复相加。`]);
if (riskReport?.hotspot_quantity_review) {
  const sizing=riskReport.hotspot_quantity_review;
  portfolioRows.push(['热点数量复核',`${publicText(sizing.status)}。数量 ${sizing.review_quantity??'未形成'}。止损不能保证成交，受 T+1 与涨跌停约束，未取得交易资格。`]);
}
const portfolioSheet=table(names[4],'我的组合',['状态 / 项目','内容 / 金额'],portfolioRows,[36,100]);
layouts.get(names[4]).forEach((row,index)=>{if(typeof row[1]==='number') {if (!Number.isFinite(row[1])) throw new Error('Invalid risk report amount');portfolioSheet.getRange(`B${index+6}`).setNumberFormat('#,##0.00;[Red](#,##0.00);"-"');}});
const privateTemplatePath='config/private-template/dual-sleeve-private-input-v1.csv';
const privateTemplateRaw=await fs.readFile(path.join(root,privateTemplatePath));
const privateTemplateHash=crypto.createHash('sha256').update(privateTemplateRaw).digest('hex');
const templateWorkbook=await Workbook.fromCSV(privateTemplateRaw.toString('utf8'),{sheetName:'Template'});
const templateRows=templateWorkbook.worksheets.getItem('Template').getUsedRange().values.slice(1);
const inputSections={IPS:'投资政策',SNAPSHOT:'组合快照',SHARED_BUDGET:'共享资金规则',CORE_VALUE:'核心价值',HOTSPOT_SATELLITE:'热点卫星',CASH_RESERVE:'保留现金',ALLOCATIONS:'持仓策略归属',SECURITY_ATTRIBUTES:'证券风险属性',HOTSPOT_REQUEST:'热点数量复核输入'};
const inputLabels={policy_id:'政策编号',policy_version:'政策版本',as_of:'基准日期',confirmation_status:'本人确认状态',confirmed_at:'确认时间',account_scope:'账户范围',investable_assets_cny:'可投资资产（元）',minimum_cash_cny:'最低现金（元）',emergency_cash_cny:'应急现金（元）',liquidity_needs_cny:'资金需求（元）',time_horizon_years:'投资期限（年）',max_single_security_pct:'单票上限（百分比）',max_single_industry_pct:'行业上限（百分比）',max_cyclical_exposure_pct:'周期敞口上限（百分比）',dividend_income_goal_cny:'股息收入目标（元）',risk_tolerance:'风险承受能力',concentration_allowed:'是否允许集中持仓',tax_regime:'税务口径',restrictions:'投资限制',snapshot_id:'快照编号',snapshot_version:'快照版本',available_at:'可用时间',cash_cny:'现金（元）',reconciliation_status:'核对状态',reconciled_at:'核对时间',holdings:'持仓明细（原始结构）',core_value_budget:'核心预算比例',tactical_hotspot_budget:'热点预算比例',cash_floor:'保留现金比例',cross_sleeve_single_stock_cap:'跨策略单票上限比例',cross_sleeve_sector_cap:'跨策略行业上限比例',policy_scope:'规则确认范围',risk_budget_cny:'风险预算（元）',max_single_security_fraction:'单票上限比例',max_industry_fraction:'行业上限比例',max_factor_fraction:'主题上限比例',single_trade_risk_fraction:'单笔风险比例',single_security_risk_cny:'单票风险限额（元）',realized_pnl_cny:'已实现损益（元）',financing_allowed:'是否允许融资',risk_tools_allowed:'是否允许风险工具',rows:'明细（原始结构）',request:'可选复核请求（原始结构）'};
const preservedInputs=new Map();
let manualInputBinding=null;
if (process.argv.includes('--manual-input-source') !== process.argv.includes('--manual-input-source-sha256')) throw new Error('Manual input source and exact SHA256 are required together');
if (process.argv.includes('--manual-input-source')) {
  const source=path.resolve(root,argument('--manual-input-source'));
  if (source===output) throw new Error('Manual source cannot be the output');
  const expected=argument('--manual-input-source-sha256');
  if (!/^[0-9a-f]{64}$/.test(expected)) throw new Error('Invalid manual source SHA256');
  const bytes=await fs.readFile(source);
  if (crypto.createHash('sha256').update(bytes).digest('hex')!==expected) throw new Error('Manual input source drift');
  const sourceWorkbook=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  if (crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex')!==expected) throw new Error('Manual input source changed during import');
  const sourceSheet=sourceWorkbook.worksheets.getItem(names[4]);
  const used=sourceSheet.getUsedRange();
  const height=used.values.length;
  const sourceRange=sourceSheet.getRange(`A1:D${Math.max(1,height)}`);
  const sourceValues=sourceRange.values;
  const sourceFormulas=sourceRange.formulas;
  const nonempty=value=>value!==null && value!==undefined && value!=='';
  const headers=sourceValues.flatMap((row,index)=>row[0]==='分区' && row[1]==='字段'?[index]:[]);
  if (headers.length>1) throw new Error('Ambiguous manual input header');
  const knownKeys=new Map(templateRows.map(([section,field])=>[JSON.stringify([inputSections[section]??section,inputLabels[field]??field]),JSON.stringify([section,field])]));
  const seen=new Set();
  for (let index=headers.length?headers[0]+1:0;index<sourceValues.length;index++) {
    const row=sourceValues[index];
    const formulas=sourceFormulas[index]??[];
    const key=knownKeys.get(JSON.stringify([row[0],row[1]]));
    if (nonempty(formulas[2]) || nonempty(formulas[3])) throw new Error('Manual input formulas are not allowed');
    if (!key) {
      if (nonempty(row[2]) || nonempty(row[3])) throw new Error('Unknown nonempty manual input key');
      continue;
    }
    if (nonempty(formulas[0]) || nonempty(formulas[1]) || seen.has(key)) throw new Error('Ambiguous manual input key');
    seen.add(key);
    if (nonempty(row[2]) || nonempty(row[3])) preservedInputs.set(key,[row[2]??null,row[3]??null]);
  }
  manualInputBinding={path:source,sha256:expected,preserved_row_count:preservedInputs.size};
}
const privateHeaderRow=layouts.get(names[4]).length+9;
portfolioSheet.getRange(`A${privateHeaderRow-1}:D${privateHeaderRow-1}`).merge();
portfolioSheet.getRange(`A${privateHeaderRow-1}`).values=[['本人输入准备：空白不等于零。须提供来源，经导入验证后才更新风险报告。']];
portfolioSheet.getRange(`A${privateHeaderRow-1}:D${privateHeaderRow+templateRows.length}`).format={font:{name:'Microsoft YaHei',size:11,color:'#202828'},rowHeight:30,verticalAlignment:'center',wrapText:true};
portfolioSheet.getRange(`A${privateHeaderRow}:D${privateHeaderRow}`).values=[['分区','字段','本人输入（保留原文）','来源 / 核验记录']];
portfolioSheet.getRange(`A${privateHeaderRow}:D${privateHeaderRow}`).format={fill:'#255C50',font:{name:'Microsoft YaHei',size:11,bold:true,color:'#FFFFFF'},rowHeight:34};
portfolioSheet.getRange(`C${privateHeaderRow+1}:D${privateHeaderRow+templateRows.length}`).setNumberFormat('@');
portfolioSheet.getRange(`A${privateHeaderRow+1}:D${privateHeaderRow+templateRows.length}`).values=templateRows.map(([section,field,value,source])=>{
  if (value || source) throw new Error('Private template must start blank');
  return [inputSections[section]??section,inputLabels[field]??field,...(preservedInputs.get(JSON.stringify([section,field]))??[null,null])];
});
portfolioSheet.getRange(`C${privateHeaderRow+1}:D${privateHeaderRow+templateRows.length}`).setNumberFormat('@');
portfolioSheet.getRange(`C${privateHeaderRow+1}:D${privateHeaderRow+templateRows.length}`).format={fill:'#FFF4CC',font:{name:'Microsoft YaHei',size:11,color:'#2456A6'}};
portfolioSheet.getRange(`C1:C${privateHeaderRow+templateRows.length}`).format.columnWidth=32;
portfolioSheet.getRange(`D1:D${privateHeaderRow+templateRows.length}`).format.columnWidth=44;
table(names[5],'事件',['公司','事件','当前结论','下一步'],snapshot.events.length?snapshot.events.map(e=>[e.company_name,e.what_happened,e.current_conclusion,e.next_step]):[['','当前没有已分类的用户事件。','公告原件取得不代表事件影响已批准。','完成证据绑定的事件审查。']],[20,55,65,55]);
const auditRows = snapshot.audit_evidence.map(e=>[e.evidence_id,e.title,e.artifact_type,e.path,e.source_url??'',e.sha256,e.available_at??'']);
if (discovery) auditRows.push(...[
  ['m2-discovery','全市场研究线索','research_leads',productExtensions.value_discovery_report.path,'',productExtensions.value_discovery_report.sha256,discovery.as_of],
  ['m2-queue','资料检查队列','research_queue',productExtensions.value_research_queue.path,'',productExtensions.value_research_queue.sha256,researchQueue.as_of],
  ...(pendingResearch?[['m2-pending-'+pendingResearch.symbol,'官方研究待审','pending_research',productExtensions.m2_pending_research.path,pendingResearch.source_url,productExtensions.m2_pending_research.sha256,pendingResearch.research_case?.generated_at??'']]:[]),
]);
auditRows.push(...(extensions?.source_bindings??[]).map((binding,index)=>[`extension-${index+1}`,'双策略展示来源','presentation_source',binding.path,'',binding.sha256,'']));
const auditSheet = table(names[6],'系统与审计',['证据编号','名称','类型','路径','原始来源网址','SHA-256','可用时间'],auditRows,[40,30,27,75,72,72,28]);
const shownAuditRows = layouts.get(names[6]);
for (let i = 0; i < shownAuditRows.length; i++) {
  const row = shownAuditRows[i];
  const evidence = snapshot.audit_evidence.find(e => e.evidence_id === row[0]);
  if (!evidence?.source_url || row[4] !== evidence.source_url) continue;
  const url = new URL(evidence.source_url);
  if (url.protocol !== 'https:' || url.username || url.password || /["\r\n]/.test(evidence.source_url)) throw new Error('Unsupported evidence URL');
  link(auditSheet.getRange(`E${i+6}`),`=HYPERLINK("${evidence.source_url}","${evidence.source_url}")`,evidence.source_url);
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
    link(ws.getRange(`A${index+6}`),`=HYPERLINK("#'03_公司'!A${companyStart.get(c.symbol)}","${title}")`,`${c.company_name} ${c.symbol}`);
  });
}
for (let i=0; i<shownCompanyRows.length; i++) if (String(shownCompanyRows[i][0]).includes('\n')) {
  const c = snapshot.companies.find(c=>String(shownCompanyRows[i][0]).endsWith('\n'+c.symbol));
  if (!c) continue;
  const auditIndex = shownAuditRows.findIndex(row=>c.evidence_refs.includes(row[0]));
  const title = `${shownCompanyRows[i][1]}（证据）`.replaceAll('"', '""');
  if (auditIndex >= 0) link(companySheet.getRange(`B${i+6}`),`=HYPERLINK("#'06_系统与审计'!A${auditIndex+6}","${title}")`,`${shownCompanyRows[i][1]}（证据）`);
}
wb.recalculate();
if (await fs.stat(output).catch(()=>null)) throw new Error('Preview already exists');
await fs.mkdir(path.dirname(output), {recursive:true});
if (process.argv.includes('--render-review')) {
  const views = names.map((sheetName,index)=>({sheetName,range:`A1:${['F','F','E','C','B','D','G'][index]}${Math.min(18,(layouts.get(sheetName)?.length??0)+5)}`,file:`sheet-${index+1}.png`}));
  if (!preservedInputs.size) views.push({sheetName:names[4],range:`A${privateHeaderRow-1}:D${privateHeaderRow+12}`,file:'private-input-area.png'});
  if(behaviorRows.length) {
    const behaviorIndex=shownCompanyRows.findIndex(row=>String(row[1]).endsWith('独立历史价格行为'));
    if(behaviorIndex<0) throw new Error('Historical price behavior preview anchor missing');
    const firstRow=behaviorIndex+6;
    views.push({sheetName:names[3],range:`A${firstRow}:C${Math.min(firstRow+5,shownCompanyRows.length+5)}`,file:'hotspot-periods.png'});
  }
  for (let i=0; i<shownCompanyRows.length; i++) if (['条件研究备选','研究假设重开条件','本次财务研究补充','Agent问题独立复核','本次研究版本比较'].includes(shownCompanyRows[i][1])) {
    views.push({sheetName:names[3],range:`A${Math.max(1,i+5)}:C${i+7}`,file:`research-${i}.png`});
  }
  if (supplements.some(item=>item.role==='valuation_proposal')) views.push({sheetName:names[3],range:`A${valueRow+6}:C${proposalRow}`,file:'proposal-values.png'});
  for (const view of views) {
    const preview=await wb.render({sheetName:view.sheetName,range:view.range,scale:1,format:'png'});
    await fs.writeFile(path.join(path.dirname(output),view.file),new Uint8Array(await preview.arrayBuffer()));
  }
}
for (const {range,formula} of links) range.formulas=[[formula]];
wb.recalculate();
// The public workbook export returns a Blob. Save only its XLSX bytes, without
// FileBlob.save's automatic inspection sidecar containing private cell values.
const exportFile=await wb.export({format:'xlsx'});
await fs.writeFile(output,new Uint8Array(await exportFile.arrayBuffer()),{flag:'wx'});
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!',options:{useRegex:true,maxResults:20}})).ndjson);
const receipt={schema_version:'d2-product-engineering-preview-v1',input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),workbook_sha256:crypto.createHash('sha256').update(await fs.readFile(output)).digest('hex'),sheets:names,source_count:publication.source_bindings.length,display_binding:{path:path.relative(root,displayPath).replaceAll('\\','/'),sha256:crypto.createHash('sha256').update(displayRaw).digest('hex')},scope:'ENGINEERING_PREVIEW_NOT_CANONICAL_OR_USER_ACCEPTANCE',canonical_written:false,action:'no_order'};
if (extensions) receipt.extension_binding={source_bindings:extensions.source_bindings};
receipt.private_input_area={sheet:names[4],header_row:privateHeaderRow,value_column:'C',source_column:'D',rows:templateRows.map(([section,field],index)=>({section,field,row:privateHeaderRow+index+1})),template_binding:{path:privateTemplatePath,sha256:privateTemplateHash},values_initially_blank:preservedInputs.size===0,publication_preservation_required:true};
if (manualInputBinding) {
  if (crypto.createHash('sha256').update(await fs.readFile(manualInputBinding.path)).digest('hex')!==manualInputBinding.sha256) throw new Error('Manual input source changed during export');
  receipt.manual_input_binding=manualInputBinding;
}
if (crypto.createHash('sha256').update(await fs.readFile(path.join(root,privateTemplatePath))).digest('hex')!==privateTemplateHash) throw new Error('Private template changed during export');
if (extensionPath) Object.assign(receipt.extension_binding,{path:path.relative(root,extensionPath).replaceAll('\\','/'),sha256:crypto.createHash('sha256').update(extensionRaw).digest('hex')});
for (const binding of extensions?.source_bindings??[]) if (crypto.createHash('sha256').update(await fs.readFile(path.resolve(root,binding.path))).digest('hex')!==binding.sha256) throw new Error('Extension source changed during export');
if (extensionPath && crypto.createHash('sha256').update(await fs.readFile(extensionPath)).digest('hex')!==receipt.extension_binding.sha256) throw new Error('Extension changed during export');
for (const binding of publication.source_bindings) {
  if (crypto.createHash('sha256').update(await fs.readFile(path.resolve(root, binding.path))).digest('hex') !== binding.sha256) throw new Error('Source changed during export');
}
await fs.writeFile(output.replace(/\.xlsx$/i,'-receipt.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
console.log(JSON.stringify(receipt));
