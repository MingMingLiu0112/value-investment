export type StrategyKey = "value" | "hotspot";
export interface Stage {
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
  version: "strategy-architecture-v1",
  reviewedAt: "2026-10-30",
  baseline: "1cf73655457094fe924001497393f2be6d22fcec",
  mode: "MANUAL_SOURCE_REVIEW",
  runtimeEvidence: "NOT_CONNECTED",
  ledger: "docs/current/web-first-full-product-execution-ledger.md",
  disclaimer:
    "静态人工维护目录，不是实时进度。源码复核仅说明模块职责；里程碑状态是基线台账的人工整理，不代表人工投资批准。运行证据未接入，也未在本页核验。",
} as const;
export const catalog: Record<
  StrategyKey,
  { title: string; summary: string; stages: Stage[] }
> = {
  value: {
    title: "价值策略架构",
    summary:
      "先理解企业如何赚钱与现金如何归属股东，再评价估值和价格。分红能力与市场股息率分开。",
    stages: [
      {
        id: "value_screen",
        title: "四通道发现",
        question: "哪些公司值得研究？",
        input: "时点明确的证券范围、财务事实和经济类型",
        output: "质量、股东现金回报、价值、周期四通道候选",
        modules: ["src/value_investment_agent/m2_opportunity_discovery.py"],
        implementation: "四通道、数据完整性及不支持类型合同",
        milestone: "筛选合同存在；当前覆盖未在本页核验。",
        evidence: "候选收据、来源哈希、available_at、规则版本与缺失原因。",
        boundary: "入池仅代表研究优先级，不代表便宜或可以买。",
        ruleWhy: "入池仅代表研究优先级，不代表便宜或可以买。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: [],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "实现已定位 · 应用证据待核验",
        channels: [
          {
            id: "quality",
            title: "质量",
            why: "寻找能持续创造利润与回报的企业；仍需验证优势及再投资回报。",
          },
          {
            id: "dividend_cash_return",
            title: "股东现金回报",
            why: "寻找现金回馈线索；历史高股息不能代替分配能力和可持续性。",
          },
          {
            id: "value",
            title: "价值",
            why: "寻找价格与经济价值可能错配的线索；低估值指标不是内在价值结论。",
          },
          {
            id: "cyclical",
            title: "周期",
            why: "区分周期位置与正常化盈利；低市盈率可能来自盈利高峰。",
          },
        ],
      },
      {
        id: "value_operating",
        title: "产品与经营路径",
        question: "产品、销量、价格与成本如何形成利润？",
        input: "披露原文、主体和报告期、事实与显式假设",
        output: "经营收入、成本与利润的情景路径",
        modules: [
          "src/value_investment_agent/application/research/product_operating_research.py",
          "src/value_investment_agent/domain/valuation/operating_product_paths.py",
        ],
        implementation: "已复核来源绑定的产品假设进入现金与RI计算的编排。",
        milestone: "经济研究仍需实质证据；历史现金诊断不是正常化可分配现金。",
        evidence: "原文页码及口径、经营机制、再投资假设、反证与敏感性。",
        boundary: "分配能力不依赖股价；股息率依赖报价，股息不能重复计入估值。",
        ruleWhy: "增长与利润必须有产品、渠道和竞争机制，不能仅外推历史均值。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep:
          "补证销量/定价压力、优势持续期与反证，保持假设和披露事实分开。",
        evidenceSource: "基线源码复核",
        dependencies: ["value_screen"],
        engineeringStatus: "已实现",
        evidenceStatus: "待验证",
        shortStatus: "实现已定位 · 应用证据待核验",
      },
      {
        id: "value_owner_cash",
        title: "利润到股东现金",
        question: "扣除投入和约束后，多少现金可归股东？",
        input: "经营利润、维护投入、营运资金、资金承诺与现金可达假设",
        output: "现金可达、受约束分配与留存资本的逐年路径",
        modules: [
          "src/value_investment_agent/application/product/consumed_economic_path.py",
          "src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py",
          "src/value_investment_agent/domain/valuation/distribution_capacity_review.py",
        ],
        implementation:
          "已消费账本六步投影及分配能力诊断：分别解释目标派息、现金上限和分配容量；识别目标缩减、期初资金依赖和资金缺口。不重算估值或批准分红。",
        milestone: "经济研究仍需实质证据；历史现金诊断不是正常化可分配现金。",
        evidence: "原文页码及口径、经营机制、再投资假设、反证与敏感性。",
        boundary: "分配能力不依赖股价；股息率依赖报价，股息不能重复计入估值。",
        ruleWhy: "归母利润不是可分配现金；未上划资金和法定容量不能忽略。",
        existingEvidence:
          "2026-10-30真实候选重放：600519悲观路径第1年约11.72亿元分配依赖期初资金；中性最低当期资源覆盖率约1.0075倍。三情景10年均达到假设目标，但不构成永久分红持续性证明。估值基准日仍为2026-06-30。",
        nextStep:
          "用经营、投入和资金上划证据复核覆盖率余量；保持条件诊断与真实现金流、法定分配及正式批准分离。",
        evidenceSource:
          "来源绑定候选及实际API：.tmp/value-distribution-acceptance/；逐年诊断与已消费账本同版本。本页为人工维护的证据记录，不是动态进度。",
        dependencies: ["value_operating"],
        engineeringStatus: "已实现",
        evidenceStatus: "真实算术已核",
        shortStatus: "三情景分配能力 · 现金约束与期初资金依赖已计算",
      },
      {
        id: "value_valuation",
        title: "模型与估值",
        question: "模型适用吗，价值依赖什么假设？",
        input: "经济类型、模型适用性、经核验事实与情景假设",
        output: "注册模型估值及经营价值到股权价值的桥接解释",
        modules: [
          "src/value_investment_agent/valuation_router.py",
          "src/value_investment_agent/valuation_bridge_review.py",
          "src/value_investment_agent/valuation_models/residual_income_path_v4.py",
        ],
        implementation: "按经济类型路由及桥接复核；回收率未知保持未知",
        milestone: "候选路径存在；主经济估值准入仍需独立复核。",
        evidence: "模型版本、输入绑定、桥接项、假设边界与实质经济论证。",
        boundary: "模型可运行不等于估值可信，不支持的类型不能硬套。",
        ruleWhy: "模型可运行不等于估值可信，不支持的类型不能硬套。",
        existingEvidence:
          "基线台账：600519实际留存来源重算及API消费三情景通过；2026-06-30、LOW置信度，非批准主估值、非当前买价。",
        nextStep: "完成主估值经济论证与G3复核；不能将三情景成功升级为批准。",
        evidenceSource:
          "基线台账记录：.tmp/batch2-real-api/600519.json（非本页实时API）",
        dependencies: ["value_owner_cash"],
        engineeringStatus: "已实现",
        evidenceStatus: "真实算术已核",
        shortStatus: "600519 · 三情景 · 2026-06-30",
      },
      {
        id: "value_gate",
        title: "研究门核验",
        question: "证据、财务、论点与估值充分了吗？",
        input: "研究案例及适用的人工研究/估值复核凭据",
        output: "G0证据 / G1财务 / G2商业论点 / G3估值及阻断原因",
        modules: [
          "src/value_investment_agent/domain/research/research_gate.py",
        ],
        implementation: "四门齐备才能进入研究就绪状态的规则",
        milestone: "G3批准仍为独立门槛；目录未作批准。",
        evidence: "绑定案例与版本的研究材料、有效复核凭据和未解决反证。",
        boundary: "研究就绪不等于价格有吸引力，更不等于交易许可。",
        ruleWhy: "研究就绪不等于价格有吸引力，更不等于交易许可。",
        existingEvidence: "源码职责已复核；此节点没有在目录中绑定运行收据。",
        nextStep: "核验所列证据、记录缺口，并在下一目录版本绑定实际收据。",
        evidenceSource: "基线源码复核",
        dependencies: ["value_valuation"],
        engineeringStatus: "已实现",
        evidenceStatus: "待人工审核",
        shortStatus: "G3仍待实质复核",
      },
      {
        id: "value_price",
        title: "价格条件与人工决策",
        question: "有效估值与价格能合法比较吗？",
        input:
          "已核验候选与显式阈值政策；当前比较另外要求模型有效性及日期/股本/分配/报价对齐",
        output: "未批准条件价格草案；当前价格资格、个人风险和人工决策分别核验",
        modules: [
          "src/value_investment_agent/price_bridge.py",
          "src/value_investment_agent/application/research/pending_candidate_price_proposal.py",
          "src/value_investment_agent/application/research/pending_candidate_alignment.py",
        ],
        implementation:
          "候选绑定的未批准提案已接入逐项对齐展示：独立行情、股本、期间分配、重大事件、新财报及模型/价格桥接；当前价格对齐与G3仍待完成。",
        milestone:
          "候选绑定的未批准价格提案已实现（交付说明）；当前价格对齐与G3待完成。",
        evidence:
          "合格报价独立展示；跨日股本与已内含分配、当前候选事件重大性、新财报及模型有效性仍需证据。扫描分页完整不等于全天或重大性通过。",
        boundary:
          "未批准提案不是当前买价，不代表currentbuy ready，不产生仓位或订单。",
        ruleWhy: "估值日的条件数字不能直接当作当前操作价。",
        existingEvidence:
          "2026-10-30原件重放：中报股本1,250,081,601股、回购注销2,188,614股及半年度不分配预案已进入消费链；分红总额与实施公告相差0.01元，保留对账缺口。10/29双源收盘1354.00元独立核验，675.10/930.01元仍是6/30条件研究参考线。",
        nextStep:
          "补齐比较日期股本锚及行动连续性、期间分配内含关系；v4已能生成当前候选未签署事件复核材料，调价、会计政策和平台划转仍待实质复核。不重复扣6/26分红，不以完整扫描代替重大性批准。",
        evidenceSource:
          "真实原件/API：.tmp/value-alignment-acceptance/600519-api.json、real-replay.json；完整公告窗口：runtime/value-alignment-event-observation/20261030T034906348838Z；未签署复核：runtime/value-current-materiality-review/20261030T035120535474Z。10/30采集不作为10/29事前证据；此为验收记录。",
        dependencies: ["value_valuation"],
        engineeringStatus: "部分接通",
        evidenceStatus: "真实算术已核",
        shortStatus: "中报字段已消费 · v4事件复核已接通 · 跨日连续性待补",
      },
      {
        id: "shared_rule_approval",
        title: "用户策略与规则门",
        question: "策略、规则版本和适用范围是否获相应批准？",
        input: "研究结果、规则版本、独立授权及适用范围",
        output: "待相应人工批准；拒绝或缺失继续停止",
        modules: [
          "src/value_investment_agent/domain/research/research_gate.py",
        ],
        implementation: "映射既有研究/策略授权边界；本页没有批准功能。",
        milestone: "未闭合：未来策略/规则变更仍需相应人工批准。",
        evidence: "版本绑定的批准依据、权限、有效期和变更后重审记录。",
        existingEvidence: "只复核已有授权合同；不宣称有可用批准收据。",
        evidenceSource: "基线源码复核",
        boundary: "浏览或点击节点不构成批准；不得由工程测试自动代签。",
        ruleWhy: "改变规则会改变结论，旧批准不能自动覆盖新策略。",
        nextStep: "向用户呈现规则及证据差异，在既有流程取得相应批准。",
        dependencies: ["value_price", "value_gate"],
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
