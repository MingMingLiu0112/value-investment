# A股价值投资 Agent（第一期）

本项目把 `A股价值投资_Agent前端智能跟踪模板.xlsx` 作为研究和人工确认交易的前端，把 PostgreSQL 作为可追溯数据底座。它不会自动下单。

## 能力边界

- 交易日收盘后拉取公共行情，并保存原始响应哈希与来源信息。
- 对缺失、过期、双源冲突或未复核数据实施门禁；门禁失败时不输出建仓信号。
- 将已校验数据同步到 Excel 的观察名单、财务指标、估值跟踪、仓位管理和审计页。
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
