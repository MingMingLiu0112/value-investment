# 系统审查与目标收敛报告

日期：2026-09-22。仓库：MingMingLiu0112/value-investment。
本轮范围为 PROJECT GOAL CONSOLIDATION：审查真实现状，更新目标、方法、架构和文档入口；不开发业务。
用户附件要求中的长期资本增值与可持续现金分红双目标已纳入三份长期权威文件。

## A. 结论与基线

方向仍以 Research / Valuation / Evidence 为核心，具备三类经济画像与模型路由基础。工程已经较昨日进步，但“工程能正确拒绝不合格输入”尚不能满足用户持续研究价值和股息机会的完整需求。
本次支持冻结既有三公司工程成果；不把美的/神华没有数值当作失败事故，也不把全是 fail-closed 的边界验收解释为三公司估值可用。

- HEAD：`052d6ffe4da8efa4b2d4a735e29f57361dbce051`，2026-09-22 14:02:08 +08:00，`Freeze unified three-company Excel MVP`。
- 审查开始工作树干净；新文档修改是本轮未提交状态，未自动 commit/push。
- 枚举 137 份既有 docs Markdown、94 个 src 文件、489 个 scripts 文件、332 个 tests 目录文件、1 个 CI 工作流。文件数不等于功能或测试数。
- 阅读优先目标、架构/方法/政策、最新验收、关键领域/编排/展示与测试，并核对 runtime 指针；没有逐行审计所有旧脚本、重新核对所有原始财报或连接服务器。
- 本轮重跑核心 CI 清单加三公司冻结验收：93 passed in 0.79s。没有重跑全量测试。
- 原 Excel Hash 为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`，与冻结记录一致；未重新打开渲染或发布原表。

昨日审查中“工作树未提交”“CI 未跟踪”“没有 Router”“有效性无日期复核”“G2 不查 next_events”的状态已被新基线纠正，不应继承为当前事实。
当前 CI 已在 HEAD，配置 push main / PR 运行 Core Gate；历史状态记载远程 run 35688371033 成功，本轮只核对配置和本地运行，未重新检查远程最新执行结果。

## B. 目标与文档冲突

旧启动文档同时写着“统一验收已完成，进入固定样本”“下一步是统一验收”和“当前三公司研究级估值主线”；旧 Excel 目标字段清单仍包含 current_price/margin，而同段正文又禁止这些字段进入 ValuationResult。
旧框架同时保留 6--10 家、20--50 家及茅台模拟扩展等旧顺序；旧 execution-status 达 324,386 字符，把历史“下一步”留在当前状态入口。这些冲突会反复重开已关闭分支。

已将产品目标、架构、方法、当前任务、政策、运行事实各归一个负责人文件；旧目标原文先归档并核对 Hash，再用原位补丁替换为导航。历史 acceptance、hash、decision 未改写。
本次没有删除任何历史材料；归档 AGENTS 原文命名为 AGENTS.before-consolidation.md，避免旧执行规则作用于归档目录。

## C. 新权威体系

| 入口 / 文件 | 唯一职责 |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | 权威、执行纪律与永久边界 |
| [north-star.md](north-star.md) | 长期资本增值 + 可持续股息现金流；漏斗与用户工作方式 |
| [architecture.md](architecture.md) | Domain / Application / Data / Presentation，身份、事件与股息层级 |
| [research-methodology.md](research-methodology.md) | 基本面、资本配置、股息能力、估值、反证和停止规则 |
| [current-stage-goal.md](current-stage-goal.md) | 唯一 NEXT TASK、边界、验收和停止条件 |
| [data-and-evidence-policy.md](data-and-evidence-policy.md) | 来源/时点/快照/发布/备份/生产保护底线 |
| [execution-status.md](execution-status.md) | 当前基线、独立状态与证据；不分配新的任务 |
| [value-investment-goal-prompt.md](value-investment-goal-prompt.md) | 用户可直接放入目标模式的启动文本；不重复路线图 |

权威是按职责划分；低层阶段目标不能弱化证据与架构底线。版本号、更新时间或历史验收中的命令不能恢复旧优先级。
数据覆盖矩阵、存储协议和外部等待政策保留为专项细则。此前完整运行日志和所有被替换的目标均保存于 [归档说明与指纹](archive/goal-consolidation-20260922/README.md)。

## D. 代码一致性审查

| 层 | 实际代码/证据 | 判断 |
| --- | --- | --- |
| ResearchCase / Gate | research_case.py；research_gate.py 的 G0-G3、next_events 和只研究结论 | 已有共同合同；状态字符串和证据内容质量仍需独立核验 |
| Profile / Router | research_profile.py；valuation_router.py 注册三模型、匹配 facts_contract | READY 的基础注册/拒绝路径；不是完整多行业覆盖 |
| Facts / Assumptions | FCFF、QualityCompounder、Cyclical 各自 Facts；valuation_assumptions.py | 可扩展；FinancialFacts 内 WACC、正常化预测类字段仍有事实/假设命名混合债 |
| Materiality | materiality.py；美的 LOW / MODEL_AS_RANGE 产物 | 可复用，未自动解除模型适用性限制 |
| Valuation | valuation_models/base.py 只含价值；三种算术实现 | 与价格分离；模型类与算术存在不证明公司生产估值完成 |
| ModelValidity | evaluate_model_validity 已可将重大事件判 STALE，日期窗口检查存在 | 比昨日完善；桥接仍未校验有效性记录与估值的身份 |
| PriceBridge | price_bridge.py:47；合成复现见下一节 | P0 漏检，可返回错误 READY |
| PriceAttractiveness | price_attractiveness.py:146；独立消费 gate + bridge | 方向正确；依赖桥接合同真实性，不应只信 READY 字符串 |
| JSON / 状态 | current_research_status.py:391、412 | 恢复时以估值 symbol 构造 gate/bridge，存在隐藏原始身份冲突风险 |
| Excel | workbook_simple_overview.py 读取 runtime，保留三公司 publisher adapter | 新核心不依赖 Excel 求估值；替换前端可行，发布编排尚有特化 |
| DB / runtime | db.py:483 与 sql/001_init.sql:151 为旧估值表；新产物主要 JSON | MVP 技术债，不能说新合同已落库；先稳定合同再迁移 |
| Distribution | 有分红公告/历史事件、分配交叉检查；无独立 DistributionCapacity/DividendSustainability/DividendYieldSnapshot | 股息研究 PARTIAL，领域引擎 NOT_STARTED |
| Event / Funnel | 有 MaterialEvent、旧市场候选/跟踪；无完整新版多通道状态机 | 长期设计，不是当前错误 |

## E. 当前最重要的具体缺陷

[price_bridge.py:47](../src/value_investment_agent/price_bridge.py#L47) 不比较 valuation.symbol 与 validity.symbol，也不验证 model_id 对应估值快照；READY 分支可接受空报价证据。
[current_research_status.py](../src/value_investment_agent/current_research_status.py) 恢复 JSON 时用 valuation 的 symbol 代替 bridge 的原始 symbol；应校验冲突而非规范化掉冲突。

本轮无文件写入的合成复现：

```python
from datetime import date
from decimal import Decimal
from value_investment_agent.valuation_models.base import ValuationResult
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_bridge import bridge

value = ValuationResult(
    "600519", "fixture", date(2026, 9, 16),
    Decimal("400"), Decimal("500"), Decimal("600"), "中",
    {}, [], [{"id": "model-a"}], [], "ready", "fixture-v1",
)
other = ModelValidity(
    "unrelated-model", "000333", date(2026, 9, 16), date(2026, 9, 16),
    date(2026, 9, 18), False, False, False, "VALID", [],
    [{"id": "other-company-scan"}],
)
result = bridge(
    value, other, quote_date=date(2026, 9, 18),
    current_price=Decimal("450"), quote_status="verified_close",
    evidence_refs=[],
)
# 本轮实际输出：bridge_status='READY', margin_to_base=Decimal('0.1')
```

这证明公共合同没有防住错误混配，不代表当前冻结的生产证据已混配或造成交易。修复只涉及研究边界，当前没有自动交易接线。

## F. 三公司与股息研究

| 维度 | 茅台 600519 | 美的 000333 | 神华 601088 |
| --- | --- | --- | --- |
| Engineering Complete | 冻结路径 READY，共同合同仍有 P0 | FCFF 正常/拒绝分支 READY | 周期正常/拒绝分支 READY |
| Research Complete | PARTIAL，G3 未过 | PARTIAL，财务范围未过 | PARTIAL，正常化研究未过 |
| Valuation Complete | PARTIAL，低置信度条件结果 | NOT_READY，无情景值 | NOT_READY，无情景值 |
| Dividend Research Complete | PARTIAL，分配与历史材料 | PARTIAL，历史分红与财务材料 | PARTIAL，历史分红与周期材料 |
| Production Data Ready | 09-21 快照 READY；09-22 未重新验证 | PENDING_EXTERNAL_DATA + 模型适用性问题 | PENDING_EXTERNAL_DATA + 假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE | NOT_ASSESSABLE | NOT_ASSESSABLE |

公司-specific scripts：moutai 195、midea 26、shenhua 23，共 244；源模块未发现同名公司前缀模块。数字含历史实验，不等于 244 个运行中任务。
只读发现 4 个 Windows 任务，涉及日更及茅台收盘前/后、Excel 发布；未改动任务。服务器任务本轮未现场核对。

合理 adapter 是特定财报结构、股本/法律披露、一次性迁移；重复架构是每家公司复制研究包组装、证据引用/Hash、日期桥接、状态聚合与发布编排。
现有 Router 可以按经济 Profile 路由，但名为 build_company_valuation_result 的入口仍只接受 FCFF、Profile 可选，未形成真正多模型通用运行器。扩样本前需收敛，不在本轮顺手重构。

股息正式进入 North Star、Research Methodology 的 Capital Allocation，以及独立 Distribution Domain；Dividend Yield 仍属于 Market 层。
当前没有自动给三家公司股息可持续性打分。金融子公司范围、母公司现金、资本开支、周期正常化和派息假设保持未知或待审查，不因新增目标而生成数值。

## G. 架构债分级与三个核心风险

| 级别 | 工作/风险 | 当前处理 |
| --- | --- | --- |
| P0 | 桥接证券/模型身份、空证据与序列化边界漏检 | 唯一下一工程任务 C0 |
| P0（文档治理） | 多目标并行指挥、旧指令复活、工程冻结混称估值完成 | 本轮已修正文档，不修改历史验收 |
| P1（三公司研究级完成前） | 事实/假设实际接线、模型适用性、可解释价值区间、基本资本配置/分配研究 | 保留未完成；按重大性及 stop rule 重开，不无限补证 |
| P2（20--50 家前） | 通用运行入口、模型专用 Facts 合同、最小分配/股息研究合同、持久化版本责任、样本与数据预算 | 完成 C0 后单独选择一项，不同时开工 |
| P3（全市场前） | 多通道漏斗、事件依赖失效、批处理失败隔离、权限/覆盖/资源与运营监测 | 设计保留 |
| Later | Web / API 产品化、完整股息引擎、Portfolio/Execution | 不在当前范围 |

三个核心风险：
1. **错误 READY**：公共价格桥接能组合不相属的证据，扩样本后风险增加；先补共同合同。
2. **能力与进度混淆**：三公司冻结确实完成，但只有一个条件估值，两家无情景，完整股息研究均未完成；不能以更多测试/文档或等待外部数据替代这一事实。
3. **扩展成本过高**：公司专用编排、通用入口只支持 FCFF、runtime 与旧 DB 双路径，使扩样本容易复制流程；先按真实重复收敛，不全面重构或先建新服务。

数据库旧表的命名/字段问题仍需治理，但没有证据证明它是当前新 B1 结果的权威写入路径。因此修订昨日“立即 PostgreSQL 迁移”的优先级，将迁移放在合同稳定后的扩样本门槛，不把技术债都升级为 P0。

## H. 唯一 NEXT TASK 与阶段结束

**C0-PRICE-BRIDGE-INTEGRITY**：修复共同研究价格桥接的证券、估值快照、模型有效性、报价证据及时点的一致性，覆盖正常调用、JSON 恢复和下游价格判断。
完整 Goal、Files likely affected、Forbidden changes、Acceptance criteria 和停止条件只有一份：[current-stage-goal.md](current-stage-goal.md)。

任务不依赖收盘、未来报告或付费数据；先复现本报告反例，再使用现有快照/fixture 验证。
本轮只修改文档，缺陷仍然存在。下一目标完成 C0 后必须停止并客观评估，再选一个后续任务。
明确暂不做：第四家公司、20--50 家批量研究、全市场、Web、银行/保险/NAV、复杂 Dividend Engine、模拟/执行扩展、数据库部署、计划任务调整和真实交易。

## I. 逐文件治理清单

以下涵盖合并前全部 137 份 docs Markdown。处置统计：KEEP 125；UPDATE 5；MERGE 5；ARCHIVE 2。
KEEP 代表原位保留，Historical/Archive 类不再是指令源；不是逐篇重新认证其全部技术或金融结论。
MERGE/ARCHIVE 文件的原内容保存在版本化归档，原路径变为跳转页。没有永久删除文件。

| 原文件 | 类别 | 动作 | 落地方式 |
| --- | --- | --- | --- |
| [AGENTS.md](../AGENTS.md) | Authority / Policy | UPDATE | 原位重写权威、当前任务与长期边界，原文归档 |
| [README.md](../README.md) | North Star / Navigation | UPDATE | 更新定位与文档导航，保留运维说明 |
| [000411-financing-debt-scope.md](archive/legacy-financing-debt-20260926/000411-financing-debt-scope.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [000429-financing-scope-review.md](archive/legacy-financing-debt-20260926/000429-financing-scope-review.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [000683-debt-scope-audit.md](archive/legacy-financing-debt-20260926/000683-debt-scope-audit.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [001233-debt-scope-20260909.md](archive/legacy-financing-debt-20260926/001233-debt-scope-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [001872-financing-scope-20260909.md](archive/legacy-financing-debt-20260926/001872-financing-scope-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600012-financing-scope-20260909.md](archive/legacy-financing-debt-20260926/600012-financing-scope-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600060-debt-scope-20260909.md](archive/legacy-financing-debt-20260926/600060-debt-scope-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600267-debt-scope-20260909.md](archive/legacy-financing-debt-20260926/600267-debt-scope-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600496-cross-page-verified-20260909.md](archive/legacy-financing-debt-20260926/600496-cross-page-verified-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600519-readiness-assessment-20260913.md](600519-readiness-assessment-20260913.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [600900-filing-retry-20260908.md](archive/legacy-financing-debt-20260926/600900-filing-retry-20260908.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [601800-verified-refresh-20260909.md](archive/legacy-financing-debt-20260926/601800-verified-refresh-20260909.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [920174-annual-diagnosis.md](archive/legacy-financing-debt-20260926/920174-annual-diagnosis.md) | Execution Status / Archive | ARCHIVE | 只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [财报候选复核操作.md](财报候选复核操作.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [财报候选自动验证说明.md](财报候选自动验证说明.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [官方证据清单说明.md](官方证据清单说明.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [交易所覆盖核查_20260907.md](交易所覆盖核查_20260907.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [金融机构规则设计.md](金融机构规则设计.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [新版表格使用说明.md](新版表格使用说明.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [annual-backfill-status.md](annual-backfill-status.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [annual-debt-gap-triage-20260909.md](annual-debt-gap-triage-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [archive/value-investment-goal-framework-v2-before-20260912-review.md](archive/value-investment-goal-framework-v2-before-20260912-review.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archive/value-investment-goal-framework-v2-before-20260914-review.md](archive/value-investment-goal-framework-v2-before-20260914-review.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archive/value-investment-goal-framework-v2-before-20260915-methodology.md](archive/value-investment-goal-framework-v2-before-20260915-methodology.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archive/value-investment-goal-prompt-before-20260912-review.md](archive/value-investment-goal-prompt-before-20260912-review.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archive/value-investment-goal-prompt-before-20260914-review.md](archive/value-investment-goal-prompt-before-20260914-review.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archive/value-investment-goal-prompt-before-20260915-methodology.md](archive/value-investment-goal-prompt-before-20260915-methodology.md) | Archive | KEEP | 已有历史快照；只读，不执行其中指令 |
| [archived-maturity-46-20260909.md](archived-maturity-46-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [bank-parser-v9-validation.md](bank-parser-v9-validation.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [benchmark-source-review.md](benchmark-source-review.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [broker-cash-conflicts-20260909.md](broker-cash-conflicts-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [broker-regulatory-reference-20260908.md](broker-regulatory-reference-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [broker-v13-live-evidence-20260908.md](broker-v13-live-evidence-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [candidate-retirement-applied-20260909.md](candidate-retirement-applied-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cash-collection-single-observation-20260909.md](cash-collection-single-observation-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cash-repair-export-20260909.md](cash-repair-export-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cash-shadowing-diagnosis-20260909.md](cash-shadowing-diagnosis-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cash-unit-reverification-applied-20260909.md](cash-unit-reverification-applied-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cebbank-metric-gap-evidence-20260908.md](cebbank-metric-gap-evidence-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [cross-page-debt-label-v33-20260909.md](cross-page-debt-label-v33-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [current-maturity-bridge-20260909.md](current-maturity-bridge-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [daily-backup-control-flow-20260909.md](daily-backup-control-flow-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [daily-tracking-disk-incident-20260908.md](daily-tracking-disk-incident-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [data-source-and-financial-coverage-matrix.md](data-source-and-financial-coverage-matrix.md) | Policy | UPDATE | 更新为单一职责；合并前原文已校验归档 |
| [database-schema.md](database-schema.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [debt-research-workbook-published-20260909.md](debt-research-workbook-published-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [debt-scope-gate-installed-20260909.md](debt-scope-gate-installed-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [debt-scope-production-sync-20260908.md](debt-scope-production-sync-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [derivation-tied-input-investigation-20260909.md](derivation-tied-input-investigation-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [derived-refresh-20260908-2216.md](derived-refresh-20260908-2216.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [distribution-coverage-research.md](distribution-coverage-research.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [dividend-tax-counterevidence-20260909.md](dividend-tax-counterevidence-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [evidence-storage-tiering.md](evidence-storage-tiering.md) | Policy | UPDATE | 更新为单一职责；合并前原文已校验归档 |
| [excel-mvp-baseline-20260921.md](excel-mvp-baseline-20260921.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [excel-mvp-stage-a-acceptance-20260921.md](excel-mvp-stage-a-acceptance-20260921.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [Excel前端设计评估.md](Excel前端设计评估.md) | Policy | KEEP | 操作/结构参考；不作为阶段完成或实时部署证明 |
| [execution-status.md](execution-status.md) | Execution Status | UPDATE | 更新为单一职责；合并前原文已校验归档 |
| [export-after-600496-20260909.md](export-after-600496-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [external-data-blocking-policy.md](external-data-blocking-policy.md) | Policy | UPDATE | 更新为单一职责；合并前原文已校验归档 |
| [filing-refresh-queue-verification-20260908.md](filing-refresh-queue-verification-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-balance-bridge-20260909.md](financing-balance-bridge-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-batch-20260908.md](financing-batch-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-batch-20260909-03.md](financing-batch-20260909-03.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-batch-20260909.md](financing-batch-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-classification-research-20260909.md](financing-classification-research-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [financing-continuation-replay-20260909.md](financing-continuation-replay-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [first-case-readiness-assessment-20260920.md](first-case-readiness-assessment-20260920.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [first-company-milestone-assessment-20260920.md](first-company-milestone-assessment-20260920.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [historical-backtest-admission-20260918.md](historical-backtest-admission-20260918.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [historical-corporate-actions.md](historical-corporate-actions.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [historical-dividend-tax.md](historical-dividend-tax.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [historical-financial-readiness.md](historical-financial-readiness.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [historical-price-crosscheck.md](historical-price-crosscheck.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [historical-publication-bounds.md](historical-publication-bounds.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [historical-trading-fees.md](historical-trading-fees.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [historical-trading-gaps.md](historical-trading-gaps.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [huaan-broker-gap-evidence-20260908.md](huaan-broker-gap-evidence-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [income-parser-v29-validation-20260909.md](income-parser-v29-validation-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [legacy-shanghai-fee-experiment.md](legacy-shanghai-fee-experiment.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [long-term-payables-source-scope.md](long-term-payables-source-scope.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [maturity-continuation-v2-20260909.md](maturity-continuation-v2-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [maturity-geometry-v3-20260909.md](maturity-geometry-v3-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [maturity-source-migration-20260909.md](maturity-source-migration-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [midea-2025-financing-scope.md](midea-2025-financing-scope.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [midea-historical-suspension-evidence-20260909.md](midea-historical-suspension-evidence-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [midea-q3-point-in-time-evidence-20260908.md](midea-q3-point-in-time-evidence-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [midea-stage-b2-convergence-assessment-20260922.md](midea-stage-b2-convergence-assessment-20260922.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [midea-stage-b2-engineering-acceptance-20260921.md](midea-stage-b2-engineering-acceptance-20260921.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [midea-stage-b2-progress-20260921.md](midea-stage-b2-progress-20260921.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-beta-peer-review-20260909.md](moutai-beta-peer-review-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-business-research-20260909.md](moutai-business-research-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-capital-cost-evidence.md](moutai-capital-cost-evidence.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-financial-report-coverage-20260920.md](moutai-financial-report-coverage-20260920.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-latest-report-review-20260909.md](moutai-latest-report-review-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-model-input-status-20260909.md](moutai-model-input-status-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-model-scope-decision-20260909.md](moutai-model-scope-decision-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-operating-forecast-review-20260909.md](moutai-operating-forecast-review-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [moutai-stage-b1-acceptance-20260922.md](moutai-stage-b1-acceptance-20260922.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [moutai-stage-b1-engineering-acceptance-20260921.md](moutai-stage-b1-engineering-acceptance-20260921.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [moutai-stage-b1-progress-20260921.md](moutai-stage-b1-progress-20260921.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [nearcomplete-financing-batch-20260909.md](nearcomplete-financing-batch-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [parser-v32-candidates-inserted-20260909.md](parser-v32-candidates-inserted-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [parser-v32-installed-20260909.md](parser-v32-installed-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [parser-v32-server-replay-20260909.md](parser-v32-server-replay-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [parser-v32-verification-20260909.md](parser-v32-verification-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [parser-v33-installed-20260909.md](parser-v33-installed-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [retained-note-scope-review-20260909.md](retained-note-scope-review-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [scheduled-workflow-audit-20260909.md](scheduled-workflow-audit-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [server-source-provenance.md](server-source-provenance.md) | Policy | KEEP | 专项/版本化协议；不能授权当前阶段之外的工作 |
| [shenhua-bvps-scope-review.md](shenhua-bvps-scope-review.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [shenhua-stage-b3-convergence-assessment-20260922.md](shenhua-stage-b3-convergence-assessment-20260922.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [shenhua-stage-b3-engineering-acceptance-20260921.md](shenhua-stage-b3-engineering-acceptance-20260921.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [shenhua-stage-b3-progress-20260921.md](shenhua-stage-b3-progress-20260921.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [storage-expansion-preflight-20260909.md](storage-expansion-preflight-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [storage-reserve-incident-20260909.md](storage-reserve-incident-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [strategy-logic-review-20260909.md](strategy-logic-review-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [strategy-validation-progress-20260908.md](strategy-validation-progress-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [strategy-validation-protocol.md](strategy-validation-protocol.md) | Policy | KEEP | 专项/版本化协议；不能授权当前阶段之外的工作 |
| [strict-verification-deployment-20260908.md](strict-verification-deployment-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [task-clock-verification-20260908.md](task-clock-verification-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [thesis-risk-fix-20260912.md](thesis-risk-fix-20260912.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [third-quarter-category-verification-20260908.md](third-quarter-category-verification-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [three-company-unified-acceptance-20260922.md](three-company-unified-acceptance-20260922.md) | Historical Acceptance | KEEP | 验收与 Hash 原样保留；只证明指定日期和范围 |
| [tracking-lock-status-20260909.md](tracking-lock-status-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [tracking-service-audit-20260908.md](tracking-service-audit-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [tracking-service-verification-20260908.md](tracking-service-verification-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [validation-checkpoint-20260909.md](validation-checkpoint-20260909.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |
| [valuation-model-research.md](valuation-model-research.md) | Research Methodology | KEEP | 方法或范围参考；保留来源日期和原版本，不制定顺序 |
| [value-investment-architecture-correction-20260921.md](value-investment-architecture-correction-20260921.md) | Architecture Contract | MERGE | 内容进入新权威文件；原路径保留跳转，原字节归档 |
| [value-investment-architecture-correction-p05-20260922.md](value-investment-architecture-correction-p05-20260922.md) | Architecture Contract | MERGE | 内容进入新权威文件；原路径保留跳转，原字节归档 |
| [value-investment-excel-mvp-goal.md](value-investment-excel-mvp-goal.md) | Current Stage Goal | MERGE | 内容进入新权威文件；原路径保留跳转，原字节归档 |
| [value-investment-full-market-funnel-goal.md](value-investment-full-market-funnel-goal.md) | North Star | MERGE | 内容进入新权威文件；原路径保留跳转，原字节归档 |
| [value-investment-goal-framework-v2.md](value-investment-goal-framework-v2.md) | Research Methodology | MERGE | 内容进入新权威文件；原路径保留跳转，原字节归档 |
| [value-investment-goal-framework-v3.md](value-investment-goal-framework-v3.md) | Archive | ARCHIVE | 旧 v3 方案退出权威链；保留跳转与原字节 |
| [value-investment-goal-prompt-v3.md](value-investment-goal-prompt-v3.md) | Archive | ARCHIVE | 旧 v3 方案退出权威链；保留跳转与原字节 |
| [value-investment-goal-prompt.md](value-investment-goal-prompt.md) | Current Stage Goal | UPDATE | 更新为单一职责；合并前原文已校验归档 |
| [zhangjiagang-bank-gap-evidence-20260908.md](zhangjiagang-bank-gap-evidence-20260908.md) | Execution Status / Archive | KEEP | 原位只读保留证据/研究/历史进度；不执行其中旧下一步 |

## J. 新增文件与可复核性

新增六份权威文件中的 north-star、architecture、research-methodology、current-stage-goal、data-and-evidence-policy；execution-status 复用现有路径。
新增本报告作为一次性审查证据，以及归档 README / manifest.json / 换行保护 .gitattributes。后续直接更新六份权威文档，禁止再通过增加目标版本文件改变执行顺序。
所有原始快照的 source_path、archive_path、SHA-256 见归档 manifest；历史原文内相对链接按原位置及基线提交解释，不为修复归档链接修改原字节。
本轮业务代码、测试代码、SQL、runtime 证据、原 Excel 和调度/服务器配置均未修改。

最终验证：14 份归档原文 SHA-256 全部匹配，20 份活动 Markdown 的本地链接检查为 0 断链，git diff --check 通过。src/scripts/tests/sql/deploy/.github 无差异，原 Excel Hash 与冻结基线一致。
