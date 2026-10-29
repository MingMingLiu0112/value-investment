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
            { key: "input", label: "输入", children: stage.input },
            { key: "output", label: "输出", children: stage.output },
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
              children: "未接入 / NOT_CONNECTED；静态快照不推定当前运行结果。",
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
export function ArchitectureView({ strategy }: { strategy: StrategyKey }) {
  const flow = catalog[strategy];
  const [selected, setSelected] = useState(flow.stages[0].id);
  const stage =
    flow.stages.find((item) => item.id === selected) || flow.stages[0];
  return (
    <>
      <Typography.Title level={2}>{flow.title}</Typography.Title>
      <Typography.Paragraph>{flow.summary}</Typography.Paragraph>
      <Alert
        type="warning"
        showIcon
        message="静态复核快照 · 非实时进度 · 非策略认证"
        description={review.disclaimer}
      />
      <p className="architecture-source">
        {review.version} · reviewed baseline <code>{review.baseline}</code>
        <br />
        复核日期：{review.reviewedAt} · 里程碑来源：<code>{review.ledger}</code>
        。最近交付说明单独标注，不代表当前运行结果。
      </p>
      <Space wrap>
        <Tag>人工整理 / {review.mode}</Tag>
        <Tag>运行证据 / {review.runtimeEvidence}</Tag>
        <Tag>action=no_order</Tag>
      </Space>
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
        Tab 移动，Enter / 空格选择。箭头表示依赖，不表示已通过。
      </p>
      <div className="architecture-layout">
        <section aria-label="策略流程图">
          <ol className="architecture-flow">
            {flow.stages.map((item) => (
              <li key={item.id}>
                {item.dependencies.length > 0 && (
                  <div className="architecture-dependencies">
                    依赖{" "}
                    {item.dependencies.map((id) => (
                      <button
                        type="button"
                        key={id}
                        onClick={() => setSelected(id)}
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
                  onSelect={setSelected}
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
