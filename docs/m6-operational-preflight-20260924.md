# M6 运营准入预检：2026-09-24

更新：2026-09-24。本文件只准备 M6 的非生产前置工程，不连接生产数据库、
不修改服务器服务/计划任务/通知，不读取真实持仓，也不执行订单。

## 状态

- 阶段状态：`M6=NOT_STARTED`。
- 预检配置的 `m2=DONE`，与 Checkpoint A 的 `HUMAN_PASS` 一致；M3-M5 仍为
  `PARTIAL`，因此本配置不能将 M6 产品前置条件写成已满足。
- 机器预检入口：`scripts/audit_m6_preflight.py`。
- 配置：`config/m6-operational-preflight-v1.json`。
- 加密备份入口：`scripts/package_encrypted_backup.py`。
- 运行控制入口：`scripts/m6_operational_control.py`。
- 动作边界：`action=no_order`。
- 干净工作树预检收据：
  `runtime/m6-operational-preflight-20260924T000810Z/receipt.json`
  （SHA-256：
  `9dadc9bdf3b7dcfb319ce35b5d7003827799a32c9dd4fe67fca74fceaba07dc3`）

当前可验证的是工程安全和恢复机制；真实 RPO/RTO、真实事件、20 个连续真实
交易会话和生产授权均不能由本地测试替代，仍保持未完成。

## 已复核的工程边界

- 隔离恢复目标固定为 `127.0.0.1:5433/value_agent_restore`。
- 恢复演练脚本使用 256 MiB 内存、0.5 CPU，并清理一次性容器。
- 备份代码使用事务快照、`pg_export_snapshot`、逐表行数/规范化 Hash、原件
  SHA-256、磁盘预留和 `--clean --if-exists --no-owner --no-acl`。
- 证据演练同时验证恢复后的财务事实、原件 Hash、月度快照和估值状态。
- 公开仓库扫描不包含 `.env`、密钥、数据库 dump、口令或个人持仓文件。
- 加密备份采用流式 AES-256-GCM，强制密钥文件位于备份源、输出目录和
  offsite staging 之外，并在解密后逐文件校验 SHA-256。
- 版本化 manifest 固定代码版本、配置清单、发布 Excel 和原件 Hash。
- 运行控制只允许按 `OFFLINE_ENGINEERING -> STAGING -> SHADOW ->
  LIMITED_USE` 逐级授权；任何阶段都可紧急停止，恢复时必须使用新授权并
  先回到离线工程状态。

## 当前明确缺口

1. 加密备份工程已离线实现，但实际云端同步部署、云盘密钥保管和密钥轮换
   方案尚未取得授权。
2. manifest 已具备代码版本、配置清单和发布 Excel Hash；仍需在真实生产
   备份作业中启用并验证。
3. 尚未执行一次真实生产快照到新库的恢复演练，因此没有可证明的 RPO/RTO。
4. 尚未建立真实 shadow 会话账本，20 个连续真实交易会话计数为 0。
5. 尚未提交并获得生产 migration、调度、通知、账户数据和回退方案授权。

## 需要用户授权或提供

- 生产 migration 的准确范围、账号和可回退方案；
- 个人组合/账户数据使用范围及私有存储位置；
- M5/M6 调度、通知目标和静默策略；
- 当前服务器 PTA 项目的资源基线、内存/磁盘余量和回退方案；
- 是否允许进入 staging/shadow，以及故障时立即停止新增复核的开关。

未取得上述授权前，不实施任何生产动作；预检只输出
`OPERATIONAL_ACCEPTANCE_STATUS=NOT_STARTED`。

预检结果同时确认当前 `engineering_status=DONE`：隔离恢复、资源上限、
事务快照、公开仓库隐私扫描、加密备份、密钥分离和完整清单均可用；真实
云端同步和运行验收仍未开始，`operational_acceptance_status=NOT_STARTED`。

## 与 M7 的关系

M7 统一工作台候选可以继续完善只读展示，但不能用展示层替代 M6 的真实运营
证据。只有 M6 通过后才能进行最终用户签收和 `INITIAL_ASSISTED_USE` 交付。

## 2026-09-24 运营控制恢复完整性收紧

运营控制状态文件现在会重放完整历史链，而不只读取当前 mode 和 permissions：

- 模式变化时间必须严格向前，且不能把同一模式记录为一次切换。
- 历史必须从 `OFFLINE_ENGINEERING` 连续推进；紧急停止保留当前授权，解除停止后
  必须使用新授权并先回到离线工程状态。
- 当前快照必须与历史最后一步一致。
- schema/action 必须精确匹配，权限字段必须为 JSON boolean，字符串 `"false"` 不再
  被静默当成真值。

`test_m6_operational_control.py` 为 `9 passed`，M6 control + readiness 联合回归为
`18 passed`。本批仍只收紧离线合同，不执行任何生产动作。

## 2026-09-24 历史 ingest 拒绝聚合视图

新增只读入口：

```powershell
.\.m1-postgres-venv\Scripts\python.exe scripts\audit_m6_historical_ingest_rejections.py `
  --state-key <M5 stream_id> `
  --state-root <M5 state JSON 目录> `
  --receipt-root <M5 durable receipt 目录>
```

该视图以最新 M5 state 的 `batch_records` 和 committed checkpoints 为链锚点，逐条重新读取
durable receipt 文件字节并验证：

- 文件名与 `receipt_id` 的 SHA-256 映射一致；JSON 必须是严格 UTF-8、无重复 key，且大小
  有上限；
- `receipt_sha256`、`audit_fingerprint`、内嵌 state/checkpoint 和 receipt id 重新解析并
  往返验证；
- receipt 的 `batch_id`、`run_id`、`namespace`、`generated_at`、`checkpoint_id` 与最新
  state 中唯一的 batch record 完全一致；
- 新收到的 receipt 必须与 batch record 保存的 `receipt_audit_fingerprint` 一致，避免在
  被拒 ingest 没有 event 的情况下单改 receipt 并重算内部 Hash 伪造拒绝项；
- state 中每个历史 revision 都必须有且仅有一份 receipt；缺失、重复、额外、跨 stream、
  损坏、rollback 或伪造绑定全部失败关闭。

输出固定为 `action=no_order`。历史拒绝与当前运行健康分开呈现：后续 receipt 可以是
`HEALTHY`，但任何历史 `FUTURE_REJECTED`、`CONFLICT_REJECTED` 或
`OBSERVED_TIME_REGRESSION_REJECTED` 仍使聚合状态为 `ATTENTION`。

当前所有 M5 durable receipt 输入都强制为 `SIMULATED`。视图明确输出
`evidence_class=SIMULATED_OFFLINE_ONLY`，真实运营会话数和真实事件数均固定为 false，
不得用于 M6 授权或验收计数。文件字节 Hash 会在读取时重算，但仓库目前没有独立签名或
外部 WORM manifest，因此真实性边界只能声明为 `LOCAL_CONSISTENCY_ONLY`；这不能被写成
防篡改或生产就绪。

本入口不实例化可写 M5 store、不连接 PostgreSQL、不创建 scheduler、不发送通知、不发布
Excel，也不产生订单。M6 仍为 `PREFLIGHT_DONE / operationally NOT_STARTED`。
