# M5 人工材料性判定接入记录

更新：2026-09-24。本文记录本批实现和边界，不制定新任务，不改变投资逻辑，不生成
交易指令。

## 范围

已有 `EventMaterialityDecision` 保存最终人工判定。本批建立
`m5_materiality_bridge.py`，把可行动判定转换为 `ChangeEventInput` 和显式依赖类型，
再进入既有 M5 事件账、有界失效和 outbox。本批仍为离线 run-once 模拟，不建立公告
采集、生产调度、通知投递、数据库迁移或实盘动作。

## 判定映射

| 人工判定 | 事件 | 直接依赖类型 | 模型有效性 |
| --- | --- | --- | --- |
| `NOT_MATERIAL` | 不生成 | 无 | 不触碰 |
| `MATERIAL_SUPPORTING_EVIDENCE` | 不生成 | 无 | 不触碰 |
| `MATERIAL_ALREADY_INCORPORATED` | 不生成 | 无 | 不触碰 |
| `DUPLICATE_OR_DERIVED` | 不生成 | 无 | 不触碰 |
| `MATERIAL_REQUIRES_RECALCULATION` | 高严重度 | 至少包含模型有效性、估值输入、决策复核；事实、估值结果等按领域/制品继续增加 | 允许失效 |
| `REQUIRES_DECOMPOSITION` | 中严重度 | 决策复核、当前研究状态 | 不直接失效 |
| `MATERIAL_RISK_MONITOR` | 中严重度 | 决策复核 | 不直接失效 |

只有 `MATERIAL_REQUIRES_RECALCULATION` 允许把模型有效性带入失效路径。拆分和风险
监控保持保守，不因“需要继续处理”就把模型标记为 stale。

## 时点与未知输入

- `available_at` 使用公告发布时间，`detected_at` 使用人工复核时间。
- 人工复核早于公告发布时 fail-closed。
- 已注册领域映射到明确依赖类型；未注册领域保留为 `unmapped_domains`。
- 已注册制品映射到明确依赖类型；未注册制品保留为 `unmapped_artifacts`。
- 不猜测未知领域或制品，不因标题规则候选自动修改估值事实。

## 合同扩展

- `m5_event_dependencies.py` 显式列出 `DEPENDENCY_KINDS`；direct node 与
  invalidation 可限定类型，并把自定义失效策略纳入确定性摘要。
- `m5_event_run.py` 的 `run_event_batch` 接收按源事件 ID 的
  `direct_kinds_by_source_event_id`，逐事件校验后应用。

## 候选工作簿

- 文件：`A股价值投资_M5材料性接入候选_20260924.xlsx`
- 字节数：13,240
- SHA-256：
  `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df`
- 工作表：`00_总览`、`01_材料性映射`、`02_事件账`、`03_依赖失效与重算`、
  `04_Outbox`、`05_输入与边界`
- 模拟结果：6 项人工材料性判定、3 项静默、3 个事件、3 条失效记录、3 条 outbox
  提醒，固定 `action=no_order`
- WPS 只读收据：`runtime/m5-materiality-wps-20260924/receipt.json`，`passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

## 验证

- M5 材料性桥接相关定向回归：39 passed。
- GitHub Core Research Gates 离线清单：405 passed。
- GitHub Core Research Gates run 37：`offline-core` 与 `postgres-integration`
  均为 `success`。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2252 passed、2 skipped、
  18 warnings、0 failed。
- `compileall` 与 `git diff --check` 通过。

## 状态边界

M2 为 `PENDING_HUMAN_REVIEW`，M3、M4、M5 为 `PARTIAL`。本批只证明人工材料性结论
可以精确接入 M5 事件管道；真实公告采集、公告级材料性判定、生产调度、通知投递、
Entry/组合复核与故障恢复仍需后续建设，不据此宣称持续市场监控已上线。
