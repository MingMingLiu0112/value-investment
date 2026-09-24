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
    同一事件更正必须保持相同的证券与 `source_event_id`，跨来源替代不得伪装成更正；
  - 晚到事件仍接受，但保留历史顺序，不重标为当前时间；
  - replay 边界拒绝 `available_at/detected_at` 晚于观察时间的事件；
  - 序列化账本重放复核更正/替代目标、唯一后继、状态一致、观察时间单调性和完整边界。
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

## 2026-09-24 重放完整性收紧

序列化事件账此前只保证事件 ID、连续序号和命名空间，未在重放时完整验证更正/替代
关系。损坏账本因此可能出现缺失目标、活动目标、跨来源更正、重复后继或无后继的
`SUPERSEDED` 事件。本轮把这些条件改为失败关闭，并要求同一来源事件的较早版本
只能是被替代状态。

- checkpoint 与 outbox 现在具备经过校验的序列化恢复入口；检查点尝试不得重叠
  或回退，提醒状态必须与尝试、重试和投递时间自洽。
- 租约同时绑定 owner 与 token，release/renew 不得穿越获取时间。
- 事件基础设施与工作簿定向回归：`32 passed`。
- 全部 M5 定向回归：`70 passed`。
- `action=no_order`；不自动修正历史、不猜测缺失目标，也不接入生产通知。

## 2026-09-24 运行状态与批次重放收口

前一版 run-once 只返回内存状态，没有把事件、水位、checkpoint、outbox 与批次幂等
记录作为一个联合状态重放验证。该边界现由 `M5EventRunState` 收口：

- `state_key/revision` 与五个子账本可共同导出/恢复；拒绝 checkpoint 空洞、重复
  event/alert/checkpoint ID、未知引用、revision/sequence 回退和跨 namespace/action
  绕过。
- batch record 绑定 `batch_id/run_id/namespace/generated_at/request_fingerprint/
  receipt_id/checkpoint_id/state_revision`，receipt 与 committed checkpoint 必须
  实际属于该状态。
- 同一 batch 只在原 run、原 namespace 和原 fingerprint 下重放；重放返回原
  generated_at/receipt ID，并恢复该批次 alerts，不重复事件、checkpoint 或 outbox。
- 被拒绝的新批次也提交审计 checkpoint 与 batch record，不再错误标记为 replay；
  watermark 前进后旧批次仍可按原请求重放。
- `expected_revision` 可在调用边界阻断陈旧快照；它不是完整 CAS 替代品。原子持久化
  StateStore、跨进程并发控制、真实通知投递和生产恢复演练仍明确未完成。
- 旧 `source_id` 缺失事件仅在人工复核为 true、`effective_at == available_at` 或
  effective 为空时按 legacy fingerprint 导入；否则失败关闭，避免删字段降级。

验证：`tests/test_m5_event_run_state_boundaries.py` 13 passed；全部 M5 定向回归
`88 passed`；本地全量离线回归 `2447 passed, 6 skipped, 18 warnings, 0 failed`。

## 2026-09-24 本地 StateStore 与 CAS 持久化

上一版仍把状态留在调用方内存，`expected_revision` 不能阻止进程重启后的状态丢失或
两个陈旧 writer 覆盖。现在由独立的 `M5EventRunStateStore` 承载状态提交：

- `InMemoryM5EventRunStateStore` 用于测试；`JsonM5EventRunStateStore` 每个 state key
  使用独立 JSON 文件，并以本地文件锁串行化跨实例访问。
- 写入先落同目录临时文件、`fsync`，再以 `os.replace` 原子替换；损坏 JSON 读取失败，
  commit 不会覆盖无法解析的现有状态。
- commit 必须提供 `expected_revision` 和 `expected_sha256`；同一 revision 只能幂等
  写入相同摘要，陈旧 revision 或摘要均失败关闭。
- `run_event_batch_persisted()` 从 store 加载最新状态、执行一个批次并 CAS 提交；
  调用方传入的旧快照不能绕过加载后的摘要检查。
- 新增 8 项存储边界回归；全部 M5 定向回归 `96 passed`。该层仍不是外部单调/签名
  信任根，不承诺掉电级耐久性，也未实现生产采集、通知投递或恢复演练。本地全量
  离线回归 `2455 passed, 6 skipped, 18 warnings, 0 failed`。

`action=no_order`；M5 仍为 `PARTIAL`，不得把本层等同于 M5/M6 产品验收。

## 2026-09-24 事件与 canonical outbox 提醒绑定

运行状态恢复此前仅验证 outbox 引用存在，未验证每个事件都有对应提醒。本轮把事件到
提醒类型的映射收敛到 outbox 领域，并在 `M5EventRunState` 中执行双向校验：

- 每个事件必须具备 canonical alert type、`event:{event_id}:{alert_type}` dedupe key、
  与事件一致的严重度和人工复核标志；删除提醒或把类型替换为 `SYSTEM_HEALTH` 均失败。
- 系统源扫描事件必须要求人工复核，不能在输入边界关闭。
- 缺失提醒、错误类型、伪造 dedupe key 和系统事件绕过四项反向回归通过；全部 M5 定向
  回归 `97 passed`，本地全量离线回归
  `2456 passed, 6 skipped, 18 warnings, 0 failed`。

本批仍不发送通知、不接生产源，`action=no_order`。

## 未完成边界

真实公告采集器、公告级材料性判定、Entry/组合复核、生产调度、通知目标和
真实故障恢复仍等待对应数据、人工授权与 M6 方案。本批不证明 M5 产品验收，
也不证明系统已持续监控真实市场。
