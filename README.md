# A股价值投资研究与跟踪系统

本项目服务长期资本增值与可持续股息现金回报，以证据、公司经济画像、研究论点和适用估值支持人工决策。原 WPS Excel 是当前研究前端，PostgreSQL 是长期结构化数据底座；部分新研究结果目前保存在有 Hash 的 runtime 快照中。系统不自动下单。

## 目标与当前进度

从 [AGENTS.md](AGENTS.md) 进入文档体系：[长期目标](docs/north-star.md)、[架构合同](docs/architecture.md)、[研究方法](docs/research-methodology.md)、[当前唯一任务](docs/current-stage-goal.md)、[数据证据政策](docs/data-and-evidence-policy.md)、[执行状态](docs/execution-status.md)、[版本记录](CHANGELOG.md)。
可直接放入目标模式的文本见 [启动入口](docs/value-investment-goal-prompt.md)。文档审查与逐文件处置清单见 [2026-09-22 治理报告](docs/project-goal-consolidation-20260922.md)。
未来多个长期 Goal 的路线、真实审查和毕业标准见 [LONG-TERM-GOAL.md](LONG-TERM-GOAL.md)。当前活动 Goal 为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`，状态 `PARTIAL`：M2 Checkpoint A 已由用户签收，当前人工聚焦为 M3 Checkpoint B；Checkpoint B-D、私有 IPS/组合输入和 M6 生产授权仍未签收。C0-C3 与 M1 已冻结，不等于投资决策就绪。

三公司工程与 Excel MVP 已冻结，研究级估值、股息可持续性和生产数据分别验收。最新人工待办与签收边界见 [M2-M7 人工复核交接清单](docs/m2-m7-human-review-handoff-20260924.md)，当前 M3 复核对象见 [Checkpoint B 复核包](docs/m3-checkpoint-b-review-packet-20260924.md)。M7 从 `.env` 的 `WORKBOOK_PATH` 打开同一份 canonical workbook；候选文件仅保留为历史审计，不是产品入口。以下运维命令仅供既有部署维护参考，不自动授权初始化、改任务、发布原表或恢复模拟/交易开发。

## 当前入口导航

不要从平铺历史文件中猜当前入口。当前产品、命令和架构分别从以下位置进入：

| 目的 | 入口 |
| --- | --- |
| 当前文档 | [docs/current/README.md](docs/current/README.md) |
| 当前支持 CLI | [config/current-cli-entrypoints-v1.json](config/current-cli-entrypoints-v1.json) |
| 当前 artifact 逻辑注册表 | [artifacts/current/artifact-registry-v1.json](artifacts/current/artifact-registry-v1.json) |
| 脚本分类与历史工具说明 | [scripts/README.md](scripts/README.md) |
| 机器可读脚本清单 | [docs/architecture/script-inventory-v1.json](docs/architecture/script-inventory-v1.json) |
| 架构与迁移地图 | [docs/architecture/repository-architecture.md](docs/architecture/repository-architecture.md) |

根目录候选 Excel、manifest 和旧研究文档仍可能因路径或 Hash 证据而原地保留；它们不再等同于当前入口。

## 公开仓库范围

本仓库是可复现的公开源码库，包含应用源码、测试、部署定义、数据库建表/迁移 SQL、工作簿模板和 M2 候选发现快照，均不含个人账户及交易记录。当前服务器的应用源码以本仓库 `src/`、`scripts/`、`deploy/server/` 为维护源；服务器不会作为另一个未受版本控制的代码来源。

下列运行时资产绝不提交到 GitHub：`.env`、SSH 私钥、数据库导出及表数据、原始公告/PDF 证据、备份、Excel 故障回退副本、运行日志、个人持仓与交易记录。数据库结构可通过 `sql/server-schema-20260921.sql` 和迁移文件重建；生产数据应使用独立的加密备份和恢复演练机制管理。

## 能力边界

- 交易日收盘后拉取公共行情，并保存原始响应哈希与来源信息。
- 对缺失、过期、冲突或未复核数据实施门禁，分别表达研究、估值和价格评估状态。
- 将研究卡、证据、估值边界和变化发布到原 Excel，保留人工与历史记录；研究结论不生成交易指令。
- 每日生成备份清单；恢复演练必须连接独立数据库后才会执行。

公共数据仅用于研究辅助。影响实际交易的财务与公告数据必须以交易所或公司 IR 原文复核。

## 单一 Excel 工作簿

项目只维护 `.env` 中 `WORKBOOK_PATH` 指向的 `A股价值投资_Agent前端智能跟踪模板.xlsx`。工作簿保留在 WPS 云盘，代码、Git、运行环境、日志和备份位于 `D:\GPTProject\value-investment`。同步原位更新同一份工作簿；每次同步前在本地 `runtime/workbook-backups/` 保留故障回退副本。跨盘发布先在工作簿所在磁盘暂存并校验，再原子替换；文件被占用或编辑时保留本地预览，不强制覆盖。

日常同步通过专用 SSH 密钥下载服务器导出的数据并验证 SHA-256，本地用 Python/openpyxl 更新 Excel，不需要 Docker Desktop。数据库直读命令仍需要 Tailscale 私网。只指定一台电脑负责写回，其他设备通过 WPS 查看，避免多个设备并发同步。

## 首次启动

1. 配置本地 `.env`，将 `WORKBOOK_PATH` 设为 WPS 工作簿的完整路径。日志和未加密备份不要放入云盘。
2. 本地模式才需要 Docker Desktop；服务器中心模式不需要在电脑上启动 Docker。
3. 使用 Python 3.12+ 执行 `python -m venv runtime/venv`，再执行 `runtime/venv/Scripts/python.exe -m pip install -e .[dev]`。移动项目后需重建环境。
4. 配置本机专用 SSH 密钥；默认位置为用户目录下 `.ssh/id_ed25519_value_investment`，私钥不进入项目或云盘。
5. 执行 `powershell -ExecutionPolicy Bypass -File scripts/run_server_excel_sync.ps1` 验证同步。
6. 服务器已部署时不要在本机重复初始化生产数据库；采集由服务器任务完成。

## 日常命令

```powershell
python -m value_investment_agent update --prices
python -m value_investment_agent quality
python -m value_investment_agent snapshot-month --month 2026-09
python -m value_investment_agent backup
python -m value_investment_agent restore-verify
```

`restore-verify` 只允许使用 `RESTORE_DATABASE_URL` 指向的隔离数据库；未配置时会明确失败，不会碰生产库。

## 自动运行

下面的命令会创建本地 Windows 计划任务并影响日常生产同步。在用户单独授权生产调度、通知目标和服务器资源前不要执行；执行前必须保护服务器 PTA 项目的资源基线并准备回退方案。M6/M7 运营验收尚未开始，注册计划任务不等于运营就绪。

完成 `.env` 和 SSH 配置后，执行下面命令创建 Windows 计划任务。任务在每个工作日 16:50 启动；电脑需开机联网，错过后在可用时补跑。搬动项目目录后需要重新注册：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_daily_task.ps1
```

每次运行的日志位于本地 `runtime/logs/`；WPS 中的 Excel 原位更新，`runtime/workbook-backups/` 保留故障回退副本。可用下面命令手动试跑一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_server_excel_sync.ps1
```

## 数据来源

- 行情：第一期默认 AkShare；可在 `.env` 切换或新增适配器。
- 财报与公告：通过 `ingest-financials` 导入已下载的官方 CSV/JSON；每条数据必须包含来源 URL、发布日期和原始文件 Hash。
- 日常 Excel 同步：使用 Python/openpyxl，无需 Codex 附带的 Node 依赖。旧版数据库直读导出器仍使用 `@oai/artifact-tool`，其环境可通过 `scripts/setup-workspace-runtime.ps1` 配置。

## 备份与密钥

备份文件不包含 `.env`。将数据库口令和备份加密口令放入系统凭据管理器或单独的密码管理器；不要与云盘备份放在同一位置。
