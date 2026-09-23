# M5 事件基础设施离线合同：2026-09-24

本文件记录 M5 第一批纯领域与离线 run-once 工程。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 均保持 `PARTIAL`；所有动作
`action=no_order`，未创建生产调度、通知投递、常驻服务或数据库改动。

## 领域对象

- `m5_event_core.py`
  - `ChangeEventInput` / `ChangeEvent` / `EventLedger`；
  - 固定 `detected_at`、`effective_at`、`available_at`，不把抓取时间写成发生时间；
  - 同一来源同一内容的重复输入幂等忽略；
  - 内容变化必须显式引用 `correction_of_event_id` 或 `supersedes_event_id`；
  - 晚到事件仍接受，但保留历史顺序，不重标为当前时间；
  - replay 边界拒绝 `available_at/detected_at` 晚于观察时间的事件。
- `m5_event_watermark.py`
  - `ScanWatermark` / `WatermarkLedger`，覆盖水位单调前进，不允许回退；
  - `TaskLock` / `TaskLockStore`，单 scope 单锁、租约、token、释放和续约。
- `m5_event_checkpoint.py`
  - `TaskCheckpoint` / `CheckpointLedger`，记录运行状态、最后序号、水位 ID 和
    已处理事件 ID，用于崩溃后幂等续接。
- `m5_event_outbox.py`
  - `EventAlert` / `OutboxLedger`，PENDING/SENT/DELIVERED/ACKNOWLEDGED/
    FAILED_RETRYABLE/FAILED_TERMINAL；
  - 同一事件同一类型不重复入队，更正产生新事件 ID，不会被旧事件吞掉；
  - 关键提醒、源健康和普通提醒分开审计，实际投递不在此层执行。
- `m5_event_dependencies.py`
  - `DependencyNode` / `DependencyGraph` / `DependencyInvalidation`；
  - 按事件类型失效对应事实、估值输入、股息、模型、论点、Entry、组合或价格节点；
  - 价格变化只影响价格桥接和当前状态，不把内在价值标记为需要重算；
  - `max_depth/max_nodes` 超出时记录 deferred，不静默扩大范围。
- `m5_event_run.py`
  - 纯 run-once 编排：取锁 -> 开检查点 -> 事件账 -> 有界失效 -> outbox ->
    提交检查点 -> 释放锁；
  - 公开入口只接受 `SIMULATED`，不启动服务或发送真实通知。

## 展示候选

- 文件：`A股价值投资_M5事件监控候选_20260924.xlsx`
- 字节数：14,989
- SHA-256：
  `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae`
- 工作表：`00_总览`、`01_事件账`、`02_水位与检查点`、
  `03_依赖失效与重算`、`04_Outbox`、`05_输入与边界`
- 示例输入：7 个事件输入，覆盖财报、价格、分红、重复、晚到、更正；
  当前有效事件 6 个，依赖失效记录 6 个，outbox 提醒 6 个。
- WPS 只读收据：
  `runtime/m5-event-wps-20260924/receipt.json`，`passed`
- WPS 云盘同名副本与仓库候选 SHA-256 一致。

## 验证

- 定向回归 `tests/test_m5_event_infrastructure.py` 与
  `tests/test_m5_event_workbook.py`：24 passed。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2244 passed、2 skipped、
  18 warnings、0 failed。
- 覆盖重复、更正、乱序、晚到、未来事件、观察时间回退、水位回退、锁冲突、
  检查点提交/失败、outbox 重试、关键提醒、价格与估值隔离、有界重算和环检测。
- 两项测试已加入 GitHub Core Research Gate。

## 未完成边界

真实公告采集器、公告级材料性判定、Entry/组合复核、生产调度、通知目标和
真实故障恢复仍等待对应数据、人工授权与 M6 方案。本批不证明 M5 产品验收，
也不证明系统已持续监控真实市场。
