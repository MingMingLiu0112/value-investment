# M7 初步辅助使用候选运行手册：2026-09-24

更新：2026-09-24。本文只说明当前 `M7 Daily Workbench v2` 候选如何安全查看、
核验和退出，不代表 M7 已验收。当前状态仍为 `PENDING_USER_ACCEPTANCE`，
所有 Review 都需用户人工决策，系统固定 `action=no_order`。

## 1. 打开哪个文件

优先打开 WPS 云盘 `价投跟踪` 文件夹中的：

```text
A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx
```

同一文件在仓库中的路径为：

```text
D:\GPTProject\value-investment\A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx
```

该候选 SHA-256：

```text
8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6
```

打开后保持只读。不要把它当作交易账户，也不要直接修改或另存覆盖生产
`A股价值投资_Agent前端智能跟踪模板.xlsx`。

## 2. 十个主入口分别看什么

| 工作表 | 用途 | 当前重点 |
| --- | --- | --- |
| `00_今日总览` | 一天内首先看什么 | 状态、边界和当前无订单结论 |
| `01_全市场与数据健康` | 官方范围、四通道和 Quality 覆盖 | Quality 财务证据仅 873/5568，属覆盖受限 |
| `02_候选与重点关注` | LEAD 与二阶段结论 | 3 个进入深研，不等于 3 个买入目标 |
| `03_决策复核` | 三张负向卡和正向价格门 | 当前无 BUY/ADD 人工复核可放行 |
| `04_当前持仓与仓位` | 组合风险和容量状态 | 缺真实 IPS/组合，明确等待用户输入 |
| `05_股息现金流` | 普通/特别股息与正常化边界 | 模拟工程展示，非个人现金流结论 |
| `06_事件与预警` | 公告队列和旧复核复用 | 24 条中 23 条继承，1 条新增待人工看 |
| `07_公司研究` | 已知公司研究限制 | 格力、华域、伊利仍需进一步研究 |
| `08_买卖逻辑与历史` | Original/Current、模拟/历史 | 历史回放最终为 `WAIT`，不是收益证据 |
| `09_审计与证据` | 路径、Hash 和上游收据 | 可从候选回到 runtime JSON 与原始公告 |

隐藏页 `_模块状态矩阵`、`_审计明细索引` 只作技术审计，不需要每天阅读。

## 3. 每次打开前的最小核验

在 PowerShell 7 中执行：

```powershell
$root = 'D:\GPTProject\value-investment'
$candidate = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx'
$manifest = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.m7-daily-workbench-manifest.json'
$canonical = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板.xlsx'

Get-FileHash -Algorithm SHA256 -LiteralPath $candidate
Get-FileHash -Algorithm SHA256 -LiteralPath $manifest
Get-FileHash -Algorithm SHA256 -LiteralPath $canonical
```

当前冻结值：

| 文件 | SHA-256 |
| --- | --- |
| M7 Daily v2 候选 | `8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6` |
| M7 Daily v2 manifest | `67b67b5ddc9725d0c701825c6959c09b2baf75e4c7a72fdd59bc2e492951bdde` |
| 生产 canonical | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |

任一 Hash 不一致时先停止使用该候选，不要据此做任何投资判断，也不要覆盖生产
工作簿；先保留现场并重新从 Git 或 WPS 云盘同名历史副本核对。

## 4. 机器复核命令

WPS 只读复核会实际打开候选、检查 10 个可见页、2 个隐藏页、公式错误、
历史回放时点表述和 `no_order` 边界。执行前确认候选没有被 WPS 占用：

```powershell
$root = 'D:\GPTProject\value-investment'
$candidate = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx'
$manifest = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.m7-daily-workbench-manifest.json'
$canonical = Join-Path $root 'A股价值投资_Agent前端智能跟踪模板.xlsx'
$receipt = Join-Path $root 'runtime\m7-daily-wps-runbook-20260924\receipt.json'

& 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File (Join-Path $root 'scripts\verify_m7_daily_workbench_wps.ps1') `
  -WorkbookPath $candidate `
  -ReceiptPath $receipt `
  -ExpectedSha256 '8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6' `
  -PackagePath $manifest `
  -CanonicalPath $canonical `
  -ExpectedCanonicalSha256 '64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911'
```

WPS 云盘公开工作簿全量一致性可重复执行：

```powershell
& 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File 'D:\GPTProject\value-investment\scripts\audit_public_workbook_wps_copies.ps1' `
  -WpsRoot 'C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪' `
  -ReceiptPath 'D:\GPTProject\value-investment\runtime\public-workbook-wps-audit-runbook-20260924\receipt.json'
```

两个脚本都是审计入口；失败时不关闭用户打开的文件，也不修改 canonical。

## 5. 日常阅读规则

1. 先看 `00_今日总览`。没有重要变化时，允许结论就是“今日无重要变化”。
2. 把 `LEAD`、`VERIFIED_FOR_DEEP_RESEARCH`、`REJECTED_AFTER_VERIFICATION` 分开，
   不要把候选数量当买入数量。
3. 当前没有真实 IPS 和持仓，`04_当前持仓与仓位` 不能给出个人仓位。
4. M3 历史回放的事实、公告、报价是 point-in-time，但 Median-PE 规则是
   2026-09-12 注册的追溯研究扩展，`future_rule_version_used=true`，最终为 `WAIT`。
5. 任何买卖、加仓、减仓或退出判断仍由用户人工完成；本候选不提供自动订单。

## 6. 故障与回退

- 候选打不开或公式错误：停止使用，保持 canonical 不动，重新运行机器复核命令。
- WPS 提示文件占用：不要强制关闭 WPS；等占用解除后再验证。
- WPS 云盘副本与仓库 Hash 不一致：以当前仓库冻结 Hash 为准继续追查，不同步覆盖。
- 需要回退本地候选时，只回退候选文件，不执行 `git reset --hard`，不清空仓库。
- 生产 canonical 被改动时，先确认改动来源并保存现场，不在未确认前覆盖。

## 7. 私有数据与授权边界

- 本候选没有导入真实 IPS、现金、持仓、券商账号或通知目标。
- 以后提供真实组合时，应使用用户确认的私有、加密存储，不进入公开 GitHub。
- 生产数据库迁移、计划任务、通知和 shadow 运行都仍需要单独授权。
- M6 尚未开始运营，M7 未完成用户签收，不能用本手册替代 Checkpoint D。

## 8. 已知限制与复审日期

支持范围：固定样本研究、四通道线索发现、M3/M4/M5 只读工程展示。

当前不支持：自动下单、券商接口、实时盘中流、个人化仓位建议、生产通知、
全行业估值模型和盈利保证。

下一复审：用户完成 M2 Checkpoint A、M3 卡片理解和 M7 Daily v2 阅读确认后，
根据真实输入与授权状态重新评审；在此之前保持 `PARTIAL`。
