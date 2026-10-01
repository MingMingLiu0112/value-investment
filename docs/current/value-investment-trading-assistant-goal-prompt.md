# VALUE-INVESTMENT-TRADING-ASSISTANT-V1

## 2026-10-01 Execution Correction: Product Progress Before Status Churn

This addendum governs execution order, not investment approval. Preserve the full objective and all final acceptance requirements below.

1. Separate `ENGINEERING_DELIVERY`, `CURRENT_RESEARCH_ADMISSION`, and `FINAL_OPERATIONAL_ACCEPTANCE`. Missing official evidence blocks only the affected conclusion. A pending quote, private input, human acceptance or twenty-session window does not by itself block independent engineering.
2. Begin by inspecting the actual shared research runner, decision/execution replay, product packet and canonical publisher. Produce a bounded dependency map: requirement, existing implementation, actual missing input/code, next independently executable task and acceptance evidence. Do not merely copy status documents. Choose a substantive product work package, not another audit-only or status-only loop.
3. Prioritize the shared single-stock research-to-presentation path, then historical execution replay, then three-company reuse. Complete every safe runnable part of the chosen work package before stopping. Existing evidence-stopped cases remain stopped until their concrete reopen trigger is met; do not repeatedly search identical sources or invent values. Assess whether another already-authorized case or an explicitly dated historical interval can exercise the same path without that event dependency.
4. Historical reconstructed PIT means only contemporaneously available facts, an explicit decision cutoff, version-frozen rules for the replay, separate assumption timestamps, and no future leakage. It does not prove the rule was operated or preregistered on that historical date. Contemporaneous/preregistered validation remains a separate stricter claim. Do not backdate rules or weaken existing verifiers: first document which claim each contract supports; use an explicitly separate versioned research-only admission if the contracts require it. Historical reconstruction never replaces the final strict PIT gate or twenty real sessions.
5. Missing real inputs may be represented by explicit NOT_READY results; synthetic fixtures can validate transitions and execution constraints but cannot satisfy real-company, real-data or investment-effectiveness acceptance. No manufactured BUY/ADD/REDUCE/EXIT and no threshold optimization for historical returns.
6. Complete a milestone's engineering delivery with code, cross-module tests, a reproducible command and human-readable output. A dataclass, green CI, repeated test run, commit/push or status-document correction alone is not substantive product delivery. Do not claim total completion from milestone delivery.
7. Keep natural-time and external gates in the remaining-gates document with exact input and reopen conditions. Before reporting an impasse, inspect all independent tasks in the dependency map, including historical reconstruction and shared integration. Do not demand user-supplied public filings before exhausting bounded official-source acquisition. Never repeatedly ask for already received workbook-reading, key-custody or remote-visibility confirmations.
8. Preserve the sole WORKBOOK_PATH workbook, protected sheets, source-hash guard and publication verification. No new user workbook, new companies outside the three authorized cases, new valuation model families, broker execution or unrelated security/backup expansion. Protect PTA and memory limits.
9. The next execution must first identify and implement the largest currently runnable missing part of the shared single-stock closure or real-input historical replay. If inspection proves neither has runnable work, give the exact source/input gap and inspected alternatives; do not substitute another status-only work package. Full investment readiness remains NOT_REACHED until every original final gate is actually verified.

将当前 A 股价值投资项目收敛为一个基于公开证据、可追溯估值和风险门禁的本地辅助交易系统。

最终用途：用户打开 C 盘 WPS 云盘中的唯一正式 Excel，即可快速看到：

1. 哪些股票已经完成研究；
2. 哪些股票仍缺少关键证据；
3. 当前价格与 Bear/Base/Bull 估值的关系；
4. 当前是否适合观察、条件性买入、加仓、持有、减仓或退出；
5. 建议仓位和调整原因；
6. 建议所依据的财报、公告、行情和计算过程；
7. 哪些风险会使建议失效。

系统只提供辅助交易建议，最终投资决定由用户完成。永久禁止自动下单，永久保留：

```text
action = no_order
```

不得承诺稳定收益、正收益或避免亏损。

## 一、工作范围

项目代码目录：`D:\GPTProject\value-investment`

唯一正式 Excel：`C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx`

当前优先级：

1. 先把 Excel 前端整理成普通人可以理解的交易决策工作台；
2. 先让一只股票跑通完整流程；
3. 再让其他股票复用同一套通用流程；
4. 最后进行历史回测、影子运行和真实交易日观察；
5. 不继续扩展无关模块，不继续无限增加候选股票或研究材料。

必须保持以下边界：

- 不接券商下单接口；
- 不自动交易；
- 不把研究状态直接当成买入信号；
- 不使用固定 PE 或单一安全边际作为主估值模型；
- 不为某家公司复制一套专属估值框架；
- 不将 Excel 作为数据库；
- 不把 PostgreSQL 数据库文件放入 WPS 云盘；
- 不把人工持仓和私人账户信息写入 GitHub；
- 不降低严格 PIT、证据完整性、价格桥接和风险门禁要求；
- 不新增 M8；
- 不把工程完成表述为总目标完成。

## 二、核心产品定义

所有股票必须使用统一的 `ResearchCase`、`ValuationModel` 和 `ValuationResult`。

输入：

- 已验证的 `FinancialFacts`；
- 公司身份和证券身份；
- `ResearchCase`；
- 适用的 `ValuationModel`；
- 当前已验证行情；
- 事件和公告状态；
- 用户投资政策和账户约束。未提供私人信息时，必须标记为待输入。

输出至少必须符合以下结构：

```json
{
  "symbol": "000333",
  "as_of": "YYYY-MM-DD",
  "bear": null,
  "base": null,
  "bull": null,
  "confidence": "LOW|MEDIUM|HIGH",
  "model": "model_name",
  "model_validity": "VALID|CONDITIONAL|NOT_ESTABLISHED",
  "price_bridge": {
    "current_price": null,
    "price_as_of": null,
    "valuation_date": null,
    "basis_consistent": false
  },
  "research_gate": "PASS|CONDITIONAL|BLOCKED",
  "decision_gate": "PASS|CONDITIONAL|BLOCKED",
  "portfolio_gate": "PASS|CONDITIONAL|BLOCKED",
  "suggested_state": "NOT_READY|WATCH|CONDITIONAL_BUY|ADD|HOLD|REDUCE|EXIT",
  "position_guidance": null,
  "blockers": [],
  "evidence_refs": [],
  "action": "no_order"
}
```

任何关键输入缺失、时间点不一致、证据冲突、模型不适用或价格桥接未建立时：

- `bear/base/bull` 可以为 `null`；
- `suggested_state` 必须为 `NOT_READY` 或 `WATCH`；
- 不得输出 `BUY`、`ADD`、`REDUCE`、`EXIT`；
- 必须显示具体 `blockers`；
- 必须列出重新开放条件。

## 三、统一决策流程

所有股票都必须复用：

```text
Universe
  -> ResearchCase
  -> Issuer Identity Gate
  -> FinancialFacts Gate
  -> Evidence and PIT Gate
  -> Business Quality Review
  -> ValuationModel Router
  -> ValuationResult
  -> Current Price Bridge
  -> Research Gate
  -> Decision Gate
  -> Portfolio Risk Gate
  -> Execution Guidance
  -> Paper Order
```

每个财务事实必须记录：

- `symbol`、`fact_name`、`value`、`unit`、`period`；
- `available_at`、`source_id`、`source_url`、`publication_time`；
- `source_file_hash`、`parser_version`、`verification_status`；
- `evidence_excerpt`。

商业质量审查至少包括：收入和利润稳定性、经营现金流、ROIC/ROE、竞争优势、行业周期、客户与供应商集中度、资本开支、资本配置、负债和流动性、分红可持续性、治理风险及重大事件影响。

模型按经济结构路由：

- 成熟制造业：Residual Income、FCFF 或适用的盈利正常化模型；
- 周期行业：Cyclical Normalized Valuation；
- 高分红稳定公司：股息或现金流模型；
- 金融机构：专门的银行/保险模型；
- 资产型公司：NAV 或资产重估模型；
- 模型不适用：返回 `NOT_ESTABLISHED`。

PE/PB 只能作为交叉检查或市场线索，不能作为主估值模型。

## 四、交易辅助状态

系统只输出条件性辅助建议，不执行交易。

- `NOT_READY`：关键证据、估值输入、PIT 或价格桥接缺失；
- `WATCH`：公司和估值具备研究价值，但尚未满足进入条件；
- `CONDITIONAL_BUY`：研究、估值、价格桥接、重大事件和组合风险门均通过，等待用户确认；
- `ADD`：原有研究仍有效，价格进入加仓区间，组合仓位未超限；
- `HOLD`：研究仍有效，未达到加仓或减仓阈值；
- `REDUCE`：估值过高、业务恶化、组合集中度超限或核心假设被破坏；
- `EXIT`：投资逻辑被证伪、模型失效或重大风险达到退出标准。

不得仅依据股价上涨或下跌触发买卖。

没有有效 `PriceBridge`、没有当前口径一致的估值或没有通过风险门禁时，禁止产生正式买卖建议。

## 五、Excel 产品要求

Excel 首页必须按用户决策顺序组织，只保留以下入口：

1. 今日总览；
2. 重点观察；
3. 决策过程；
4. 公司卡片；
5. 我的组合；
6. 事件风险；
7. 系统与审计。

首页必须显示：数据截止日期、研究对象数量、已完成研究数量、估值可用数量、重点观察股票、条件性建议数量、阻塞事项数量、系统状态以及永久 `action=no_order`。

“重点观察”每行只显示：代码、名称、当前价格、价格日期、Bear/Base/Bull、置信度、研究状态、估值状态、价格桥接状态、当前建议、建议原因、风险提醒和证据入口。

“决策过程”必须逐项显示：

```text
事实是否齐全
  -> 商业质量是否合格
  -> 估值模型是否适用
  -> Bear/Base/Bull 是否生成
  -> 当前价格是否有效桥接
  -> 研究门是否通过
  -> 组合风险是否通过
  -> 最终建议状态
```

每一步显示 `PASS`、`CONDITIONAL` 或 `BLOCKED`，并显示具体原因、证据来源和下一步动作。

内部阶段码、哈希、解析器版本、运行收据和测试信息统一放在“系统与审计”页。

## 六、数据来源和阻塞处理

关键事实优先使用：上海证券交易所、深圳证券交易所、巨潮资讯网、香港交易所、公司官网投资者关系页面、年报、半年报、季报、审计报告和公告原件。

AkShare、同花顺、东方财富、新浪、腾讯等结构化接口用于补充和交叉验证。关键财务事实和重大事件应尽量绑定到第一手原始文件。

必须区分：

1. 工程是否可以继续；
2. 当前投资结论是否可以更新。

外部接口失败时：

- 可以继续开发 Excel、模型接口、测试、回测和审计；
- 可以使用最近一次已验证历史数据进行开发回放；
- 必须显示行情截止日期；
- 不得把历史结果伪装成当前建议；
- 不得修改研究状态来掩盖数据缺失；
- 只阻塞受影响的研究结论。

## 七、开发阶段和验收

### 阶段 1：Excel 产品收敛

先整理 C 盘唯一正式 Excel：统一首页、隐藏内部页、减少重复字段、统一状态颜色和日期格式，建立“决策过程”页。

验收：普通用户在 3 分钟内能够理解某只股票目前是 `NOT_READY`、`WATCH` 还是条件性建议；缺数据时能看到具体原因；没有重复入口和互相矛盾的状态。

### 阶段 2：单票完整闭环

优先选择 `000333` 或 `600887`：完成官方财报事实、统一 `ResearchCase`、适用估值模型、`ValuationResult`、当前 `PriceBridge`、Excel 同步和回放测试。

验收：`research 000333` 或 `research 600887` 能生成合法 JSON，能追溯到官方财报和公告；Excel 能展示 Bear/Base/Bull、置信度、门禁和 blockers；不足时明确显示 `NOT_READY`。

### 阶段 3：决策规则和回测

使用历史已公开数据重放买入、加仓、持有、减仓和退出逻辑，检查未来数据泄露，并记录手续费、滑点、停牌、涨跌停和分红。

验收：至少一个股票完成完整历史回放；每个状态可解释；输入、输出和证据可复现；未通过回测的规则不得进入实时建议。

### 阶段 4：多票复用

让 `000333`、`600887`、`601088` 使用同一接口，只通过模型路由适配经济结构。禁止复制公司专属交易流程。

### 阶段 5：影子运行

每个交易日生成一次只读建议，保存输入、输出、证据和状态，完成至少 20 个连续真实交易日观察，并统计误报、漏报、回撤和状态变化。

### 阶段 6：用户验收

用户实际阅读首页、查看一家公司决策过程、追溯一条财务事实、检查一次风险阻塞和一次状态变化，并确认建议可理解、最终决定仍由用户完成。

阶段 6 通过前，不得宣称达到初步实盘辅助使用。

## 八、SubAgent 协作

SubAgent 可以独立负责数据源调研、模型审查、Excel 布局审查、回测方法审查、独立测试和反例审查。

SubAgent 不得修改共享正式 Excel、交易模块、目标文档或其他 Agent 的结果，不得生成订单，不得宣称总目标完成。

Root Agent 负责共享文件修改、结果合并、Excel 发布、最终测试和唯一状态维护。

每个 SubAgent 输出必须包含：工作范围、输入及哈希、修改文件、测试结果、未解决问题、对研究结论的影响和对交易状态的影响。

## 九、当前执行顺序

严格按以下顺序执行：

1. 整理 C 盘正式 Excel；
2. 建立“今日总览”和“决策过程”两个清晰入口；
3. 选择一只股票完成完整 `ResearchCase`；
4. 生成统一 `ValuationResult`；
5. 将 JSON 和证据链同步到 Excel；
6. 完成单票历史回放；
7. 通过单票验收后再扩展其他股票；
8. 完成多票复用；
9. 完成 20 个真实交易日影子运行；
10. 完成用户验收。

如果存在无法由工程解决的外部门禁，生成 `REMAINING-GATES-TO-INITIAL-ASSISTED-USE`，每项写明：

- `DAG_NODE`；
- `CURRENT_STATUS`；
- `WHY_REQUIRED`；
- `WHAT_IS_ALREADY_DONE`；
- `EXACT_EXTERNAL_INPUT`；
- `REOPEN_CONDITION`；
- `WHAT_CAN_CONTINUE_IN_PARALLEL`。

不要新增阶段，不要为了保持 Goal Mode 活跃而增加无价值代码。

## 十、当前默认状态

```text
TOTAL_GOAL_STATUS = IN_PROGRESS
M2 = DONE
M3 = PARTIAL
M4 = NONPERSONALIZED_ENGINEERING_COMPLETE
M5 = OFFLINE_CHAIN_VALIDATED_BUT_NOT_OPERATIONAL
M6 = NOT_STARTED
M7 = DISPLAY_ENGINEERING_AVAILABLE_BUT_USER_ACCEPTANCE_PENDING
VALUATION_READY = 0/3
STRICT_PIT = NOT_PROVEN
INITIAL_ASSISTED_USE = NOT_REACHED
ACTION = NO_ORDER
```

只有在以下条件全部满足时，才可将总目标标记为完成：

- 至少一只股票完成可追溯估值和价格桥接；
- 至少一只股票完成历史回放；
- 至少三家公司复用统一流程；
- 买入、加仓、持有、减仓、退出均有规则和测试；
- 严格 PIT 通过；
- 完成 20 个连续真实交易日影子运行；
- 真实备份恢复验收通过；
- Excel 完成用户验收；
- 用户确认系统能够理解并辅助交易决策；
- 永久保留 `action=no_order`；
- 没有把辅助建议表述成收益保证。
