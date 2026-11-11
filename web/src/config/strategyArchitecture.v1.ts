import mainlineCatalog from "../../../config/value-mainline-modules-v1.json";
export type StrategyKey = "value" | "hotspot";
export type CapabilityStatus = "DESIGNED" | "IMPLEMENTED" | "PARTIAL";
export interface NativeModuleContract {
  source: string;
  phase1Delta?: {
    scope: string;
    deployment: string;
    implementation: string[];
    boundary: string;
  };
  inputSchemaRefs: string[];
  outputSchemaRefs: string[];
  entryRefs: string[];
  methods: Record<string, CapabilityStatus>;
  nativeInputs?: string[];
  nativeOutputs?: string[];
  methodEvidence?: Record<string, { native_refs: string[]; scope: string }>;
  rawMethods?: Record<string, string>;
  baseline?: string;
  requiredDependencies?: string;
  evidence?: string;
}
export const valueMainModuleIds = [
  "A",
  "B",
  "C",
  "D1",
  "D2",
  "E1",
  "E2",
  "F1",
  "F2",
  "G1",
  "G2",
] as const;
export const valueSharedModuleIds = ["S1", "S2", "S3", "S4", "W1"] as const;
export interface DeliveryReview {
  inputDetails?: string[];
  steps?: { title: string; description: string }[];
  outputDetails?: string[];
  acceptanceChecks?: string[];
  implementationRefs?: { path: string; symbol?: string; description: string }[];

  status: "COMPLETE" | "LIMITED" | "PARTIAL" | "UNVERIFIED";
  what: string;
  why: string;
  how: string;
  scope: string;
  done: string;
  gap: string;
  acceptance: string;
  evidence: string[];
  runHref: string;
}
export const deliveryReviewMeta = {
  reviewedAt: "2026-11-02",
  baseline: "f9aadce0",
  kind: "人工交付复核，不是实时运行状态",
} as const;
export interface Stage {
  deliveryReview?: DeliveryReview;
  nativeContract?: NativeModuleContract;
  progress?: {
    consumer: string;
    realData: string;
    economic: string;
    deployment: string;
    acceptance: string;
  };
  id: string;
  title: string;
  question: string;
  input: string;
  output: string;
  engineeringStatus: string;
  evidenceStatus: string;
  shortStatus: string;
  channels?: { id: string; title: string; why: string }[];
  dependencies: string[];
  ruleWhy: string;
  nextStep: string;
  existingEvidence: string;
  evidenceSource: string;
  modules: string[];
  implementation: string;
  milestone: string;
  evidence: string;
  boundary: string;
}
export const review = {
  version: "value-mainline-p0-module-map",
  reviewedAt: "2026-11-01",
  baseline: mainlineCatalog.source_baseline,
  mode: "MANUAL_SOURCE_REVIEW",
  runtimeEvidence: "NOT_CONNECTED",
  ledger: "docs/current/web-first-full-product-execution-ledger.md",
  disclaimer:
    "静态人工维护目录，不是实时进度。源码复核仅说明模块职责；里程碑状态是基线台账的人工整理，不代表人工投资批准。本目录尚未接运行reader，也未在本页核验；不否认既有API与页面消费者。",
} as const;
export const valueVerticalScope = {
  focus: "D2 → 股东现金 → 估值 → 条件价格",
  evidenceSource: "artifacts/current/d2-operating-driver-20261101.json",
  capitalUnknownCount: 9,
  cashEvidenceSource:
    "artifacts/current/value-main-revalidation-20261101/index.json",
  accepted:
    "人工回执快照，非自动监测：本轮正式回执已形成条件研究工作候选，待人工经济复核；三条条件值约6.19516/16.85149/27.22284，Jun30财务基准、Sep30最新实际，三情景共30行现金账。最终回执runtime/value-main-revalidation-20261101/acceptance-source-lf-v2.json；来源spec2c09f05f及SHA已固定。业务版7537c7a0已在唯一8001完成公司页与API核验；当前运行版本见系统页。旧全产品刊发注册仍不可用，用户尚未确认；主区间未采用，无投资批准。",
  currentFollowup:
    "新链只计入一次Q3实际（9M－H1），Q4由上年同季基数作显式季节预测，次年H1另列条件假设，再经既有共享v4。母公司v2三条账面义务合计11,013,375,072.53元仅在模型年1假定清偿一次，后续不重复；非新分红、非CapEx，不能与年度新distribution相加当股东回报。已有价格引擎生成带日期未批准draft，但未选数值规则，无当前买价。旧9.03/20.26/25.82及170.1621亿元历史静态余量保留作历史说明，不是本轮最新结果，不覆盖旧raw。",
  currentBlocker:
    "当前阻断：工作候选待人工经济复核，季节性/持续盈利与资金政策尚未获经济采纳；85亿元财政政策尚未完整建模，既不证明履约也不证明违约。当前资本/分配/事件/报价尚未对齐，无阈值理由不出条件价。原9项资本UNKNOWN不因复用来源绑定的条件现金政策而升级为已证；不能补零、未经核验沿用旧假设或重试模型凑通过。现金/估值计算通道不是永久缺失，当前也不自动获得价格或交易资格。",
  nextRequired: [
    "年度经营路径（正式冷重放已接，经济适用性待核）：新Q3实际 + 条件Q4 + 条件次年H1完整组成首滚动模型年，后续盈利与终端假设明确保留；复用既有计算、不复制公式，非机械年化，不得H1×2，不得调整COGS凑利润，不再列作计算通道缺失；须验证季节性及持续盈利适用性。",
    "税后归属与现金政策（经济采纳待验）：母公司v2义务与准备金实际进入模型，未净扣母现金为期初，旧股利与债务账面清偿首年一次，排除重复WC；付款年是研究假设，不证明真实到期、支付或当前容量。经营税前利润不能直接当股东现金；不得与年度新分红相加当作回报，不冒充本次D2消费或升级原UNKNOWN。",
    "条件估值已消费，主区间未采用：本轮为低置信度条件研究工作候选，待人工经济复核；分红政策未完整建模须保留，不等于必须先扩新模型框架才可呈现条件研究。原假设的维护投入、资金准备与长期持续性仍待经济采纳，不把算术一致性当作未来参数已证。",
    "当前资本/分配/事件/报价及价格理由（当前必需）：带日期未批准研究draft可以单独展示，不代表当前买价；当前未选数值规则，无阈值理由不出条件价，当前不生成买价。公开条件研究不依赖私人持仓解锁；须另核股本、分配、事件、报价及采用资格，不自动形成个人数量或订单。",
  ],
  futureExtensions: [
    "全市场自动研究、通用企业分类与新增公司样本：属于后续扩展，不是本轮纵向链的前置任务。",
    "真实组合、私人持仓、个人账户收益/分红对账与交易执行：不在本轮范围，不作为公开研究的解锁条件；不包含本轮必需的公开股本/分配/事件/报价核验。",
    "热点通道及更多平台能力：保留既有状态，本轮不并行扩展；C职责冻结。",
  ],
  boundary:
    "本轮只推进当前纵向链。下方全景保留其他模块职责，不表示需先完成全部模块；本页仅手工整理真实回执，非自动监测。生产部署与用户确认仍单独验收，不提前记为通过。",
} as const;

export const catalog: Record<
  StrategyKey,
  { title: string; summary: string; stages: Stage[] }
> = {
  value: {
    title: "价值投资 · 模块化研究与决策闭环",
    summary:
      "从公开证据到企业经营、股东现金与估值，再到当前价格、持仓和持续复核。展示11个价值主链模块与5个共享支持模块；热点H1–H4保留为独立暂停通道。",
    stages: [
      {
        id: "A",
        deliveryReview: {
          inputDetails: [
            "显式证券、发行人和报告期请求；官方原件receipt、相对路径、SHA256及原始取得时间。",
            "沪市主板链另读取官方名单、供应商行情/财务、完整合并表、Sina三表及可选官方PDF绑定；不将供应商观察当作法定事实。",
          ],
          steps: [
            {
              title: "取得或复用公开原件",
              description:
                "run_public_evidence按请求执行；新网络取得须显式授权。复用保留原fetched时间，不把本次读取时间改成历史可得时间。",
            },
            {
              title: "校验整包闭包",
              description:
                "load_bundle校验请求、receipt、事实快照及export绑定。来源缺失或不支持保持缺口；来源取得成功不证明事实完整。",
            },
            {
              title: "逐项复核后交队列",
              description:
                "validate_queue_public_evidence要求export路径和SHA完全一致。严格闭包的PARTIAL可消费健康来源；任何已声明receipt原件损坏则整体拒绝，全无可核来源也拒绝。",
            },
            {
              title: "按既有窄规则采纳",
              description:
                "官方资产、负债、权益两期精确勾稽经既有_reconcile_official_balance_ratio；身份、期间、币种或存量已采纳事实冲突时不采纳，最多形成限定debt_ratio事实。",
            },
            {
              title: "可携带归档与隔离恢复",
              description:
                "archive_public_evidence只枚举已绑定闭包；restore_public_evidence在隔离目录预检并恢复，保留字节/来源时间，不联网、不发布current、不覆盖不一致目标。",
            },
          ],
          outputDetails: [
            "来源包、事实快照、财务export及归档manifest引用；系统页区分来源状态、已采纳字段和未采纳原因。",
            "局部真实验收：最终A+B回执覆盖1700只官方主板证券、1618家普通企业；官方勾稽样本列600519/600887/603985，正式范围仍仅既有资产负债率方法。",
          ],
          acceptanceChecks: [
            "检查项：错Hash、错主体/期间、缺币种及坏receipt不能被静默剔除或补零。",
            "检查项：隔离恢复后load_bundle及队列消费者结果一致；旧原件和fetched时间不变。",
            "未完成：全市场任意报告解析、完整融资分类和全量财务质量准入；本次只核源码及留存回执，不重新采集。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/public_evidence.py",
              symbol: "load_bundle",
              description: "请求范围来源包的严格闭包校验。",
            },
            {
              path: "src/value_investment_agent/application/research/public_evidence.py",
              symbol: "validate_queue_public_evidence",
              description: "PARTIAL包健康来源消费及坏原件整体拒绝。",
            },
            {
              path: "src/value_investment_agent/application/research/public_evidence.py",
              symbol: "restore_public_evidence",
              description: "精确闭包隔离恢复；与archive_public_evidence配对。",
            },
            {
              path: "src/value_investment_agent/application/research/value_evidence_enrichment_v1.py",
              symbol: "_reconcile_official_balance_ratio",
              description: "沿用两期勾稽的单字段采纳规则。",
            },
            {
              path: "scripts/current/collect_public_evidence.py",
              symbol: "main",
              description: "显式采集/归档/恢复CLI入口。",
            },
          ],
          status: "LIMITED",
          what: "取得并保存公开原件。",
          why: "研究必须有可核对的出处。",
          how: "下载原件、绑定来源和哈希，再核验期间与口径。",
          scope: "沪市主板公开观察初筛；模块长期能力和完整经济研究仍未完成。",
          done: "1700只主板来源重放已接通；三表、双源和官方资产负债率窄勾稽有真实留存验收。",
          gap: "完整融资分类、全量财务质量及行情交易日仍未核验；来源取得不代表事实完整。",
          acceptance: "独立取得所需原件；缺失、冲突和重复执行均有准确回执。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/abc-e-audit.md",
            "runtime/sse-main-financial-verification-20261102/final-delivery-receipt.json（本机留存，不随源码分发）",
          ],
          runHref: "/strategy/value",
        },
        title: "A · 公开资料与证据",
        question: "资料是否真实、何时可得、属于哪个主体？",
        dependencies: [],
        input: "证券、报告期、官方来源",
        output: "带原件、哈希、时间和覆盖范围的事实",
        modules: [
          "src/value_investment_agent/infrastructure/filings/official_report_acquisition.py",
          "src/value_investment_agent/application/research/public_evidence.py",
          "scripts/current/collect_public_evidence.py",
        ],
        engineeringStatus: "受限采集与消费已接通",
        evidenceStatus: "三公司真实原件已重放",
        shortStatus: "仅核验请求报告；BSE、半年报事实解析与全市场覆盖未完成",
        implementation:
          "三份FY2025官方年报自动取得；茅台、伊利各一项资产负债率由两期报表勾稽后进入既有财务消费者；中原环保币种证据不足，未采纳",
        milestone:
          "公开原件→来源包→限定事实→既有队列/财务消费者→只读系统页；不代表完整财务准入。",
        existingEvidence:
          "三份FY2025官方年报自动取得；茅台、伊利各一项资产负债率由两期报表勾稽后进入既有财务消费者；中原环保币种证据不足，未采纳",
        evidenceSource:
          "2026-10-30；runtime/public-evidence/20261030T110724-accepted/acceptance.json；原件恢复重放、旧Hash与取得时间保持；/system读取当前公开来源状态",
        evidence: "仅核验请求报告；BSE、半年报事实解析与全市场覆盖未完成",
        nextStep:
          "保持未覆盖范围显式：北交所来源、半年报事实、修订版冲突需复核；本轮不扩大其他策略",
        ruleWhy: "可靠事实是后续计算前提；今天下载不自动证明历史可得。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "现有v2研究队列校验来源包；consume_retained_enrichment实际消费两项限定事实",
          realData: "三家FY2025真实来源及空目录恢复已验；非全市场覆盖",
          economic: "不适用或由下游独立准入",
          deployment: "源码与只读API已接通；实际运行状态请打开系统页核对",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "B",
        deliveryReview: {
          inputDetails: [
            "A提供的官方SSE主板A股范围、带来源时点的行情/年度财务/分红观察；可选三表、债务、Sina及官方附注补证。",
            "筛选政策和四通道规则；Web查询仅传搜索词、状态、offset/limit，不传自造估值或筛选结果。",
          ],
          steps: [
            {
              title: "先锁定证券范围",
              description:
                "compile_inputs先验证来源和SSE/主板/A股身份，拒绝重复symbol；先限定官方名单再执行通道预算，不把其他交易所混入。",
            },
            {
              title: "复用四通道原规则",
              description:
                "build_discovery_receipt调用既有质量、股息现金回报、价值和周期规则。报价冲突、风险警示、数据不足与方法不适用分别保留；展示数量限制不会丢弃已通过初筛的公司。",
            },
            {
              title: "区分取得与核验",
              description:
                "财务诊断逐字段显示已取得待核验、真正缺失、口径受限或冲突。金融机构提示专用指标，不以普通企业9项完成率评价。",
            },
            {
              title: "独立来源比较与债务拆分",
              description:
                "compare_observations验证期间、范围、单位、时间和不同供应商；一致仅是E1观察。debt_details只合计已识别借款/债券/非流动租赁，待分类项及官方构成单列，不补零或重复加。",
            },
            {
              title: "把完整初筛集合送入研究队列",
              description:
                "显式SSE适配重放完整1700只及原始财务消费输入，保留预算外候选；复用原质量计算，资料未准入的进入补证队列，有可用质量分数的才进入深研优先队列。30只是初始研究预算，不是新增买入门槛。",
            },
            {
              title: "跨轮延续并有限补证",
              description:
                "保存首次入池、父版本和暂停原因，保持已跟踪成员，不因排序变化静默换票；现有补证执行器每批最多3家，公平轮转、失败隔离。新来源经重验进入下一队列版本，不倒灌旧时点；页面只读，不启动采集。",
            },
            {
              title: "重放并分页交付",
              description:
                "read_screen重新校验实现、来源和结果绑定；旧快照显示年龄，失败返回UNAVAILABLE且total=null。前端保持后端排序，展示每通道状态、理由和缺口；GET不采集。",
            },
          ],
          outputDetails: [
            "隔离分支重新按来源重放：1700只中候选738、排除142、无法评价820；资料截至2026-11-10，尚未发布到8001。官方名单均有记录不代表资料完整。",
            "1618家普通企业至少比对一项，4844项一致、2项冲突、1581家有已识别融资金额；冲突不择源消除。",
            "可搜索分页股票池、逐通道理由、字段值差异、融资分项与原件页链接；初筛不是买入。",
          ],
          acceptanceChecks: [
            "检查项：未来来源/错币种/混合单位/同源镜像不能记双源一致；跨表倍率未声明不放行。",
            "检查项：重复债务不重加，null与0区分；已识别小计不替代完整有息负债，双源MATCHED不升级质量门。",
            "局部真实验收：旧final-delivery-receipt属于历史实现；新实现按142份Hash绑定来源重新计算，并由隔离API读取。完整有息负债NOT_PROVEN、full_financial_quality NOT_GRANTED，行情交易日仍未独立核验。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/sse_research_priority_v1.py",
              symbol: "build_sse_research_priority",
              description:
                "SSE完整来源到现有质量分流与长期研究队列的显式适配。",
            },
            {
              path: "src/value_investment_agent/application/research/sse_research_pipeline_v1.py",
              symbol: "prepare_sse_research_run / read_sse_research_pool",
              description:
                "版本留存、现有补证执行器消费和公开只读结果出口；不创建新任务平台。",
            },
            {
              path: "src/value_investment_agent/application/discovery/sse_main_screening.py",
              symbol: "compile_inputs",
              description: "官方范围、补证、四通道和行级诊断实际聚合。",
            },
            {
              path: "src/value_investment_agent/application/discovery/sse_main_screening.py",
              symbol: "read_screen",
              description: "只读重放、失效拒绝及全量分页。",
            },
            {
              path: "src/value_investment_agent/domain/discovery/financial_source_comparison_v1.py",
              symbol: "compare_observations",
              description: "不同供应商数值比较，不授正式事实资格。",
            },
            {
              path: "src/value_investment_agent/domain/discovery/financial_source_comparison_v1.py",
              symbol: "debt_details",
              description: "去重的已识别融资小计及未分类项。",
            },
            {
              path: "web/src/components/SseMainScreeningPanel.tsx",
              symbol: "SseMainScreeningPanel",
              description: "真实股票池、缺口、双源和官方附注展示。",
            },
          ],
          status: "LIMITED",
          what: "从市场中找值得继续研究的公司。",
          why: "避免只研究事先指定的股票。",
          how: "复用四通道筛选，将入池理由和缺口送入队列。",
          scope: "沪市主板公开观察初筛；模块长期能力和完整经济研究仍未完成。",
          done: "隔离分支1700只逐股初筛已重算：738候选、142排除、820无法评价；旧双源与融资统计是历史回执，须与新版重放分开查看。",
          gap: "完整债务和全量质量资格仍未通过；新队列接线不等于批量经营研究、估值及持续自动监控已完成。",
          acceptance: "来源与交易日核验通过，候选、排除理由及覆盖范围可复算。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/abc-e-audit.md",
            "docs/current/value-transparent-workbench-v1.md",
          ],
          runHref: "/strategy/value",
        },
        title: "B · 四通道筛选与研究队列",
        question: "哪些公司值得投入研究时间？",
        dependencies: ["A"],
        input: "有时点的证券范围、财务与行情",
        output: "质量／现金回报／价值／周期研究线索",
        modules: [
          "src/value_investment_agent/application/discovery/value_candidate_selection.py",
        ],
        engineeringStatus:
          "初筛、调度与限定事实消费已验证；新版来源重放已接隔离API",
        evidenceStatus: "142份公开来源经Hash核对并重算；8001待发布验收",
        shortStatus:
          "四通道初筛与排序已验；新版1700只重算后738候选，仍有820只无法评价；历史离线调度和限定事实消费须分开核对",
        implementation:
          "Hash绑定公开来源→当前实现重算→四通道排序与诊断→现有只读API分页；补证队列与正式事实消费沿用原合同，不自动授予投资资格",
        milestone: "初筛与限定事实消费已验证；经济研究与正式资格未完成。",
        existingEvidence:
          "历史沪深观察范围5224家及限定补证结果另存；新版沪市主板1700只重放为738候选、142排除、820无法评价，深度研究不因入池自动完成",
        evidenceSource:
          "历史回执见runtime/b-real-acceptance-20261030；新版隔离清单runtime/sse-main-screening/sse-main-ab-v8-20261111T091228/manifest.json，隔离API已消费，8001仍待验收",
        evidence:
          "新版资料截至2026-11-10，读取时标为历史快照；沪市主板1700只并非全A，报价交易日未独立核验；报价CONFLICT保留原始来源，不冒充当前有效行情",
        nextStep:
          "继续核验各通道经营与经济证据；新增资产负债率不代表完整债务、企业质量或估值准入",
        ruleWhy: "不同企业的价值线索不同；低PE和高股息都可能是陷阱。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "当前实现重算已进入隔离API并保持738条候选分页；历史补证队列仅在原合同内消费，不等于批量深研",
          realData:
            "新版142份公开来源Hash核对，沪市主板1700只历史时点重算；旧5224家沪深观察与两项限定事实另属历史回执",
          economic:
            "初筛线索不证明ROIC、正常化盈利或分红持续性；资产负债率仅按窄方法核验",
          deployment:
            "隔离源码、API与构建已验；8001进程归属记录不一致，尚未切换，历史数据日期不随发布滚动",
          acceptance: "用户尚未确认最终验收；action=no_order",
        },
        channels: [
          {
            id: "quality",
            title: "质量",
            why: "盈利、现金转换与再投资能力，仍需经营证据。",
          },
          {
            id: "dividend_cash_return",
            title: "股东现金回报",
            why: "分红覆盖与可持续性，历史高股息不等于可持续。",
          },
          {
            id: "value",
            title: "价值",
            why: "寻找价格错配线索，不能把低PE当内在价值。",
          },
          {
            id: "cyclical",
            title: "周期",
            why: "用正常化盈利识别周期位置，拒绝峰值利润陷阱。",
          },
        ],
      },
      {
        id: "C",
        deliveryReview: {
          inputDetails: [
            "已消费研究包、descriptor及发行人经营原文；固定source-only样本的官方完整段落和审核规则。",
            "冻结五家为600519、600887、000333、601088、600036；000568的E2首编不增加C样本。",
          ],
          steps: [
            {
              title: "优先校验已有研究",
              description:
                "load_company_profile先取当前已绑定候选或重放包，核验时点；损坏当前证据不能悄悄退回source-only。",
            },
            {
              title: "绑定画像与输入",
              description:
                "validate_company_profile_for_package核对经营与资本证据；project_company_profile生成业务画像，并与真实消费descriptor一致性校验。",
            },
            {
              title: "有限原文路由",
              description:
                "固定新三家按已审核完整原文映射业务族：制造及周期仅提供条件模型路由，银行明确方法不适用；不是名称关键词通用分类器。",
            },
            {
              title: "列出模型缺项",
              description:
                "既有路由返回required_inputs与拒绝原因；画像不代填预测或资本参数，不允许无输入估值，不授经济批准。",
            },
          ],
          outputDetails: [
            "来源绑定的经营画像、模型路由、必需输入和反证；旧两家公司分析消费保持一致。",
            "固定五家局部真实验收：000333/601088只有路由与输入缺口，600036金融拒绝；不是五家都可估值。",
          ],
          acceptanceChecks: [
            "已验范围：冻结五家来源与API回执；检查错公司、坏Hash、descriptor不一致不得回退。",
            "未完成：任意新公司自动分类和模型经济适用性验证；固定五家完成不能外推全行业。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/company_profile.py",
              symbol: "load_company_profile",
              description: "当前研究优先级和真实descriptor对齐。",
            },
            {
              path: "src/value_investment_agent/application/research/company_profile.py",
              symbol: "validate_company_profile_for_package",
              description: "画像来源与模型输入校验。",
            },
            {
              path: "src/value_investment_agent/application/research/company_profile_sources_v1.py",
              symbol: "load_source_company_profile",
              description: "固定原文审核样本入口。",
            },
            {
              path: "src/value_investment_agent/domain/research/profile_applicability_v1.py",
              symbol: "contract_for_profile",
              description: "路由必需输入与禁止批准边界。",
            },
          ],
          status: "COMPLETE",
          what: "判断企业类型及适用研究方法。",
          why: "不同企业不能套同一种估值公式。",
          how: "读取企业画像，核对模型必需输入，不适用时明确拒绝。",
          scope: "固定五家画像与方法适用性；不含经济质量或投资准入。",
          done: "固定五家画像与路由已验收；支持有据路由和明确拒绝。",
          gap: "固定五家之外未验收；不是通用自动分类器。",
          acceptance: "固定五家来源、适用和拒绝合同独立通过，API可读取。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/abc-e-audit.md",
            "runtime/c-closeout-20261031/api-acceptance/receipt.json",
          ],
          runHref: "/strategy/value",
        },
        title: "C · 企业画像与模型适用性",
        question: "企业靠什么赚钱，适合什么模型？",
        dependencies: ["A", "B"],
        input: "业务原文、产品收入、财务口径与资本结构",
        output: "来源绑定的经营分类、既有资本证据、路由、反证与适用限制",
        modules: [
          "src/value_investment_agent/application/research/company_profile.py",
          "src/value_investment_agent/domain/research/research_profile.py",
          "src/value_investment_agent/valuation_router.py",
        ],
        engineeringStatus: "工程闭环完成",
        evidenceStatus: "固定五家验收通过",
        shortStatus:
          "固定五家：旧两家消费不变；制造与周期仅条件路由、输入待补；金融有据拒绝",
        implementation:
          "复用既有研究及有限官方完整段落审核准入；不代表通用自动分类，不新增预测或估值",
        milestone:
          "固定五家及合同已验，C职责冻结；有限审核不代表通用分类或经济准入。",
        existingEvidence:
          "旧两家来源与消费指纹不变；美的完整主营与资本范围、神华一体化周期业务、招商银行身份与金融主营已核",
        evidenceSource:
          "artifacts/current/company-profile-c-closeout-20261031.json；runtime/c-closeout-20261031/api-acceptance/receipt.json；source-pack.json",
        evidence:
          "000333仅FCFF路由、10项输入全缺；601088仅周期正常化路由、13项输入全缺；600036身份已验后金融拒绝，无替代模型",
        nextStep:
          "C职责冻结；D1受限执行、D2假设、E2首编按各自证据验收，不反向扩大C",
        ruleWhy:
          "行业、经营收入机制与资本结构共同约束模型；不能以行业标签或品牌名称证明质量。",
        boundary:
          "经营分类与既有模型路由不授予经济、估值或交易资格；保留来源日期、未知与反证。action=no_order。",
        progress: {
          consumer:
            "固定五家接口已验；旧两家分析消费不变，新两家仅路由，银行有据拒绝",
          realData: "固定五家已验；新三家有限官方完整段落审核，未新增公司深研",
          economic:
            "业务族仅约束模板候选，不证明经济质量；正常化盈利、资本回报和持续分配仍有缺口",
          deployment: "部署待验收；部署后仅按独立运行回执更新",
          acceptance: "用户尚未确认此版本；部署通过不代替用户确认",
        },
      },
      {
        id: "D1",
        deliveryReview: {
          inputDetails: [
            "显式任务请求、已封存官方source context、模型配置及预算权限；不将旧估值或保存响应冒充新研究。",
            "经营、反证、事件三角色结构化合同，逐角色request/response及usage记录。",
          ],
          steps: [
            {
              title: "创建冻结任务",
              description:
                "LiveOperatingTaskService复用ResearchTaskService的锁和状态版本；绑定来源与实现，执行前重建context并校验身份。",
            },
            {
              title: "先检查预算再请求",
              description:
                "调用前预留CNY预算并检查跨任务日上限，Provider返回后记录usage和结算；估算不是供应商账单，未结算不伪造零费用。",
            },
            {
              title: "逐角色校验与留痕",
              description:
                "FUNDAMENTAL后再由反证和事件角色审视本次提案；引用、字段或反证缺失拒绝，原失败响应保留，恢复不能冒称首次即成功。",
            },
            {
              title: "有界执行与取消",
              description:
                "既有HTTP后台由supervise_live_task监督自有子进程，取消或总超时须回收worker；终态锁冲突保留pending记录，不伪装状态已落盘。",
            },
            {
              title: "只输出研究草案",
              description:
                "任务视图重新校验绑定并展示真实角色完成情况；执行成功不代表经济论断正确、主区间采用或投资批准。",
            },
          ],
          outputDetails: [
            "来源可追踪的角色响应、失败轨迹、费用估计、检查点和可恢复任务状态。",
            "2026-11-05真实600323任务rt-cc3d5e56a5a22e6deb03100092dad471：三角色完成；事件首答被拒后仅恢复该角色，合计4次调用，估算费用0.204382元。旧失败与前两角色检查点均保留。",
          ],
          acceptanceChecks: [
            "检查项：未经明确操作不调用模型；预算不足、来源变化、坏响应应准确拒绝。",
            "检查项：取消/超时不被晚返回覆盖，终态写入失败可见；旧raw响应及实现绑定不改。",
            "2026-11-05：任务/API定向167项、恢复互斥2项、前端83项通过；本轮修改不产生新模型调用。历史真实三角色产物与本轮工程验证分开。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/agent_review/operating_task_v2.py",
              symbol: "LiveOperatingTaskService",
              description: "来源重验、预算、角色执行和持久状态。",
            },
            {
              path: "src/value_investment_agent/application/research/agent_review/operating_driver_draft_v2.py",
              symbol: "validate_response",
              description: "结构化经营驱动响应校验。",
            },
            {
              path: "src/value_investment_agent/operations/live_task_controller_v1.py",
              symbol: "supervise_live_task",
              description: "自有worker总时限、取消及回收。",
            },
            {
              path: "docs/current/value-transparent-workbench-v1.md",
              description: "历史成功、近期取消和监督修复分别记载。",
            },
          ],
          status: "COMPLETE",
          what: "让三类AI执行来源绑定的研究。",
          why: "同时研究经营、反证和事件，避免单面叙事。",
          how: "绑定封存来源→调用前预留预算→依次执行经营、反证、事件→校验引用并封存角色→供D2消费；中断后锁定恢复，页面跟踪真实状态。",
          scope:
            "已配置公开来源公司的受限三角色执行、持久化、预算、取消及恢复；不是全市场自动深度研究。",
          done: "真实600323完整三角色及失败后仅续跑未完成角色已运行成功；页面跟踪、历史恢复、预算与结果封存已接通。",
          gap: "用户尚未确认。经济假设采纳、现金政策和估值属于D2/E2，不能因D1成功自动通过；新公司仍须有合格来源。",
          acceptance:
            "真实模型完整完成三角色；预算、失败、取消和恢复均可验证。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/d1-g2-audit.md",
            "docs/current/value-transparent-workbench-v1.md",
          ],
          runHref: "/strategy/value",
        },
        title: "D1 · 受限研究执行",
        question: "研究能否在预算内运行并恢复？",
        dependencies: ["A", "B"],
        input: "封存摘要、任务与预算权限",
        output: "受控模型响应、成本、错误与任务轨迹",
        modules: [
          "src/value_investment_agent/infrastructure/agent_runtime/provider.py",
          "src/value_investment_agent/application/research/agent_review/operating_task_v2.py",
        ],
        engineeringStatus:
          "真实三角色执行、失败分类与拒绝恢复已验收；当前版本已有完整三角色研究",
        evidenceStatus:
          "600323的 rt-72bd66eee8fdba9ae99240ac1029e44e 是历史成功任务；引用枚举修复后的 rt-7e972278c9c6186dbfbe0121cf270fe8 已完成当前版本三角色研究。中间失败回执仍独立保留。",
        shortStatus:
          "600323当前版本已有真实三角色研究；任务成功不等于经营假设、主估值或交易通过",
        implementation:
          "三角色依次执行，调用前预留费用，完成一角即封存检查点；恢复先取得controller和execution锁，只继续未完成角色。页面每3秒只读跟踪所选任务，读取失败即暂停，刷新后可从历史继续跟踪；取消任务不复活。",
        milestone:
          "任务 rt-7e972278c9c6186dbfbe0121cf270fe8 在引用枚举修复后完成三角色调用；历史不完整响应与伪造引用失败回执均保留，未以重试覆盖。",
        existingEvidence:
          "600323的来源绑定摘要、角色回执、提示词版本、输入指纹和费用记录均留在任务存储；不读取旧估值或把保存响应冒充新研究。",
        evidenceSource:
          "runtime/research-task-execution-v1/live-operating-v1/ 下的600323任务状态、角色响应和receipt；源码版本见实际运行身份。",
        evidence:
          "每日预算上限10元；成功任务的内部预算结算为0.127354元，属于配置费率估算，不能当作供应商账单或扩大后续调用额度。",
        nextStep:
          "本执行模块收尾；后续只维护供应商兼容和失败恢复，经营参数及现金估值交D2/E2独立验收，不扩D1职责。",
        ruleWhy: "执行可靠性与投资判断不同；Mock只能证明工程路径。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "现有公司AI区域显式操作 → 任务API → 持久执行器；不在首屏后台调用",
          realData:
            "600323当前任务完成三角色真实调用；引用不足、供应商不完整响应与伪造引用失败均保留为独立任务历史，不升级为投资结论",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "D2",
        deliveryReview: {
          inputDetails: [
            "600519/600887来源绑定的历史事实、假设及proposal；另一条000568新研究链读取官方摘录和三角色驱动范围。",
            "明确期间的量、价、产品结构、成本假设；资金可达、维护及终端缺依据项允许UNKNOWN。",
          ],
          steps: [
            {
              title: "重放历史经营基准",
              description:
                "load_operating_assumption_draft冷核官方报表及历史字段，核对source/assumption/proposal绑定；历史重放不叫重新生成未来预测。",
            },
            {
              title: "把事实与预测分开",
              description:
                "新driver响应通过来源和calendar合同后，历史量价成本属于事实基础，未来区间仍标FORECAST；不能以引用存在证明文字经济正确。",
            },
            {
              title: "确定性派生经营结果",
              description:
                "operating_driver_bridge按同期间基准计算路径及七维角点，不让语言模型直接填最终利润率；FY对FY、H1对H1。",
            },
            {
              title: "生成反证与重开条件",
              description:
                "build_thresholds与evaluate_condition使用同一bounds、期间和基线，阈值等号不当超限；保留受影响字段及尚未证实资本条件。",
            },
            {
              title: "交现金模型但不采用主区间",
              description:
                "经营驱动经后续期间适配和共享v4消费；条件算术通过与季节性、持续盈利和资金政策被经济采用分开。",
            },
          ],
          outputDetails: [
            "可定位来源的假设、经营驱动范围、派生增长/利润率、反证阈值与UNKNOWN。",
            "局部真实样本：000568的21项驱动、3×128角点、6项代码派生指标及9项资本UNKNOWN；不把后续有条件现金政策反写为事实。",
          ],
          acceptanceChecks: [
            "检查项：错来源/期间/字段、历史值与proposal不一致应拒绝；不靠H1乘2或调成本凑利润。",
            "局部验收：独立角点和阈值复算有留存记录；未完成参数未来适用性和经济主区间采用。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/operating_assumption_draft_v1.py",
              symbol: "load_operating_assumption_draft",
              description: "旧两公司来源绑定假设重放。",
            },
            {
              path: "src/value_investment_agent/domain/research/operating_driver_bridge_v1.py",
              symbol: "calculate_path",
              description: "同期间量价成本及角点计算。",
            },
            {
              path: "src/value_investment_agent/domain/research/operating_driver_bridge_v1.py",
              symbol: "evaluate_condition",
              description: "同基线反证条件评价。",
            },
            {
              path: "src/value_investment_agent/application/research/main_valuation_revalidation_v1.py",
              symbol: "_consume",
              description: "季度经营到实际共享现金模型的后续消费者。",
            },
            {
              path: "docs/current/value-mainline-p0-20261101/d2-f-audit.md",
              description: "三家公司分路径审计及真实复算边界。",
            },
          ],
          status: "PARTIAL",
          what: "把资料变成有依据的经营假设和反证。",
          why: "估值参数需要经济理由，而不是AI直接报价格。",
          how: "区分事实与预测，推导量价成本及资金路径，保留反例。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "11月11日增量：原V7和一次纠错均因引用错误被拒，现金阶段未调用。新版本已用封存年报/半年报计算历史成本率反证；发行人两页分红规划原件经Hash和取得时间核验，明确2024—2026有条件派息目标。新年度、现金合同只保留为未批准研究输入。",
          gap: "当前预测年为2027，发行人派息规划只到2026；它只能作历史反证，不能推出2027派息率或母公司可达现金。新合同未进入真实任务及E2消费；原失败、费用和UNKNOWN保留，无新的真实估值或条件价。",
          acceptance:
            "来源绑定的经营假设、三情景、反证和重开条件可被模型消费。",
          evidence: ["docs/current/value-mainline-p0-20261101/d2-f-audit.md"],
          runHref: "/strategy/value",
        },
        title: "D2 · 经营假设与反证",
        question: "增长和分配为何成立，什么会推翻？",
        dependencies: ["C", "D1"],
        input:
          "同公司官方事实、明确年度或半年口径、经营驱动假设与反证；年度补充保留独立任务、截止日和输入版本",
        output:
          "600323输出逐年条件税前/归属利润，尚无现金政策；000568历史条件现金与估值单独保留，不混用",
        modules: [
          "src/value_investment_agent/application/research/product_operating_research.py",
          "src/value_investment_agent/application/research/agent_review/operating_draft_v1.py",
        ],
        engineeringStatus:
          "条件压力算术已验／000568经营→现金→条件估值有限工程链已验收；经济待审",
        evidenceStatus:
          "96条官方来源；21项经营驱动范围、6项增长/税前利润率由代码派生、9项资本UNKNOWN；不是模型直接填利润率；新增30行现金账与v4条件估值真实消费",
        shortStatus:
          "600323三角色成功；FY2025→2027全年经营已编译年度归属利润输入。税费事实已补齐；仍缺连续现金路径、适用终端和主区间，尚无F1/F2价格结论",
        implementation:
          "原驱动桥锁定H12026→H12027，按每情景128角点重算；同比FY只对FY、H1只对H1。新增2026Jul–2027Jun滚动全年适配，后续flat，ResearchApplicationService→既有v4计算",
        milestone:
          "V7已把年度经营研究与来源锚定的股东现金政策拆成同一任务的两阶段，并接入E2严格读取。600519真实年度调用因证据ID无效失败；现金阶段未执行，估值与条件价仍未形成。不同任务不自动合并主预测；现金和估值仍未闭环。",
        existingEvidence:
          "旧D2两公司草案及rt-c40经济拒绝保留为历史，不覆盖旧raw；当前H1第11/14/12页量价成本表构成新驱动桥，不沿用旧直接填利润率路径",
        evidenceSource:
          "runtime/d2-operating-driver-20261101/rt-eac1c74997d17510398ce1fe1e5bea9e-recovered.json；runtime/d2-operating-driver-20261101/independent-acceptance.json；artifacts/current/d2-cash-consumption-20261101/index.json；源码版本见实际运行身份；验收索引 artifacts/current/d2-operating-driver-20261101.json",
        evidence:
          "仅拒绝两类AI文字：产品结构向高档集中误述、Event母现金23.93亿元少10倍；不作为事实摘要，typed bridge不消费这些文字，算术验收不受其替代。Event仍限FY/H1；未来参数适用性未证，原9项资本UNKNOWN不升级已证；新现金/估值仅复用另行绑定的条件政策。",
        nextStep:
          "将版本化来源、年度成本反证和2026派息规划接入同一真实任务；先通过严格引用与经济审查，再生成现金路径并交E2/F1/F2。规划不外推2027年后，不以派息目标替代母公司现金，不重复付费重试旧响应。",
        ruleWhy: "价格上涨不直接等于净利上涨；预测必须明确为假设。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "开发分支已将年度经营与股东现金分两段持久执行，同一任务绑定后进入E2检查；完整政策、经济区间和模型适用性齐备后才进入共享估值与条件价格。旧研究路径保持原状。",
          realData:
            "人工维护进度：600519来源绑定的V6任务两段成功，但未来现金参数仍为UNKNOWN，E2拒绝。V7真实deepseek-flash年度阶段因一条伪造证据ID失败，现金阶段未调用；不能据此生成估值或条件价。",
          economic:
            "历史派息和未缴基金承诺可作条件锚点；参数经济适用性未证，母公司资金可达、维持投入及经营营运现金缺乏可审阅的未来桥，不能补零或把余额变动当现金。E2/F1/F2正向路径仍未通过。",
          deployment:
            "V7提交9179c77a的Core/Web CI通过；本机8001已发布66f2c19c，研究任务根与共享预算账本绑定至既有数据根。真实失败任务可通过授权API读取，现金和估值仍未形成。",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "E1",
        deliveryReview: {
          inputDetails: [
            "既有公司研究包、候选/assumption/proposal绑定与新版本事实；必须有真实前序研究，不适用无旧包首编。",
            "实际消费choice、模型实现身份及descriptor；600519/600887为已验证案例，不是任意symbol模板。",
          ],
          steps: [
            {
              title: "从旧包准备新候选",
              description:
                "prepare_pending_research_candidate读取真实来源及显式研究选择，在新产物中保留前序谱系，不用最终估值反推输入。",
            },
            {
              title: "核对经济输入一致",
              description:
                "_verify_joint_economic_inputs复核assumption、proposal和descriptor；换公司、换来源或实际choice不符拒绝。",
            },
            {
              title: "冷核并重算",
              description:
                "verify_pending_research_candidate重核原件/实现，构建v4 descriptor和ResearchRunSpec，调用ResearchApplicationService，不能只返回保存的估值。",
            },
            {
              title: "通过已有分析消费者公开",
              description:
                "project_value_research_analysis比较实际descriptor、年度现金review和三情景数值；新候选保持待复核，当前价格资格另交F2。",
            },
          ],
          outputDetails: [
            "带版本谱系及来源绑定的新候选、真实输入descriptor、三情景现金/估值与未批准review。",
            "局部真实验证：600519/600887同一v4消费路径成功；已有包更新不证明任意新公司首编。",
          ],
          acceptanceChecks: [
            "检查项：坏原件/错实现/错choice或冷重算不一致拒绝，不静默继续旧结果。",
            "检查项：真实源环境缺失不能把skip算真实通过；历史包不可覆盖。",
            "未完成：通用独立重新研究及全部当前对齐条件；conditional_research_only不是正式研究采用。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/product/pending_research_candidate.py",
              symbol: "prepare_pending_research_candidate",
              description: "新候选准备与来源绑定。",
            },
            {
              path: "src/value_investment_agent/application/product/pending_research_candidate.py",
              symbol: "verify_pending_research_candidate",
              description: "旧候选实际冷重算入口。",
            },
            {
              path: "src/value_investment_agent/application/research/value_research_analysis.py",
              symbol: "project_value_research_analysis",
              description: "现金review和估值实际消费一致性。",
            },
            {
              path: "tests/test_joint_cash_v4_two_company_real_replay.py",
              description: "两公司真实同内核消费测试，需真实来源环境。",
            },
          ],
          status: "PARTIAL",
          what: "根据新输入重算已有研究。",
          why: "研究要更新并保留原判断的变化原因。",
          how: "读取旧研究版本，重编译受影响输入，再交共享内核计算。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "600519、600887旧包真实再编译并进入消费者。",
          gap: "仍偏固定案例，通用独立重新研究入口尚未完整证明。",
          acceptance: "独立更新输入、重算、保留历史并在API看到新版本。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/abc-e-audit.md",
            "runtime/sse-main-financial-verification-20261102/final-delivery-receipt.json（本机留存，不随源码分发）",
          ],
          runHref: "/strategy/value",
        },
        title: "E1 · 已有研究更新与重放",
        question: "新资料如何改变已有判断？",
        dependencies: ["F1"],
        input: "已有候选、事实与假设的新版本",
        output: "可重算新候选、版本谱系与差异",
        modules: [
          "src/value_investment_agent/application/product/pending_research_candidate.py",
          "src/value_investment_agent/application/product/neutral_valuation_proposal.py",
        ],
        engineeringStatus: "有限贯通",
        evidenceStatus: "真实样本部分验证",
        shortStatus: "已有两公司成功不等于任意公司首版研究",
        implementation: "600519、600887已有真实来源候选与消费链",
        milestone: "有限贯通；不代表正式研究准入或实盘资格。",
        existingEvidence: "600519、600887已有真实来源候选与消费链",
        evidenceSource:
          "d01923cd；docs/current/web-first-full-product-execution-ledger.md；.tmp/value-followup-acceptance/real-business-receipt.json（本机留存，不公开私人文件）",
        evidence: "已有两公司成功不等于任意公司首版研究",
        nextStep: "保持旧版本，按新输入重算并强制真实来源重放",
        ruleWhy: "更新必须定位改变的假设，不能覆盖历史或抄最终估值。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "真实样本部分验证（见证据）",
          economic: "条件研究／未批准",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "E2",
        deliveryReview: {
          inputDetails: [
            "无旧研究包公司的自身原件、native facts、首编spec和显式条件假设；不能要求E1旧候选作为前置。",
            "000568官方FY/H1事实；条件owner-equivalent现金、capacity/floor及未来投入须标假设，未知实际净可新增分配不补零。",
          ],
          steps: [
            {
              title: "验证首编规格",
              description:
                "_prepare拒绝前序候选、市场价格、批准等越界键，要求源绑定和实现身份；未备齐必要输入返回明确缺口。",
            },
            {
              title: "原页重建历史事实",
              description:
                "replay_first_research_facts核发行人、期间、页列、金额及单位；TTM仅在受支持同字段上按FY+当期H1－同期H1派生，不允许历史值手填假设。",
            },
            {
              title: "编译十年条件输入",
              description:
                "明确三情景未来收入/成本、资金可达、维护/WC/承诺及终端条件；已宣告股利和期初资源口径单独约束，不能当新分配重复消费。",
            },
            {
              title: "实际调用共享内核",
              description:
                "replay_first_research_input重建proposal/package和descriptor，经ResearchApplicationService运行v4并比对冷重算指纹，不是套用600519/600887结果。",
            },
            {
              title: "只写新首版产物",
              description:
                "build_first_research_input要求新输出目录，不注册当前候选；公开reader重验receipt后展示条件研究，主区间与C分类均不随首编成功升级。",
            },
          ],
          outputDetails: [
            "首版proposal、package、receipt、三条十年现金账及条件压力估值，或字段级拒绝。",
            "000568两份自身官方原件84项事实首编有留存API验收；main_range_adopted=false，主经济区间REJECTED。",
          ],
          acceptanceChecks: [
            "检查项：无旧包仍可首编，输出已存在拒覆盖；来源变化、未来日期或descriptor不一致拒绝。",
            "检查项：只证明明确条件下数学压力可重算，不把终端假说、未来资金或利润称已证。",
            "未完成：通用独立首编自动化、主估值经济闭环；不新增第六家C。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/first_research_input_v1.py",
              symbol: "_prepare",
              description: "首编来源与条件输入合同。",
            },
            {
              path: "src/value_investment_agent/application/research/first_research_input_v1.py",
              symbol: "replay_first_research_input",
              description: "实际共享v4冷重算。",
            },
            {
              path: "src/value_investment_agent/infrastructure/filings/first_research_fact_replay_v1.py",
              symbol: "replay_first_research_facts",
              description: "原页事实重放。",
            },
            {
              path: "src/value_investment_agent/application/product/first_research_input_view_v1.py",
              symbol: "read_first_research_input",
              description: "注册首输入公开reader。",
            },
            {
              path: "artifacts/current/first-research-input-e2-20261031.json",
              description: "000568首编验收索引。",
            },
          ],
          status: "PARTIAL",
          what: "为没有旧研究包的公司首次建立模型输入。",
          why: "不能永远依赖预先准备好的公司研究。",
          how: "核验事实和假设，经画像路由编译为共享模型输入。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "000568以84项事实完成首编；11月5日新增600323全年经营→年度利润输入的实际API消费，缺年不填充。",
          gap: "通用入口仍缺一条由当前D2完整现金政策驱动、可冷重放并进入共享估值模型的真实正向首编；只有年度利润或历史候选不算完成。",
          acceptance: "无旧研究包的真实公司经同一入口形成可消费的完整输入。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/abc-e-audit.md",
            "runtime/sse-main-financial-verification-20261102/final-delivery-receipt.json（本机留存，不随源码分发）",
          ],
          runHref: "/strategy/value",
        },
        title: "E2 · 新公司首次编译",
        question: "没有旧估值，能否完成第一份研究？",
        dependencies: ["B", "C", "D2"],
        input: "该公司自身事实、假设与模型适用性",
        output: "来源绑定首版模型输入、年度现金路径、条件压力计算或精确拒绝",
        modules: [
          "src/value_investment_agent/application/research/first_research_input_v1.py",
          "src/value_investment_agent/infrastructure/filings/first_research_fact_replay_v1.py",
          "src/value_investment_agent/application/product/first_research_input_view_v1.py",
        ],
        engineeringStatus: "工程首编与真实来源重算完成／部署待验收",
        evidenceStatus: "000568自身两份官方原件、84项事实冷重放",
        shortStatus: "无旧包首编已实际消费共享v4；主研究区间未采纳",
        implementation:
          "同一入口读取自身经营假设、现金约束，形成三条十年路径及共享模型条件压力计算",
        milestone: "首输入条件研究闭环；不代表经济质量、主估值采用或投资准入。",
        existingEvidence:
          "同一入口读取自身经营假设、现金约束，形成三条十年路径及共享模型条件压力计算",
        evidenceSource:
          "artifacts/current/first-research-input-e2-20261031.json；官方FY2025/H12026原件与独立冷重算回执",
        evidence: "无旧包首编已实际消费共享v4；主研究区间未采纳",
        nextStep:
          "逐项复核渠道恢复、持续投入、资金可达及终端假设；不增加第六个C样本，不生成买价",
        ruleWhy: "E2不以E1旧候选为前提；禁止换名字复制茅台假设。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "来源→首输入→共享v4→ResearchCase→公开API与现有公司页面",
          realData: "000568两份原件84事实；三情景每年账与RI/分配折现核对",
          economic: "条件研究／未批准",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "F1",
        deliveryReview: {
          inputDetails: [
            "通过类型/范围校验的年度利润与资本路径、期初权益、现金、分配容量、现金底线和折现率。",
            "显式十年经营/资金政策及独立终端合同；输入来自E1或E2等受支持入口，不要求两者同时存在。",
          ],
          steps: [
            {
              title: "逐年递推真实模型输入",
              description:
                "compile_joint_capital_cash_path消费显式利润路径与资本配置；新经营/流动资本回报单独计算，留存不自动获得高回报。",
            },
            {
              title: "现金和容量同时限分配",
              description:
                "_step先处理利润可达/未上划、维护/WC/承诺，再以目标、现金和可分配容量限制新分配，结转现金、权益与未上划余额。",
            },
            {
              title: "一次性义务与持续投入分开",
              description:
                "当前000568主重验将账面借款和旧股利在假定Y1清偿一次，并移出对应floor避免重复；不是新股东分配，不推未来利息节约。",
            },
            {
              title: "终端仍受现金合同约束",
              description:
                "value_terminal_economic_contract按旧业务持续假说、新资本回报和维护/现金底线递推，要求受支持的收敛合同；十年不是永久可持续证明。",
            },
            {
              title: "提供诊断与独立复算",
              description:
                "共享v4输出年度账和估值；分配诊断区分经营缺口与各年期初资源支持下限，累计支持不是模型起始日所需现金，覆盖倍数不是市场股息率。",
            },
          ],
          outputDetails: [
            "三情景年度利润、现金、权益、分配、终端与折现结果；资金约束失败或未支持合同的精确原因。",
            "已实现内核及局部真实消费：两既有公司与000568主重验；仅有界模型合同可交付，不代表全行业估值完成。",
          ],
          acceptanceChecks: [
            "检查项：年度账与descriptor一致；目标分配不能越过现金/容量，旧股利和义务不重扣。",
            "检查项：终端持续投入和未付义务不能凭空消失；算术成功不授经济批准。",
            "已验为源码及留存真实复算范围；假设持续性、主采用和当前买价另审。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py",
              symbol: "compile_joint_capital_cash_path",
              description: "年度现金/权益联合编译。",
            },
            {
              path: "src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py",
              symbol: "value_terminal_economic_contract",
              description: "终端递推及收敛合同。",
            },
            {
              path: "src/value_investment_agent/domain/research/liability_settlement_schedule_v1.py",
              symbol: "compile_liability_settlements",
              description: "一次性非生产义务清偿账本。",
            },
            {
              path: "src/value_investment_agent/application/research/main_valuation_revalidation_v1.py",
              symbol: "_consume",
              description: "季度与义务输入实际进入共享模型。",
            },
            {
              path: "src/value_investment_agent/domain/valuation/distribution_capacity_review.py",
              symbol: "explain_distribution_capacity",
              description: "年度分配覆盖与约束诊断。",
            },
          ],
          status: "COMPLETE",
          what: "计算给定假设下的条件价值。",
          why: "让估值算术可以独立复算，而非接受自然语言报价。",
          how: "逐年计算利润、现金、分配和权益，按合同处理终值与折现。",
          scope: "既有模型、有界合法输入的计算合同；不含假设采用与投资批准。",
          done: "两家真实输入通过共享现金、权益、终值与独立重算。",
          gap: "不证明未来假设必然实现；不等于当前买价或经济批准。",
          acceptance:
            "既有模型及有界输入内，年度账、现金约束和终值合同可独立验证。",
          evidence: ["docs/current/value-mainline-p0-20261101/d2-f-audit.md"],
          runHref: "/strategy/value",
        },
        title: "F1 · 经营—股东现金—估值内核",
        question: "利润何时真正成为股东现金？",
        dependencies: ["A", "C"],
        input: "合法年度经营、资本、资金约束与假设",
        output: "年度现金与权益、三情景估值、终值诊断",
        modules: [
          "src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py",
          "src/value_investment_agent/valuation_models/residual_income_path_v4.py",
          "src/value_investment_agent/domain/valuation/distribution_capacity_review.py",
        ],
        engineeringStatus: "有限贯通",
        evidenceStatus: "真实样本部分验证",
        shortStatus: "算术通过不证明长期利润或全额分配可持续",
        implementation: "两公司v4条件研究与真实来源重算已交付",
        milestone: "有限贯通；不代表正式研究准入或实盘资格。",
        existingEvidence: "两公司v4条件研究与真实来源重算已交付",
        evidenceSource:
          "d01923cd；docs/current/web-first-full-product-execution-ledger.md；.tmp/value-followup-acceptance/real-business-receipt.json（本机留存，不公开私人文件）",
        evidence: "算术通过不证明长期利润或全额分配可持续",
        nextStep: "复核关键经济假设、现金覆盖和终端持续投入",
        ruleWhy:
          "目标派息只是上限；留存不自动带来高回报，母现金不同于集团现金。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "真实样本部分验证（见证据）",
          economic: "条件研究／未批准",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "F2",
        deliveryReview: {
          inputDetails: [
            "确切候选及descriptor、估值基准日、合格报价，期间股本/分红/重大事件/财务更新的原件与复核绑定。",
            "显式价格政策和阈值理由；有条件估值数值不等于已有可用数值价格规则。",
          ],
          steps: [
            {
              title: "绑定同一候选",
              description:
                "load_pending_candidate_alignment拒绝候选或descriptor不匹配，来源消费和准入结论分开，不能拿另一版本复核代用。",
            },
            {
              title: "独立检查五个维度",
              description:
                "报价、资本结构、期间分配、重大事件和财务更新逐项评价；原件已消费不等于事件重大性批准。",
            },
            {
              title: "保留当前不兼容",
              description:
                "报价过期、跨日行动链未闭合或财报更新未复核时返回具体阻断；不会通过改日期或默认不变凑齐当前资格。",
            },
            {
              title: "生成未批准价格草案",
              description:
                "project_pending_candidate_price_proposal消费对齐和既有价格政策；无数值规则/理由则不生成当前条件价，有日期参考线也不是BUY。",
            },
          ],
          outputDetails: [
            "同候选五维状态、已消费来源/未复核原因、日期参考线或明确拒绝；action=no_order。",
            "局部真实证据是600519/600887的阻断及000568未采用主区间的条件草案，不是全部当前门槛联合成功。",
          ],
          acceptanceChecks: [
            "检查项：未知不映射无影响，原件声明不代独立重大性审核，旧报价不冒当前价。",
            "检查项：candidate/quote/action错绑定拒绝；未选规则不给默认安全边际。",
            "未完成：同一经济采用候选的全部当前对齐联合正例；本页不授批准或个人数量。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/pending_candidate_alignment.py",
              symbol: "load_pending_candidate_alignment",
              description: "五维来源核验和精确候选绑定。",
            },
            {
              path: "src/value_investment_agent/application/research/pending_candidate_price_proposal.py",
              symbol: "project_pending_candidate_price_proposal",
              description: "未注册条件价格草案。",
            },
            {
              path: "src/value_investment_agent/domain/decision/value_price_policy.py",
              description: "既有价格政策合同，不由Web新增公式。",
            },
            {
              path: "web/src/components/CandidatePriceDraft.tsx",
              description: "当前资格、来源明细及阻断可读展示。",
            },
            {
              path: "docs/current/value-mainline-p0-20261101/d2-f-audit.md",
              description: "真实拒绝而非联合成功的审计记录。",
            },
          ],
          status: "PARTIAL",
          what: "将条件价值连接到当前价格判断。",
          why: "历史估值不能直接当作今天的买入依据。",
          how: "核对股本、期间分配、事件、模型有效性和合格报价。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "对齐、拒绝和精确缺口展示已接通。",
          gap: "同一候选的全部当前对齐条件尚缺联合成功样本。",
          acceptance: "完整对齐正例能产未批准条件价；不齐时准确拒绝。",
          evidence: ["docs/current/value-mainline-p0-20261101/d2-f-audit.md"],
          runHref: "/strategy/value",
        },
        title: "F2 · 价格对齐与条件决策",
        question: "历史估值今天还能与价格比较吗？",
        dependencies: ["E1", "E2", "F1", "S1", "S4"],
        input: "研究版本、报价、股本、分配、事件、财务更新",
        output: "五维资格、条件价格或实质拒绝理由",
        modules: [
          "src/value_investment_agent/application/research/pending_candidate_alignment.py",
          "src/value_investment_agent/application/research/pending_candidate_price_proposal.py",
          "src/value_investment_agent/domain/decision/value_price_policy.py",
        ],
        engineeringStatus: "部分接通",
        evidenceStatus: "真实样本部分验证",
        shortStatus: "跨日股本、后续分配及材料性未闭合；旧报价会失效",
        implementation: "600519已有2026-06-30基准未批准参考线；非当前买价",
        milestone: "部分接通；不代表正式研究准入或实盘资格。",
        existingEvidence: "600519已有2026-06-30基准未批准参考线；非当前买价",
        evidenceSource:
          "d01923cd；docs/current/web-first-full-product-execution-ledger.md；.tmp/value-followup-acceptance/real-business-receipt.json（本机留存，不公开私人文件）",
        evidence: "跨日股本、后续分配及材料性未闭合；旧报价会失效",
        nextStep: "补跨日有效公司行动链及经济影响复核",
        ruleWhy: "价格桥不改变内在价值；UNKNOWN不是NO_TRADE，参考线不是BUY。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "真实样本部分验证（见证据）",
          economic: "条件研究／未批准",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "G1",
        deliveryReview: {
          inputDetails: [
            "公开公司API的来源绑定画像、经营草案、首输入、条件现金/估值及当前价格资格。",
            "实际任务返回的结果、错误与source refs；当前页面读取与点击执行分开。",
          ],
          steps: [
            {
              title: "沿现有公司入口读取",
              description:
                "DecisionDetail复用公开研究API，按symbol展示画像、假设、首编和研究分析，不建立第二公司页面或前端估值公式。",
            },
            {
              title: "各自呈现来源与缺口",
              description:
                "公开panel保留UNKNOWN、拒绝、报告期间和模型年区别，来源页/链接可查，技术Hash及年度长表折叠。",
            },
            {
              title: "显式打开新研究功能",
              description:
                "LiveOperatingResearchPanel由用户打开后读上下文/模型状态，执行需明确操作；不能把已有保存响应说成新模型研究。",
            },
            {
              title: "展示本次实际任务输出",
              description:
                "扫描/重放显示绑定候选正文，重算/模拟显示共享内核结果，REVIEW_NOTE显示注释边界；失败不得残留旧成功画面冒充本次。",
            },
            {
              title: "把交付与运行资格分开",
              description:
                "组件有内容不代表全链已验收；研究、当前可比、代码运行身份及正式发布分别呈现，公开研究不要求私人账户解锁。",
            },
          ],
          outputDetails: [
            "可读公司研究、三情景摘要、年度明细、原件引用、当前对齐缺口及实际任务结果。",
            "局部真实浏览器/接口回执存在；11模块完整交互矩阵和全量用户确认仍未证明。",
          ],
          acceptanceChecks: [
            "检查项：页面金额/状态来自API，未知不补0、无前端重算金融；加载失败不伪装空股票池。",
            "检查项：手机/桌面及刷新后真实状态需分别验收；本次内容更新不代表重新验证线上版本。",
          ],
          implementationRefs: [
            {
              path: "web/src/pages/DecisionDetail/index.tsx",
              description: "现有公司页及公开研究panel挂载。",
            },
            {
              path: "web/src/components/LiveOperatingResearchPanel.tsx",
              description: "显式研究操作和原生结果。",
            },
            {
              path: "src/value_investment_agent/application/product/company_research.py",
              symbol: "run_company_research_for_symbol",
              description: "已有公司研究应用入口。",
            },
            {
              path: "web/src/components/SseMainScreeningPanel.tsx",
              symbol: "SseMainScreeningPanel",
              description: "A+B公开初筛与财务诊断消费者。",
            },
            {
              path: "docs/current/value-transparent-workbench-v1.md",
              description: "真实操作、取消与未验收事项记录。",
            },
          ],
          status: "PARTIAL",
          what: "在网页读懂并操作研究流程。",
          why: "用户不应依靠源码或终端理解结果。",
          how: "现有工作台调用真实API，展示研究、证据及任务回执。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "真实页面已执行重算、扫描、取消重试与来源下载。",
          gap: "11模块独立操作及完整用户交互矩阵尚未全部验收。",
          acceptance: "真实浏览器逐项完成操作、回执、异常和刷新恢复验收。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/g1-web-audit.md",
            "docs/current/value-transparent-workbench-v1.md",
          ],
          runHref: "/strategy/value",
        },
        title: "G1 · 公司研究 API 与页面",
        question: "用户能否直接读懂真实结论？",
        dependencies: ["E1", "E2", "F2"],
        input: "来源绑定研究、候选、价格资格",
        output: "公开公司详情、依据、反证与条件研究",
        modules: [
          "src/value_investment_agent/application/product/company_research.py",
          "web/src/pages/DecisionDetail/index.tsx",
        ],
        engineeringStatus: "有限贯通",
        evidenceStatus: "真实样本部分验证",
        shortStatus: "页面有内容不等于经济批准；部分当前价格仍不可比",
        implementation: "现有API和8001已消费两公司研究、现金诊断及事件草案",
        milestone: "有限贯通；不代表正式研究准入或实盘资格。",
        existingEvidence: "现有API和8001已消费两公司研究、现金诊断及事件草案",
        evidenceSource:
          "d01923cd；docs/current/web-first-full-product-execution-ledger.md；.tmp/value-followup-acceptance/real-business-receipt.json（本机留存，不公开私人文件）",
        evidence: "页面有内容不等于经济批准；部分当前价格仍不可比",
        nextStep: "同版本核验真实API、构建和公司页面",
        ruleWhy: "公开研究不依赖私人账户解锁；私有数量保持独立。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "真实样本部分验证（见证据）",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "G2",
        deliveryReview: {
          inputDetails: [
            "已注册来源/spec及prepare返回的可执行payload；六类operation由服务定义，缺基线明确disabled。",
            "显式用户假设白名单或研究意见；actor来自路由授权上下文，不能payload自报批准。",
          ],
          steps: [
            {
              title: "准备实际输入",
              description:
                "TransparentTaskService.prepare核验来源/研究基线，返回每项enabled/reason/payload；FRESH默认未授权网络，不给用户手填SHA/path。",
            },
            {
              title: "冻结并版本化任务",
              description:
                "create复用父类锁、head和状态，冻结输入及所需实现源码；读历史任务发现输入/实现变更时current_validation不可评价，原成功历史和manifest保持。",
            },
            {
              title: "分发真实业务",
              description:
                "_dispatch分别调用A核证、B保留重放或新公开run_once、主重验和共享内核假设模拟；离线重放不叫今日scan，不调用旧saved响应冒充新业务。",
            },
            {
              title: "保留运行与取消轨迹",
              description:
                "run/resume/cancel依据持久状态；重启未完任务需明确恢复，未知进度为null。取消终止自有worker，retry创建新ID并保留失败parent。",
            },
            {
              title: "注释不变批准",
              description:
                "REVIEW_NOTE将意见与真实target绑定保存为同task artifact，scope为COMMENT_NOT_G3_APPROVAL，approval_changed=false；任务不发布正式current。",
            },
          ],
          outputDetails: [
            "统一视图状态、native_status、attempt/run身份、真实起止与步骤、输入/输出manifest和错误；不伪造进度百分比。",
            "已支持六类透明操作；D1走既有Live服务，其余模块保持原生只读入口，不生成假的通用run按钮。",
          ],
          acceptanceChecks: [
            "检查项：输入/实现变化不能洗旧任务；取消后迟到输出不能覆写CANCELLED。",
            "检查项：模拟须绑定基线和白名单且真实调用shared core；意见不是G3或投资判断。",
            "局部真实运行及取消重试有台账；完整操作矩阵仍PARTIAL，未知历史时间不得补造。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/transparent_task_v1.py",
              symbol: "TransparentTaskService",
              description: "父服务子类：prepare、持久任务及真实状态视图。",
            },
            {
              path: "src/value_investment_agent/application/research/transparent_task_v1.py",
              symbol: "_dispatch",
              description: "六种operation调用原生服务。",
            },
            {
              path: "src/value_investment_agent/application/research/transparent_task_v1.py",
              symbol: "_simulate",
              description: "显式白名单假设经共享模型计算。",
            },
            {
              path: "docs/current/value-transparent-workbench-v1.md",
              description: "本机任务结果、取消及验收边界。",
            },
          ],
          status: "PARTIAL",
          what: "保存研究任务的执行与产物历史。",
          why: "任务中断或重试不能丢失过程和版本。",
          how: "复用持久任务、不可变清单和阶段事件，关联输入输出。",
          scope: "已列明的真实能力；尚不标模块整体完成。",
          done: "版本链、历史、取消、新任务重试及终态恢复已有。",
          gap: "全部模块统一独立运行与持久产物闭环尚未完整证明。",
          acceptance: "任务恢复、幂等、取消、重试和产物版本均可独立重放。",
          evidence: [
            "docs/current/value-mainline-p0-20261101/d1-g2-audit.md",
            "docs/current/value-transparent-workbench-v1.md",
          ],
          runHref: "/strategy/value",
        },
        title: "G2 · 研究任务操作",
        question: "能否开始、取消、恢复并解释失败？",
        dependencies: ["D1"],
        input: "显式用户操作、任务版本和预算",
        output: "持久任务进度、取消与恢复结果",
        modules: [
          "src/value_investment_agent/presentation/web_api/agent_research_routes.py",
          "src/value_investment_agent/application/research/agent_review/status.py",
        ],
        engineeringStatus: "部分实现",
        evidenceStatus: "源码定位／业务待验",
        shortStatus:
          "已有保留响应与真实经营研究任务操作；本目录未接任务运行reader，不代表缺少既有消费者",
        implementation:
          "既有任务面板已接开始、历史读取、手动刷新、取消与恢复；保留响应和真实模型执行分开",
        milestone: "部分实现；不代表正式研究准入或实盘资格。",
        existingEvidence:
          "ResearchTaskPanel与LiveOperatingResearchPanel已有显式任务操作接线；本轮仅源码复核，不新增运行验收结论",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence:
          "已有保留响应与真实经营研究任务操作；本目录未接任务运行reader，不代表缺少既有消费者",
        nextStep: "与D1共用持久任务状态，不另建任务平台",
        ruleWhy: "页面GET只读；真正恢复要保留步骤和已验证产物。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "端到端尚未证明",
          realData: "本轮未验真实业务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "S1",
        deliveryReview: {
          inputDetails: [
            "经认证的账户快照、IPS版本、持仓批次、既有资金承诺及研究/风险请求；本轮未读取这些私人数据。",
          ],
          steps: [
            {
              title: "校验风险输入",
              description:
                "review_dual_sleeve_risk验证金额、时间、精确字段、账户和策略范围；缺输入返回blockers，不能借公开研究成功补资格。",
            },
            {
              title: "合并既有占用",
              description:
                "PrivateCommittedRiskService从已确认记录构造风险上下文，核对账户、IPS和lots，避免单笔建议忽略已有承诺。",
            },
            {
              title: "给复核边界而非订单",
              description:
                "既有风险合同计算资金/集中度等限制；输出原因和可复核范围，真实个人政策与当前资金资格仍须独立确认。",
            },
          ],
          outputDetails: [
            "风险限制、阻断原因和承诺投影；源码存在，不代表本轮真实账户验收。",
          ],
          acceptanceChecks: [
            "待独立验收：真实账户时点、IPS/批次绑定、重复占用和当前可用资金。",
            "保持未验证边界：本次只读源码，不访问私人账本，不因主链通过提升状态。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/domain/portfolio/dual_sleeve_risk.py",
              symbol: "review_dual_sleeve_risk",
              description: "双仓共享风险校验与限制。",
            },
            {
              path: "src/value_investment_agent/application/portfolio/private_committed_risk.py",
              symbol: "PrivateCommittedRiskService",
              description: "已确认资金承诺的账户/IPS绑定服务。",
            },
          ],
          status: "PARTIAL",
          what: "约束现金、仓位和组合风险。",
          why: "单只股票便宜，不代表账户有能力继续买。",
          how: "读取已确认账户与IPS，计算预算和集中度限制。",
          scope: "共享支持；不随主模块接入自动标完成。",
          done: "已有组合风控与私人风险读取实现。",
          gap: "缺本轮独立交付及真实账户对齐验收。",
          acceptance:
            "独立真实输入、异常处理、运行回执和现有消费者逐项通过后再标完成。",
          evidence: ["docs/current/value-mainline-p0-20261101/g1-web-audit.md"],
          runHref: "/portfolio",
        },
        title: "S1 · 共享现金与组合风险",
        question: "即使便宜，账户能承受多少？",
        dependencies: ["S2"],
        input: "已确认账户、IPS、现金、持仓与策略预算",
        output: "风险原因、允许复核的数量上限",
        modules: [
          "src/value_investment_agent/domain/portfolio/dual_sleeve_risk.py",
          "src/value_investment_agent/application/portfolio/private_committed_risk.py",
        ],
        engineeringStatus: "部分接通",
        evidenceStatus: "源码定位／业务待验",
        shortStatus: "真实用户政策、当前账户资格未由本次审查验收",
        implementation: "双策略预算及组合风险合同存在",
        milestone: "部分接通；不代表正式研究准入或实盘资格。",
        existingEvidence: "双策略预算及组合风险合同存在",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence: "真实用户政策、当前账户资格未由本次审查验收",
        nextStep: "复用已有风险链验证集中度与现金占用",
        ruleWhy: "安全边际不机械转换仓位；两策略不得重复使用同一现金。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "本轮未验真实业务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "S2",
        deliveryReview: {
          inputDetails: [
            "用户确认的成交、账户基线、手续费/税费、日期、幂等键和预期revision；模拟与真实账户上下文分开。",
          ],
          steps: [
            {
              title: "准备及确认成交",
              description:
                "PrivatePortfolioService校验证券、数量、日期和金额，按准备/确认流程处理；研究候选不是成交事实。",
            },
            {
              title: "追加记录并重放",
              description:
                "PrivateJournal校验记录链，服务用revision和幂等键防止重复记账或并发覆盖；重放计算持仓及可卖量。",
            },
            {
              title: "呈现对账状态",
              description:
                "reconciliation_state区分内部重放和外部对账证据；凭证引用及人工确认不能冒充自动券商流水完整核对。",
            },
          ],
          outputDetails: [
            "可追溯成交记录、持仓/成本/可卖量及对账缺口；本轮未写任何实盘记录。",
          ],
          acceptanceChecks: [
            "待独立验收：真实成交准备/确认/取消、幂等冲突、更正及外部对账全链。",
            "本轮只核实现位置，不声明本人持仓已正确或交易已发生。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/portfolio/private_portfolio_service.py",
              symbol: "PrivatePortfolioService",
              description: "成交校验与持仓重放服务。",
            },
            {
              path: "src/value_investment_agent/application/portfolio/private_portfolio_service.py",
              symbol: "PrivateJournal",
              description: "追加事件链和并发锁。",
            },
            {
              path: "src/value_investment_agent/application/portfolio/private_portfolio_service.py",
              symbol: "reconciliation_state",
              description: "对账状态表达。",
            },
          ],
          status: "PARTIAL",
          what: "记录人工成交并核对持仓。",
          why: "持仓建议必须基于真实、可对账的资产。",
          how: "校验并确认成交，按事件账本重放成本和持仓。",
          scope: "共享支持；不随主模块接入自动标完成。",
          done: "已有成交校验、确认与账本服务。",
          gap: "真实成交完整入账与对账尚未完成验收；本轮不写实盘。",
          acceptance:
            "独立真实输入、异常处理、运行回执和现有消费者逐项通过后再标完成。",
          evidence: ["docs/current/value-mainline-p0-20261101/g1-web-audit.md"],
          runHref: "/portfolio",
        },
        title: "S2 · 人工成交与持仓对账",
        question: "实际买卖后，账是否准确？",
        dependencies: [],
        input: "本人确认成交、资金事件、可核对持仓",
        output: "可重放持仓、成本、可卖量与差异",
        modules: [
          "src/value_investment_agent/application/portfolio/private_portfolio_service.py",
        ],
        engineeringStatus: "部分接通",
        evidenceStatus: "源码定位／业务待验",
        shortStatus: "内部重放不等于券商对账；本轮未访问私人账户",
        implementation:
          "已接成交准备/确认/取消与幂等；外部对账仍是凭证引用加人工确认",
        milestone: "部分接通；不代表正式研究准入或实盘资格。",
        existingEvidence:
          "已接成交准备/确认/取消与幂等；外部对账仍是凭证引用加人工确认",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence: "内部重放不等于券商对账；本轮未访问私人账户",
        nextStep: "单独核验更正、公司行动及外部对账",
        ruleWhy: "模拟记录不得变本人事实；研究信号不能生成真实成交。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "本轮未验真实业务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "S3",
        deliveryReview: {
          inputDetails: [
            "明确账户/股份税处理、取得日、股权登记日、卖出结算日和应税基数；应税基数不能直接等同现金股息。",
            "批次及有序账户净值路径；现有收益函数限定无外部资金流。",
          ],
          steps: [
            {
              title: "按受支持税制计算",
              description:
                "calculate_dividend_tax要求有限非负Decimal及明确日期/账户类型；不支持账户、边界日期和月末约定拒绝，不自行猜扣税日或舍入。",
            },
            {
              title: "保持批次与现金口径",
              description:
                "已有FIFO批次组件与税计算分别存在；预测分红、应收、实际到账和补税不可合并成同一现金事件。",
            },
            {
              title: "限定账户路径收益",
              description:
                "account_path_metrics校验日期顺序和正净值，算收盘标记收益/回撤/资金占用；不支持外部流量归因，不称可执行净业绩。",
            },
          ],
          outputDetails: [
            "税额/追加税计算及限定账户路径指标；不是实际到账证明，也不是可再投资现金的完整闭环。",
          ],
          acceptanceChecks: [
            "未完成：税批次/收益组件接入私人账户服务及真实到账、补税、外部资金流核对。",
            "本轮只核计算源码，不读取个人流水或验证税务适用事实。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/dividend_tax.py",
              symbol: "calculate_dividend_tax",
              description: "受限个人股息税计算，非结算账本。",
            },
            {
              path: "src/value_investment_agent/dividend_tax_lots.py",
              description: "已有FIFO税批次组件。",
            },
            {
              path: "src/value_investment_agent/account_path_metrics.py",
              symbol: "account_path_metrics",
              description: "无外部流量的标记账户收益及回撤。",
            },
          ],
          status: "PARTIAL",
          what: "跟踪实际股息及税后现金流。",
          why: "公布分红与实际可用现金并不是一回事。",
          how: "结合持仓、税费和现金事件计算可再投资金额。",
          scope: "共享支持；不随主模块接入自动标完成。",
          done: "已有股息税费及账户路径计算。",
          gap: "税后现金与逐笔实际到账的完整业务链待验收。",
          acceptance:
            "独立真实输入、异常处理、运行回执和现有消费者逐项通过后再标完成。",
          evidence: ["docs/current/value-mainline-p0-20261101/g1-web-audit.md"],
          runHref: "/portfolio",
        },
        title: "S3 · 分红现金与收益",
        question: "实际收到多少，税后能否持续？",
        dependencies: ["S2", "F1"],
        input: "实际分红、批次、外部现金流与适用税规则",
        output: "税后现金、可解释收益与预测区分",
        modules: [
          "src/value_investment_agent/dividend_tax.py",
          "src/value_investment_agent/account_path_metrics.py",
        ],
        engineeringStatus: "部分实现",
        evidenceStatus: "源码定位／业务待验",
        shortStatus:
          "确定缺口：税批次与收益函数尚未被私人账户服务消费；真实到账、补税和外部资金流未闭环",
        implementation:
          "分红税、FIFO批次及无外部资金流收益组件存在；不是实际到账链",
        milestone: "部分实现；不代表正式研究准入或实盘资格。",
        existingEvidence:
          "分红税、FIFO批次及无外部资金流收益组件存在；不是实际到账链",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence:
          "确定缺口：税批次与收益函数尚未被私人账户服务消费；真实到账、补税和外部资金流未闭环",
        nextStep: "核对到账、批次税费、外部流量，避免重复计息",
        ruleWhy: "预测股息不是到账；除息不是免费收益，税规则需按日期核验。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "端到端尚未证明",
          realData: "本轮未验真实业务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "S4",
        deliveryReview: {
          inputDetails: [
            "精确候选/descriptor、已核事件原文及实际经营路径；私人持仓支线另需原入场逻辑、当前计划与风险。",
          ],
          steps: [
            {
              title: "定位实际被消费假设",
              description:
                "candidate_event_impact仅消费事件与当前候选/descriptor一致的记录，把affected_model_fields定位到情景、模型年和输入路径。",
            },
            {
              title: "区分事实与待核影响",
              description:
                "零售与销售合同价格变化分别计算，不直接推净利；资产划转决议不叫完成，会计政策声明不叫独立重大性批准。缺销量/渠道/税基等列下一核验事项。",
            },
            {
              title: "保持持有逻辑连续性",
              description:
                "held_continuity已有原入场依据、当前计划及风险适配；事件草案只提出重开复核，不改模型、不自动卖出或批准持有。",
            },
          ],
          outputDetails: [
            "未批准事件研究草案、受影响输入、反证/下一核验事项；私人持有连续性结论需另有真实输入。",
          ],
          acceptanceChecks: [
            "局部真实：600519事件到模型字段定位有历史证据；不能据此证明全部当前事件完成。",
            "未完成：真实原始买入逻辑到后续事件/私人风险的完整连续验收。",
          ],
          implementationRefs: [
            {
              path: "src/value_investment_agent/application/research/candidate_event_impact.py",
              description: "精确候选绑定的事件到实际模型字段草案。",
            },
            {
              path: "src/value_investment_agent/application/portfolio/held_continuity.py",
              symbol: "evaluate_owned_held_advisory",
              description: "原入场逻辑与当前持有建议适配。",
            },
            {
              path: "src/value_investment_agent/application/portfolio/held_continuity.py",
              symbol: "project_held_continuity",
              description: "持仓连续性公开投影逻辑；本轮不读取账户。",
            },
          ],
          status: "PARTIAL",
          what: "检查新事件是否改变原投资逻辑。",
          why: "买入后需要知道原来的理由是否仍成立。",
          how: "对比原研究与新事件，定位受影响假设和复核事项。",
          scope: "共享支持；不随主模块接入自动标完成。",
          done: "已有事件影响和持仓逻辑连续性实现。",
          gap: "真实原始买入逻辑到后续事件的完整连续验收未齐。",
          acceptance:
            "独立真实输入、异常处理、运行回执和现有消费者逐项通过后再标完成。",
          evidence: ["docs/current/value-mainline-p0-20261101/g1-web-audit.md"],
          runHref: "/strategy/value",
        },
        title: "S4 · 事件与持有逻辑跟踪",
        question: "什么变化需要重看原来的判断？",
        dependencies: ["A", "S2"],
        input: "公告、新事实、原Thesis与研究版本",
        output: "影响定位、重开研究、持有或退出复核理由",
        modules: [
          "src/value_investment_agent/application/research/candidate_event_impact.py",
          "src/value_investment_agent/application/portfolio/held_continuity.py",
        ],
        engineeringStatus: "部分接通",
        evidenceStatus: "真实样本部分验证",
        shortStatus:
          "事件影响定位不是量化或正式批准；持仓连续性已有适配，真实输入及成功路径未核验",
        implementation:
          "600519官方事件已定位模型年度字段；持仓跟踪已接原入场依据、当前计划与风险",
        milestone: "部分接通；不代表正式研究准入或实盘资格。",
        existingEvidence:
          "600519官方事件已定位模型年度字段；持仓跟踪已接原入场依据、当前计划与风险",
        evidenceSource:
          "d01923cd；docs/current/web-first-full-product-execution-ledger.md；.tmp/value-followup-acceptance/real-business-receipt.json（本机留存，不公开私人文件）",
        evidence:
          "事件影响定位不是量化或正式批准；持仓连续性已有适配，真实输入及成功路径未核验",
        nextStep: "将关键变化交给E1重算，保留原始买入逻辑",
        ruleWhy: "标题或公告抓取完成不能证明无影响；下跌不自动加仓。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "已有消费者／部分链路",
          realData: "真实样本部分验证（见证据）",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "W1",
        deliveryReview: {
          inputDetails: [
            "同一strategyArchitecture目录、Root模块机器目录、台账及精确留存验收路径；不是自动运行结果订阅。",
          ],
          steps: [
            {
              title: "读取统一目录",
              description:
                "catalog.value提供11主模块和5共享支持；nativeContract从value-mainline-modules-v1.json投影方法能力、输入输出与入口，不复制任务平台。",
            },
            {
              title: "分层说明交付",
              description:
                "deliveryReview保留简明概述，细节按输入、处理、输出、检查项和源码引用组织；静态人工复核、局部真实验收及未完成分别说明。",
            },
            {
              title: "跳转实际功能并保留边界",
              description:
                "现有架构页选择模块和跳转研究入口；代码运行身份由系统页独立读取，本目录不证明实时健康、部署成功或用户批准。",
            },
          ],
          outputDetails: [
            "可供renderer消费的16模块结构化交付详情、现有能力/证据定位和缺口；热点目录保持独立。",
          ],
          acceptanceChecks: [
            "本次检查：16模块字段齐全、主模块4–6步骤、共享2–4步骤、引用文件/符号存在。",
            "renderer、交互和部署验收由Root另行执行；本配置更新不宣称所有模块完成。",
          ],
          implementationRefs: [
            {
              path: "web/src/config/strategyArchitecture.v1.ts",
              symbol: "catalog",
              description: "单一展示目录和人工交付详情。",
            },
            {
              path: "web/src/pages/StrategyArchitecture/index.tsx",
              symbol: "DeliverySummary",
              description: "现有交付概述renderer；详细字段由Root接线。",
            },
            {
              path: "config/value-mainline-modules-v1.json",
              description: "Root统一模块能力目录。",
            },
            {
              path: "docs/current/web-first-full-product-execution-ledger.md",
              description: "历史验收与未完成边界台账。",
            },
          ],
          status: "PARTIAL",
          what: "展示模块实现、证据与缺口。",
          why: "让用户直接判断开发方向与交付质量。",
          how: "读取同一展示目录，分开呈现交付复核和运行版本。",
          scope: "共享支持；不随主模块接入自动标完成。",
          done: "已有流程图、模块导航及本轮简明交付总览。",
          gap: "当前是人工复核快照；不代表全部模块实时健康。",
          acceptance:
            "独立真实输入、异常处理、运行回执和现有消费者逐项通过后再标完成。",
          evidence: ["docs/current/value-mainline-p0-20261101/g1-web-audit.md"],
          runHref: "/project",
        },
        title: "W1 · 模块进度与证据工作台",
        question: "哪里能用，哪里还缺什么？",
        dependencies: ["G1", "G2", "S1", "S2", "S3", "S4"],
        input: "同一模块目录、源码及验收证据",
        output: "目标流程、实现状态、缺口与公司链接",
        modules: [
          "web/src/config/strategyArchitecture.v1.ts",
          "web/src/pages/StrategyArchitecture/index.tsx",
        ],
        engineeringStatus: "本轮更新",
        evidenceStatus: "源码定位／业务待验",
        shortStatus: "静态复核不等于实时监控，用户确认与正式批准独立",
        implementation: "以当前工作树替换旧价值流程，保持热点独立",
        milestone: "本轮更新；不代表正式研究准入或实盘资格。",
        existingEvidence: "以当前工作树替换旧价值流程，保持热点独立",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence: "静态复核不等于实时监控，用户确认与正式批准独立",
        nextStep: "逐模块随真实交付更新证据，不用百分比掩盖缺口",
        ruleWhy: "单一目录维护目标与进度；未合入分支不算当前部署。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer: "端到端尚未证明",
          realData: "本轮未验真实业务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
    ],
  },
  hotspot: {
    title: "热点策略架构",
    summary:
      "市场观察与完成K线形成条件计划，再独立检验有效性和风险。热点准入不以价值估值或G3为输入。验证与Shadow是准入证据支线，不是每个候选都会重跑的步骤。",
    stages: [
      {
        id: "hotspot_pool",
        title: "市场候选观察",
        question: "哪些行业和证券值得观察？",
        input: "有交易日期的市场数据、行业分类和成交额",
        output: "行业相对强弱与流动性排序、有限跨行业候选池",
        modules: [
          "src/value_investment_agent/application/hotspot/daily_selection.py",
          "src/value_investment_agent/domain/hotspot/daily_selection.py",
        ],
        implementation: "有界采集、可回放排序与跨行业轮选",
        milestone: "描述性候选模块存在；历史候选池PIT仍需证明。",
        evidence: "同时期留存的候选范围、行业分类、来源及可用时间。",
        boundary: "今天下载历史数据不能证明当时已知；排序不等于准入。",
        ruleWhy: "今天下载历史数据不能证明当时已知；排序不等于准入。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: [],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "实现已定位 · 应用证据待核验",
      },
      {
        id: "hotspot_structure",
        title: "结构与条件价格",
        question: "完成K线支持什么条件？",
        input: "有序且已完成的日线、60分钟或15分钟OHLCV",
        output: "相对前五根完成K线的触发价、失效参考及量能条件",
        modules: [
          "src/value_investment_agent/domain/hotspot/price_action_plan.py",
        ],
        implementation: "确定性价格规则与OHLC校验",
        milestone: "条件计算存在；触发不能替代策略验证。",
        evidence: "完整K线截止时点、可比价格口径、公司行动和规则版本。",
        boundary: "失效价是结构参考，不是止损单；不臆造目标价。",
        ruleWhy: "失效价是结构参考，不是止损单；不臆造目标价。",
        existingEvidence:
          "基线台账：300059 ACTUAL留存样本，34次历史触发、32次完整五交易日跟踪、2次右删失；不是34笔成交。",
        nextStep:
          "从交易复盘查看现有样本；补历史可交易性、涨跌停、流动性、成本与公司行动证据。",
        evidenceSource:
          "基线台账记录：.tmp/h2-final/300059-api-receipt.json（本页未加载原始收据）",
        dependencies: ["hotspot_pool"],
        engineeringStatus: "已实现",
        evidenceStatus: "历史观察",
        shortStatus: "300059 · 34触发 / 32完整 / 2右删失",
      },
      {
        id: "hotspot_validation",
        title: "PIT与样本外验证",
        question: "规则在未触碰样本和成本下有效吗？",
        input: "预先声明协议、当时可知数据、冻结规则与成本",
        output: "分块对照、成本压力及不确定性诊断草案",
        modules: [
          "src/value_investment_agent/application/hotspot/quantitative_validation.py",
        ],
        implementation: "定量协议草案及计算，不是已批准的策略政策",
        milestone: "基线台账：strategy_validation=NOT_PROVEN；PIT/OOS未建立。",
        evidence:
          "同时期候选、原始PIT留存、未触碰窗口、可交易性、成本和预声明政策。",
        boundary: "回放成功或测试通过不证明超额收益，不能追认样本外。",
        ruleWhy: "回放成功或测试通过不证明超额收益，不能追认样本外。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: ["hotspot_pool"],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "PIT/OOS未建立 · NOT_PROVEN",
      },
      {
        id: "hotspot_shadow",
        title: "真实时间观察",
        question: "冻结条件在后续真实时段表现如何？",
        input: "时间一致的案例、计划与冻结参考K线",
        output: "后续完成时段的条件路径与Shadow观察基线",
        modules: [
          "src/value_investment_agent/domain/hotspot/shadow_observation.py",
        ],
        implementation: "冻结条件与真实完成时段观察合同",
        milestone: "基线台账：真实Shadow未建立；本页不累计时段。",
        evidence: "事先冻结时间、后续真实交易时段、完整观察链与缺失说明。",
        boundary: "重跑或历史回放不能增加真实观察天数。",
        ruleWhy: "重跑或历史回放不能增加真实观察天数。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: ["hotspot_structure"],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "真实Shadow未建立",
      },
      {
        id: "hotspot_admission",
        title: "独立准入与风险复核",
        question: "十类门槛及独立授权都有有效证据吗？",
        input:
          "身份、证券/事件风险、数据、完成K线、趋势、结构、风险收益、策略验证、执行约束",
        output: "仅观察或可进入风险复核；保留缺失、过期与失败原因",
        modules: [
          "src/value_investment_agent/domain/hotspot/independent_admission.py",
        ],
        implementation: "十门证据与独立授权的时间区间及哈希检查",
        milestone: "策略未证明；正式资格与个人风险不能从工程进展推定。",
        evidence: "逐门有效证据、独立策略授权；个人组合限制与执行许可另审。",
        boundary:
          "不依赖价值G3；风险复核资格不是正式交易资格。action=no_order。",
        ruleWhy:
          "不依赖价值G3；风险复核资格不是正式交易资格。action=no_order。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: [
          "hotspot_structure",
          "hotspot_validation",
          "hotspot_shadow",
        ],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "实现已定位 · 应用证据待核验",
      },
      {
        id: "shared_rule_approval",
        title: "用户策略与规则门",
        question: "策略、规则版本和适用范围是否获相应批准？",
        input: "研究结果、规则版本、独立授权及适用范围",
        output: "待相应人工批准；拒绝或缺失继续停止",
        modules: [
          "src/value_investment_agent/domain/hotspot/independent_admission.py",
        ],
        implementation: "映射既有研究/策略授权边界；本页没有批准功能。",
        milestone: "未闭合：未来策略/规则变更仍需相应人工批准。",
        evidence: "版本绑定的批准依据、权限、有效期和变更后重审记录。",
        existingEvidence: "只复核已有授权合同；不宣称有可用批准收据。",
        evidenceSource: "基线源码复核",
        boundary: "浏览或点击节点不构成批准；不得由工程测试自动代签。",
        ruleWhy: "改变规则会改变结论，旧批准不能自动覆盖新策略。",
        nextStep: "向用户呈现规则及证据差异，在既有流程取得相应批准。",
        dependencies: ["hotspot_admission"],
        engineeringStatus: "部分接通",
        evidenceStatus: "待人工审核",
        shortStatus: "共享门槛未闭合",
      },
      {
        id: "shared_portfolio_risk",
        title: "共享组合风险 · 未闭合",
        question: "两个策略占用的资金与风险是否冲突？",
        input: "本策略有效准入、既有组合/承诺、账户时点和明确风险政策",
        output: "共享资金与分仓风险复核；缺失则无法评价",
        modules: [
          "src/value_investment_agent/domain/portfolio/dual_sleeve_risk.py",
          "src/value_investment_agent/application/portfolio/private_committed_risk.py",
        ],
        implementation: "已复核双仓风险合同和既有承诺投影；不新增算法。",
        milestone: "未闭合：个人输入与风险批准未在目录核验。",
        evidence:
          "有效账户时点、承诺、风险参数及真实个人授权（在既有私人流程处理）。",
        existingEvidence: "存在双仓风险及承诺合同；不证明当前组合风险通过。",
        evidenceSource: "基线源码复核",
        boundary:
          "热点可独立进入本节点，不要求价值G3通过；本页不读取私人数据。",
        ruleWhy: "两个策略共用真实资金，单策略条件成立不证明组合可承受。",
        nextStep: "在既有组合页核验当前承诺与个人风险边界，缺失保持阻断。",
        dependencies: ["shared_rule_approval"],
        engineeringStatus: "部分接通",
        evidenceStatus: "待验证",
        shortStatus: "共享门槛未闭合",
      },
      {
        id: "shared_manual_decision",
        title: "人工复核终点 · 未闭合",
        question: "人是否理解依据、反证和失效条件？",
        input: "本策略证据及有效组合风险复核",
        output: "人工审阅或不操作；永久action=no_order",
        modules: [
          "src/value_investment_agent/application/portfolio/decision_logic.py",
        ],
        implementation:
          "已复核现有决策解释投影，仅展示来源绑定内容，不新增权力。",
        milestone: "未闭合：本页不宣称人工验收或正式交易资格。",
        evidence: "当前版本的理由、反证、失效条件及相应人工决定。",
        existingEvidence: "现有解释投影存在；无本页作出的人工决定。",
        evidenceSource: "基线源码复核",
        boundary: "通过→人工复核；人工决定与自动下单严格分开。",
        ruleWhy: "研究与风险检查只能支持决定，不能替人承担决策。",
        nextStep: "从今日决策选择真实条目进入详情复核，结果在既有历史页追踪。",
        dependencies: ["shared_portfolio_risk"],
        engineeringStatus: "部分接通",
        evidenceStatus: "待人工审核",
        shortStatus: "共享门槛未闭合",
      },
    ],
  },
};

const capabilityLabels: Record<string, CapabilityStatus> = {
  EXISTING_NATIVE: "IMPLEMENTED",
  DESIGN_ONLY: "DESIGNED",
  PARTIAL: "PARTIAL",
};
function nativeRef(ref: { type: string; path: string; entrypoint?: string }) {
  return [ref.type, ref.path, ref.entrypoint].filter(Boolean).join(" · ");
}
// Build-time read of Root's sole catalog: no network, task state or duplicate capability table.
for (const stage of catalog.value.stages) {
  const module = mainlineCatalog.modules.find(
    (item) => item.module_id === stage.id,
  );
  if (!module) continue;
  stage.nativeContract = {
    source: "config/value-mainline-modules-v1.json",
    ...(stage.id === "A" || stage.id === "B"
      ? {
          phase1Delta: {
            ...mainlineCatalog.phase1_implementation_delta[stage.id],
            scope: mainlineCatalog.phase1_implementation_delta.scope,
            deployment: mainlineCatalog.phase1_implementation_delta.deployment,
          },
        }
      : {}),
    baseline: mainlineCatalog.source_baseline,
    inputSchemaRefs: [module.input_schema.$ref],
    outputSchemaRefs: [module.output_schema.$ref],
    nativeInputs: module.native_inputs.map(nativeRef),
    nativeOutputs: module.native_outputs.map(nativeRef),
    entryRefs: module.entrypoints.map(nativeRef),
    methods: Object.fromEntries(
      Object.entries(module.method_status).map(([method, status]) => [
        method,
        capabilityLabels[status],
      ]),
    ),
    rawMethods: module.method_status,
    methodEvidence: module.method_evidence,
    requiredDependencies: JSON.stringify(module.required_dependencies),
    evidence: module.source_report,
  };
}
