# 当前阶段：研究价格桥接完整性修复

更新：2026-09-22。唯一活动工程任务：`C0-PRICE-BRIDGE-INTEGRITY`。
执行入口为 [value-investment-goal-prompt.md](value-investment-goal-prompt.md)；证据基线见 [execution-status.md](execution-status.md)。
本轮文档治理已完成目标定义，下面的代码任务尚未执行。

## 已有成果和冻结边界

Stage A、P0/P0.5 已有验收；三公司统一验收于 2026-09-22 为 PASSED_FOR_FREEZE。
这表示统一工程/研究展示合同可以冻结，不表示三家公司估值或股息研究完成：茅台低置信度条件估值，美的与神华 not_ready，三家价格吸引力均 NOT_ASSESSABLE。
保留现有 ResearchCase、Profile、Router、Assumptions、Materiality 和原 Excel；不重新建设这些模块，不重估茅台参数，不追加美的/神华证据脚本。
本轮发现的合同缺陷作为冻结后的 P0 完整性修复，不抹掉旧验收，也不把旧测试通过当成没有缺陷。

## NEXT TASK

Goal：使研究价格比较只能使用同一证券、同一估值快照、覆盖报价时点的 ModelValidity 和可核验 QuoteSnapshot；同一不变量贯穿正常调用、JSON 恢复和价格吸引力聚合。

### 已复现问题

2026-09-22 在 `052d6ffe4da8efa4b2d4a735e29f57361dbce051` 的内存合成检查中：
`valuation.symbol=600519`、`validity.symbol=000333`、`model_id=unrelated-model`，
报价证据为空，`bridge()` 仍输出 `READY / margin_to_base=0.1`。
不是生产混配事故证明，但证明通用合同存在漏检。
`current_research_status_from_payloads()` 还用估值 symbol 构造桥接对象，可能掩盖输入 JSON 的身份冲突。

### 实施范围

先在现有测试中重现失败，再修复最小合同。复用快照 Hash、引用或最小身份字段绑定估值与有效性记录；研究并确定最小 QuoteSnapshot 输入合同，不提前构建行情服务。
审查并收紧 READY 的构造不变量及反序列化边界；报价身份/证据、估值版本、事件复核时点、边际算式必须一致。
只修改该任务必需的调用处；旧快照以显式版本适配或 fail-closed 处理，保留旧文件和原判断，不能静默用新 symbol 或默认 VALID 洗掉冲突。

Files likely affected：
- `src/value_investment_agent/price_bridge.py`
- `src/value_investment_agent/model_validity.py`
- `src/value_investment_agent/current_research_status.py`
- `src/value_investment_agent/price_attractiveness.py`
- 仅在绑定身份确有必要时调整 `valuation_models/base.py` 或最小 snapshot 合同，以及直接生产/恢复该载荷的 adapter。
- 对应现有 tests / fixtures；新防回归用例加入既有 Core Gate，不新增另一套 CI。

### Acceptance Criteria

1. 跨公司 ModelValidity、不同估值快照/模型版本、过期或错误时点检查，必须拒绝或返回 INVALID/NOT_ASSESSABLE，并能定位原因。
2. 非核验报价、缺证据或快照身份、未知/STALE 模型不能产生 READY；直接构造和 JSON 恢复同样有效。
3. 不同证券/估值版本的 JSON 不能被规范化成同一证券；margin 必须由绑定的估值和报价复算，篡改值被拒绝。
4. 同一合法快照、有效事件扫描下允许模型与报价跨日；真实缺报价为 PENDING_EXTERNAL_DATA，原估值及置信度完整保留。
5. ResearchGate 继续只描述研究；坏桥接永远不输出 RESEARCH_ATTRACTIVE；conditional_research_only 不被升级为正式估值。
6. 当前三家公司冻结快照回归保持既有研究语义；如合同升级使旧快照需重新验证，报告明确兼容状态并保留旧 Hash，不改估值参数、原 Excel 或历史 acceptance。
7. Core Gate 在不依赖联网、未跟踪 runtime、WPS 或生产数据库的 fixture 上通过；本地三公司回归单列。报告测试能证明的边界及尚待生产验证项。
8. diff 只含本任务必要改动，`execution-status.md` 写明实际结果、测试和一个建议后续任务；不以文件/测试数量算完成度。

### Forbidden Changes

不得新增第四家公司、扩全市场、实现新估值/股息引擎、调整估值/价格阈值或仓位、扩展模拟/历史策略、接券商、修改 WPS 原表、迁生产数据库、改计划任务或服务器服务。
不进行通用目录重构，不复制公司流水线，不放宽证据门禁，不为得到 READY 修饰 fixture。

## 停止条件与后续路线

本任务完成并验证后停止目标运行，交付可复现证据和实际 diff；不自动开始下一阶段。
只在当前任务内处理回归及必要兼容问题。外部数据等待不阻塞上述工程工作；真正合同设计问题应先做有界论证，并报告受影响部分，不能无限补证。

候选后续顺序（尚未授权开发）：固定样本准入协议与公共编排审查 -> 20--50 家范围/分批计划 -> 在允许扩样本前补齐通用入口、持久化与最小现金回报研究合同 -> 逐批验证 -> 扩大候选与事件运营。
固定样本准入须分开“流程可复用”和“生产估值可用”；边界案例可保持不可估值，但不能把全部结果为空当成研究产品已可用。至少应有可复核的有界价值判断与现金回报解释，或明确且可执行的模型替代/停止决定。
这些后续任务须在 C0 的节点评估后选定一个更新本文件。旧文档中的 P1/P2/P3、R1/R2、6--10 家或“继续三公司冻结”不自动恢复。

