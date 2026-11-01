import { useState } from "react";
import { Link } from "@umijs/max";
import { Alert, Card, Descriptions, Space, Tag, Typography } from "antd";
import { Workbench } from "../../components/Workbench";
import {
  catalog,
  review,
  valueVerticalScope,
  valueMainModuleIds,
  valueSharedModuleIds,
  type Stage,
  type StrategyKey,
} from "../../config/strategyArchitecture.v1";
import "./architecture.css";

export function CStatusAxes({ stage }: { stage: Stage }) {
  if (stage.id !== "C" || !stage.progress) return null;
  return (
    <span aria-label="C模块四轴状态">
      <Tag color="blue">{stage.engineeringStatus}</Tag>
      <Tag color="blue">{stage.evidenceStatus}</Tag>
      <Tag color="gold">{stage.progress.deployment}</Tag>
      <Tag>{stage.progress.acceptance}</Tag>
    </span>
  );
}

export function StageButton({
  stage,
  selected,
  onSelect,
}: {
  stage: Stage;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className="architecture-node"
      aria-pressed={selected}
      aria-controls="architecture-detail"
      onClick={() => onSelect(stage.id)}
    >
      <strong>{stage.title}</strong>
      <code>{stage.id}</code>
      <span>{stage.question}</span>
      <small>规则理由：{stage.ruleWhy}</small>
      <span className="architecture-node-status">
        {stage.id === "C" ? (
          <CStatusAxes stage={stage} />
        ) : (
          <>
            <Tag color="blue">工程：{stage.engineeringStatus}</Tag>
            <Tag color="gold">证据：{stage.evidenceStatus}</Tag>
          </>
        )}
      </span>
      <span>{stage.shortStatus}</span>
    </button>
  );
}
export function NativeContractDetail({ stage }: { stage: Stage }) {
  const contract = stage.nativeContract;
  if (
    !contract &&
    (valueSharedModuleIds as readonly string[]).includes(stage.id)
  )
    return (
      <p>共享支持模块：保留现有输入输出与消费者，不虚构主链八方法合同。</p>
    );
  if (!contract)
    return (
      <p>
        原生输入/输出schema及8方法能力：等待Root合同文件接入；未读取不推定能力或运行状态。
      </p>
    );
  return (
    <section aria-label="原生模块合同与方法能力">
      <p>
        合同来源：<code>{contract.source}</code>
        ；能力状态是源码合同，不是本次运行结果或经济批准。原生已实现不等于统一wrapper已完成。
      </p>
      <p>
        源码审计基线：<code>{contract.baseline || "未提供"}</code>
        ；未在本目录读取运行状态。
      </p>
      <p>标准wrapper schema引用不替代原生输入输出及金融校验。</p>
      {contract.phase1Delta && (
        <section aria-label="阶段1源码增量">
          <h4>阶段1源码增量 · 本轮源码未部署</h4>
          <p>
            {contract.phase1Delta.scope} · {contract.phase1Delta.deployment}
          </p>
          <ul>
            {contract.phase1Delta.implementation.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
          <p>实现边界：{contract.phase1Delta.boundary}</p>
        </section>
      )}
      {[
        { title: "原生输入", refs: contract.nativeInputs || [] },
        { title: "原生输出", refs: contract.nativeOutputs || [] },
        { title: "原生入口", refs: contract.entryRefs },
        { title: "输入schema引用", refs: contract.inputSchemaRefs },
        { title: "输出schema引用", refs: contract.outputSchemaRefs },
      ].map(({ title, refs }) => (
        <div key={title}>
          <strong>{title}</strong>
          <ul>
            {refs.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <ul>
        {Object.entries(contract.methods).map(([method, status]) => (
          <li key={method}>
            <code>{method}</code>：{status}（
            {
              {
                DESIGNED: "已设计",
                IMPLEMENTED: "已实现",
                PARTIAL: "部分实现",
              }[status]
            }
            ）
            {contract.rawMethods?.[method] && (
              <small> · 原始合同状态：{contract.rawMethods[method]}</small>
            )}
            {contract.methodEvidence?.[method] && (
              <details>
                <summary>方法依据与范围</summary>
                <p>{contract.methodEvidence[method].scope}</p>
                <ul>
                  {contract.methodEvidence[method].native_refs.map((ref) => (
                    <li key={ref}>
                      <code>{ref}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
      <p>
        必需依赖（all_of/any_of/external，非所有关联共同前置）：
        <code>{contract.requiredDependencies}</code>
      </p>
      <p>
        审计证据：<code>{contract.evidence}</code>
      </p>
    </section>
  );
}
export function StageDetail({ stage }: { stage: Stage }) {
  return (
    <section
      id="architecture-detail"
      aria-label="所选模块详情"
      aria-live="polite"
    >
      <Card title={stage.title}>
        <CStatusAxes stage={stage} />
        <NativeContractDetail stage={stage} />
        <Descriptions
          column={1}
          size="small"
          bordered
          items={[
            {
              key: "id",
              label: "稳定模块 ID",
              children: <code>{stage.id}</code>,
            },
            ...(stage.progress
              ? [
                  {
                    key: "consumer",
                    label: "实际消费",
                    children: stage.progress.consumer,
                  },
                  {
                    key: "realData",
                    label: "真实数据验证",
                    children: stage.progress.realData,
                  },
                  {
                    key: "economic",
                    label: "经济批准",
                    children: stage.progress.economic,
                  },
                  {
                    key: "deployment",
                    label: "运行部署",
                    children: stage.progress.deployment,
                  },
                  {
                    key: "acceptance",
                    label: "用户确认",
                    children: stage.progress.acceptance,
                  },
                ]
              : []),
            {
              key: "input",
              label:
                stage.id === "C"
                  ? "已验输入（固定五家范围）"
                  : stage.progress
                    ? "目标输入"
                    : "输入",
              children: stage.input,
            },
            {
              key: "output",
              label:
                stage.id === "C"
                  ? "已验输出（固定五家范围）"
                  : stage.progress
                    ? "目标输出（不代表已实现）"
                    : "输出",
              children: stage.output,
            },
            ...(stage.channels
              ? [
                  {
                    key: "channels",
                    label: "四通道规则理由",
                    children: (
                      <ul>
                        {stage.channels.map((channel) => (
                          <li key={channel.id}>
                            <strong>{channel.title}</strong>：{channel.why}
                          </li>
                        ))}
                      </ul>
                    ),
                  },
                ]
              : []),
            { key: "why", label: "规则为什么", children: stage.ruleWhy },
            {
              key: "code",
              label: "模块实现 · 源码/交付复核",
              children: stage.implementation,
            },
            {
              key: "milestone",
              label: "里程碑 · 人工整理",
              children: stage.milestone,
            },
            {
              key: "existing",
              label: "已记录证据",
              children: (
                <>
                  {stage.existingEvidence}
                  <p className="architecture-source">{stage.evidenceSource}</p>
                </>
              ),
            },
            { key: "required", label: "仍需证据", children: stage.evidence },
            {
              key: "runtime",
              label: "运行证据状态",
              children:
                stage.id === "A" ? (
                  <Link to="/system">
                    查看A模块公开来源实测状态（只读；按请求范围）
                  </Link>
                ) : stage.id === "B" ? (
                  <Link to="/daily">
                    查看B模块真实候选与覆盖范围（只读；保留资料日期）
                  </Link>
                ) : stage.id === "C" ? (
                  <Link to="/daily">
                    从真实候选进入公司，查看企业画像与模型依据
                  </Link>
                ) : (
                  "本目录尚未接运行reader / NOT_CONNECTED；不否认既有API和页面消费者，静态快照不推定当前运行结果。"
                ),
            },
            { key: "next", label: "下一步", children: stage.nextStep },
            { key: "boundary", label: "停止边界", children: stage.boundary },
            {
              key: "modules",
              label: "实现定位（仓库相对路径）",
              children: (
                <ul>
                  {stage.modules.map((path) => (
                    <li key={path}>
                      <code>{path}</code>
                    </li>
                  ))}
                </ul>
              ),
            },
          ]}
        />
      </Card>
    </section>
  );
}
export function ValuePlanOverview() {
  return (
    <section aria-label="新方案与当前架构对标" className="value-plan">
      <Card title="先看清整条业务链">
        <p>
          方案包含11个价值主链模块与5个共享支持模块。旧页面按9个粗阶段展示；本页改为逐模块对标，未增加新的选股或估值公式。
        </p>
        <section aria-label="本轮纵向链与扩展边界">
          <h3>本轮仅推进：{valueVerticalScope.focus}</h3>
          <p>{valueVerticalScope.accepted}</p>
          <p>{valueVerticalScope.currentFollowup}</p>
          <section aria-label="当前阻断与后续纵向验收">
            <h4>当前阻断与后续纵向验收</h4>
            <Alert type="warning" message={valueVerticalScope.currentBlocker} />
            <ul>
              {valueVerticalScope.nextRequired.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <section aria-label="未来扩展非本轮前置">
            <h4>未来扩展（非本轮前置，不计作当前阻断）</h4>
            <ul>
              {valueVerticalScope.futureExtensions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <p>{valueVerticalScope.boundary}</p>
          <p>
            当前依据：<code>{valueVerticalScope.evidenceSource}</code>
            ；新增现金/条件估值回执：
            <code>{valueVerticalScope.cashEvidenceSource}</code>
            （静态回执，非实时进度）
          </p>
        </section>
        <div className="value-plan-lanes" aria-label="业务依赖图">
          <div>
            <strong>发现与研究</strong>
            <p>
              A 官方证据 → B 四通道候选 → C 企业画像 → D1 受限执行 + D2
              假设与反证
            </p>
          </div>
          <div>
            <strong>两条输入路径，共用计算</strong>
            <p>已有候选 → E1 更新重放 → F1 经营、现金与估值</p>
            <p>无旧估值 → E2 首次编译 → F1 同一内核（不要求先有E1）</p>
          </div>
          <div>
            <strong>价格与用户决策</strong>
            <p>
              F1 → F2 五维当前口径核对 → G1 公司研究；S1 组合风险 + S2
              真实持仓共同约束个人复核。
            </p>
          </div>
          <div>
            <strong>持续循环</strong>
            <p>
              S3 实际分红与收益；S4 事件与原始论点 → E1 重开研究；G2 管任务，W1
              展示进度与证据。
            </p>
          </div>
        </div>
        <Alert
          type="info"
          message="C工程闭环完成、固定五家验收通过并冻结职责；部署待验收，用户尚未确认。两家既有条件研究与两家输入待补路由、银行拒绝均不等于自动研究所有新公司或取得买卖资格。"
        />
        <details>
          <summary>方案与当前实现的关键差异、验收依据</summary>
          <ul>
            <li>
              A/B：来源、筛选与覆盖范围按各自证据核验，候选不是买入名单。C仅完成固定五家的有限官方完整段落审核与合同验收，不是通用自动分类器，也不是经济质量批准。
            </li>
            <li>
              D1/D2：000568最新rt-eac任务三角色成功，4次调用含1次反证缺字段拒绝后恢复；96条官方来源，21项经营驱动范围（7×3），6项增长/税前利润率由代码派生，不是模型直接填值；原9项资本UNKNOWN不升级已证；新现金/估值仅复用另行绑定的条件政策。量价成本表来源为H1第11/14/12页，锁定H12026→H12027，历史同比FY只对FY、H1只对H1。独立冷复算3×128角点与12条重审阈值一致，工程及条件压力分析算术已验收；128角点是压力包络，不是概率。AI原文两类误述（产品结构向高档集中、母现金少10倍）仅拒这些文字，驱动桥不消费它们；Event仍不是当前完整事件扫描。旧rt-c40经济拒绝与原始回执保留，不覆盖旧raw或当作本任务。
            </li>
            <li>
              E1/F1/G1：已有600519、600887真实条件研究链。年度现金、留存和终值可复算，但预测不因此成为事实。
            </li>
            <li>
              F2/S4：已定位股本、分红及经营事件；跨日公司行动连续性、经济影响与正式复核尚未闭合，不能输出当前低估结论。
            </li>
            <li>
              S1/S2/S3：有风险、账本和计算合同；真实账户、外部对账及实际税后分红闭环需独立验收，本页不访问私人资料。
            </li>
            <li>
              W1：/project保留模块地图，/strategy/value进入价值研究工作台；路由接通不代表生产部署验收，也不代替用户确认。
            </li>
          </ul>
          <p>
            依据：用户方案《A股价值投资策略科学论证_模块化闭环对标方案_20261030.md》第4–10节，与d01923cd源码及唯一执行台账对照。理论依据与开源参考不等于本策略已取得超额收益证据；本轮未重新认证方案引用的法规或研究结论。
          </p>
          <p>
            验收分别看：数据/时点 → 财务经济 → 可复核研究 → 价格可比 → 组合约束
            → 实际产品。工程通过不自动升级经济批准或用户确认。
          </p>
        </details>
        <p>
          C职责冻结，后续顺序为D1受限执行 → D2经营假设与反证 →
          E2首次编译。不因C完成而推定已闭环。D1真实执行接线、D2新假设生成和E2首输入分别展示输入、输出与证据；真实三角色工程与条件压力分析算术已验收，不等于未来参数已证明、主估值、E2批准、G3或交易。首要决定性缺口是验证参数经济适用性及资本/现金资料，不重试模型凑通过。12条重审阈值来自同一bounds，须同期间、同范围、同比较基线严格越界；同值不触发，不能混用历史阈值。比率单位示例：0.10=10%，仅单位说明，本页不重算。
        </p>
        <Space wrap>
          <Link to="/decisions/600519?strategy=value">
            600519 实际研究与未批准条件草案
          </Link>
          <Link to="/decisions/600887?strategy=value">600887 实际研究</Link>
          <Link to="/decisions/000568?strategy=value">
            000568 真实Agent研究结果（条件现金/估值已接，待终验）
          </Link>
          <Link to="/system">查看实际运行版本与数据状态</Link>
        </Space>
        <p>
          H1–H4
          热点通道：保留既有发现、结构、独立验证与跟踪成果；本轮暂停新增开发，未并入价值门禁。
          <Link to="/strategy/hotspot">查看原热点流程与未证明边界</Link>
        </p>
      </Card>
    </section>
  );
}
export function ArchitectureView({ strategy }: { strategy: StrategyKey }) {
  const flow = catalog[strategy];
  const [selected, setSelected] = useState(flow.stages[0].id);
  const stage =
    flow.stages.find((item) => item.id === selected) || flow.stages[0];
  const selectStage = (id: string) => {
    setSelected(id);
    if (typeof document !== "undefined") {
      document
        .getElementById("architecture-detail")
        ?.scrollIntoView?.({ block: "start" });
    }
  };
  return (
    <>
      <Typography.Title level={2}>{flow.title}</Typography.Title>
      <Typography.Paragraph>{flow.summary}</Typography.Paragraph>
      <Alert
        type="warning"
        showIcon
        message="静态复核快照 · 非实时进度 · 非策略认证"
      />
      <details className="architecture-source">
        <summary>复核日期 {review.reviewedAt} · 查看版本与证据边界</summary>
        <p>{review.disclaimer}</p>
        <p>
          {review.version} · reviewed baseline <code>{review.baseline}</code>
          <br />
          复核日期：{review.reviewedAt} · 里程碑来源：
          <code>{review.ledger}</code>
          。最近交付说明单独标注，不代表当前运行结果。
        </p>
        <Space wrap>
          <Tag>人工整理 / {review.mode}</Tag>
          <Tag>运行证据 / {review.runtimeEvidence}</Tag>
          <Tag>action=no_order</Tag>
        </Space>
      </details>
      <nav aria-label="策略及现有工作入口" className="architecture-links">
        <Link to="/strategy/value">价值策略</Link>
        {strategy === "value" && (
          <Link to="/project">项目进度（同一模块目录）</Link>
        )}
        <Link to="/strategy/hotspot">热点策略</Link>
        <Link to="/daily">今日决策</Link>
        <Link to="/daily">选取真实条目 → 决策详情</Link>
        <Link to="/portfolio">组合风险</Link>
        <Link to="/history">交易复盘 / 300059历史样本</Link>
        <Link to="/system">数据状态</Link>
      </nav>
      <p>
        节点徽标是人工整理的工程与证据状态；“真实算术已核”仅指台账记载的历史样本，不代表策略有效。点击节点查看实现、证据和下一步；键盘
        Tab 移动，Enter /
        空格选择。箭头表示目标流转，不表示已通过。价值模块关联不代表共同前置：E1/E2二选一进入F1，S1/S2仅约束个人决策，不阻塞公开研究。
      </p>
      {strategy === "value" && <ValuePlanOverview />}
      {(strategy === "value"
        ? [
            {
              title: "价值主链（11个模块）",
              stages: flow.stages.filter((item) =>
                (valueMainModuleIds as readonly string[]).includes(item.id),
              ),
            },
            {
              title: "共享支持（5个模块，非公开研究共同前置）",
              stages: flow.stages.filter((item) =>
                (valueSharedModuleIds as readonly string[]).includes(item.id),
              ),
            },
          ]
        : [{ title: "完整策略阶段总览", stages: flow.stages }]
      ).map((group) => (
        <section key={group.title} aria-label={group.title + "分组"}>
          <h3>{group.title}</h3>
          <nav aria-label={group.title} className="architecture-overview">
            {group.stages.map((item, index) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={stage.id === item.id}
                onClick={() => selectStage(item.id)}
                aria-controls="architecture-detail"
              >
                <strong>
                  {index + 1}. {item.title}
                </strong>
                <span>
                  {item.id === "C" ? (
                    <CStatusAxes stage={item} />
                  ) : (
                    <>
                      {item.engineeringStatus} · {item.evidenceStatus}
                    </>
                  )}
                </span>
                <small>
                  {item.dependencies.length
                    ? (strategy === "value" ? "关联模块：" : "依赖：") +
                      item.dependencies
                        .map(
                          (id) =>
                            flow.stages.find((s) => s.id === id)?.title || id,
                        )
                        .join("、")
                    : "流程起点"}
                </small>
              </button>
            ))}
          </nav>
        </section>
      ))}
      <div className="architecture-layout">
        <section aria-label="策略流程图">
          <ol className="architecture-flow">
            {(strategy === "value" ? [stage] : flow.stages).map((item) => (
              <li key={item.id}>
                {item.dependencies.length > 0 && (
                  <div className="architecture-dependencies">
                    {strategy === "value" ? "关联模块（非共同前置）" : "依赖"}{" "}
                    {item.dependencies.map((id) => (
                      <button
                        type="button"
                        key={id}
                        onClick={() => selectStage(id)}
                      >
                        {id}
                      </button>
                    ))}{" "}
                    <span aria-hidden="true">↓</span>
                  </div>
                )}
                <StageButton
                  stage={item}
                  selected={stage.id === item.id}
                  onSelect={selectStage}
                />
              </li>
            ))}
          </ol>
        </section>
        <div className="architecture-detail-column">
          <StageDetail stage={stage} />
          <Card
            title="每个判断节点的停止分支"
            className="architecture-branches"
          >
            <ul>
              <li>资料不足 → 无法评价：补证后重新核验。</li>
              <li>条件不符 → 不操作：保留原因与重开条件。</li>
              <li>通过 → 人工复核：仍需相应规则批准与共享组合风险核验。</li>
            </ul>
            <p>共享终点未闭合。点击不批准策略、规则或投资决定；不生成订单。</p>
          </Card>
        </div>
      </div>
      <footer className="architecture-source">
        交互参考：
        <a
          href="https://github.com/xyflow/xyflow"
          target="_blank"
          rel="noreferrer"
        >
          React Flow 官方仓库
        </a>{" "}
        ·
        <a
          href="https://github.com/mermaid-js/mermaid"
          target="_blank"
          rel="noreferrer"
        >
          Mermaid 官方仓库
        </a>
        。
        仅借鉴节点选择和流程依赖表达，使用原生按钮与箭头，无代码复制或新增依赖。
      </footer>
    </>
  );
}
export default function StrategyArchitecture({
  strategy,
}: {
  strategy: StrategyKey;
}) {
  return (
    <Workbench>
      <ArchitectureView key={strategy} strategy={strategy} />
    </Workbench>
  );
}
