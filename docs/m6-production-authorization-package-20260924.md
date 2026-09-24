# M6 生产授权包（未授权草案）

更新：2026-09-24。本文件为未来授权审查准备边界，不批准或执行生产操作。

```text
M6 engineering preflight = DONE / PARTIAL
M6 operational acceptance = NOT_STARTED
M6 production authorization = NOT_YET
action = no_order
```

## 当前禁止原因

- M3 Checkpoint B 是 `PARTIAL`，严格 contemporaneous-rule PIT 尚未证明；
- M4 缺真实、人工确认且完成对账的私有 IPS/组合；
- M5 尚缺真实事件产品闭环，600519 九条公告仍待用户材料性判定；
- 无真实隔离恢复记录，实际 RPO/RTO 未测得；Shadow 会话和真实事件计数均为 0。

因此本文件不是授权请求通过，也不允许开始 Shadow 计数。

## 未来逐项授权范围

| 项目 | 当前状态 | 授权记录必须明确 |
| --- | --- | --- |
| 数据库 migration | 未设计/未授权 | 地址、迁移文件、备份点、回退命令、维护窗口 |
| M5/M6 调度 | 未部署 | 数据源、频率、并发、失败预算、锁、停止条件 |
| 通知 | 未配置 | 渠道、接收人、静默窗口、严重度、确认方式 |
| 私有组合数据 | 未导入 | 私有根、密钥保管、保留期、设备访问与删除流程 |
| 服务器资源 | 未重新测量 | PTA 基线、内存/磁盘、CPU 预算及越界动作 |
| 备份/异地副本 | 未部署 | 加密位置、独立密钥位置、保留策略、恢复负责人 |
| Shadow | 未授权 | 开始日期、停止/重置规则、会话账本位置 |

不得以“同意部署”等笼统措辞替代单项决定。

## 永久边界

- 不修改、重启或挤占 `web_app_integrated.py` / `web-app-pta`。
- PostgreSQL 数据目录不进入 WPS；WPS 只同步展示工作簿，指定发布端才可写。
- 个人 IPS、现金、持仓、成本和 Journal 不进入 Git、WPS 或公开 runtime。M4 输入拒绝
  `WPSDrive`、仓库路径和仓库内密钥。
- 不连接券商、不自动交易；全部状态保留 `requires_human_review=true`、`action=no_order`。

## 资源、恢复与回退

现有隔离恢复上限为 `127.0.0.1:5433/value_agent_restore`、256 MiB、0.5 CPU、
`max_connections=10`。这不是服务器余量证明。授权前，人工须保存如下只读检查并确认
至少保留 2 GiB 磁盘储备及 PTA 基线：

```bash
free -m
df -h
systemctl status web-app-pta --no-pager
ps -eo pid,ppid,%mem,%cpu,cmd --sort=-%mem | head -n 25
```

真实恢复只能在隔离目标完成，记录 backup ID、密文/清单 Hash、关键表行数/规范化 Hash、
原件 Hash、Excel Hash、实际 RPO/RTO 和失败原因。`RPO <= 24h`、`RTO <= 4h` 是目标，
不是当前通过事实。任何异常先停本项目写入与发布，保留证据；绝不覆盖生产库或 PTA。

## Shadow 规则与紧急停止

Shadow 必须按 `OFFLINE_ENGINEERING -> STAGING -> SHADOW` 逐级推进，每次转换需要新的
明确授权 ID。当前命令只写本地控制证据，不触碰生产：

```powershell
python scripts/m6_operational_control.py status
python scripts/m6_operational_control.py stop --reason <reason> --operator <operator>
python scripts/m6_operational_control.py advance --target STAGING --authorization-id <approved-id> --reason <reason> --operator <operator>
```

数据完整性失败、时钟/水位回退、Hash 不匹配、资源越界、PTA 异常、私有边界失败、
未经确认的通知投递或 P0/P1 缺陷均停止或不计入会话。修复 P0/P1 后按预登记规则重新
计算受影响窗口。M6 至少需要连续 20 个真实交易会话和一件真实财务/资本配置事件；模拟、
replay 和补填不计入。

## 未来授权收据

真正授权时必须新增 append-only 收据，绑定授权人、时间、Git commit、容器/配置 Hash、
数据库/迁移清单、私有数据范围、通知范围、资源基线、备份摘要、回退步骤及 Shadow
停止/重置规则。任何变更新建收据，不覆盖旧授权。
