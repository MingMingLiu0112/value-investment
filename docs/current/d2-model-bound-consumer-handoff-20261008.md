# D2 官方证据、参数与产品消费者交接

日期：2026-10-08。当前 main HEAD 为 `5ba570920f588f4660e91439dedb5ab6f32ff1fe`，继承已有未提交工作树。上一轮进度复测属于 PROGRESS：真实失败改变了本轮修复路径。本轮没有提交/推送、生产变更或正式工作簿发布。

## 实际完成

1. `application/product/event_followup.py` 绑定独立报告、实际模型输入包、执行 receipt 的 valuation_package hash、descriptor hash 和回放后的 Facts/Assumptions。事件提到的参数必须在三个情景中确实消费；参数值与原件漂移拒绝。复用既有 descriptor、binding validator 和 artifact replay，不另建估值或审批系统。
2. `presentation/read_models/event_followup.py` 使用 EvidenceRecord.path，模型引用须属于当前估值步骤；卡片中仅保留旧模型引用不够。全部七公告留审计，五项只在审计显示，两项形成 EVIDENCE_GAP 研究提醒。保持决策、估值、报价与个人组合原状态。
3. `application/product/research_publication_input.py` 正确解析旧包 supersedes 的相邻文件名，继续验证哈希。普通财报证据路径仍按项目根解析；缺失/漂移拒绝，不用同名文件替换或跳过历史链。
4. 新独立研究已由官方物理页核对并用 Decimal 对平 FY2025 + H1 2026 - H1 2025：报告归母 TTM 81,433,985,225.44 CNY、扣非归母 TTM 81,367,067,677.44 CNY，差 66,917,548.00 CNY。生成 historical-profit-reconciliation-v1.json 并绑定新包的 ResearchCase financial_summary、假设依据和实际模型输入；未改变任何情景参数。

## 最新真实链

目录：`runtime/d2-model-bound-followup-20261008/`。

```text
官方 FY2025/H1 原件、七公告
  -> 独立盈利质量与事件研究
  -> historical-profit-reconciliation-v1.json
  -> package-v4-financial-evidence-bound.json
  -> 共享 ResearchApplicationService / Router
  -> workbench-v6.json（完整制品重放）
  -> event-followup-v4.json（精确模型、输入及来源绑定）
  -> 现有产品 CLI
  -> product-read-model-v5.json
  -> product-publication-input-v5.json
```

真实产品 CLI exit=0；四家公司保留，七项模型影响解释、两项可见研究风险事件、七项事件审计。最新 handoff 包含 181 个传递来源绑定，重新加载仍需实际验证各来源。没有把七条解释当作材料性或模型批准。

茅台保持 NO_ACTION、ModelValidity UNKNOWN、PriceBridge INVALID；买入/减仓区间与仓位均为空。Bear/Base/Bull 数值与前版完全相等，仍是低置信度强衰减压力情景。历史扣非 TTM 算术正确不等于跨周期正常化盈利、未来 ROE 下限或有效中性估值。完整财务与商业研究、提价量价利润桥、留存资本回报、优势持续期、分配能力仍须审阅。

## 验证与状态

本轮 coupled：235 passed，17.65 秒。全量：4018 passed、41 skipped、56 warnings，529.14 秒。跳过项未转为通过。独立 subagent 的 36 个合成对抗用例覆盖七公告、错模型、未消费参数、输入/报告/来源漂移、隐藏审计、真实公共工程入口及状态保留；合成测试与真实研究产物分别记录。

机器收据：`runtime/d2-model-bound-followup-20261008/explanatory-consumer-receipt-v1.json`，绑定本轮代码、测试 XML 和最新运行产物。前轮 193 passed/5 failed 仍是当时事实，不覆盖或改写旧审查报告。

| 状态 | 范围内判断 |
| --- | --- |
| CODE_IMPLEMENTED | 事件解释、消费绑定、版本链及产品数据包修复已实现 |
| AUTOMATED_TEST_PASSED | 上述 coupled 与当前全量回归通过；不证明策略金融有效性 |
| REAL_DATA_ADMITTED | 官方历史盈利勾稽有具体验证；当前完整研究/模型/投资准入尚未通过 |
| USER_ACCEPTED | 未通过；本轮没有正式发布或最终用户验收 |

D 盘七页工程预览由托管 artifact-tool 生成并有导出/hash记录；七页顶部范围及事件页已查看。authoring 进程在文件和 receipt 写出后返回 exit=1，尚未诊断，也未做原生 WPS 验收或完整长页视觉审查；该预览不能作为正式发布候选的验收证明。Canonical 保持原 SHA-256 `5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`。

## 后续最短顺序

1. 继续同一模型的正常化盈利、资本留存回报与优势持续期研究，把历史质量反证和未量化事件转成可复核的经济假设边界；不由当前股价反拟合参数，不人为制造 BUY。
2. 将具体事实、假设、重大性和模型审阅按既有精确版本合同闭合；先形成完整非个性化决策，再处理 D3 的持仓/组合。未知只约束相应结论，不能阻断其他工程。
3. 同一产品消费者形成保持手工/历史55页的正式候选，完成发布前验证；当前范围仍不授权正式发布。
4. D1/D5 保持接口设计范围，沿用 open-source-adapter-review-20261008.md 及 d2-architecture-delta-and-adapter-handoff-20261008.md。五库源码、许可证和数据限制已有有界审查；两库许可 UNKNOWN 不复制代码，其他算法也不继承为准入策略。不得先扩大全市场排名或情绪信号。

D2_STATUS=IN_PROGRESS；总 Goal 继续 ACTIVE。永久 action=no_order。完成上述工程包不等于 D2 产品完成、真实策略通过或用户已可实盘使用。
