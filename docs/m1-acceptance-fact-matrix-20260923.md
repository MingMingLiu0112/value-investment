# M1 AC1-AC10 事实状态矩阵

更新：2026-09-23。本文件只汇总已实际生成的仓库产物与测试证据，不创造新的研究结论，不把待人工复核写成已完成。

状态词遵循 [current-stage-goal.md](current-stage-goal.md)：`DONE` 表示对应验收已由可复核产物和测试支持；`PARTIAL` 表示数量或工程部分完成、仍有质量门或事实缺口；`PENDING_HUMAN_REVIEW` 表示机器证据已存在，但 G3、事件重要性或研究深度仍需人工判断；`PENDING_EXTERNAL_DATA` 表示外部事实尚未形成，不能由工程推进替代。

## 结论

`M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 仍为 `IN_PROGRESS`。工程闭环和首个三公司 Application 已成立，但 AC4、AC6、AC10 仍有明确人工复核项，正常化股息仍未完成，因此不能把 M1 标为 achieved，也不能把条件估值升级为价格吸引力或买入判断。

## 验收矩阵

| AC | 状态 | 已实际完成的证据 | 未通过/需复核部分 |
| --- | --- | --- | --- |
| 1 | DONE | 原三公司冻结回归 `48 passed`；新增 000651/600741/600887 三份包由共享 `m1-valuation-package-builder`、`m1-distribution-package-builder` 与 Application 服务运行，没有为新增公司复制整条 symbol 专用 pipeline | 本项只证明工程可复用，不证明三公司生产研究或估值已完成 |
| 2 | DONE | `research_input` / `research_read_model` / `research_application` / `research_gate` / `m1_*` 回归覆盖错日期、未来披露、事实/假设绑定、规则变化、坏 descriptor 隔离；本轮聚焦测试 `82 passed` | 全仓库仍有一个与旧茅台硬编码日期相关的已知失败，不计入本轮 M1 新增路径；见 execution-status |
| 3 | DONE | 预登记 20 家；`report_m1_research_dossiers.py` 实测 `READABLE=6, BLOCKED=3, NOT_STARTED=11`；负面/不支持公司仍可见，没有伪装 READY。六份 READABLE 档案均含 8 个 BusinessQuality 维度、FinancialQuality、CapitalAllocation、Thesis、反证、breaker 与下一事件，事实/解释项绑定官方 PDF 引用，未知维度显式标出 | `DONE` 只表示研究档案达到可读和可追溯要求，不表示研究内容已人工批准、估值完成或任何公司可投资 |
| 4 | PENDING_HUMAN_REVIEW | 三公司条件估值已产出：000651 FCFF、600741 FCFF、600887 剩余收益；均含 Bear/Base/Bull、3 个敏感性、2 个反向估值；`action=no_order` | 每家公司 `model_validity.status=VALID` 但同时带 `pre-model disclosures require human review before the model basis is complete`；G3 未批准，价格吸引力仍 `NOT_ASSESSABLE` |
| 5 | DONE | 伊利、华域、格力三家均有官方生命周期证据支撑的 `LOW` 可持续性评估；paid/proposed、普通/特别、事实/政策/预测、当前/正常化分层均在分布包与 Excel 中分开 | 三家正常化股息情景仍 `NOT_READY`；低可持续性不等于可投资结论 |
| 6 | PENDING_HUMAN_REVIEW | 000651/600741/600887 报价日均为 2026-09-22，双源/带日期报价已核验；三家 PriceBridge 均为 `READY`；三家 CNINFO 事件扫描均为 `COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW` | 三家事件扫描均为 `pre_model_review_status=PENDING_HUMAN_REVIEW`；标题规则分类不能替代人工阅读公告原件判断重要性 |
| 7 | DONE | `m1-pit-source-replay-20260923T042556Z` 对格力、华域、伊利真实官方财报重放信息可用边界；每家 2 份原件、4 个边界、3 个未来披露排除点；另保留五粮液真实财报更正 replay 反例 | 这是来源可用性 replay，不是估值或交易策略回测 |
| 8 | DONE | 新冷回放 `m1-postgres-cold-replay-20260923T060159Z`：PostgreSQL 18.6，首轮写入 30 个制品，冷重启后验证 30/30，`semantic_equality=true`，`action=no_order`；receipt SHA-256 `bd643fc080c82d2c174948067918488ae8c38aee2f6a615d763d7bc9ed9286e8` | 隔离 loopback 回放，不等同于生产数据库或跨设备持久化验收 |
| 9 | DONE | 42 页受保护候选已原子发布进原 WPS 工作簿；前 6 页为 M1 Application，原 36 页 worksheet XML 逐字节未变；发布后工作簿 SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，WPS 只读打开/重算校验 passed | 当前收据不含桌面鼠标逐链接视觉点击验证；用户对六个新页的最终可用性确认属于人工复核 |
| 10 | PENDING_HUMAN_REVIEW | 全部运行结果 `action=no_order`；未连生产 PostgreSQL、未 SSH、未改 PTA 或计划任务、未降低数据门禁 | G3 估值批准与事件重要性阅读仍未由人工完成；这些不是工程缺口，而是 M1 事实边界 |

## 三公司条件估值与价格桥接

| 公司 | 模型 | Bear | Base | Bull | 报价日/价格 | Bridge | 研究结论 |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 000651 格力电器 | FCFF | 65.6683 | 83.2519 | 97.7513 | 2026-09-22 / 38.18 | READY | 估值未就绪 |
| 600741 华域汽车 | FCFF | 24.4786 | 33.7466 | 39.9382 | 2026-09-22 / 14.92 | READY | 估值未就绪 |
| 600887 伊利股份 | 剩余收益 | 10.3718 | 17.0230 | 24.0717 | 2026-09-22 / 26.77 | READY | 估值未就绪 |

三组数值都是 `conditional_research_only`，不是合理价或买卖点。价格低于某个条件情景包络只能说明“当前价格不在该研究包络内”，不能自动形成安全边际或买入结论。

## 六份 READABLE 档案

| 代码 | 公司 | 画像 | 档案第一阻断示例 |
| --- | --- | --- | --- |
| 600887 | 伊利股份 | quality_compounder | 2026 半年报未经审计 |
| 000651 | 格力电器 | mature_manufacturing | ROIC 与增量 ROIC 未计算 |
| 600188 | 兖矿能源 | cyclical_cash_return | 正常化利润、维护资本开支与单位成本/运输口径未完成 |
| 000858 | 五粮液 | quality_compounder | 2026 半年报未经审计 |
| 600690 | 海尔智家 | mature_manufacturing | 2026 半年报未经审计 |
| 600741 | 华域汽车 | mature_manufacturing | 2026 半年报未经审计 |

`READABLE` 表示研究内容已完整呈现且未知项显式可见，不表示研究批准、估值有效或交易可执行。

## 主要收据

| 收据 | 路径 | SHA-256 |
| --- | --- | --- |
| 当前 M1 Application | `runtime/m1-research-application-20260923T055026Z/evidence.json` | `f76356886a58ef5a497822ee3b477f4c13f05b6f833114afc063e87bdbea342f` |
| 隔离 PostgreSQL 冷回放 | `runtime/m1-postgres-cold-replay-20260923T060159Z/receipt.json` | `bd643fc080c82d2c174948067918488ae8c38aee2f6a615d763d7bc9ed9286e8` |
| 三公司真实披露 PIT replay | `runtime/m1-pit-source-replay-20260923T042556Z/evidence.json` | `f9a19f4da5d06ace7cb5b681e910925f45137f3c17df9e600be0f782ae34bf7f` |
| 格力股息生命周期 | `runtime/company-research/m1-dividend-lifecycles/20260923T055500Z/manifest.json` | `41f2114f7261370984e0219a8ec13aba658ff6f7b32af2b97c2ae7430b97c965` |
| 三家事件扫描清单 | `runtime/company-research/m1-event-scans/20260923T051018Z/manifest.json` | `96db1ce5c187c90de3e99b28fba398b2a5050cf95159bf2fd4dc79004426443d` |
| M1 集成 Excel 候选/发布文件 | `runtime/m1-integrated-dividend-20260923T055026Z/M1-integrated-candidate.xlsx` | `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58` |

## 不成立的结论

- 不成立：三家估值已经可指导买卖。事实：G3 与事件重要性仍未人工批准。
- 不成立：股息率约 7.86% 可以直接决定格力吸引力。事实：这是 trailing paid 事实快照，尚未完成正常化与法人层级可分配现金核对。
- 不成立：PostgreSQL 冷回放通过代表生产备份已验收。事实：这是 loopback 隔离 replay，只证明当前输入包可恢复且语义不变。
- 不成立：Excel 发布完成代表 M1 完成。事实：AC4/AC6/AC10 仍为 `PENDING_HUMAN_REVIEW`。

人工复核入口见 [m1-human-review-checklist-20260923.md](m1-human-review-checklist-20260923.md)；带逐条公告原件的直接决策表见 [m1-human-review-packet-20260923.md](m1-human-review-packet-20260923.md)。

## 机器复算入口

本矩阵已由 `scripts/audit_m1_acceptance.py` 从当前 runtime/config/WPS 收据重新核对。命令：

```powershell
D:\APP\Python313\python.exe scripts\audit_m1_acceptance.py --run-tests
```

最新自动审计收据为 `runtime/m1-acceptance-audit-20260923T063453Z/receipt.json`，SHA-256 `5c267d7811ba3460034fe7cead824c8a4d4b1f2c4b770cbb37549ca9e56721f4`。审计器只读，不会自动批准 G3 或事件重要性。
