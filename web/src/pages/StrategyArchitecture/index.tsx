import { useState } from "react";
import { Link } from "@umijs/max";
import { Alert, Card, Descriptions, Space, Tag, Typography } from "antd";
import { Workbench } from "../../components/Workbench";
import {
  catalog,
  review,
  type Stage,
  type StrategyKey,
} from "../../config/strategyArchitecture.v1";
import "./architecture.css";

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
        <Tag color="blue">工程：{stage.engineeringStatus}</Tag>
        <Tag color="gold">证据：{stage.evidenceStatus}</Tag>
      </span>
      <span>{stage.shortStatus}</span>
    </button>
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
              label: stage.progress ? "目标输入" : "输入",
              children: stage.input,
            },
            {
              key: "output",
              label: stage.progress ? "目标输出（不代表已实现）" : "输出",
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
                ) : (
                  "未接入 / NOT_CONNECTED；静态快照不推定当前运行结果。"
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
          方案覆盖16个价值/共享模块。旧页面按9个粗阶段展示；本页改为逐模块对标，未增加新的选股或估值公式。
        </p>
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
          message="目前能看到两家公司条件研究，不等于自动研究所有新公司，也不等于已形成当前买卖资格。"
        />
        <details>
          <summary>方案与当前实现的关键差异、验收依据</summary>
          <ul>
            <li>
              A/B/C：已有来源、筛选和路由，仍需核实冲突传播、覆盖率和画像证据。候选不是买入名单。
            </li>
            <li>
              D1/D2/E2/G2：已有模型接口、研究发现和事实上下文；从零自动编译首版研究与持久任务生命周期仍是缺口。
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
              W1：本页使用同一模块目录；当前工作树没有已接入的/project目录，未合入分支不计部署。
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
          后续顺序：B 队列正确性 → F2/S4 当前口径 → C/D2/E2 新公司研究 → S1–S4
          持仓与现金闭环。该顺序是对标建议；A已接通本轮受限来源闭环，其余模块尚不代表完成。
        </p>
        <Space wrap>
          <Link to="/decisions/600519?strategy=value">
            600519 实际研究与未批准条件草案
          </Link>
          <Link to="/decisions/600887?strategy=value">600887 实际研究</Link>
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
      <nav aria-label="完整策略阶段总览" className="architecture-overview">
        {flow.stages.map((item, index) => (
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
              {item.engineeringStatus} · {item.evidenceStatus}
            </span>
            <small>
              {item.dependencies.length
                ? (strategy === "value" ? "关联模块：" : "依赖：") +
                  item.dependencies
                    .map(
                      (id) => flow.stages.find((s) => s.id === id)?.title || id,
                    )
                    .join("、")
                : "流程起点"}
            </small>
          </button>
        ))}
      </nav>
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
