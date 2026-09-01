# A股价值投资 Agent（第一期）

本项目把 `A股价值投资_Agent前端智能跟踪模板.xlsx` 作为研究和人工确认交易的前端，把 PostgreSQL 作为可追溯数据底座。它不会自动下单。

## 能力边界

- 交易日收盘后拉取公共行情，并保存原始响应哈希与来源信息。
- 对缺失、过期、双源冲突或未复核数据实施门禁；门禁失败时不输出建仓信号。
- 将已校验数据同步到 Excel 的观察名单、财务指标、估值跟踪、仓位管理和审计页。
- 每日生成备份清单；恢复演练必须连接独立数据库后才会执行。

公共数据仅用于研究辅助。影响实际交易的财务与公告数据必须以交易所或公司 IR 原文复核。

## 首次启动

1. 复制 `.env.example` 为 `.env`，设置 `BACKUP_DIRECTORY` 为你的加密云盘同步目录。
2. 本地模式才需要 Docker Desktop；服务器中心模式不需要在电脑上启动 Docker。
3. 使用 Python 3.12+ 创建虚拟环境并执行 `pip install -e .[dev]`。
4. 在 Codex Desktop 中执行 `powershell -ExecutionPolicy Bypass -File scripts/setup-workspace-runtime.ps1`，以启用 Excel 同步组件。
5. 初始化数据库：`python -m value_investment_agent init-db`。
6. 拉取行情并生成 Excel 副本：`python -m value_investment_agent update --prices`。

## 日常命令

```powershell
python -m value_investment_agent update --prices
python -m value_investment_agent quality
python -m value_investment_agent backup
python -m value_investment_agent restore-verify
```

`restore-verify` 只允许使用 `RESTORE_DATABASE_URL` 指向的隔离数据库；未配置时会明确失败，不会碰生产库。

## 自动运行

完成 `.env` 配置并启动 Docker Desktop 后，执行下面命令创建 Windows 计划任务。任务会在每个工作日 16:15 启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_daily_task.ps1
```

每次运行的日志位于 `runtime/logs/`，同步后的 Excel 位于 `runtime/`。可用下面命令手动试跑一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_update.ps1
```

## 数据来源

- 行情：第一期默认 AkShare；可在 `.env` 切换或新增适配器。
- 财报与公告：通过 `ingest-financials` 导入已下载的官方 CSV/JSON；每条数据必须包含来源 URL、发布日期和原始文件 Hash。
- Excel 同步：使用 Codex 工作区附带的 `@oai/artifact-tool`。在当前 Codex 环境运行 `python -m value_investment_agent sync-excel` 即可；若脱离该环境运行，请为 `scripts/node_modules` 配置同名依赖。

## 备份与密钥

备份文件不包含 `.env`。将数据库口令和备份加密口令放入系统凭据管理器或单独的密码管理器；不要与云盘备份放在同一位置。
