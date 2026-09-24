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
  v1 receipt 口径当前有效事件 6 个，依赖失效记录 6 个，outbox 提醒 6 个。
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

## 2026-09-24 Outbox 迁移日志与事件批次历史不可改写

事件批次 revision 之前同时承担 outbox 状态变化，无法在不制造虚假批次的情况下
持久记录提醒投递结果。现在 outbox 使用独立的追加日志，并补齐事件批次 successor
对旧历史的不可改写约束：

- `M5EventRunState` v2 增加 `outbox_revision` 和不可变
  `outbox_transitions`；StateStore 可在同一事件批次 revision 接受恰好一个合法
  outbox successor，陈旧 writer 和无关 same-revision 改写仍失败关闭。
- `apply_outbox_transition()` 记录 `PENDING/SENT/DELIVERED/ACKNOWLEDGED` 与
  retryable/terminal failure 迁移；重复请求幂等，重放重建同一 outbox。该函数只
  记录调用方已确认的 transport 结果，不发送通知。
- event-batch successor 现在逐字段比较旧事件，只允许明确的 correction/supersede
  将 `ACTIVE` 改为 `SUPERSEDED`；旧 checkpoint、watermark 和 outbox alert 也必须保持
  合法前缀或单调推进。
- 对抗审查构造了伪造第三批次改写旧事件 `ingested_at`、同时重建 outbox 的反例；
  当前 StateStore 会拒绝该状态，并已加入回归。
- 事件身份以 canonical JSON `source-id-v2` 生成新 ID；带 `source_id` 的历史 payload
  继续按原 `source-id-v1` 算法校验，更早的无 `source_id` payload 按 legacy 算法
  校验。v1 序列化不增加版本字段，因此旧 batch fingerprint 与旧事件 ID 保持一致。
- v2 fingerprint 同时绑定 `detected_at`、`available_at` 和 `effective_at`；修改
  PIT 时间但不重新计算 ID 会在事件账恢复时失败关闭。
- 旧批次重放和提醒恢复按该批次输入对应的精确 event ID 查询，不再取相同来源的最新
  事件，因此允许历史 v1 事件由新的 v2 correction 显式取代，同时保持旧回执幂等。
- 冻结 M5 demo fixture 显式按 legacy 身份构造，并固定回归首个历史事件 ID
  `m5-4b18852347f226b8aa172d96aec307af`，避免发布工作簿因默认算法变化而漂移。
- 迁移/StateStore/事件/工作簿边界定向回归 `77 passed`；全部 M5 定向回归
  `115 passed`；本地全量离线回归
  `2474 passed, 6 skipped, 18 warnings, 0 failed`。

本批仍不发送真实通知、不接生产源，也不承诺外部单调/签名防回滚或掉电级耐久性；
当时冻结的 v1 工作簿尚未展示身份版本，v1/legacy 为兼容也不能补绑 PIT 时间字段。`M5`
保持 `PARTIAL`，`action=no_order`。

## 2026-09-24 Outbox 迁移展示候选 v2

在原 6 页冻结候选之外新增独立 v2 展示候选，把事件身份版本、来源 ID、提醒发送时间、
追加式迁移日志和 final state 摘要放到同一可审计工作簿。v1 文件及 SHA-256 保持不变，
M7 仍固定引用 v1；v2 不替换 canonical，也不接入通知网络。

- 文件：`A股价值投资_M5事件监控候选_v2_20260924.xlsx`
- 字节数：17,652
- SHA-256：
  `5c3f1e7aee518029a6cc5da10139a86aecd61a9acf5caf37a56dfe69d747d1bc`
- 工作表：`00_总览`、`01_事件账`、`02_水位与检查点`、
  `03_依赖失效与重算`、`04_Outbox`、`05_Outbox迁移`、`06_输入与边界`。
- v2 事件账显示 `身份版本` 与 `来源ID`；被 correction 取代的旧事件显示
  `已被替代`，不再用输入时状态冒充当前生命周期状态。
- v2 总览显示 7 个输入、5 个当前有效事件、6 个提醒、outbox revision 7、
  7 条迁移记录和 `action=no_order`。v1 的 `6` 是冻结 receipt 级 accepted-event
  快照计数；v2 的 `5` 来自当前 event ledger，两者的语义和展示边界已明确区分。
- `05_Outbox迁移` 直接展示来源事件 ID、来源 ID、身份版本、alert ID、前后状态、
  发生时间、错误和动作，可从工作簿逐行追溯到 base fixture、迁移 fixture 和 manifest。
- base fixture SHA-256：
  `0bba84f6450f308a02dff0a703c17eab9f77d5f65a13a6184be7f8c52b9ca8f4`。
- 迁移 fixture SHA-256：
  `f70deb515c10557c25246dda34e772fb2a7717e9ba70f2dfb9634f8c26e5d8be`；
  其 `generated_at=2026-09-24T16:10:00+08:00` 是全部迁移时间的确定性上界。
- base state SHA-256：
  `486cdc0fe6dc25a8d84e4dccb9c6edf3b19b1c2e859ada60459a1d1ac2430542`。
- final state SHA-256：
  `7a7c82434b4bf41a11ef68e95c1b384cf605f9455c75438f440966fd05764955`。
- manifest 使用 `m5-outbox-transition-candidate-v2` schema，绑定 base/迁移文件
  Hash、workbook/state Hash、6 个提醒终态、冻结 v1 parent Hash，以及 builder/
  workbook module 的字节 Hash；manifest 自身保持本地运行产物，不进入公开仓库。
- 迁移解析同时检查 `source_event_id + alert_type` 的唯一性；存在 correction 版本
  歧义时失败关闭。迁移时间必须位于对应 run 之后且不晚于迁移批次 generated_at；
  同一 alert 必须按时间顺序追加。等价的时区表达统一按 UTC 计算 transition ID。
- 构建使用独占发布锁，输出或 manifest 已存在、已有一轮发布会进行中时拒绝覆盖。

验证：

- `tests/test_m5_outbox_transition_candidate.py`：`8 passed`。
- 全部 M5 定向回归：`120 passed`。
- 本地全量离线回归：
  `2483 passed, 6 skipped, 18 warnings, 0 failed`。
- WPS 只读收据：
  `runtime/m5-outbox-transition-wps-v2-20260924/receipt.json`，`passed`；
  WPS 云盘同名 v2 副本与仓库文件 SHA-256 一致。
- 公开工作簿 WPS 云盘全量字节审计：`30/30 MATCH`。

本工作包仍不发送真实通知、不接生产源、不承诺外部单调/签名防回滚或掉电级耐久性。
另有非阻断兼容债：schema v1 若带有非 `PENDING` 的旧 outbox 状态且没有迁移历史，
当前恢复入口会失败关闭；在出现真实 v1 非 pending 状态前记录为 backlog，不伪造迁移
历史。`M5` 保持 `PARTIAL`，`action=no_order`。

## 2026-09-24 fail-closed 加固

本轮对 M5 离线域做了第二轮对抗审查，修复了身份兼容、批次 replay、水位时效、
invalidation 投影和材料性 Hash 的真实反例：

- `source-id-v3` 使用 UTC-normalized canonical JSON；v2/v1/legacy 保持原算法和冻结
  event ID。v2 与 v3 相同 dedupe key 但不同内容时，无显式 correction 即拒绝。
- batch replay 从 checkpoint 的 pre-batch prefix 重建，不再把已提交批次重复追加；
  first/replay 的 ingest verdict、invalidation、alert 必须一致，且 accepted event IDs
  必须精确等于 checkpoint 记录。
- duplicate 事件的 replay 不携带旧 alert；incomplete batch 在后续 complete scan 后
  replay 仍保持原 `ATTENTION/silent_ok=false`。
- 新批次禁止 future watermark；运行时钟必须不早于所有 observed times，默认超过
  15 分钟的水位视为 stale 并失败关闭。
- M4/M5 投影前校验 invalidation 的 event/type/symbol/policy/node kind/图内节点；
  跨标伪造不再影响其他公司。`result_id` 绑定完整图、receipt state 和最终 artifacts。
- materiality decision/source/human evidence/current-state 的 SHA-256、review window
  和 decision clock 均失败关闭；所有身份版本的 material announcement 都要人工复核。
- 定向回归 `146 passed`；全量离线回归 `2507 passed, 5 skipped, 18 warnings, 0 failed`。

真实 review workbook 仍没有 durable run request 和 receipt publish/read contract，
apply 只到 bridge artifact。600519 9 条真实公告保持待人工判断，不在此轮代签。

## 未完成边界

真实公告采集器、公告级材料性判定、Entry/组合复核、生产调度、通知目标和
真实故障恢复仍等待对应数据、人工授权与 M6 方案。本批不证明 M5 产品验收，
也不证明系统已持续监控真实市场。

## 2026-09-24 durable run request 与 receipt publish 契约

上一轮结束时，人工材料性 review 只生成 `intake.json` / `reviews.json` /
`bridge_batches.json`，manifest 明确写着 `events_not_applied: true`：bridge artifact
不是可重放请求，也没有 durable receipt。本轮把这段补齐，全部使用合成数据验证，
不触碰 600519 九条真实公告。

闭环现在固定为：

```text
human materiality review
  -> MaterialityBridgeBatch.from_payload()          # 人工判定可反序列化
  -> M5EventRunRequest                               # 自包含 + request_id + SHA-256
  -> apply_run_request()                             # 一次提交 + 一次收据
  -> M5EventRunReceipt artifact                      # receipt_sha256 / audit_fingerprint
  -> JsonM5EventRunReceiptStore                      # write-once + 原子替换
```

关键事实：

- `M5EventRunRequest` 嵌入 events、observed times、完整 `ScanWatermark`、
  `DependencyGraph`、direct dependency kinds，以及 run/batch/stream id 和
  `generated_at`；`from_payload()` 要求 payload 往返到 canonical 形式，缺键、多键、
  改时间或改 fingerprint 都会失败关闭。
- `batch_request_fingerprint()` 是唯一实现：run state 的 `M5EventBatchRecord` 与
  run request 共用同一指纹算法，收据发布前逐一比对，防止「请求 A、提交 B」。
- `M5EventRunReceipt` artifact 记录 `receipt_sha256`（content hash）与
  `audit_fingerprint`（仅覆盖批次事实：verdicts、invalidations、checkpoint、
  run/batch/stream、generated_at）。重试在同批次上复现相同 audit fingerprint，
  同时不假装 ambient state（水位、outbox 投递状态、state revision）从未变化。
- `JsonM5EventRunReceiptStore.publish()` 是 write-once：临时文件 + `fsync` +
  `os.replace`，并与 state store 共用文件锁。同一 `receipt_id` 再次发布且 audit
  fingerprint 一致时返回 `ALREADY_PUBLISHED`；不一致时抛
  `M5StateStoreConflict`，不覆盖既有证据。
- 两个崩溃窗口都有测试：state commit 前失败 → 重试只提交一次（revision 1、
  1 条 batch record、1 个 committed checkpoint）；state commit 后、receipt 发布前
  失败 → 重试为 `idempotent_noop` replay，并把收据补写一次。
- 收据自身 `verify()` 会要求每条 accepted ingest verdict、每个 alert、
  每条 invalidation 都存在于其内嵌 state；只容忍 ledger 拥有的 `status` 迁移
  （例如后续批次 supersede），其余字段不一致即拒绝。
- silent-only 批次（例如 `MATERIAL_ALREADY_INCORPORATED`）生成 events 为空的合法
  请求，仍然只推进覆盖水位、不产生事件、不产生 `BUY/ADD`。

对抗审查同时修掉两个 fail-open：

- `FAILED_TERMINAL` 通知失败原先被视为「已结案」，会让后续 run 报 `HEALTHY` 且
  `silent_ok=true`。现在只有 `ACKNOWLEDGED` 才算结案，通知未到达人工时保持
  `ATTENTION` 并出现在 `review_due`。
- 复核对账原先允许重复 prior `review_id` 覆盖 Hash，可能把另一份 review 的 Hash
  携带到当前判定；现在重复 id 直接失败关闭。

验证：`tests/test_m5_run_request.py` `12 passed`，M5 定向回归 `58 passed`，本地全量
离线回归 `2522 passed, 5 skipped, 18 warnings, 0 failed`。

## 2026-09-24 归档 PDF 字节复核与工作簿关系字段

此前 intake 只读取队列 JSON 中的 `sha256`，回填表也缺少关系字段和原件链接。现在
人工材料性入口统一为以下 fail-closed 顺序：

```text
queue candidate
  -> unique SOURCE_ARCHIVED PDF ref
  -> canonical symbol/date/announcement path
  -> reject links/traversal/outside-root paths
  -> open file once, verify %PDF- magic
  -> recompute SHA-256 from bytes
  -> compare recorded digest
  -> human decision / reconciliation
```

- 文件缺失、路径逃逸、多 PDF 引用、身份不匹配、PDF magic 错误或摘要不一致都会失败
  关闭。复核对账不能仅凭 queue JSON 与 prior review JSON 的相同 Hash 直接结转旧判定。
- `01_人工判定` 新增 `替代事件ID` / `事件簇ID` 两列；旧的 13 列工作簿仍可读取。
  `PDF SHA-256` 保持纯文本并附加本地归档 PDF hyperlink。
- 600519 v2 空白复核包绑定 9 条真实候选并完成现场 Hash 复核，但所有人工材料性字段
  仍为空，等待用户逐条判断。

仍未完成：

1. 当前 run health 只描述本次运行，历史被拒 ingest 需要在 M6 运营聚合视图中单独
   呈现；
2. 600519 九条真实公告仍保持 `PENDING_HUMAN_REVIEW`，等待用户逐条材料性判定；
3. `M5` 保持 `PARTIAL`，`action=no_order`，不发送通知、不接生产调度。
