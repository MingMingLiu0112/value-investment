# Excel 工作簿版本记录

更新：2026-09-24。本文件记录公开仓库工作簿快照、WPS 云盘字节核对和 M2 原表统一发布
边界，不改变投资逻辑，不生成交易指令。当前项目状态为
`M2 / PENDING_HUMAN_REVIEW`、`M3 / M4 / M5 / PARTIAL`、
`M6 / NOT_STARTED`、`M7 / PARTIAL`，全部候选 `action=no_order`。

## 2026-09-24 M7 Daily Workbench v2 表述纠偏

新增第 21 个受 Git 跟踪的公开工作簿，只修正 M7 日常工作台对 M3 Historical
Research Replay 的时点表述，不覆盖 v1 候选、不改 canonical 或投资结论。

- 文件：
  `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx`
- SHA-256：
  `8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6`
- 构建入口：`scripts/build_m7_daily_workbench.py`
- WPS 只读验证：`runtime/m7-daily-wps-v2-20260924/receipt.json`，`passed`。
- WPS 云盘同名 v2 候选与仓库文件逐字节一致。
- 事实/行情 PIT 与追溯规则边界已在工作簿内明示，不再写成“真实 PIT / 当时规则”。
- WPS 验证收据新增
  `historical_replay_boundary.facts_quote_pit=true`、
  `contemporaneous_rule_pit=false`、`future_rule_version_used=true`。
- WPS 验证器已改为从 `UsedRange.Value2` 物化文本，避免本机 WPS COM 对
  `UsedRange.Text` 返回空串；候选 Hash 未变化。

## 2026-09-24 可重复执行 WPS 云盘副本审计

新增只读脚本 `scripts/audit_public_workbook_wps_copies.ps1`，遍历 Git 跟踪的全部
23 个公开工作簿，与 WPS 云盘同名副本逐项计算 SHA-256。实跑结果 `23/23 MATCH`；
脚本只生成 JSON 收据，缺失或不一致时失败关闭，不复制、移动或删除工作簿。新增静态
回归 `tests/test_public_workbook_wps_audit.py` 已进入 Core Research Gates。

- 收据：`runtime/public-workbook-wps-audit-final-20260924/receipt.json`。
- Core Research Gates run `35956322034`：`offline-core` 与 `postgres-integration`
  均 `success`。

## 2026-09-24 WPS 云盘全量字节审计

对 Git 跟踪的全部 23 个公开工作簿重新计算仓库与 WPS 云盘同名副本的 SHA-256，
结果 `23/23 MATCH`。本轮补齐以下 3 个此前缺少云盘同名副本的文件：

| 文件 | SHA-256 |
| --- | --- |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |
| A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_20260924.xlsx | `0230877890ad8f2e688e1218cd5707bb4c95b33a70a7da26e4c7afa8c3894409` |
| A股价值投资_M2通道验证人工复核包候选_20260924.xlsx | `53dee83af418249c27d3e4413855c231d585025d846e3a6b8953c3354faecc12` |

## 2026-09-24 最终公开工作簿上传记录

本轮核对基点为 `main` HEAD `19cd9b5`，该提交与 `origin/main` 一致且工作树干净。
以下 18 个公开工作簿均已由 Git 跟踪并上传至 GitHub；WPS 云盘中的同名公开副本与
仓库文件逐字节一致。本轮没有遗漏的公开工作簿字节，新增 Excel 已全部纳入既有提交。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| A股价值投资_Agent前端智能跟踪模板.xlsx | 13,199,222 | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx | 13,168,877 | `95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a` |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx | 13,199,222 | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |
| A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx | 13,200,586 | `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3` |
| A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx | 13,208,437 | `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d` |
| A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx | 13,262,051 | `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582` |
| A股价值投资_M2机会发现_20260923.xlsx | 53,299 | `a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821` |
| A股价值投资_M2机会发现_v2_20260923.xlsx | 1,020,221 | `4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63` |
| A股价值投资_M3决策卡候选_20260924.xlsx | 15,102 | `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d` |
| A股价值投资_M3历史链候选_20260924.xlsx | 12,121 | `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0` |
| A股价值投资_M4仓位与股息候选_20260924.xlsx | 11,504 | `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e` |
| A股价值投资_M4组合风险候选_20260924.xlsx | 10,060 | `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7` |
| A股价值投资_M5事件监控候选_20260924.xlsx | 14,989 | `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae` |
| A股价值投资_M5材料性接入候选_20260924.xlsx | 13,240 | `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df` |
| A股价值投资_M5真实披露待复核队列_20260924.xlsx | 13,130 | `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5` |
| A股价值投资_M5真实披露人工复核回填_20260924.xlsx | 13,885 | `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420` |
| M1_三公司研究Application候选_20260923_033001.xlsx | 17,357 | `0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbb51c3d34` |
| M1_三公司研究Application候选_20260923_122010.xlsx | 17,025 | `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8` |

未上传的本地边界文件继续为：WPS 本地回退件
`.A股价值投资_Agent前端智能跟踪模板.p2.stage.xlsx`、
`A股价值投资_Agent前端智能跟踪模板.checks.json`、人工使用手册、`runtime/`、
`*.manifest.json`、`*.receipt.json`、`.env` 及 M3 生成过程中的中间替换页
`*.m3-decision-addon.xlsx`。这些文件含本地路径、运行收据或临时回退内容，不是
公开产品工作簿，因此不加入公开仓库。

本次记录只确认上传清单与字节身份；上传完成不等于人工验收、估值正确或实盘准入。

## M7 统一工作台 v2 候选

本批新增第 20 个受 Git 跟踪的公开工作簿。它在原 90 页 M7 统一工作台候选上追加
第七个只读展示层 `M4/M5 联合检查点`，不修改或覆盖原 90 页候选，不发布 canonical，
也不导入真实组合或创建订单。

- 文件：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx`
- 字节数：13,271,164
- SHA-256：
  `d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc`
- 工作表：96 个。首张 `00_M7总览`；随后 29 个原 M4/M5 页面、6 个
  `M4M5联合_*` 页面，最后 60 页完整保留 M3 历史链叠加基底。
- 总览导航：10 个内部入口，新增 `M4M5联合_00_总览`。
- 构建入口：`scripts/build_m7_workbench_v2_candidate.py`
- WPS 只读验证：`runtime/m7-workbench-v2-wps-20260924/wps-verification.json`，
  `passed`；WPS 云盘同名副本与仓库候选逐字节一致。
- M7 v1/v2 定向回归：6 passed。
- GitHub 发布：release commit `0e922ab`；Core Research Gates
  [run 35941189851](https://github.com/MingMingLiu0112/value-investment/actions/runs/35941189851)
  为 `success`。
- 详细边界：[m7-workbench-v2-candidate-20260924.md](m7-workbench-v2-candidate-20260924.md)

该候选只证明 M4/M5 联合成果可以被同一个 M7 入口导航，不等同 Checkpoint D、
M7 交付、真实事件观察或实盘准入。

## M4/M5 联合检查点候选

本批新增第 19 个受 Git 跟踪的公开工作簿。它把 M4 组合风险、仓位与股息基线和 M5
有界依赖失效结果合并为一个只读联合状态，不重新计算仓位，不覆盖 canonical，也不
连接真实账户或生成订单。

- 文件：
  `A股价值投资_M4M5联合检查点候选_20260924.xlsx`
- 字节数：13,162
- SHA-256：
  `353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`
- 工作表：6 个。`00_总览`、`01_M4组合基线`、`02_M5事件批`、
  `03_依赖失效映射`、`04_联合产品状态`、`05_输入与边界`
- 模拟事件：4 个。仓位风险、分红变化、无关新财报、论点破坏。
- 联合状态：10 个产品 `PAUSED/NEGATIVE`，1 个无关财务事实保持 `READY`。
- WPS 只读收据：
  `runtime/m4m5-joint-wps-20260924/wps-verification.json`，`passed`
- 定向回归 4 passed；M4/M5 联合回归 72 passed。
- GitHub 发布：release commit `d6a3abd`，已推送 `origin/main`。
- GitHub Core Research Gates：
  [run 35939972803](https://github.com/MingMingLiu0112/value-investment/actions/runs/35939972803)，
  对应 `head_sha=d6a3abd32609f0f93e12605b2656d98a9c14dc71`，结论 `success`。
- 详细边界：[m4-m5-integration-20260924.md](m4-m5-integration-20260924.md)

该候选只证明 M4 与 M5 能通过同一依赖失效结果联动，不等同 Checkpoint C、真实事件
或实盘准入。真实组合输入、用户 IPS 与生产通知仍需后续授权。

## M6 运行控制上传记录

版本包 `v2026.09.24-m6-operational-control` 只新增 M6 运行控制状态机、
CLI、回归测试和 CI 配置，不修改任何公开 Excel 字节。本轮 Git 工作树中的
`.xlsx` 均无未提交修改；WPS 云盘与仓库中当前受跟踪的 18 个工作簿逐字节一致。
最新 M7 统一工作台候选继续为 13,262,051 字节，SHA-256
`829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`；
canonical 继续为
`64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

## M7 统一工作台展示候选

本批新增第 18 个受 Git 跟踪的公开工作簿。它把 M3 历史链叠加候选与六个 M4/M5
只读候选合并为一个 90 页的 M7 展示层候选，仅做统一入口准备，不发布 canonical，
不创建真实 IPS、持仓、决策或订单。

- 文件：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx`
- 字节数：13,262,051
- SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`
- 工作表：90 个。首张为 `00_M7总览`，随后是 29 个带前缀的 M4/M5 页面，
  最后 60 页完整保留 M3 历史链叠加候选。
- 本地 manifest：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.candidate.manifest.json`
- WPS 只读收据：
  `runtime/m7-workbench-wps-20260924/wps-verification.json`，`passed`
  （SHA-256：
  `c237b14482398b4903c13b0447ba406d11ec4688b8a17e3b99b045f1f5210e1e`）
- WPS 云盘同名副本与仓库候选逐字节一致；canonical SHA-256 仍为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 构建与状态详情：[m7-workbench-candidate-20260924.md](m7-workbench-candidate-20260924.md)
- 全量离线回归：2292 passed、6 skipped、0 failed。
- GitHub 修复提交 `fa23f05` 把 `graft` 新增层 ZipInfo 时间戳固定为
  `1980-01-01T00:00:00`；修复后 run `35933960701` 的 `offline-core` 与
  `postgres-integration` 均为 `success`。本次发布候选本身未重新生成，仍为
  `9e37435` 中冻结的 13,262,051 字节和上述 SHA-256；用修复后代码重建时，90 页
  工作表的解压 XML 内容保持一致，仅新增层 ZIP 元数据时间戳会规范化。

该候选只证明只读展示叠加可重复，不等同于 Checkpoint D、M7 交付或实盘准入。

## M3 历史链叠加候选

本批新增第 17 个受 Git 跟踪的公开工作簿。它把五页显式模拟历史链追加到已受保护的
M3 决策复核候选，不替换任何源页面，不覆盖 canonical，不读取真实账户或生成仓位/订单。

- 文件：`A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`
- 字节数：13,208,437
- SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`
- 工作表：60 个。前 5 页 `00_历史链`、`01_原Entry`、`02_决策日志`、
  `03_一致性复核`、`04_来源哈希`；后 55 页完整保留 M3 决策复核候选。
- 输入绑定：M3 决策复核候选 SHA-256
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`；
  独立历史链候选 SHA-256
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`；
  模拟历史输入 SHA-256
  `4969a5d3b8bb80dfa743807053a75bc4e1595a5081953ecff1a83ba56c8f057c`。
- WPS 只读收据：
  `runtime/m3-history-overlay-wps-20260924/wps-verification.json`，`passed`
- WPS 云盘同名副本与仓库候选逐字节一致；canonical SHA-256 仍为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- GitHub Core Research Gates 运行 `35931101091`：`offline-core` 与
  `postgres-integration` 均为 `success`；公开提交为 `d614b5b`。

该候选只演示模拟理由链与 M3 决策页的叠加形态，不等于 Checkpoint B、真实成交或
实盘准入。

## M5 真实披露待复核队列

本批新增一个独立、真实 CNINFO 数据驱动的 M5 披露队列，不自动判定材料性，也不修改
原 55 页生产工作簿：

- 文件：`A股价值投资_M5真实披露待复核队列_20260924.xlsx`
- 字节数：13,130
- SHA-256：
  `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5`
- 工作表：4 个，`00_总览`、`01_待复核公告`、`02_来源覆盖`、`03_输入与边界`
- 真实范围：600887、600741、000651，2026-08-27 至 2026-09-24
- 真实结果：41 条公告、24 条待人工复核候选、24 份候选 PDF、0 个来源失败
- WPS 只读收据：
  `runtime/m5-disclosure-review-20260923T213249Z/wps-verification.json`，
  `passed`
- WPS 云盘同名副本与本仓库候选逐字节一致
- Git 提交：`e81e99695a127f3ceead9d1e5fc6a98ce3bf0b49`

该候选只建立真实披露等待队列；材料性结论仍需用户逐条给出。

## M5 真实披露人工复核回填

本批新增一个独立、真实 CNINFO 数据驱动的 M5 人工复核回填工作簿。它把 24 条待复核
候选转为可由用户逐条填写的判定表，不预填结论，不执行 M5 事件，也不修改原 55 页
生产工作簿：

- 文件：`A股价值投资_M5真实披露人工复核回填_20260924.xlsx`
- 字节数：13,885
- SHA-256：
  `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420`
- 工作表：4 个，`00_总览`、`01_人工判定`、`02_判定说明`、`03_边界`
- 真实范围：600887、600741、000651，2026-08-27 至 2026-09-24
- 真实结果：24 条待人工复核候选，判定列和说明列均从空值开始
- 队列语义 SHA-256：
  `9ff56ebe8ab2902d4339fda881c0a0d4697a1066014f477053198dd00e4e905d`
- WPS 只读收据：
  `runtime/m5-disclosure-review-intake-20260924/wps-verification.json`，
  `passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该工作簿只是人工复核入口；24 条材料性结论仍需用户逐条给出。纳入当前清单后，
受 Git 跟踪的公开工作簿由 13 个增至 14 个。

## M5 材料性判定接入模拟候选

本批新增一个独立、显式模拟的 M5 材料性接入候选。它把人工材料性结论映射为事件、
依赖失效和 Outbox，不建立公告采集、生产调度或通知投递，也不修改原 55 页生产工作簿：

- 文件：`A股价值投资_M5材料性接入候选_20260924.xlsx`
- 字节数：13,240
- SHA-256：
  `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df`
- 工作表：6 个，`00_总览`、`01_材料性映射`、`02_事件账`、
  `03_依赖失效与重算`、`04_Outbox`、`05_输入与边界`
- 示例结果：6 项人工材料性判定、3 项静默、3 个事件、3 条失效记录、3 条 outbox
  提醒，固定 `action=no_order`
- WPS 只读收据：`runtime/m5-materiality-wps-20260924/receipt.json`，`passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该候选只演示人工材料性结论到 M5 事件的精确接入，不构成持续市场监控证明，也不生成
任何估值、仓位或投资建议。

## M5 事件监控模拟候选

本批新增一个独立、显式模拟的 M5 事件基础设施候选，不启动生产调度、不投递真实通知，
也不修改原 55 页生产工作簿：

- 文件：`A股价值投资_M5事件监控候选_20260924.xlsx`
- 字节数：14,989
- SHA-256：
  `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae`
- 工作表：6 个，`00_总览`、`01_事件账`、`02_水位与检查点`、
  `03_依赖失效与重算`、`04_Outbox`、`05_输入与边界`
- 示例输入：7 个事件输入、6 个当前有效事件、6 条失效记录、6 条 outbox 提醒，
  固定 `action=no_order`
- WPS 只读收据：`runtime/m5-event-wps-20260924/receipt.json`，`passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该候选只演示事件账、水位、检查点、锁、outbox 和有界依赖失效的结构，不构成持续市场
监控证明，也不生成任何投资建议。

## M4 分层仓位与股息收入模拟候选

本批新增一个独立、显式模拟的 M4 仓位与股息候选，不读取真实账户、IPS、现金或
持仓，也不修改原 55 页生产工作簿：

- 文件：`A股价值投资_M4仓位与股息候选_20260924.xlsx`
- 字节数：11,504
- SHA-256：
  `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e`
- 工作表：5 个，`00_总览`、`01_仓位分层`、`02_共同预算`、
  `03_股息收入`、`04_输入与边界`
- 示例结果：4 个仓位候选、4 个股息口径，固定 `action=no_order`
- WPS 只读收据：`runtime/m4-guidance-income-wps-20260924/receipt.json`，
  `passed`
- WPS 云盘同名副本与本仓库候选逐字节一致

该候选只演示预算、分层上限和收入口径，不构成真实组合建议、仓位分配或交易指令。

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
- Git 提交：`324694744b51a3f0c3f2316e1ce206ac6cad6cb2`
  `feat: add M4 portfolio-risk assessment and simulated Excel candidate`
- GitHub Core Research Gates：[run 35913005217](https://github.com/MingMingLiu0112/value-investment/actions/runs/35913005217)
  为 `success`；本地 M4 定向回归 11 passed

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
| A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx | 13,262,051 | 829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582 | 本轮 M7 展示候选 |
| A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx | 13,208,437 | 67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d | d614b5b |
| A股价值投资_M5真实披露人工复核回填_20260924.xlsx | 13,885 | 1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420 | 本轮 M5 人工复核回填 |
| A股价值投资_M5真实披露待复核队列_20260924.xlsx | 13,130 | 58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5 | e81e996 |
| A股价值投资_M5材料性接入候选_20260924.xlsx | 13,240 | e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df | 1017f1d |
| A股价值投资_M5事件监控候选_20260924.xlsx | 14,989 | 2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae | 2c66f86 |
| A股价值投资_M4仓位与股息候选_20260924.xlsx | 11,504 | 764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e | 207c937 |
| A股价值投资_M4组合风险候选_20260924.xlsx | 10,060 | 0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7 | 3246947 |
| A股价值投资_M3历史链候选_20260924.xlsx | 12,121 | 5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0 | 511c64a |
| A股价值投资_M3决策卡候选_20260924.xlsx | 15,102 | 589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d | 1338eab |
| A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx | 13,200,586 | ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3 | 本轮 M3 决策复核原工作簿候选 |
| A股价值投资_Agent前端智能跟踪模板.xlsx | 13,199,222 | 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911 | 8fdb361 |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx | 13,199,222 | 64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911 | 8fdb361 |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx | 13,168,877 | 95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a | 0566ed4 |
| A股价值投资_M2机会发现_20260923.xlsx | 53,299 | a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821 | f4bb55c |
| A股价值投资_M2机会发现_v2_20260923.xlsx | 1,020,221 | 4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63 | 71c0ad5 |
| M1_三公司研究Application候选_20260923_033001.xlsx | 17,357 | 0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbbd51c3d34 | 71c0ad5 |
| M1_三公司研究Application候选_20260923_122010.xlsx | 17,025 | 2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8 | 71c0ad5 |

其中受保护的三个生产工作簿快照如下：

- `A股价值投资_Agent前端智能跟踪模板.xlsx`：WPS 生产原表发布后的公开快照。
- `A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx`：与生产原表同一发布
  内容的独立 M2 候选快照。
- `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`：上一版 M2 候选快照。
- WPS 云盘同名生产原表：与当前 `A股价值投资_Agent前端智能跟踪模板.xlsx` 和
  `A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx` 逐字节一致，SHA-256
  相同。

## 2026-09-24 GitHub 上传对账

本次对账把版本记录补齐为全部 13 个受 Git 跟踪的工作簿，并确认 WPS 云盘同名副本与仓库
快照逐字节一致。对账基点为 `8d5e955cc04c14997f6d22a651abd7ff48370385`，该提交时本地
`main` 与 `origin/main` 一致，工作树干净；本轮只补充版本记录与变更说明，不修改任何
Excel 字节、投资逻辑或数据库。

- 受跟踪工作簿：18 个，均已推送到公开仓库；最新一次 Excel 新增为 M7 统一工作台
  展示候选。
- WPS 云盘比对：18 个同名工作簿字节数与 SHA-256 与仓库工作树一致。
- 不公开上传：`runtime/`、`.pytest-tmp-*`、顶层 `*.manifest.json`，以及 WPS 本地的
  `.A股价值投资_Agent前端智能跟踪模板.p2.stage.xlsx`、
  `A股价值投资_Agent前端智能跟踪模板.checks.json` 和人工使用手册。这些内容包含本地
  绝对路径、运行收据、故障回退或人工资料，不属于公开仓库工作簿清单。
- 状态边界不变：`M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，
  全部候选 `action=no_order`。上传完成不等于人工验收、估值正确或实盘准入。

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

## M3 决策复核原工作簿候选

本批新增第 16 个受 Git 跟踪的工作簿。它由当前 55 页 canonical 生成，只替换派生页
`00_决策复核`，不修改其他 54 页，也不覆盖 WPS 生产原表或 canonical 快照。

- 文件：`A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx`
- 字节数：13,200,586
- SHA-256：
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`
- 绑定输入：冻结 M1 integrated-runs SHA-256
  `b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459`；
  M1 预登记 SHA-256
  `5b7df98f8781080f66e5e053b8d0015f0b7c7eee9e27e8a10f7b0fe7990ab5b1`。
- WPS 只读验证：`passed`；WPS 云盘同名候选与仓库候选逐字节一致。
- 三张卡均为负向状态，`positive_review_count=0`，`action=no_order`。

本候选只证明 M3 决策 read model 能接入原工作簿派生页，不等同 Checkpoint B、M3 产品
验收或 canonical 发布。

## 状态

`M2` 为 `PENDING_HUMAN_REVIEW`，`M3/M4/M5` 为 `PARTIAL`。本记录确认工作簿快照、
哈希、发布前/发布后一致性和回退位置均已记录；不将 Excel 上传等同于估值、买入、
仓位或实盘准入通过。
