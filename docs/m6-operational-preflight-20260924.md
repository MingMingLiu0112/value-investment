# M6 运营准入预检：2026-09-24

更新：2026-09-24。本文件只准备 M6 的非生产前置工程，不连接生产数据库、
不修改服务器服务/计划任务/通知，不读取真实持仓，也不执行订单。

## 状态

- 阶段状态：`M6=NOT_STARTED`。
- 机器预检入口：`scripts/audit_m6_preflight.py`。
- 配置：`config/m6-operational-preflight-v1.json`。
- 加密备份入口：`scripts/package_encrypted_backup.py`。
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
