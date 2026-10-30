/**
 * A reviewed, read-only project map. This is not a live readiness calculator.
 * Module IDs follow the user's A–G plan, not the historical ResearchGate G0–G3.
 * Updating this snapshot never grants research, portfolio, or trading approval.
 */
export type StrategyLane = "value" | "hotspot" | "shared";
export type ModuleId =
  | "A"
  | "B"
  | "C"
  | "D1"
  | "D2"
  | "E1"
  | "E2"
  | "F1"
  | "F2"
  | "G1"
  | "G2"
  | "H1"
  | "H2"
  | "H3"
  | "H4"
  | "S1"
  | "S2"
  | "S3"
  | "S4"
  | "W1";
export type ImplementationStatus =
  "planned" | "partial" | "implemented" | "connected";
export type VerificationStatus = "pending" | "partial" | "verified" | "blocked";
export type CriterionStatus = "met" | "partial" | "pending" | "blocked";

export interface ProjectEvidence {
  id: string;
  label: string;
  kind: "source" | "test" | "ci" | "document";
  url: string;
  summary: string;
}

export interface ProjectCriterion {
  id: string;
  text: string;
  status: CriterionStatus;
  evidenceIds: string[];
}

export type ProjectOwnerReview =
  | { status: "unconfirmed"; summary: string }
  | ({
      status: "accepted" | "changes_requested";
      summary: string;
      reviewedCommit: string;
      reviewedScope: string;
      reviewedAt: string;
    } & (
      | { userQuote: string; recordRef?: string }
      | { userQuote?: string; recordRef: string }
    ));

export interface ProjectModule {
  id: ModuleId;
  lane: StrategyLane;
  reviewedCommit: string;
  reviewedAt: string;
  title: string;
  summary: string;
  inputs: string[];
  outputs: string[];
  currentOutcomes: string[];
  nextDeliverable: string;
  dependencyIds: ModuleId[];
  scope: string[];
  limitations: string[];
  implementation: { status: ImplementationStatus; summary: string };
  verification: {
    status: VerificationStatus;
    summary: string;
    evidenceIds: string[];
  };
  ownerReview: ProjectOwnerReview;
  criteria: ProjectCriterion[];
  evidence: ProjectEvidence[];
}

export interface ProjectConnection {
  from: ModuleId;
  to: ModuleId;
  label: string;
  kind: "flow" | "dependency" | "feedback";
}

export interface ProjectFlowStage {
  lane: StrategyLane;
  id: string;
  title: string;
  caption: string;
  moduleIds: ModuleId[];
}

export interface ProjectBatch {
  id: string;
  title: string;
  status: "current" | "next" | "later";
  goal: string;
  moduleIds: ModuleId[];
  deliverables: string[];
  exitCriteria: string[];
}

// Keep this initial audit binding immutable. Later module reviews override their
// own metadata and evidence; updating the overall inventory must not rebind it.
const initialAuditCommit = "1e3f6af10e62fc55cf0141e0c91dddee12310aa3";
const initialAuditDate = "2026-10-28";
const repository = "https://github.com/MingMingLiu0112/value-investment";
const blob = (path: string, commit: string) =>
  `${repository}/blob/${commit}/${path}`;
const evidence = (
  id: string,
  label: string,
  path: string,
  summary: string,
  kind: ProjectEvidence["kind"] = "source",
  commit: string = initialAuditCommit,
): ProjectEvidence => ({
  id,
  label,
  kind,
  url: path.startsWith("https://") ? path : blob(path, commit),
  summary,
});
const moduleRecord = (
  record: Omit<ProjectModule, "ownerReview" | "reviewedCommit" | "reviewedAt"> &
    Partial<
      Pick<ProjectModule, "ownerReview" | "reviewedCommit" | "reviewedAt">
    >,
): ProjectModule => ({
  ...record,
  reviewedCommit: record.reviewedCommit ?? initialAuditCommit,
  reviewedAt: record.reviewedAt ?? initialAuditDate,
  ownerReview: record.ownerReview ?? {
    status: "unconfirmed",
    summary: "尚未记录用户对本模块的最终验收；工程证据不代替用户确认。",
  },
});

export const projectControl = {
  title: "双策略架构与开发进度",
  summary:
    "沿两条独立研究主线查看业务输入、输出、依赖和下一交付；分别核对实现、验证与用户确认。",
  // Overall inventory metadata is independent from each module and evidence.
  snapshotCommit: "1e3f6af10e62fc55cf0141e0c91dddee12310aa3",
  lastReviewed: "2026-10-28",
  sourceBranch: "codex/value-f1-e1-g1-20261027",
  scopeNote:
    "业务进度基于该源码快照；建议排程须结合最新用户任务使用，当前页面不声称实时部署状态。A–G 为本轮模块编号，不等同于历史研究门禁编号。",
  boundaries: [
    "价值与热点分别形成研究结论、分别接受准入审查，共享组合、现金、成交和事件基础；热点不以价值估值通过为前提。",
    "热点新增开发当前暂停；既有观察、结构分析和生命周期能力保留，暂停不表示技术能力被删除。",
    "事实、经营假设、数值计算、研究批准、价格判断与人工成交分别记录；所有路径永久 action=no_order。",
    "工程实现、样本验证、真实来源恢复、经济或策略准入、部署、用户验收各自举证；没有主观完成百分比。",
    "研究候选不会自动成为订单或持仓；现金、成本、实际成交与账户约束来自本人核验资料，缺失不能补零。",
    "复用现有 Web、数据获取、估值与组合服务；本页面只解释范围和证据，不更改阈值、模型或投资逻辑。",
  ],
  batches: [
    {
      id: "close-existing",
      title: "当前建议 · 关闭已有估值与展示证据",
      status: "current",
      goal: "将 F1 / E1 / G1 已有代码转为可恢复、同版本、可核验的有限交付，同时修正已确认的队列状态缺陷。",
      moduleIds: ["F1", "E1", "G1", "B"],
      deliverables: [
        "两公司原件恢复清单与强制真实回放",
        "模型、候选、API、页面版本一致的交接记录",
        "预算不覆盖数据冲突状态",
      ],
      exitCriteria: [
        "缺真实源包时验收失败而非静默跳过",
        "研究限定与未批准状态在页面保留",
        "第 51 位冲突候选仍被研究队列拒绝",
      ],
    },
    {
      id: "data-handoff",
      title: "下一批建议 · 有限数据与事实交接",
      status: "next",
      goal: "在明确支持范围内补足采集稳定性，并让新公司的事实基线可靠交给后续研究。",
      moduleIds: ["A", "B"],
      deliverables: [
        "限流、更正歧义与原件恢复规则",
        "含缺失、冲突、行业适用性的新公司事实包",
        "公平排队与失败隔离的复用验收",
      ],
      exitCriteria: [
        "局部失败不阻塞其他公司",
        "缺失、否决、预算延期分别显示",
        "新公司无旧估值仍可形成事实研究上下文",
      ],
    },
    {
      id: "bounded-runner",
      title: "后续建议 · 最小真实研究任务",
      status: "later",
      goal: "先验证一个有界真实调用与持久任务，再扩展经营研究。",
      moduleIds: ["D1", "G2"],
      deliverables: [
        "真实执行端适配与用量记录",
        "阶段检查点、取消、恢复与同输入去重",
      ],
      exitCriteria: [
        "一次真实调用具备来源、成本和结果记录",
        "中断恢复不无意重复调用",
        "界面状态能对应同一个持久任务",
      ],
    },
    {
      id: "first-research",
      title: "后续建议 · 新公司完整研究与条件判断",
      status: "later",
      goal: "完成画像、假设与首版模型编译，以未参与开发的支持样本验收。",
      moduleIds: ["C", "D2", "E2", "G2", "F2"],
      deliverables: [
        "证据驱动公司画像和经营假设",
        "无旧预测包的首版模型输入",
        "任务操作与更新版本链",
        "条件价格及持有退出理由",
      ],
      exitCriteria: [
        "事实与假设可分辨并可重放",
        "留出样本无需复制既有公司预测",
        "F2 在已有研究和当前数据齐备时可前移，不机械等待 Agent 全部完成",
      ],
    },
  ] as ProjectBatch[],
};

export const projectLanes: {
  id: StrategyLane;
  title: string;
  subtitle: string;
  developmentStatus: "active" | "paused" | "shared";
}[] = [
  {
    id: "value",
    title: "价值投资",
    subtitle: "理解经营与现金回报，形成有依据的价值与条件判断",
    developmentStatus: "active",
  },
  {
    id: "hotspot",
    title: "热点策略",
    subtitle: "观察市场与结构，独立验证准入；当前暂停新增开发",
    developmentStatus: "paused",
  },
  {
    id: "shared",
    title: "共享能力",
    subtitle: "统一账户事实、风险、事件与展示，保留两策略边界",
    developmentStatus: "shared",
  },
];

export const projectFlowStages: ProjectFlowStage[] = [
  {
    lane: "value",
    id: "value-discover",
    title: "发现与排队",
    caption: "先决定研究谁",
    moduleIds: ["B"],
  },
  {
    lane: "value",
    id: "value-evidence",
    title: "原件与画像",
    caption: "确认事实和适用方法",
    moduleIds: ["A", "C"],
  },
  {
    lane: "value",
    id: "value-research",
    title: "经营研究",
    caption: "形成有依据的假设",
    moduleIds: ["D1", "D2"],
  },
  {
    lane: "value",
    id: "value-model",
    title: "估值候选",
    caption: "既有更新与首次编译分开",
    moduleIds: ["E1", "E2", "F1"],
  },
  {
    lane: "value",
    id: "value-decision",
    title: "判断与跟踪",
    caption: "条件、结果与任务操作",
    moduleIds: ["F2", "G1", "G2"],
  },
  {
    lane: "hotspot",
    id: "hotspot-discover",
    title: "热点发现",
    caption: "市场与行业观察",
    moduleIds: ["H1"],
  },
  {
    lane: "hotspot",
    id: "hotspot-evidence",
    title: "标的证据",
    caption: "完整周期和结构",
    moduleIds: ["H2"],
  },
  {
    lane: "hotspot",
    id: "hotspot-plan",
    title: "独立准入与计划",
    caption: "策略验证后再审个人风险",
    moduleIds: ["H3"],
  },
  {
    lane: "hotspot",
    id: "hotspot-lifecycle",
    title: "生命周期",
    caption: "围绕原始入场依据复核",
    moduleIds: ["H4"],
  },
  {
    lane: "shared",
    id: "shared-risk",
    title: "组合与现金",
    caption: "共享账户，分别约束",
    moduleIds: ["S1"],
  },
  {
    lane: "shared",
    id: "shared-records",
    title: "实际成交与持仓",
    caption: "人工确认、可追溯记录",
    moduleIds: ["S2"],
  },
  {
    lane: "shared",
    id: "shared-followup",
    title: "回报与事件",
    caption: "现金变化和研究更新",
    moduleIds: ["S3", "S4"],
  },
  {
    lane: "shared",
    id: "shared-web",
    title: "既有 Web",
    caption: "解释状态与下一步",
    moduleIds: ["W1"],
  },
];

export const projectModules: ProjectModule[] = [
  moduleRecord({
    id: "A",
    lane: "value",
    title: "来源获取与原件归档",
    summary: "为支持范围内的公司取得可识别、可恢复的财报原件。",
    inputs: ["证券身份、报告期间和采集范围", "官方公告索引与已保留原件"],
    outputs: ["带来源、期间、哈希和可用时间的原件包", "缺失、歧义与失败原因"],
    currentOutcomes: [
      "年报／半年报获取、身份核验、原件校验和留存复用已接通。",
      "已有有限重试，不以重新抓取时间证明历史同时点可得。",
    ],
    nextDeliverable:
      "补齐限流、更正报告歧义和最小原件恢复清单，并在支持样本上恢复重放。",
    dependencyIds: [],
    scope: ["有限公司和报告类型", "复用既有采集及证据存储"],
    limitations: [
      "HTTP 429 / Retry-After 尚未纳入当前重试策略。",
      "修订报告多匹配会停止，尚无完整替代版本处理。",
    ],
    implementation: {
      status: "connected",
      summary: "原件获取与留存读取已在补证据链中使用。",
    },
    verification: {
      status: "partial",
      summary: "有来源合同与回归；跨环境恢复及异常策略仍需有限验收。",
      evidenceIds: ["A-source", "A-test"],
    },
    criteria: [
      {
        id: "A-identity",
        text: "证券、报告期间、原件哈希一致，保留真实取得时间。",
        status: "met",
        evidenceIds: ["A-source", "A-test"],
      },
      {
        id: "A-failure",
        text: "限流与修订歧义产生明确、可恢复的局部结果。",
        status: "partial",
        evidenceIds: ["A-source"],
      },
      {
        id: "A-restore",
        text: "凭最小清单在新环境恢复原件并重放。",
        status: "pending",
        evidenceIds: ["A-source"],
      },
    ],
    evidence: [
      evidence(
        "A-source",
        "官方报告获取与留存读取",
        "src/value_investment_agent/infrastructure/filings/official_report_acquisition.py",
        "身份、报告选择、有限重试与原件读取实现；也暴露限流和多匹配边界。",
      ),
      evidence(
        "A-test",
        "官方报告获取回归",
        "tests/test_official_report_acquisition.py",
        "工程反例与输入验证，不能替代广泛真实来源验收。",
        "test",
      ),
    ],
  }),
  moduleRecord({
    id: "B",
    lane: "value",
    title: "事实、四通道与研究队列",
    summary: "将市场线索分为可研究公司、数据缺口和预算延期。",
    inputs: ["官方证券范围、报价与分红线索", "已验证年度事实和证据缺口"],
    outputs: [
      "质量／分红／价值／周期通道结果",
      "深研与补证据队列、仅事实研究上下文",
    ],
    currentOutcomes: [
      "四通道、观测排序、质量评分和新公司事实壳已有实现。",
      "补证据具备预算、公平调度、去重、逐公司检查点与失败隔离。",
    ],
    nextDeliverable:
      "修复预算覆盖报价冲突；分离数据状态、适用性与预算状态，完成新公司事实交接。",
    dependencyIds: ["A"],
    scope: ["研究工作排序", "缺失值与行业适用性说明"],
    limitations: [
      "第 51 位以后的候选可能由 CONFLICT 被覆盖成 BUDGET_EXCLUDED，进而误入研究队列。",
      "固定质量阈值尚非跨行业、跨周期投资有效性的证明。",
    ],
    implementation: {
      status: "connected",
      summary: "扫描、排序与证据补全已有实际调用链。",
    },
    verification: {
      status: "blocked",
      summary: "研究队列正确性存在已复现缺陷；不涉及正式交易门禁放行。",
      evidenceIds: ["B-screen", "B-rank", "B-queue"],
    },
    criteria: [
      {
        id: "B-conflict",
        text: "预算截断绝不覆盖报价冲突，边界候选仍被拒绝进入研究队列。",
        status: "blocked",
        evidenceIds: ["B-screen", "B-rank"],
      },
      {
        id: "B-missing",
        text: "缺失不补零；支持范围、经济判断与证据工作量分别解释。",
        status: "partial",
        evidenceIds: ["B-quality", "B-queue"],
      },
      {
        id: "B-handoff",
        text: "无旧估值公司能够得到事实研究上下文；失败不阻塞其他公司。",
        status: "met",
        evidenceIds: ["B-enrich"],
      },
    ],
    evidence: [
      evidence(
        "B-screen",
        "四通道与预算截断",
        "src/value_investment_agent/m2_discovery_engine.py#L866-L886",
        "预算状态覆盖评估状态的根因；本页面只记录缺陷，未修改投资筛选。",
      ),
      evidence(
        "B-rank",
        "研究资格投影",
        "src/value_investment_agent/application/discovery/value_candidate_selection.py#L156-L173",
        "从通道状态反推冲突并接受预算排除项，构成研究队列误判链。",
      ),
      evidence(
        "B-quality",
        "年度质量规则",
        "src/value_investment_agent/financial_quality.py",
        "九项字段、年度一致性、金融画像边界与启发式评分。",
      ),
      evidence(
        "B-queue",
        "质量与补证据队列",
        "src/value_investment_agent/application/research/value_research_priority_v2.py",
        "有分数与缺字段分队列，不能解释为统一收益排名。",
      ),
      evidence(
        "B-enrich",
        "有界补证据执行",
        "src/value_investment_agent/application/research/value_enrichment_batch.py",
        "新公司上下文、公平调度、逐公司检查点和局部失败处理。",
      ),
    ],
  }),
  moduleRecord({
    id: "C",
    lane: "value",
    title: "企业画像与方法选择",
    summary: "解释公司如何赚钱，再选择适用的研究与估值方法。",
    inputs: ["已验证事实与业务原文", "经营结构、资本配置和生命周期证据"],
    outputs: ["有证据的公司画像", "模型适用／不支持判断与必要研究问题"],
    currentOutcomes: [
      "质量复利、成熟制造、周期现金回报三类显式画像及路由已存在。",
      "不支持的画像保持拒绝，不按证券代码自动选择模型。",
    ],
    nextDeliverable:
      "将原文证据编译为可复核画像，明确商业模式判断与财务评分的差别。",
    dependencyIds: ["A", "B"],
    scope: ["已注册方法与支持行业", "证据驱动画像，不扩大成全行业模型库"],
    limitations: [
      "现有静态画像模板不等于自动公司研究。",
      "金融等未注册结构不能借用一般企业估值。",
    ],
    implementation: {
      status: "partial",
      summary: "静态画像与模型路由可复用，证据驱动画像尚待实现。",
    },
    verification: {
      status: "partial",
      summary: "路由边界可核对；自动画像质量未完成真实样本验收。",
      evidenceIds: ["C-profile", "C-router"],
    },
    criteria: [
      {
        id: "C-route",
        text: "方法由经济结构与已注册合同决定，不支持时明确停止。",
        status: "met",
        evidenceIds: ["C-profile", "C-router"],
      },
      {
        id: "C-evidence",
        text: "画像每项关键判断可回到原文，反证可改变适用性。",
        status: "pending",
        evidenceIds: ["C-profile"],
      },
      {
        id: "C-holdout",
        text: "支持范围内的新公司无需证券专用分支即可选择方法。",
        status: "partial",
        evidenceIds: ["C-router"],
      },
    ],
    evidence: [
      evidence(
        "C-profile",
        "研究画像合同",
        "src/value_investment_agent/domain/research/research_profile.py",
        "三类显式画像与模型适用范围。",
      ),
      evidence(
        "C-router",
        "估值路由",
        "src/value_investment_agent/valuation_router.py",
        "选择已注册模型，不提供自动经营画像结论。",
      ),
    ],
  }),
  moduleRecord({
    id: "D1",
    lane: "value",
    title: "有界研究执行端",
    summary: "可靠执行一次有成本、有来源、有边界的真实研究任务。",
    inputs: ["绑定来源的任务快照", "执行端配置、用量预算与单次调用授权"],
    outputs: ["结构化研究响应与用量记录", "明确的成功、失败、超时或取消状态"],
    currentOutcomes: [
      "真实 OpenAI-compatible API adapter、Mock 与三角色 pilot 已存在。",
      "已有 JSON 输出、引用、超时及单次预算约束。",
    ],
    nextDeliverable:
      "复用 provider，完成最小真实调用、阶段持久化与取消恢复合同。",
    dependencyIds: ["A", "B"],
    scope: ["一个可替换执行端", "有限任务，不扩自主 Agent 平台"],
    limitations: [
      "日报研究仍有 mock 路径；不能将其算作真实研究验收。",
      "当前 pilot 最后集中保存，后段失败可能导致前段重跑花费。",
    ],
    implementation: {
      status: "partial",
      summary: "真 provider 可调用，持久 Runner 尚未闭环。",
    },
    verification: {
      status: "partial",
      summary: "接口与工程控制有据；本快照未登记完整真实执行生命周期验收。",
      evidenceIds: ["D1-provider", "D1-pilot"],
    },
    criteria: [
      {
        id: "D1-provider",
        text: "结构化输出、来源约束、超时与用量均有可检查结果。",
        status: "partial",
        evidenceIds: ["D1-provider", "D1-pilot"],
      },
      {
        id: "D1-real",
        text: "一次授权真实任务产生可恢复、可复核的阶段结果和实际成本。",
        status: "pending",
        evidenceIds: ["D1-pilot"],
      },
      {
        id: "D1-resume",
        text: "中断、取消和未知调用结果不会无意重复执行。",
        status: "pending",
        evidenceIds: ["D1-pilot"],
      },
    ],
    evidence: [
      evidence(
        "D1-provider",
        "真实与模拟 Provider",
        "src/value_investment_agent/infrastructure/agent_runtime/provider.py",
        "真 API 适配器存在，不等于当前生产研究已运行。",
      ),
      evidence(
        "D1-pilot",
        "三角色研究 pilot",
        "src/value_investment_agent/application/research/agent_review/llm_pilot.py",
        "顺序调用、单次约束与最终集中持久化。",
      ),
    ],
  }),
  moduleRecord({
    id: "D2",
    lane: "value",
    title: "经营假设与反证研究",
    summary: "把事实转为有依据、有范围、可反驳的未来经营假设。",
    inputs: [
      "公司画像、原件与已验证事实",
      "待解决问题、证据缺口与研究停止条件",
    ],
    outputs: [
      "经营假设草案及证据范围",
      "反证、置信度、未解决问题和重新开启条件",
    ],
    currentOutcomes: [
      "基本面、反证和事件评论角色及来源摘录验证已有实现。",
      "模型不能把评论直接升级为财务事实或批准。",
    ],
    nextDeliverable:
      "为支持画像定义经营假设合同、阶段结果和语义复核，接入已有确定性计算。",
    dependencyIds: ["C", "D1"],
    scope: ["有界补证与假设研究", "模型辅助解释，数值由既有计算验证"],
    limitations: [
      "当前每角色短 finding 不构成十年经营输入。",
      "假设区间、资本配置与反证更新链尚未完整接通。",
    ],
    implementation: {
      status: "partial",
      summary: "评论助手与来源验证可复用，完整经营研究新增部分未闭环。",
    },
    verification: {
      status: "pending",
      summary: "尚待可进入首次模型编译的真实研究产物。",
      evidenceIds: ["D2-pilot", "D2-semantic"],
    },
    criteria: [
      {
        id: "D2-separate",
        text: "每项关键假设标明事实基础、判断范围与反证，不冒充披露事实。",
        status: "partial",
        evidenceIds: ["D2-semantic"],
      },
      {
        id: "D2-contract",
        text: "结构化经营假设可交给模型编译并由确定性计算校验。",
        status: "pending",
        evidenceIds: ["D2-pilot"],
      },
      {
        id: "D2-stop",
        text: "新增证据只有能改变判断时才继续，保留明确重新开启条件。",
        status: "pending",
        evidenceIds: ["D2-semantic"],
      },
    ],
    evidence: [
      evidence(
        "D2-pilot",
        "现有研究输出范围",
        "src/value_investment_agent/application/research/agent_review/llm_pilot.py#L27-L104",
        "短 finding 与工具／计算限制，显示其与完整经营假设合同的距离。",
      ),
      evidence(
        "D2-semantic",
        "来源语义复核",
        "src/value_investment_agent/application/research/agent_review/semantic_review.py",
        "可复用的来源引用和语义检查。",
      ),
    ],
  }),
  moduleRecord({
    id: "E1",
    lane: "value",
    title: "已有研究候选更新与消费",
    summary: "让已有经济研究按新版本重算、封存、重放并进入既有消费者。",
    inputs: ["已有研究事实、假设与场景", "更新后的估值内核和来源绑定"],
    outputs: ["可重放的新版本候选", "明确新旧版本关系与研究限定"],
    currentOutcomes: [
      "两公司 v4 候选已有消费路径，保留来源绑定。",
      "候选仍是 LOW／RESEARCH_ONLY，未获得正式资格或交易计划。",
    ],
    nextDeliverable:
      "恢复两公司实际源包，强制重放并核对候选、API、页面同版本。",
    dependencyIds: ["F1"],
    scope: ["已有合法研究输入的更新", "保持旧版本不可变与候选替代关系"],
    limitations: [
      "当前研究指针含本地原件依赖，源码更新不证明其他环境已部署。",
      "既有基线消费能力不能代替 E2 首次编译。",
    ],
    implementation: {
      status: "connected",
      summary: "v4 候选已经接入已有研究消费链。",
    },
    verification: {
      status: "partial",
      summary: "真实源包缺失可令回放跳过，仍需独立恢复验收。",
      evidenceIds: ["E1-proposal", "E1-replay"],
    },
    criteria: [
      {
        id: "E1-bind",
        text: "新候选明确绑定事实、假设、模型版本和原件，不覆盖旧结果。",
        status: "partial",
        evidenceIds: ["E1-proposal"],
      },
      {
        id: "E1-real",
        text: "两公司真实源包在独立环境恢复，缺包必须使验收失败。",
        status: "pending",
        evidenceIds: ["E1-replay"],
      },
      {
        id: "E1-limit",
        text: "消费后仍保留研究限定、低置信度和未批准状态。",
        status: "met",
        evidenceIds: ["E1-proposal", "E1-replay"],
      },
    ],
    evidence: [
      evidence(
        "E1-proposal",
        "既有研究候选构建",
        "src/value_investment_agent/application/product/neutral_valuation_proposal.py",
        "消费已有事实、场景和基线；不能作为无旧估值入口的完成证明。",
      ),
      evidence(
        "E1-replay",
        "两公司 v4 真实回放门禁",
        "tests/test_joint_cash_v4_two_company_real_replay.py",
        "存在真实回放测试，但缺 runtime 原件且未开启必跑开关时可跳过。",
        "test",
      ),
    ],
  }),
  moduleRecord({
    id: "E2",
    lane: "value",
    title: "新公司的首次模型编译",
    summary: "让没有旧估值的公司从事实与研究草案形成首版合法输入。",
    inputs: ["仅事实研究上下文", "适用画像、已核验经营假设和反证"],
    outputs: ["首版模型输入包与来源映射", "不支持、缺假设和编译失败的明确原因"],
    currentOutcomes: [
      "新公司 fact-only ResearchCase 已有实际创建和登记路径。",
      "事实壳保留未选模型、未研究经济假设与估值未评估状态。",
    ],
    nextDeliverable:
      "补上事实与假设草案到首次模型输入的编译合同，并用留出公司验证。",
    dependencyIds: ["B", "C", "D2", "F1"],
    scope: ["已支持画像的首版编译", "不复制既有公司预测，不扩金融模型"],
    limitations: [
      "neutral proposal 仍需要已有场景与基线。",
      "事实载体中的旧类型名不意味着已经为新公司选择模型。",
    ],
    implementation: {
      status: "partial",
      summary: "入口事实壳已接通；首次完整模型编译尚缺。",
    },
    verification: {
      status: "pending",
      summary: "无旧估值的端到端经济研究尚未验收。",
      evidenceIds: ["E2-facts", "E2-baseline"],
    },
    criteria: [
      {
        id: "E2-context",
        text: "新公司没有旧预测也能登记事实研究上下文。",
        status: "met",
        evidenceIds: ["E2-facts"],
      },
      {
        id: "E2-compile",
        text: "事实、假设与适用性足够时独立生成首版模型输入。",
        status: "pending",
        evidenceIds: ["E2-baseline"],
      },
      {
        id: "E2-holdout",
        text: "留出公司不依赖预置预测或证券专用捷径完成重放。",
        status: "pending",
        evidenceIds: ["E2-facts", "E2-baseline"],
      },
    ],
    evidence: [
      evidence(
        "E2-facts",
        "新公司事实研究入口",
        "src/value_investment_agent/application/research/value_enrichment_batch.py#L128-L158",
        "仅事实 ResearchCase 已实现，保留模型和假设缺口。",
      ),
      evidence(
        "E2-baseline",
        "当前编译的基线要求",
        "src/value_investment_agent/application/product/neutral_valuation_proposal.py#L662-L686",
        "已有构建路径仍依赖先前事实、场景及可用估值基线。",
      ),
    ],
  }),
  moduleRecord({
    id: "F1",
    lane: "value",
    title: "经营、现金、权益与估值内核",
    summary: "用一致的经营与资本路径计算股东价值，解释尾期和误差。",
    inputs: ["有版本的事实与经营假设", "再投资、分配、资本结构和折现合同"],
    outputs: [
      "年度经营／现金／权益路径与情景价值",
      "尾期依据、误差拆分、敏感性与阻塞项",
    ],
    currentOutcomes: [
      "v4 已实现显式股东现金尾期与解析合同。",
      "截断误差、数值误差与经济不确定性分别表达，不把计算收敛当研究可靠。",
    ],
    nextDeliverable:
      "关闭实际源包必跑、跨环境恢复和同版本消费者验证，保留独立反例。",
    dependencyIds: [],
    scope: ["既有支持模型的正确性", "不借调参生成理想估值或投资资格"],
    limitations: [
      "当前 CI 成功不能证明真实原件回放必跑。",
      "算术正确不消除经营假设和尾期经济条件的不确定性。",
    ],
    implementation: {
      status: "connected",
      summary: "v4 内核与已有候选消费者已接通。",
    },
    verification: {
      status: "partial",
      summary: "有新合同与工程回归；真实来源恢复验收仍需关闭。",
      evidenceIds: ["F1-kernel", "F1-test", "F1-real"],
    },
    criteria: [
      {
        id: "F1-tail",
        text: "尾期经济条件、显式现金与权益关系可审计，并拆分误差类别。",
        status: "met",
        evidenceIds: ["F1-kernel", "F1-test"],
      },
      {
        id: "F1-counter",
        text: "独立展开、边界和反例与解析值一致，失败条件保留。",
        status: "partial",
        evidenceIds: ["F1-test"],
      },
      {
        id: "F1-real",
        text: "真实两公司在可恢复原件上必跑，不能以 skipped 通过退出门。",
        status: "pending",
        evidenceIds: ["F1-real"],
      },
    ],
    evidence: [
      evidence(
        "F1-kernel",
        "v4 联合现金与资本路径",
        "src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py",
        "新尾期合同和误差边界的确定性实现。",
      ),
      evidence(
        "F1-test",
        "v4 尾期合同回归",
        "tests/test_terminal_economic_contract_v4.py",
        "数值和边界测试，不能替代真实经济研究验收。",
        "test",
      ),
      evidence(
        "F1-real",
        "真实源包回放开关",
        "tests/test_joint_cash_v4_two_company_real_replay.py#L58-L66",
        "JOINT_CASH_V4_REAL_REQUIRED 未开启时，缺原件可 skip。",
        "test",
      ),
    ],
  }),
  moduleRecord({
    id: "F2",
    lane: "value",
    title: "条件价格与持有退出判断",
    summary: "把有效研究与当前价格、事件和账户约束组合成可解释条件。",
    inputs: [
      "适用且有效的估值、研究与批准状态",
      "当前报价、期间分配／股本变化、事件和账户风险",
    ],
    outputs: [
      "价格条件、动作复核理由与仍缺前提",
      "持有、减仓、退出的论点及风险依据",
    ],
    currentOutcomes: [
      "已有价格吸引力、显式情景比例与动作规则。",
      "质量复利的价格吸引力要求当前价不高于熊情景且置信度非低；与另行登记的动作价格政策分别核对。",
    ],
    nextDeliverable:
      "用已有研究打通当前价格与事件有效性，补全估值兑现和账户风险等独立复核理由。",
    dependencyIds: ["E1", "S1", "S4"],
    scope: [
      "既有价格与动作引擎的条件交接",
      "可在数据就绪时前移，不等待全部 Agent 功能",
    ],
    limitations: [
      "当前低置信度研究候选不自动产生价格计划。",
      "现有减仓／退出规则依赖论点 WEAKENED／BROKEN，独立风险理由仍需补足。",
    ],
    implementation: {
      status: "partial",
      summary: "规则存在，完整业务条件链尚未闭合。",
    },
    verification: {
      status: "partial",
      summary: "价格与动作合同有据；当前真实数据和合法研究的联验仍需完成。",
      evidenceIds: ["F2-price", "F2-policy", "F2-action"],
    },
    criteria: [
      {
        id: "F2-align",
        text: "估值、报价、分配、股本与事件有效性在同一证券和版本下对齐。",
        status: "partial",
        evidenceIds: ["F2-price", "F2-policy"],
      },
      {
        id: "F2-reason",
        text: "持有、估值兑现、论点失效和账户风险分别给出可复核理由。",
        status: "partial",
        evidenceIds: ["F2-action"],
      },
      {
        id: "F2-human",
        text: "条件判断保留个人风险及人工决定门槛，永不输出订单。",
        status: "met",
        evidenceIds: ["F2-action", "F2-policy"],
      },
    ],
    evidence: [
      evidence(
        "F2-price",
        "价格吸引力条件",
        "src/value_investment_agent/price_attractiveness.py",
        "研究置信度、价格与合法模型前提。",
      ),
      evidence(
        "F2-policy",
        "显式价格政策",
        "src/value_investment_agent/domain/decision/value_price_policy.py",
        "情景与比例需显式给出，不隐含统一折价。",
      ),
      evidence(
        "F2-action",
        "动作与论点规则",
        "src/value_investment_agent/domain/decision/recommendation_rules.py",
        "当前减仓与退出的论点状态要求及 no_order 边界。",
      ),
    ],
  }),
  moduleRecord({
    id: "G1",
    lane: "value",
    title: "已有研究结果 API 与展示",
    summary: "让已有研究结果以同一版本进入证券详情和经营现金解释。",
    inputs: ["已登记研究候选和来源状态", "模型输出、限制、版本与阻塞原因"],
    outputs: [
      "公司详情、经营资本路径和研究材料",
      "新旧版本与未批准状态的清晰说明",
    ],
    currentOutcomes: [
      "证券详情、JointCapitalReview 和 v4 消费适配已有出口。",
      "研究输出与正式资格保持区分。",
    ],
    nextDeliverable:
      "在恢复的真实候选上核对 API、页面与研究版本，完成浏览器复核。",
    dependencyIds: ["E1"],
    scope: ["消费既有 Application 结果", "保持展示层不重算估值"],
    limitations: [
      "仓库实现和本地指针不证明线上服务已更新。",
      "页面展示数值不等于用户已验收或经济研究获准。",
    ],
    implementation: {
      status: "connected",
      summary: "已有研究与 v4 展示出口存在。",
    },
    verification: {
      status: "partial",
      summary: "API 回归已纳入 CI；当前源包与运行页面仍需联验。",
      evidenceIds: ["G1-service", "G1-view", "G1-test"],
    },
    criteria: [
      {
        id: "G1-version",
        text: "原件、模型、候选、API 和页面都指向同一研究版本。",
        status: "partial",
        evidenceIds: ["G1-service", "G1-test"],
      },
      {
        id: "G1-limit",
        text: "置信度、研究限定、缺失和旧版本均清晰显示。",
        status: "partial",
        evidenceIds: ["G1-view"],
      },
      {
        id: "G1-browser",
        text: "真实恢复样本完成现有页面的浏览器复核。",
        status: "pending",
        evidenceIds: ["G1-view", "G1-test"],
      },
    ],
    evidence: [
      evidence(
        "G1-service",
        "公司研究消费者",
        "src/value_investment_agent/application/product/company_research.py",
        "既有研究包与版本的应用层消费。",
      ),
      evidence(
        "G1-view",
        "经营与资本结果组件",
        "web/src/components/JointCapitalReview.tsx",
        "已存在的结果展示，不赋予审批权限。",
      ),
      evidence(
        "G1-test",
        "联合现金 API 回归",
        "tests/web_api/test_joint_cash_v3_api.py",
        "API 测试进入 Web 工作流，不替代真实页面验收。",
        "test",
      ),
    ],
  }),
  moduleRecord({
    id: "G2",
    lane: "value",
    title: "研究任务生命周期与操作",
    summary: "让用户看见、启动、停止和恢复同一个持久研究任务。",
    inputs: ["研究请求、输入版本与任务预算", "执行阶段、错误与用量事件"],
    outputs: ["可追踪任务状态与阶段产物", "开始／更新／取消／恢复操作结果"],
    currentOutcomes: [
      "已有只读研究状态 API、Agent 面板与运行产物。",
      "已有锁和输出复用基础，但不是完整持久任务状态机。",
    ],
    nextDeliverable:
      "先接持久任务与阶段检查点，再将开始、更新、取消和恢复操作接到既有页面。",
    dependencyIds: ["D1"],
    scope: ["现有 Web 内的任务操作", "同公司同输入去重与明确取消语义"],
    limitations: [
      "浏览器取消请求不等于取消后台任务。",
      "当前未形成可验证的启动／取消／恢复 API 闭环。",
    ],
    implementation: {
      status: "partial",
      summary: "展示与运行基础存在，新操作链尚未接通。",
    },
    verification: {
      status: "pending",
      summary: "持久任务和操作恢复需端到端验收。",
      evidenceIds: ["G2-api", "G2-view", "G2-state"],
    },
    criteria: [
      {
        id: "G2-id",
        text: "相同输入能复用任务，状态与阶段产物持久绑定。",
        status: "partial",
        evidenceIds: ["G2-state"],
      },
      {
        id: "G2-cancel",
        text: "取消和恢复作用于后台任务，不能只取消页面请求。",
        status: "pending",
        evidenceIds: ["G2-api", "G2-view"],
      },
      {
        id: "G2-flow",
        text: "开始／更新操作在原有公司页形成可观察、可恢复闭环。",
        status: "pending",
        evidenceIds: ["G2-api", "G2-view"],
      },
    ],
    evidence: [
      evidence(
        "G2-api",
        "现有只读研究 API",
        "src/value_investment_agent/presentation/web_api/agent_research_routes.py",
        "当前提供状态与单公司研究读取。",
      ),
      evidence(
        "G2-view",
        "既有 Agent 研究面板",
        "web/src/pages/DecisionDetail/AgentResearchPanel.tsx",
        "展示已有产物和请求状态，不能当作后台任务控制。",
      ),
      evidence(
        "G2-state",
        "研究状态投影",
        "src/value_investment_agent/application/research/agent_review/status.py",
        "读取已登记工作流的状态，尚非完整持久任务生命周期。",
      ),
    ],
  }),
  moduleRecord({
    id: "H1",
    lane: "hotspot",
    title: "热点发现与观察池",
    summary: "从市场和行业活跃度产生有限观察池，说明覆盖与缺失。",
    inputs: ["市场、行业与证券快照", "交易会话、分类来源与规则版本"],
    outputs: ["热点观察池及选择理由", "覆盖、日期和未评估项"],
    currentOutcomes: [
      "已有日度选择、当前观察池和候选结构消费路径。",
      "候选排序明确属于研究观察，不是策略准入。",
    ],
    nextDeliverable:
      "恢复新增开发后，先核对当前源、分类时点及观察池的完整覆盖。",
    dependencyIds: [],
    scope: ["保留既有观察能力", "新增开发当前暂停"],
    limitations: [
      "回溯取得的分类或新规则不能证明历史同时点可得。",
      "活跃度不等于可交易结构或预期收益。",
    ],
    implementation: {
      status: "connected",
      summary: "观察与候选读取已有实现；排程暂停不删除能力。",
    },
    verification: {
      status: "partial",
      summary: "有限结构包有证据，完整策略验证未证明。",
      evidenceIds: ["H1-select", "H1-validation"],
    },
    criteria: [
      {
        id: "H1-coverage",
        text: "展示整个观察池覆盖与遗漏，不把未评估当作无机会。",
        status: "met",
        evidenceIds: ["H1-select"],
      },
      {
        id: "H1-time",
        text: "当前规则、行业分类和市场快照有可证明的可用时点。",
        status: "partial",
        evidenceIds: ["H1-validation"],
      },
      {
        id: "H1-scope",
        text: "观察结果保持研究限定，不授予策略或账户资格。",
        status: "met",
        evidenceIds: ["H1-select"],
      },
    ],
    evidence: [
      evidence(
        "H1-select",
        "观察池候选选择",
        "src/value_investment_agent/application/hotspot/candidate_selection.py",
        "完整池覆盖、同会话核验与研究观察边界。",
      ),
      evidence(
        "H1-validation",
        "已冻结结构验证说明",
        "docs/current/closure-hotspot-validation.md",
        "明确规则／分类 PIT、成本、OOS 与 Shadow 尚未完成。",
        "document",
      ),
    ],
  }),
  moduleRecord({
    id: "H2",
    lane: "hotspot",
    title: "标的证据与多周期结构",
    summary: "为观察标的核对完整价格周期、关键位置和失效条件。",
    inputs: [
      "观察池证券和真实来源绑定",
      "日线、60 分钟、15 分钟完整行情及口径",
    ],
    outputs: [
      "结构、确认条件、关键价位和数据质量",
      "缺周期、冲突、过期或待确认原因",
    ],
    currentOutcomes: [
      "已有当前价格案例核验、完成 bar 与结构条件投影。",
      "缺失或无效案例保留 UNKNOWN，不冒充负面结构证据。",
    ],
    nextDeliverable:
      "恢复开发后，在当前完整同会话来源上关闭多周期和公司行为可比性验收。",
    dependencyIds: ["H1"],
    scope: ["既有多周期结构与原件消费", "不补造分钟线或执行时点"],
    limitations: [
      "有限案例不代表全池结构已评估。",
      "复权、现金事件与当前时点可比性仍需逐案例证明。",
    ],
    implementation: {
      status: "connected",
      summary: "结构案例与观察条件已有消费链。",
    },
    verification: {
      status: "partial",
      summary: "有限案例与反例保留，当前全覆盖未验收。",
      evidenceIds: ["H2-review", "H2-plan"],
    },
    criteria: [
      {
        id: "H2-bars",
        text: "只使用已完成且同一证券、同一会话的真实周期证据。",
        status: "partial",
        evidenceIds: ["H2-review"],
      },
      {
        id: "H2-conditions",
        text: "进入条件与失效条件可追溯，不将结构距离冒充盈利概率。",
        status: "partial",
        evidenceIds: ["H2-plan"],
      },
      {
        id: "H2-missing",
        text: "缺失、冲突与过期可见，不从日线推造分钟线。",
        status: "met",
        evidenceIds: ["H2-review"],
      },
    ],
    evidence: [
      evidence(
        "H2-review",
        "当前标的案例核验",
        "src/value_investment_agent/application/hotspot/current_case_review.py",
        "原件、身份、时点与当前性检查。",
      ),
      evidence(
        "H2-plan",
        "结构条件投影",
        "src/value_investment_agent/application/hotspot/price_action_case.py",
        "多周期结构与条件计划的应用层消费。",
      ),
    ],
  }),
  moduleRecord({
    id: "H3",
    lane: "hotspot",
    title: "独立策略准入与条件计划",
    summary: "独立检验热点策略，再交共享个人风险审查。",
    inputs: [
      "证券、事件、数据与结构证据",
      "策略验证、授权、执行约束和个人风险",
    ],
    outputs: ["观察／可进入风险复核状态", "有前提的计划与未满足门槛"],
    currentOutcomes: [
      "独立热点准入合同已存在，不要求价值估值或价值 G3。",
      "缺任一准入证据保留 OBSERVATION_ONLY，不给个人仓位。",
    ],
    nextDeliverable:
      "恢复开发后补齐冻结规则的严格时点、成本、样本外与自然时间 Shadow 证据。",
    dependencyIds: ["H2", "S1", "S4"],
    scope: ["版本化独立热点准入", "策略证据和个人风险分别验收"],
    limitations: [
      "现有结构验证明确 STRATEGY_VALIDATION=NOT_PROVEN。",
      "策略规则通过也不代替个人账户约束或人工决定。",
    ],
    implementation: {
      status: "implemented",
      summary: "独立准入与条件边界已实现。",
    },
    verification: {
      status: "blocked",
      summary: "策略有效性和正式准入证据尚未齐备；暂停仅是当前排程。",
      evidenceIds: ["H3-gates", "H3-proof"],
    },
    criteria: [
      {
        id: "H3-independent",
        text: "热点准入独立于价值估值，缺失门槛逐项拒绝。",
        status: "met",
        evidenceIds: ["H3-gates"],
      },
      {
        id: "H3-validation",
        text: "冻结规则完成严格时点、成本、未触碰样本外与自然时间 Shadow。",
        status: "blocked",
        evidenceIds: ["H3-proof"],
      },
      {
        id: "H3-risk",
        text: "通过策略复核后仍单独审查账户风险，计划不成为订单。",
        status: "met",
        evidenceIds: ["H3-gates"],
      },
    ],
    evidence: [
      evidence(
        "H3-gates",
        "独立热点准入合同",
        "src/value_investment_agent/domain/hotspot/independent_admission.py",
        "十类门槛与独立授权；明确无价值估值输入。",
      ),
      evidence(
        "H3-proof",
        "策略验证尚未证明",
        "docs/current/closure-hotspot-validation.md",
        "保留回溯扩展与未来规则版本限制，不虚报策略有效。",
        "document",
      ),
    ],
  }),
  moduleRecord({
    id: "H4",
    lane: "hotspot",
    title: "热点持有与退出生命周期",
    summary: "围绕实际持有的原始入场依据复核，而非只看新的观察池。",
    inputs: [
      "已核验的持有、成交与原始研究引用",
      "当前结构、现金事件和失效证据",
    ],
    outputs: ["原始依据与当前结构的连续性解释", "待复核风险与不可评估原因"],
    currentOutcomes: [
      "已有结构连续性和 owned-entry 消费适配。",
      "执行时点未证明时保持 NOT_ASSESSABLE，不推定持有或加仓许可。",
    ],
    nextDeliverable:
      "恢复开发后，以真实持有引用验收执行时点、原始依据和当前结构的连续性。",
    dependencyIds: ["H3", "S2", "S4"],
    scope: ["原始研究依据的持续复核", "保留实际成交和研究引用的区别"],
    limitations: [
      "当前 owned 适配明确不能证明交易前连续性。",
      "原始研究引用存在不等于精确执行时点已核验。",
    ],
    implementation: {
      status: "partial",
      summary: "只读连续性与持有引用已有实现，实际生命周期仍受时点约束。",
    },
    verification: {
      status: "partial",
      summary: "工程边界可核查，真实持有生命周期未最终验收。",
      evidenceIds: ["H4-review", "H4-owned"],
    },
    criteria: [
      {
        id: "H4-owned",
        text: "只从已核验持有上下文取得原始依据，不由当前候选推造持仓。",
        status: "met",
        evidenceIds: ["H4-owned"],
      },
      {
        id: "H4-time",
        text: "原始研究、实际成交和当前证据的精确时序可证明。",
        status: "blocked",
        evidenceIds: ["H4-owned"],
      },
      {
        id: "H4-exit",
        text: "退出与继续观察理由基于同一原始依据，并显示不可评估原因。",
        status: "partial",
        evidenceIds: ["H4-review"],
      },
    ],
    evidence: [
      evidence(
        "H4-review",
        "结构连续性复核",
        "src/value_investment_agent/application/hotspot/lifecycle_review.py",
        "基于原始案例与当前案例的只读比较。",
      ),
      evidence(
        "H4-owned",
        "已持有热点适配",
        "src/value_investment_agent/application/portfolio/owned_hotspot_lifecycle.py",
        "明确 EXACT_EXECUTION_TIME_NOT_PROVEN 与原始引用范围。",
      ),
    ],
  }),
  moduleRecord({
    id: "S1",
    lane: "shared",
    title: "组合、现金与双策略风险",
    summary: "共用账户事实，分别约束价值与热点预算，并合并看风险暴露。",
    inputs: [
      "本人确认的政策、现金、持仓和限额",
      "候选计划、费用、滑点与共同暴露",
    ],
    outputs: ["现金／策略／同股／行业约束结果", "可用空间、冲突和待补个人资料"],
    currentOutcomes: [
      "双策略现金、预算、集中度及费用滑点约束已有实现。",
      "输出是约束和上限，不是最优仓位。",
    ],
    nextDeliverable:
      "用已核验私人账户在既有入口完成组合约束和两策略共同暴露的用户复核。",
    dependencyIds: ["S2"],
    scope: ["共享风险底座与独立策略预算", "私人输入不进入公共源码"],
    limitations: [
      "缺账户事实不能给个人数量或默认风险比例。",
      "模型风险上限不等于可成交承诺或最优配置。",
      "因子标签聚合不等于统计相关性分析或完整组合压力测试。",
    ],
    implementation: {
      status: "connected",
      summary: "风险合同与双策略入口存在。",
    },
    verification: {
      status: "partial",
      summary: "工程约束可核对，实际账户与用户验收未记录完成。",
      evidenceIds: ["S1-risk", "S1-contract"],
    },
    criteria: [
      {
        id: "S1-separate",
        text: "两策略现金和风险预算分别核算，同时识别同股与共同因素暴露。",
        status: "met",
        evidenceIds: ["S1-risk"],
      },
      {
        id: "S1-private",
        text: "实际政策、现金和持仓有本人核验依据，缺失保持未接入。",
        status: "pending",
        evidenceIds: ["S1-contract"],
      },
      {
        id: "S1-cost",
        text: "费用、滑点、流动性与现金限制进入数量上限说明。",
        status: "partial",
        evidenceIds: ["S1-risk"],
      },
    ],
    evidence: [
      evidence(
        "S1-risk",
        "双策略风险实现",
        "src/value_investment_agent/domain/portfolio/dual_sleeve_risk.py",
        "分策略预算与共享暴露约束，不进行最优配置。",
      ),
      evidence(
        "S1-contract",
        "私人风险输入合同",
        "docs/current/dual-sleeve-risk-contract-v1.md",
        "个人资料、风险范围和公开／私人边界。",
        "document",
      ),
    ],
  }),
  moduleRecord({
    id: "S2",
    lane: "shared",
    title: "实际成交、持仓与对账",
    summary:
      "只用本人确认的成交更新持仓，保留基线、来源与成交审计历史；更正流程仍待补全。",
    inputs: ["私人账户基线与确认成交", "外部对账凭据、原始入场依据"],
    outputs: [
      "可重放持仓与现金变化",
      "对账状态与凭据（数值差异核对待接入）",
      "持有研究连续性和审计记录",
    ],
    currentOutcomes: [
      "已有私人组合服务、成交记录及基线加成交重放。",
      "持有连续性保留离开 shortlist 的公司，不只跟踪新候选。",
    ],
    nextDeliverable: "明确外部凭据对账与本地重放差异，补全更正及现金事件交接。",
    dependencyIds: [],
    scope: ["本人确认成交，不自动下单", "复用私人日志及持有上下文"],
    limitations: [
      "当前对账不等于自动核对券商余额。",
      "记录类型尚未覆盖分红、税、外部现金流和拆股等所有账户事件。",
    ],
    implementation: {
      status: "connected",
      summary: "实际输入记录与持仓重放已有服务。",
    },
    verification: {
      status: "partial",
      summary: "本地持仓路径可检查；完整账户对账仍需真实资料验收。",
      evidenceIds: ["S2-service", "S2-held"],
    },
    criteria: [
      {
        id: "S2-fill",
        text: "计划与实际成交分别记录，持仓由确认事实重放。",
        status: "met",
        evidenceIds: ["S2-service"],
      },
      {
        id: "S2-reconcile",
        text: "对账差异与外部凭据明确对应，不能用本地自洽代替券商核验。",
        status: "partial",
        evidenceIds: ["S2-service"],
      },
      {
        id: "S2-held",
        text: "离开筛选名单的持仓继续保留研究依据与跟踪。",
        status: "met",
        evidenceIds: ["S2-held"],
      },
    ],
    evidence: [
      evidence(
        "S2-service",
        "私人组合服务",
        "src/value_investment_agent/application/portfolio/private_portfolio_service.py",
        "记录类型、确认成交、本地基线重放和对账边界。",
      ),
      evidence(
        "S2-held",
        "持有研究连续性",
        "src/value_investment_agent/application/portfolio/held_continuity.py",
        "持有公司不因离开 shortlist 而从跟踪中消失。",
      ),
    ],
  }),
  moduleRecord({
    id: "S3",
    lane: "shared",
    title: "分红、税务与投资收益",
    summary: "区分公司现金分配能力、本人实际到账与账户投资收益。",
    inputs: [
      "公司分配证据、账户持有批次与现金事件",
      "税费口径、外部现金流和估值路径",
    ],
    outputs: [
      "分红与税务估算及适用范围",
      "研究账户收益口径与未覆盖现金事件说明",
    ],
    currentOutcomes: [
      "分红税自然月／年边界与账户证券 FIFO 批次计算已有组件。",
      "账户路径指标存在，但假设没有外部现金流。",
    ],
    nextDeliverable:
      "把分红和税费事件接入实际账本，并明确有外部现金流时的收益口径。",
    dependencyIds: ["S2", "F1"],
    scope: [
      "复用分配、税务及收益计算",
      "不将预期分红当作到账，也不重复计入估值",
    ],
    limitations: [
      "税务计算组件尚不等于实际账本扣款。",
      "当前路径收益指标不能直接解释含外部现金流的真实账户表现。",
    ],
    implementation: {
      status: "partial",
      summary: "计算组件较完整，实际现金账本连接仍缺。",
    },
    verification: {
      status: "partial",
      summary: "组件与边界可检查；到账、补税和收益对账尚未整体验收。",
      evidenceIds: ["S3-tax", "S3-lots", "S3-return"],
    },
    criteria: [
      {
        id: "S3-lots",
        text: "税务持有期和 FIFO 绑定正确账户与证券，不混用批次。",
        status: "met",
        evidenceIds: ["S3-tax", "S3-lots"],
      },
      {
        id: "S3-cash",
        text: "实际到账和扣税形成可对账现金事件，不只停留在估算。",
        status: "pending",
        evidenceIds: ["S3-lots"],
      },
      {
        id: "S3-return",
        text: "含外部现金流的收益口径明确，分红不在估值中重复计价。",
        status: "partial",
        evidenceIds: ["S3-return"],
      },
    ],
    evidence: [
      evidence(
        "S3-tax",
        "分红税持有期计算",
        "src/value_investment_agent/dividend_tax.py",
        "自然月和自然年边界的组件实现，不构成税务个案核定。",
      ),
      evidence(
        "S3-lots",
        "账户证券分红税批次",
        "src/value_investment_agent/dividend_tax_lots.py",
        "FIFO 与批次隔离，尚需接实际现金记录。",
      ),
      evidence(
        "S3-return",
        "账户路径收益指标",
        "src/value_investment_agent/account_path_metrics.py",
        "存在无外部现金流假设，不能直接泛化为任意账户收益。",
      ),
    ],
  }),
  moduleRecord({
    id: "S4",
    lane: "shared",
    title: "事件、变化与持续跟踪",
    summary: "发现新事实后只重新研究受影响的依赖，保留原始入场依据。",
    inputs: [
      "新公告、财报、分配和资本事件",
      "研究版本、持有依据与事件覆盖窗口",
    ],
    outputs: ["事件待复核队列与受影响依赖", "更新、风险复核或继续等待的理由"],
    currentOutcomes: [
      "已有事件材料性桥接、有限依赖失效和持有持续跟踪。",
      "价格变化与内在价值变化分开，标题线索不直接批准材料性。",
    ],
    nextDeliverable:
      "核对当前事件窗口完整性，联验关键变化对研究、价格和持有判断的有界更新。",
    dependencyIds: ["A", "S2"],
    scope: ["现有事件与依赖机制", "当前性和完整覆盖，不新增生产通知服务"],
    limitations: [
      "新取得原件不等于事件影响已批准。",
      "历史事件桥接或回放不能证明持续监控服务已运行。",
    ],
    implementation: {
      status: "connected",
      summary: "事件桥接与持有跟踪已有模块，持续运行需独立证据。",
    },
    verification: {
      status: "partial",
      summary: "工程机制可复用，当前窗口与业务影响联验仍需完成。",
      evidenceIds: ["S4-materiality", "S4-held", "S4-contract"],
    },
    criteria: [
      {
        id: "S4-time",
        text: "事件发生、披露可用、抓取时间与覆盖缺口分别记录。",
        status: "partial",
        evidenceIds: ["S4-contract"],
      },
      {
        id: "S4-invalidate",
        text: "只失效受影响依赖，报价变化不自动重算内在价值。",
        status: "met",
        evidenceIds: ["S4-materiality"],
      },
      {
        id: "S4-holding",
        text: "新证据与原始持有论点连续比较，不覆盖入场历史。",
        status: "partial",
        evidenceIds: ["S4-held"],
      },
    ],
    evidence: [
      evidence(
        "S4-materiality",
        "事件材料性桥接",
        "src/value_investment_agent/m5_materiality_bridge.py",
        "消费已有材料性判断并映射有界影响，不自动批准事件。",
      ),
      evidence(
        "S4-held",
        "持有连续性消费者",
        "src/value_investment_agent/application/portfolio/held_continuity.py",
        "持续使用持有与原始研究依据。",
      ),
      evidence(
        "S4-contract",
        "架构中的事件和版本合同",
        "docs/architecture.md",
        "时间、依赖失效与生产运营边界；文档合同不等于部署证明。",
        "document",
      ),
    ],
  }),
  moduleRecord({
    id: "W1",
    lane: "shared",
    title: "既有 Web 与状态解释",
    summary: "在同一工作台解释两策略、账户、事件与开发范围。",
    inputs: ["已有应用服务的业务结果", "版本、日期、限制和本次模块审计快照"],
    outputs: [
      "今日、机会、决策、公司、组合和事件页面",
      "可点击架构、模块证据与下一交付",
    ],
    currentOutcomes: [
      "既有 Web 页面、共享 Workbench 和状态展示已存在。",
      "本次新增架构进度页只消费静态审计数据，不触发研究或改变业务结果。",
    ],
    nextDeliverable:
      "完成本页与现有导航的集成、交互验证，再由用户确认是否便于控制开发方向。",
    dependencyIds: ["G1", "S1", "S2", "S3", "S4"],
    scope: ["现有 Web 中增加解释与导航", "固定版本审计，不伪造实时完成度"],
    limitations: [
      "本页最后审阅日期不等于运行服务数据更新时间。",
      "全绿 CI 不证明每个模块具备投资可用性或用户已接受。",
    ],
    implementation: {
      status: "connected",
      summary: "既有 Web 可复用；本页交付状态以本次分支检查为准。",
    },
    verification: {
      status: "partial",
      summary: "基线 Web CI 成功；新增页面需本次独立检查与用户确认。",
      evidenceIds: ["W1-shell", "W1-ci"],
    },
    criteria: [
      {
        id: "W1-separate",
        text: "实现、验证、用户确认三个状态分别显示，所有模块初始均未确认。",
        status: "pending",
        evidenceIds: ["W1-shell"],
      },
      {
        id: "W1-navigation",
        text: "可从流程进入模块、依赖、验收和固定版本证据。",
        status: "pending",
        evidenceIds: ["W1-shell"],
      },
      {
        id: "W1-no-action",
        text: "页面只解释和导航，不产生研究批准、投资资格或订单。",
        status: "pending",
        evidenceIds: ["W1-shell"],
      },
    ],
    evidence: [
      evidence(
        "W1-shell",
        "既有工作台入口",
        "web/src/components/Workbench.tsx",
        "新页集成基于现有外壳；此固定基线链接不包含本次新增页面。",
      ),
      {
        id: "W1-ci",
        label: "本次审计基线 Web CI",
        kind: "ci",
        url: `${repository}/actions/runs/40659010020/job/122717042700`,
        summary:
          "固定基线 Web 成功；不是新增架构页的测试结果，也不证明线上部署。",
      },
    ],
  }),
];

// Business handoffs, not an executable DAG or a claim that every gate is ready.
// Feedback edges deliberately preserve continuing research and holding review.
export const projectConnections: ProjectConnection[] = [
  { from: "A", to: "B", label: "原件与事实", kind: "flow" },
  { from: "B", to: "C", label: "研究对象与缺口", kind: "flow" },
  { from: "C", to: "D2", label: "画像与方法", kind: "flow" },
  { from: "D1", to: "D2", label: "有界执行", kind: "dependency" },
  { from: "D2", to: "E2", label: "新公司经营假设", kind: "flow" },
  { from: "E2", to: "F1", label: "首版合法输入", kind: "flow" },
  { from: "F1", to: "E1", label: "已有研究重算", kind: "flow" },
  { from: "E1", to: "G1", label: "版本化研究结果", kind: "flow" },
  { from: "E1", to: "F2", label: "研究与估值前提", kind: "flow" },
  { from: "D1", to: "G2", label: "任务与阶段产物", kind: "flow" },
  { from: "H1", to: "H2", label: "观察标的", kind: "flow" },
  { from: "H2", to: "H3", label: "结构与证据", kind: "flow" },
  { from: "H3", to: "H4", label: "独立准入与原始计划", kind: "flow" },
  { from: "S2", to: "S1", label: "真实账户事实", kind: "flow" },
  { from: "S1", to: "F2", label: "价值账户约束", kind: "dependency" },
  { from: "S1", to: "H3", label: "热点账户约束", kind: "dependency" },
  { from: "S2", to: "H4", label: "已核验持有与成交", kind: "dependency" },
  { from: "S2", to: "S3", label: "持有批次与现金事实", kind: "flow" },
  { from: "S4", to: "F2", label: "事件有效性", kind: "feedback" },
  { from: "S4", to: "D2", label: "需要重开的研究问题", kind: "feedback" },
  { from: "S4", to: "H4", label: "结构与事件变化", kind: "feedback" },
  { from: "G1", to: "W1", label: "已有研究结果", kind: "flow" },
  { from: "H4", to: "W1", label: "热点观察与连续性", kind: "flow" },
  { from: "G2", to: "W1", label: "任务操作与状态", kind: "flow" },
];
