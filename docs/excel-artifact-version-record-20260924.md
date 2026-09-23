# Excel 工作簿版本记录

更新：2026-09-24。本文件记录公开仓库工作簿快照、WPS 云盘字节核对和 M2 原表统一发布
边界，不改变投资逻辑，不生成交易指令。当前项目状态为 `M2 / PENDING_HUMAN_REVIEW`，
`action=no_order`。

## M4 组合风险模拟候选

本批新增一个独立、显式模拟的 M4 组合风险候选，不读取真实账户、IPS、现金或持仓，
也不修改原 55 页生产工作簿：

- 文件：`A股价值投资_M4组合风险候选_20260924.xlsx`
- 字节数：10,060
- SHA-256：
  `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7`
- 工作表：4 个，`00_组合风险`、`01_持仓与集中度`、
  `02_风险发现`、`03_输入与边界`
- 示例组合：3 个模拟持仓，3 项风险发现，固定 `action=no_order`
- WPS 只读收据：`runtime/m4-portfolio-risk-wps-20260924/receipt.json`，
  `passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该候选只演示非个人化风险计算结构，不构成真实组合报告、仓位建议或交易指令。

## M3 论点连续性历史链模拟候选

本批新增一个独立、显式模拟的 M3 历史链候选，不改写原 55 页生产工作簿，不读取
真实账户或真实 Entry：

- 文件：`A股价值投资_M3历史链候选_20260924.xlsx`
- 字节数：12,121
- SHA-256：
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`
- 工作表：5 个，`00_历史链`、`01_原Entry`、`02_决策日志`、
  `03_一致性复核`、`04_来源哈希`
- 示例证券：600887，仅 `simulated`，结论 `action=no_order`
- WPS 只读收据：`runtime/m3-history-wps-20260924/receipt.json`，`passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该候选演示原 Entry 到持有、论点削弱、论点破坏和减仓复核的结构，不构成任何投资
建议，也不能替代真实 Entry 确认或 Checkpoint B 用户验收。

## M3.1 提交对工作簿的影响

`v2026.09.24-m3-shared-decision-domain` 只提交 M3 共享决策域代码、测试、CI 与文档，
不修改任何 Excel 文件字节。当前仓库 canonical、独立候选和 WPS 云盘生产原表继续逐字节
一致，三处 SHA-256 均为：

- `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`

公开仓库中的两个新发布快照文件名分别是
`A股价值投资_Agent前端智能跟踪模板.xlsx` 和
`A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx`；它们是同一内容的两个受保护
快照，不表示 M3 已产生新的估值、买入、仓位或订单。

## M3.2 独立决策卡候选

M3.2 本轮只发布一个独立候选工作簿，不改写原 55 页生产工作簿。候选只展示三张真实
负向决策卡、缺失输入、来源 Hash 和冻结证据链接：

- 文件：`A股价值投资_M3决策卡候选_20260924.xlsx`
- 字节数：15,102
- SHA-256：
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`
- 工作表：4 个，`00_决策卡`、`01_缺失与阻断`、`02_来源哈希`、`03_证据引用`
- 卡片结论：000651、600741、600887 均为 `INSUFFICIENT_RESEARCH`、
  `action=no_order`、`positive_review_count=0`
- WPS 云盘同名副本与本仓库候选逐字节一致；WPS 只读收据
  `runtime/m3-decision-card-wps-20260924/receipt.json` 为 `passed`

该候选尚未并入原工作簿 `00_决策复核`。原 canonical、M2 候选与 WPS 生产原表的
SHA-256 继续为
`64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

## M3 决策卡验收审计版本包

`v2026.09.24-m3-decision-acceptance-audit` 只新增 M3 机器审计、测试、CI 与复核清单，
不修改任何公开 Excel 字节。上表两个 M3/M2 公开工作簿和 WPS 云盘原表继续保持不变：

- 提交：`41ac62cf77a1e01aaf123c0809ad4baf4bea2a84`
- CI：[Core Research Gates](https://github.com/MingMingLiu0112/value-investment/actions/runs/35907116392)
  `success`；`offline-core` 与 `postgres-integration` 均通过
- M3 候选仍为 15,102 bytes，SHA-256
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`
- 原 55 页工作簿仍为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`

## 2026-09-24 GitHub 上传核验

- 基准提交：`0761b390e56a97695d328305d40b253cb6aab503`
  `Add M3 shared decision domain contracts`
  （提交时间 `2026-09-24T02:17:45+08:00`）。
- `git status --short --branch` 为 `## main...origin/main`，工作树干净；
  `git ls-remote` 核对远端 `origin/main` 与本地上传目标一致。
- 新建 Excel `A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx` 已于
  `8fdb361`（`2026-09-24T01:02:06+08:00`）纳入公开仓库；当前文件字节数
  `13,199,222`，SHA-256 保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 仓库 canonical、同内容 M2 候选与 WPS 云盘生产原表三者继续逐字节一致；
  本轮核验未产生新的 Excel 字节变更、未发现未跟踪工作簿，也未改变
  `action=no_order` 边界。

## 本版发布事件

本版把 M2 AC8 研究报告与证据并入原有 WPS 工作簿，并在受保护发布后统一仓库 canonical、
独立候选和 WPS 云盘生产原表。

- 发布前原工作簿 SHA-256：
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- 发布后工作簿 SHA-256：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`
- 回退原件：
  `runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/before.xlsx`
- 发布收据：
  `runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/publication.json`
- WPS 发布前收据：
  `runtime/m2-original-candidate-20260924-v4/wps-prepublication.json`
- WPS 发布后收据：
  `runtime/m2-original-candidate-20260924-v4/wps-published.json`

本版新增工作簿结构为 55 个工作表：13 个 M2、6 个 M1 Application、36 个原工作簿页；
42 个原有工作表被保留，96 个原始部分未变化。研究报告页 22 行，研究证据页 245 行，
识别 228 个来源链接。

WPS 只读校验只覆盖打开/计算、公式错误、工作表顺序和链接数量，不覆盖人工逐链接或视觉
点击，因此 AC8 仍为 `AC8_REVIEW_PENDING`，AC10 为机器检查通过、用户审核待完成，M2 不因
本版宣告完成。

## 当前公开工作簿清单

| 文件 | 字节数 | SHA-256 | 最近提交 |
| --- | ---: | --- | --- |
| A股价值投资_M3决策卡候选_20260924.xlsx | 15,102 | 589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d | 本轮 M3.2 独立候选 |
| A股价值投资_Agent前端智能跟踪模板.xlsx | 13,199,222 | 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911 | 本轮 M2 AC10 集成发布 |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx | 13,199,222 | 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911 | 本轮 M2 AC10 集成发布 |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx | 13,168,877 | 95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a | 0566ed4197135008648bf3f3046ac49d481aed63 |
| A股价值投资_M2机会发现_20260923.xlsx | 53,299 | a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821 | f4bb55cd686838b874b6a8b0c601492c8bd7aab5 |
| A股价值投资_M2机会发现_v2_20260923.xlsx | 1,020,221 | 4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |
| M1_三公司研究Application候选_20260923_033001.xlsx | 17,357 | 0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbbd51c3d34 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |
| M1_三公司研究Application候选_20260923_122010.xlsx | 17,025 | 2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |

其中前三行是本仓库当前受保护工作簿，含义分别如下：

- 第一行：M3.2 独立决策卡候选，尚未并入原生产工作簿。
- 第二行：WPS 生产原表发布后的公开快照。
- 第三行：与第二行同一发布内容的独立 M2 候选快照。
- WPS 云盘同名生产原表：与第二、三行逐字节一致，SHA-256 相同。

## M2 AC1-AC12 审计器版本包

本版本新增的 M2 统一验收审计器不创建第二份“最新工作簿”，只继续核对上表 canonical、
候选和 WPS 生产原表三者的字节一致性。当前三者仍为
`64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`；
新提交中的 Excel 文件与上表相同，未发生额外字节变更。

- 审计配置：`config/m2-acceptance-audit-v1.json`
- 审计模块：`src/value_investment_agent/m2_acceptance_audit.py`
- 审计命令：`scripts/audit_m2_acceptance.py`
- 回归测试：`tests/test_m2_acceptance_audit.py`

后续 CI 修复提交把回归测试中的完整 audit 调用改为不依赖 Git 忽略目录 runtime/
的封闭 AC1/AC12 单元回归。该修复只改测试与版本记录，三个公开工作簿快照和
WPS 生产原表的字节、SHA-256 均保持不变。

## 被替换前的历史 canonical

本轮替换前，仓库和 WPS 云盘的原工作簿版本为：

- 文件：`A股价值投资_Agent前端智能跟踪模板.xlsx`
- 字节数：12,210,200
- SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- 回退副本：`runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/before.xlsx`

该历史版本已不再位于公开仓库当前快照，但发布前 Hash 和回退原件仍可核对。

## 不上传的本地文件

以下 WPS 云盘文件属于本地故障回退、WPS 校验或人工资料，按公开仓库边界不提交：

- `.A股价值投资_Agent前端智能跟踪模板.p2.stage.xlsx`
- `A股价值投资_Agent前端智能跟踪模板.checks.json`
- `价投跟踪系统_框架逻辑与使用手册.docx`

## 状态

`M2` 仍为 `PARTIAL`。本记录确认工作簿快照、哈希、发布前/发布后一致性和回退位置均已记录；
不将 Excel 上传等同于估值、买入、仓位或实盘准入通过。
