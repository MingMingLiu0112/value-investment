# TL9-MVP1 统一每日公开决策数据包设计冻结（2026-10-13）

本轮检查点：MVP-1 统一公开每日数据包及版本一致性。本文件冻结数据包合同，
后续 MVP-2 至 MVP-5 都以此为准。永久边界保持不变：`action=no_order`。

## 1. 唯一数据包

- 合同：`schema_version = "daily-public-packet-v1"`，`action = "no_order"`。
- 生成入口（同一份应用层实现，Web 与 CLI 共用）：
  `src/value_investment_agent/application/product/daily_public_packet.py`。
- CLI 入口：`scripts/current/build_daily_public_packet.py`，把数据包按
  `publication_id` 版本化写入 `runtime/daily-public-packet/`，不覆盖历史。
- Web 入口：`GET /api/v1/daily-public-packet`（只读实时计算，不落盘），
  并且 `/api/v1/daily-decisions`、`/api/v1/decisions/{symbol}`、
  `/api/v1/decision-history`、`/api/v1/system/status` 都附带同一个
  `publication` 摘要块（`publication_id`、`research_version`、日期边界）。

## 2. publication_id 定义（含上游身份的内容寻址）

```
publication_id = "pub-" + sha256(canonical_json({
    "schema": "daily-public-packet-identity-v1",
    "bindings": [ {role, path, sha256} ... 链上全部绑定，按 role 排序 ],
    "quote_bridge_sha256": <config/current-quote-bridge.json 原文 sha256 或 null>,
}))[:20]
```

理由：内容相同但上游 receipt 不同的两次发布必须得到不同 `publication_id`，
因此身份取自“上游绑定的 path+sha256 集合”，而不是数据包正文哈希；同一组
上游输入在 Web 与 CLI 上重复计算必须得到相同 id。数据包正文哈希
（`packet_sha256`）单独由 CLI 落盘时记录，用于审计该次写出的字节。

## 3. 日期语义（不得合并成“今日”）

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| `current_natural_date` | 当前自然日期（Asia/Shanghai） | 生成时刻 |
| `latest_completed_trade_session` | 官方归档日历能证明的最近已完成交易日 | 行情包归档日历（桥接执行结果） |
| `quote_trade_date` / `quote_observed_at` | 已登记行情交易日 / 采集完成时间 | `execute_quote_bridge_for_symbol` |
| `research_as_of` | 研究截止日 | handoff snapshot `as_of`（与指针 `research_as_of` 必须一致，不一致记 blocker） |
| `model_validity` | 模型有效性状态与有效截止（未知时为 null + blocker） | 状态公司 `decision.model_validity` |
| `decision_published_on` | 决策发布登记日 | 指针 `current_publication.registered_at` |
| `excel_published_as_of` | Excel 发布链的历史快照时点 | 指针顶层 `as_of` 与 `quote_observation_as_of` |

## 4. 失败关闭（fail-closed）边界

- 链上任何绑定缺失、越界或哈希不符：数据包 `packet_status = "UNAVAILABLE"`，
  `publication_id = null`，`chain_error` 记录具体原因；Web 原有接口维持既有
  `PUBLICATION_UNAVAILABLE` 行为。
- 单个行情登记、单条公司记录、单条注册研究证据损坏：只降级对应条目，
  记 `SOURCE_BINDING_HASH_MISMATCH:<role>` 或条目级 blocker，不伪造成功。
- 数据包不包含任何私人持仓、现金、账户或私人风险信息；私人状态只在
  已授权本地会话的私人接口中出现。

## 5. 公司覆盖范围

`company_statuses` 覆盖当前发布物 companies + opportunities 的并集（当前 6 家）
以及行情登记中出现的其它标的；`000333`、`601088` 等只有导出层状态的公司，
以 `config/current-company-research-registry.json` 注册的阻塞与证据显示，
不制造估值。注册文件按 path+sha256 绑定证据；证据变更时只降级该条目。

## 6. 计数语义

- `formal_admission_count`：发布行中 `valuation_status.code == "ADMITTED"` 的公司数
  （继承 `/api/v1/daily-decisions` 的原推导，单一实现）。
- `pending_review_count`：`company_statuses` 中 `pending_actions` 非空的公司数。
  `pending_actions` 只由真实信号推导：桥接 `needs_re_research`、模型有效性
  `UNKNOWN`、人工审批未决（状态 blockers 或解释 `requires_human_review`）、
  事件材料性未决。

## 7. 验收对应

- Web 每日总览 / 公司详情 / 历史研究 / CLI 摘要共享同一 `publication_id`
  与同一日期边界（本文件第 2、3 节）。
- `MVP-2` 统一入口、`MVP-3` 私人状态一致性、`MVP-4` 阅读路径、`MVP-5`
  Windows 端到端验收都读取本数据包，不复制业务计算。
