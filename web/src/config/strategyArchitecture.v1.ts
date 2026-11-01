export type StrategyKey = "value" | "hotspot";
export interface Stage {
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
  version: "strategy-architecture-v2-module-map",
  reviewedAt: "2026-11-01",
  baseline: "d01923cd72c3e638bb3df490f9e148abccd82219",
  mode: "MANUAL_SOURCE_REVIEW",
  runtimeEvidence: "NOT_CONNECTED",
  ledger: "docs/current/web-first-full-product-execution-ledger.md",
  disclaimer:
    "静态人工维护目录，不是实时进度。源码复核仅说明模块职责；里程碑状态是基线台账的人工整理，不代表人工投资批准。运行证据未接入，也未在本页核验。",
} as const;
export const valueVerticalScope = {
  focus: "D2 → 股东现金 → 估值 → 条件价格",
  evidenceSource: "artifacts/current/d2-operating-driver-20261101.json",
  capitalUnknownCount: 9,
  cashEvidenceSource:
    "artifacts/current/d2-cash-consumption-20261101/index.json",
  accepted:
    "当前真实回执：D2→股东现金→条件估值工程已接，待最终验收。ResearchApplicationService已消费年度输入并复用v4，三路径共30行现金账；纯条件模型结果9.03/20.26/25.82，非主区间、非买价，不代表整链或投资批准。",
  currentFollowup:
    "已接通财政年度分红政策诊断及000568真实后续原件：H1政策、年度股利实施、9月解限售股数表和Q3。财政年度目标与滚动现金模型分开；85亿元目标高于条件盈利不等于资金短缺或违约。新Q3不只标过期：已报告1—9月归母56.7106亿元，高于旧条件全年53.9239亿元，隐含Q4需亏损约2.7867亿元；这是旧情景的推导要求，不是已发生亏损或新预测，须重验。母公司资金子包已合并：H1现金扣已宣派股利后的170.1621亿元仅为历史静态余量；义务未拆全，分配上限与缺口为空，8月实施安排不再重复扣股利。当前股本连续性、现金能力及重大性不因此自动通过。",
  currentBlocker:
    "当前阻断：季节性/持续盈利与资金政策尚未获经济采纳，当前资本/分配/事件/报价尚未对齐，无阈值理由不出条件价。原9项资本UNKNOWN不因复用来源绑定的条件现金政策而升级为已证；不能补零、未经核验沿用旧假设或重试模型凑通过。年度计算通道已接，不能据此推定主区间获批。",
  nextRequired: [
    "年度经营路径（工程已接，待终验）：H2逐组成行压力投影，与原D2 H1同一个margin_lower witness组成2026年7月—2027年6月滚动全年，后续年度flat；非机械年化，复用既有计算、不复制公式，不得H1×2，不得调整COGS凑利润。当前需验证季节性与持续盈利的经济适用性，不再列作计算通道缺失。",
    "税后归属与现金政策（经济采纳待验）：年度PBT→税后归属→v4现金/终值已真实消费，三路径共30行现金账；经营税前利润不能直接当股东现金。复用000568原已来源绑定的条件资金政策，但不是批准，不升级原9项资本UNKNOWN；历史代理或旧首编单独重放不冒充本次D2消费。",
    "条件估值已消费，主区间未采用：当前三路径压力值仅为条件研究，RI/DDM差小于1e-36属于算术一致性；季节性、持续盈利与资金政策经济采纳、模型终端适用性仍须验收，不代表未来参数已证、主估值或投资批准。",
    "当前资本/分配/事件/报价及价格理由（当前必需）：核验股本连续性、当前分配/事件/报价及估值采用资格；无阈值理由不出条件价，当前不生成买价。公开条件研究不依赖私人持仓解锁，不把压力结果直接套为当前参考价格。",
  ],
  futureExtensions: [
    "全市场自动研究、通用企业分类与新增公司样本：属于后续扩展，不是本轮纵向链的前置任务。",
    "真实组合、私人持仓、个人账户收益/分红对账与交易执行：不在本轮范围，不作为公开研究的解锁条件；不包含本轮必需的公开股本/分配/事件/报价核验。",
    "热点通道及更多平台能力：保留既有状态，本轮不并行扩展；C职责冻结。",
  ],
  boundary:
    "本轮只推进当前纵向链。下方全景保留其他模块职责，不表示需先完成全部模块；生产部署与用户确认仍单独验收。",
} as const;

export const catalog: Record<
  StrategyKey,
  { title: string; summary: string; stages: Stage[] }
> = {
  value: {
    title: "价值投资 · 模块化研究与决策闭环",
    summary:
      "从公开证据到企业经营、股东现金与估值，再到当前价格、持仓和持续复核。完整展示16个价值/共享模块；热点H1–H4保留为独立暂停通道。",
    stages: [
      {
        id: "A",
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
        title: "B · 四通道筛选与研究队列",
        question: "哪些公司值得投入研究时间？",
        dependencies: ["A"],
        input: "有时点的证券范围、财务与行情",
        output: "质量／现金回报／价值／周期研究线索",
        modules: [
          "src/value_investment_agent/application/discovery/value_candidate_selection.py",
        ],
        engineeringStatus: "初筛、调度与限定事实消费已验证",
        evidenceStatus: "真实来源重放、公开获取与接口验收已完成",
        shortStatus:
          "四通道初筛与排序已验；两条离线调度失败、新增事实0；公开获取后重试成功消费2项资产负债率事实",
        implementation:
          "保留日期原件重放→四通道初筛→排序→预算队列→官方获取→限定事实冷读消费；现有接口透传已核验市场范围",
        milestone: "初筛与限定事实消费已验证；经济研究与正式资格未完成。",
        existingEvidence:
          "5224家沪深观察范围；质量0／现金回报50／价值50／周期50；补证111条、预算2；000151/000498各消费1项资产负债率，深度研究0",
        evidenceSource:
          "runtime/b-real-acceptance-20261030/receipt.json；runtime/b-real-acceptance-20261030-public-retry/consumer-acceptance.json（限定事实冷读消费）；现有接口验收",
        evidence:
          "行情2026-10-23（供应商交易日未独立核验），筛选2026-10-25；历史保留研究，非当前刷新；北交所缺失、非全A；报价CONFLICT按原始来源保留并阻断入队",
        nextStep:
          "继续核验各通道经营与经济证据；新增资产负债率不代表完整债务、企业质量或估值准入",
        ruleWhy: "不同企业的价值线索不同；低PE和高股息都可能是陷阱。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "初筛、排序及预算调度已验；两条离线任务失败；官方获取后限定事实消费2项成功",
          realData:
            "历史初筛5224家、非全A；离线失败新增事实0；公开获取后新增2项限定事实，保留实际获取时间",
          economic:
            "初筛线索不证明ROIC、正常化盈利或分红持续性；资产负债率仅按窄方法核验",
          deployment: "发布身份与浏览器验收单独记录；历史数据日期不随发布滚动",
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
        title: "D1 · 受限研究执行",
        question: "研究能否在预算内运行并恢复？",
        dependencies: ["A", "B"],
        input: "封存摘要、任务与预算权限",
        output: "受控模型响应、成本、错误与任务轨迹",
        modules: [
          "src/value_investment_agent/infrastructure/agent_runtime/provider.py",
          "src/value_investment_agent/application/research/agent_review/operating_task_v2.py",
        ],
        engineeringStatus: "真实三角色执行与拒绝恢复已验收",
        evidenceStatus:
          "000568最新rt-eac任务三角色成功，4次调用含1次反证缺字段拒绝后恢复；不是今日调用总数",
        shortStatus:
          "工程与真实执行已验收；条件压力算术另验，不代表未来参数、主估值或交易通过",
        implementation:
          "复用D1追加状态和锁，接真实Provider、逐角色检查点、调用前CNY预留、跨任务日限额和显式取消恢复",
        milestone:
          "rt-eac1c74997d17510398ce1fe1e5bea9e最终SUCCEEDED、两次执行尝试；4次调用含反证字段校验拒绝与恢复，不隐藏失败轨迹。",
        existingEvidence:
          "000568共96条官方来源记录，含H1第11/14/12页量价成本表；不读取旧估值或保存响应，当前来源与角色回执绑定",
        evidenceSource:
          "runtime/d2-operating-driver-20261101/rt-eac1c74997d17510398ce1fe1e5bea9e-recovered.json；runtime/d2-operating-driver-20261101/independent-acceptance.json；源码版本见实际运行身份；验收索引 artifacts/current/d2-operating-driver-20261101.json",
        evidence:
          "每日上限10元；历史rt-c40任务峰值费率保守估算0.15066元，非账单；昨日浏览器实际0.158元，旧估算7.33345元不是实际费用。已核费率为峰2/8、非峰1/4元每百万输入/输出token",
        nextStep:
          "验证参数经济适用性及资本/现金资料，不重试模型凑通过；不以执行成功授予E2或主估值批准",
        ruleWhy: "执行可靠性与投资判断不同；Mock只能证明工程路径。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "现有公司AI区域显式操作 → 任务API → 持久执行器；不在首屏后台调用",
          realData:
            "最新rt-eac任务三角色、4次调用，含1次反证缺字段拒绝与恢复；旧rt-c40经济拒绝及其他失败run原始回执保留，不混为本任务",
          economic: "不适用或由下游独立准入",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "D2",
        title: "D2 · 经营假设与反证",
        question: "增长和分配为何成立，什么会推翻？",
        dependencies: ["C", "D1"],
        input:
          "D2 H1同一margin_lower witness、年度/H1实际、逐行H2压力投影与来源绑定的条件现金政策",
        output:
          "滚动全年税前/税后归属输入、三路径30行现金账、未采用主区间的条件估值；无条件价",
        modules: [
          "src/value_investment_agent/application/research/product_operating_research.py",
          "src/value_investment_agent/application/research/agent_review/operating_draft_v1.py",
        ],
        engineeringStatus:
          "条件压力算术已验／D2→现金→条件估值工程已接，待最终验收",
        evidenceStatus:
          "96条官方来源；21项经营驱动范围、6项增长/税前利润率由代码派生、9项资本UNKNOWN；不是模型直接填利润率；新增30行现金账与v4条件估值真实消费",
        shortStatus:
          "D2 H1 witness + H2逐行压力 → 滚动全年 → v4现金/条件估值已接；季节性、持续盈利和资金政策未获经济采纳",
        implementation:
          "原驱动桥锁定H12026→H12027，按每情景128角点重算；同比FY只对FY、H1只对H1。新增2026Jul–2027Jun滚动全年适配，后续flat，ResearchApplicationService→既有v4计算",
        milestone:
          "独立Euclid冷复算3×128角点及12条阈值一致，工程与条件压力分析算术验收通过。12条重审严格按同bounds、同期间/基线比较，等于不触发，不混用历史阈值。",
        existingEvidence:
          "旧D2两公司草案及rt-c40经济拒绝保留为历史，不覆盖旧raw；当前H1第11/14/12页量价成本表构成新驱动桥，不沿用旧直接填利润率路径",
        evidenceSource:
          "runtime/d2-operating-driver-20261101/rt-eac1c74997d17510398ce1fe1e5bea9e-recovered.json；runtime/d2-operating-driver-20261101/independent-acceptance.json；artifacts/current/d2-cash-consumption-20261101/index.json；源码版本见实际运行身份；验收索引 artifacts/current/d2-operating-driver-20261101.json",
        evidence:
          "仅拒绝两类AI文字：产品结构向高档集中误述、Event母现金23.93亿元少10倍；不作为事实摘要，typed bridge不消费这些文字，算术验收不受其替代。Event仍限FY/H1；未来参数适用性未证，原9项资本UNKNOWN不升级已证；新现金/估值仅复用另行绑定的条件政策。",
        nextStep:
          "首要决定性缺口：验证参数经济适用性及资本/现金资料，不重试模型凑通过；重点为季节性/持续盈利与资金政策经济采纳、当前资本/分配/事件/报价对齐，无阈值理由不出条件价；原9项资本UNKNOWN不升级，不授予投资批准",
        ruleWhy: "价格上涨不直接等于净利上涨；预测必须明确为假设。",
        boundary:
          "事实、预测、研究候选与批准分开；未知必须保留。action=no_order。",
        progress: {
          consumer:
            "D2滚动年度输入 → ResearchApplicationService → v4条件现金/估值 → 公开研究；新消费待最终验收",
          realData:
            "最新rt-eac三角色、4次调用；96官方记录，21驱动范围、6代码派生指标、9资本UNKNOWN；独立3×128角点与12阈值复算一致",
          economic: "条件现金/估值工程已接待终验／参数经济适用性未证／非主区间",
          deployment: "模块部署资格未逐项认证；页面发布不等于业务准入",
          acceptance: "用户尚未确认此版本",
        },
      },
      {
        id: "E1",
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
          "确定缺口：现有研究包/状态仅GET，没有开始、取消、恢复及任务检查点接线",
        implementation: "已有研究状态及Agent界面入口",
        milestone: "部分实现；不代表正式研究准入或实盘资格。",
        existingEvidence: "已有研究状态及Agent界面入口",
        evidenceSource: "d01923cd源码职责复核；本轮未运行该模块真实业务验收",
        evidence:
          "确定缺口：现有研究包/状态仅GET，没有开始、取消、恢复及任务检查点接线",
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
