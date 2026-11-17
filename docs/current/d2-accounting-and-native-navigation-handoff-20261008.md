# D2 会计研究消费与 WPS 内部导航交接

本轮为 PROGRESS：实际新增原件核对、研究输入和共享消费产物，修复旧研究文字及原生导航；不是重新描述状态。main HEAD 保持 `5ba570920f588f4660e91439dedb5ab6f32ff1fe`，继承工作区改动不回滚，本轮未提交或推送。D2 与总 Goal 保持 IN_PROGRESS。

## 已实施的变化

1. `600519-profit-adjustment-bridge-20261008.md` 和 `profit-adjustment-bridge-v1.json` 核对官方财报 44 个金额，关闭两期扣非归母桥、上年同期季度独立比较、金融非经常类别二次扣减、信用减值符号及税费二次计税问题。税费打印分项与合计差 0.01 元，保留差额；逐项税后归母调整未知，不写成零。
2. SubAgent 独立交付 `600519-parent-distribution-capital-bridge-20261008.md` 和 JSON，核对现金、权益、派息、回购、股权用途、资金主体与基金承诺。Root 重核两期母公司现金桥、四条权益桥及跨期连续性。年度子公司分配实收与成本法收入总额匹配；H1 使用期初现金承接支出，不由 CFO 减 capex 缺口直接推断不能分红。
3. 新版 `package-v5-accounting-bridges-bound.json` 将上述实际研究接入既有 ResearchCase financial_summary、反证、下一研究步骤及受影响假设依据，再执行原 ResearchApplicationService / Router。`workbench-v7.json` 和 `event-followup-v5.json` 精确绑定实际输入。没有调参数、改审批、另建模型或由当前价格反拟合价值。
4. `decision_surface.py` 原来更新决策字段但保留旧商业说明和反证。现在从重放验证后的同一 Recommendation 更新这些文字、引用及“最强反证”，避免新研究仅成为不可见的 hash。没有修改价格、建议、组合评估或研究批准。
5. 沿用既有产品 CLI，从同一已验证、未投影事件的 base publication v2 重建 read-model / publication v7。不能把已经投影同一七事件的 v6 再重复追加；第一次重复尝试被拒绝，未写产物。新包四公司、186 个传递研究绑定、七事件审计及两条可见风险事件。
6. artifact-tool 导出 donor v9，沿用原保护集成入口。审计 E 列允许精确匹配同一行 evidence_id 所登记 source_url 的 HTTPS HYPERLINK；其他页/列、错来源、任意公式、显示伪装、HTTP 和 URL 凭据均拒绝。没有开放任意外部依赖或更换发布器。
7. WPS 的公式 HYPERLINK 未进入 Hyperlinks 集合，最初 native verifier 拒绝。公开 artifact-tool help 仅给出 HYPERLINK 公式。现有 `replace_sheet` 增加默认关闭的 `native_navigation` 兼容选项：只从已验证内部公式产生原生 location/display，保留公式、拒绝不存在/冲突/重复目标，不新增 worksheet relationships。仅 authored 管理页调用启用。

## 实际验证

| 验证 | 证据与边界 |
| --- | --- |
| 财务独立复核 | SubAgent 对 Root 扣非/税/信用桥无发现，重算 Decimal 与 hash；没有逐项重新辨认全部原件列位，不是投资批准。Root 原件阅读与页码/金额复核另外记录。 |
| 研究消费 | package v5 → workbench v7 → Recommendation 实际含新反证及下一研究步骤；三情景值逐项与 v6 相等；NO_ACTION、买入/减仓区间及仓位 null。 |
| 产品/研究回归 | `.tmp/d2-accounting-projection-final-20261008.xml`：153 passed、0 failures、37 warnings。 |
| 作者页/原生导航回归 | `.tmp/d2-native-navigation-20261008.xml`：96 passed、0 failures、73 warnings。后加冲突/重复保护的窄复验 `.tmp/d2-native-navigation-guards-20261008.xml`：6 passed；测试有重叠，不合计为独立数量。 |
| 原生链接 | 最新 v6 `native-links.json`：16 个内部链接实际 Follow 并核对活动 sheet/行列；17 个 HTTPS 公式显示通过。外部网络点击为 0，不能称外部网址点击已验收。 |
| WPS 只读打开 | 最新 v6 七管理页重开、计算及 PDF 导出 PASS，工作簿 hash 不变；不关闭用户原有文件。 |
| 可读性 | 最新 v6 `readability.json` 七页无裁切行，B4 冻结 PASS。 |
| 来源与保留 | 最新 v6 `delivery-recheck.json`：191 个唯一绑定重验；55 历史/手工页 XML 字节及原 workbook.xml 不变。 |
| 视觉 | 五张 contact sheet 查看全部 35 个 PDF 页面布局；不是逐页放大文字验收。发现公司末页仅一条压力情景，待避免该打印断组；没有生成正式 visual-review PASS。 |

最新候选目录为 `runtime/d2-canonical-integration-20261008-v6`，是工程候选，不是 current pointer 或正式 Excel。候选 SHA-256 `cc4d8ced1dbdcaf65b83fa2d8850166811c050a4fabdccbd21c086a8ffb2b5fe`；源集合 SHA-256 `5fa3a43e23b72527f74d97c3a6fcbe97e8cf48109312c55c32887ff757b81731`。

唯一 C 盘原表没有写入，SHA-256 仍为 `5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`。旧候选和研究输入保留为各自时点证据，不覆盖旧收据以伪装新验证。

## 仍需完成的真实目标

会计桥消除了具体核对问题，但不会验证未来盈利、长期 75% 分配、新增资本回报或优势衰减期限。允许现在论证有界条件假设，不要求把未来变成事实；不要再重复已关闭金额的采集。下一关键工作是经营机制及反证对前瞻情景的约束与独立研究/模型审阅，随后才可用已有报价或明确历史报价进入合法价格评估。当前报价观察不是已准入的 PriceBridge。

同时收尾打印断组、正文可理解性及外部链接实际可用性；全部候选验收完成后再进入单独授权的正式发布。原生产入口、数据库、调度、服务器 PTA 和真实 Shadow 本轮未操作。无真实 IPS/portfolio 时个性化仓位仍为空。

D1/D5 保持既有开源设计/接口边界，不重复五库审查，不先扩展全市场排名或情绪交易。架构差异及许可证记录沿用 `d2-architecture-delta-and-adapter-handoff-20261008.md`、`open-source-adapter-review-20261008.md`；本轮追加的是上述研究文字消费者、证据链接及 OOXML 兼容变化。

```text
CODE_IMPLEMENTED = scoped accounting-consumer and native-navigation changes
AUTOMATED_TEST_PASSED = scoped suites above; not a new full-suite run
REAL_DATA_ADMITTED = false for complete investment/model/price admission
USER_ACCEPTED = false
D2_STATUS = IN_PROGRESS
TOTAL_GOAL_STATUS = IN_PROGRESS
action = no_order
```
