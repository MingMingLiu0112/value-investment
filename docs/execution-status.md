# 当前执行状态

更新：2026-09-22。本文只记录事实，不制定新任务。唯一活动任务见 [current-stage-goal.md](current-stage-goal.md)。
此前完整运行记录原样归档于 [execution-status.md 历史快照](archive/goal-consolidation-20260922/execution-status.md)。

## C0 验收基线

- HEAD：`2baa77e86c31259d6f82de7cf1400e64d680d84b`。
- 提交时间：2026-09-22 15:33:49 +08:00；提交信息：`Consolidate-project-governance-and-current-stage-goal`。
- C0 开始前工作树干净。当前 C0 改动尚未提交，不表示已部署或已推送。
- 修复前复现：`600519 valuation + 000333 ModelValidity(unrelated-model) + quote evidence=[]` 返回 `READY / margin_to_base=0.1`；定向基线 `35 passed`，但没有覆盖该身份漏检。
- 未连接服务器、生产数据库或定时任务；未重做原始财报、行情或重大事项审计。

## C0 验收结果

C0-PRICE-BRIDGE-INTEGRITY：`PASSED_FOR_FREEZE`。

本阶段只修复共享价格桥接合同，不新增公司、模型、数据源或交易能力。核心改动如下：

- 新增 `QuoteSnapshot`：绑定证券、报价日、价格、状态和证据；`verified_close` 必须有正有限价格及 Hash 地址化证据。
- 收紧 `ModelValidity`：要求非空模型 ID、六位证券代码、命名证据；VALID 必须覆盖报价日且完成无重大事项检查。
- 收紧 `PriceBridgeResult`：保存 schema、模型 ID/版本/as-of、报价证券、绑定估值情景，并在构造时重算两个 margin。
- 增加 `bridge_with_quote()` 主入口，保留 `bridge()` 兼容入口；直接构造和 JSON 恢复都必须满足相同身份、版本、时点、报价证据和 margin 不变量。
- `current_research_status_from_payloads()` 不再用估值 symbol 覆盖桥接身份，改为同时校验 gate、valuation、price_bridge、model_validity。
- 下游价格吸引力对身份绑定失败返回 `NOT_ASSESSABLE`；坏桥接不会升级为 `RESEARCH_ATTRACTIVE`。
- 旧 runtime 载荷按 legacy 合同显式恢复。茅台旧 READY 必须携带其 model_validity 并重新通过绑定校验，恢复结果增加 `legacy_price_bridge_contract_revalidated` 标记；美的和神华继续保持 fail-closed。

验证证据：

- 定向防回归：`47 passed`，包含三公司冻结回归和茅台导出回归。
- Core Gate 清单：`102 passed`。
- 全量测试：`1896 passed, 1 skipped, 18 warnings`。本机默认 pytest 临时目录被另一 Windows 账户占用，改用项目内 `--basetemp` 后通过；未改变测试内容。
- `compileall` 通过；`git diff --check` 通过。
- 三公司 runtime 四个 evidence.json Hash 与冻结记录一致；原 WPS 工作簿 Hash 仍为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`。
- 未改动 runtime Hash、历史 acceptance、估值参数、原 Excel、数据库、计划任务或服务器服务。

## 阶段语义

三公司统一工程/Excel 验收已通过并冻结。C0 通过表示共享价格桥接身份和反序列化合同已修复，不代表研究、估值、股息能力、生产数据或价格判断已经完成。

| 维度 | 600519 贵州茅台 | 000333 美的集团 | 601088 中国神华 |
| --- | --- | --- | --- |
| Engineering Complete | READY：三公司路径和 C0 共享桥接合同已冻结 | READY：FCFF 算术和拒绝边界，不等于该公司估值 | READY：周期算术和拒绝边界，不等于该公司估值 |
| Research Complete | PARTIAL：商业/财务材料与论点存在，G3 未通过 | PARTIAL：事实范围 MODEL_NOT_APPLICABLE | PARTIAL：正常化假设和财务门未通过 |
| Valuation Complete | PARTIAL：低置信度 conditional_research_only | NOT_READY：无三情景值 | NOT_READY：无三情景值 |
| Dividend Research Complete | PARTIAL：有历史分红及分配交叉检查 | PARTIAL：有历史派息与部分财务材料 | PARTIAL：有派息与周期候选材料 |
| Production Data Ready | 2026-09-21 快照 READY；未验证 09-22 当前生产 | PENDING_EXTERNAL_DATA，并存模型适用性问题 | PENDING_EXTERNAL_DATA，并存未注册假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE：低置信度及研究门限制 | NOT_ASSESSABLE | NOT_ASSESSABLE |

三家公司完整 DividendSustainability 评估均未完成。美的与神华缺失不能全称“等行情”：前者含 MODEL_NOT_APPLICABLE，后者含 ASSUMPTION_MISSING / 未注册模型输入，需不同处理。

## 当前可追溯产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司研究卡 | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 茅台条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `5fd86bd643d958a93462905f32eae57fad3e8a7ee6c8986dce7ba2ef73ee9495` |
| 美的未就绪结果 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 神华未就绪结果 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |

茅台估值/报价日期均为 2026-09-21，条件情景 403.44 / 478.43 / 571.25 元每股；此处仅描述冻结模型，不是当前合理价或投资建议。美的、神华载荷日期为 2025-12-31，不能称作今日估值。

## 剩余风险与边界

- C0 是工程合同验证，不替代生产行情、公告或重大事项复核；当前价格评估仍为 NOT_ASSESSABLE。
- 旧 `bridge()` 兼容入口仍会从散字段临时构造 QuoteSnapshot。后续调用方应逐步切换到显式 QuoteSnapshot，但当前旧 runtime 已 fail-closed 恢复。
- 模型身份当前从估值 evidence Hash 和 model_version 集合校验，尚未迁移到 PostgreSQL 的持久化模型快照注册表。
- 全市场漏斗、正式股息可持续性、Web 前端和券商接入均未实现，不属于 C0 回归范围。

## 唯一建议后续任务

`NEXT TASK: 固定样本准入协议与公共编排审查`。目标是在扩样本前，把“流程可复用”和“生产估值可用”分开：定义三家公司进入固定研究样本的准入证据、可复用的公共编排入口、失败退出和人工确认边界；不改估值参数，不连接自动交易。

当前 C0 已完成，停止本阶段目标运行，不自动开始下一任务。
