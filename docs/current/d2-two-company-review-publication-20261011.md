# D2 两家公司待审研究与 Excel 发布审核入口

本材料用于审核实际研究候选及新的 Excel 显示版本，不授予投资、生产运行或最终用户验收批准。`action=no_order`，`position_guidance=null`。

## 实际研究结果

| 公司 | 实际候选生成日 / 财务基期 | 低 / 中 / 高条件值（元/股） | 当前用途 |
| --- | --- | ---: | --- |
| 600519 贵州茅台 | 2026-10-11 / 2026-06-30 | 437.66 / 587.88 / 812.27 | B：十年盈利持续条件及五年全资本衰减，待审，非买点 |
| 600887 伊利股份 | 2026-10-11 / 2026-06-30 | 9.80 / 10.08 / 10.30 | 一年盈利条件及三年全资本衰减，待审，非买点 |

两份实际 package、workbench 和 consumed-review 已由现有共享模型生成并核验。正式注册研究日期及决策没有被候选覆盖。10/9 双源历史收盘仅独立展示，不计算当前正式安全边际。

最小经济审核包：

- 茅台：`runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/pending-candidate/candidate-review.md`，五组盈利、持续期、资本分配、成本终端及版本准入问题。
- 伊利：`runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/candidate-review.md`，四组盈利、现金分配、成本期限及事件准入问题。

每组可接受具体用途、拒绝或判定证据不足；接受条件研究不等于批准公允价值。未获精确模型批准时维持待审，不能通过发布工作簿推定投资批准。

## 唯一待发布显示候选

文件：`runtime/daily-trade-assistant/20261011-d2-two-company-review-v2/canonical-integration-historical-preview.xlsx`

SHA-256：`6c90ae7a24d07f5dc3cf3e05a997db1984c85fd87820248c80528979d7166900`

保留原工作簿 55 张其他表；更新既有七个产品页面，没有新增 Tab。公司页明确分开原估值日期和 10/11 待审候选，21 个条件数值与实际来源一致。两处日期标题行高已修正。

验证证据全部位于该候选目录：

- `engineering-source-acceptance.json`：284 项来源绑定、21 个条件数值核验。
- `canonical-preservation.json`：其他 55 张表保留，正式文件未写入。
- `native-review/receipt.json`：WPS 只读打开七个页面并导出实际 PDF。
- `native-links.json`：17 个内部导航链接通过，无外网点击。
- `readability.json`：七页均无检测到的截断行，公司页实际打印 11 页。
- `visual-review.json`：实际查看四张 WPS 页面联系图；无观察到的标题截断或重叠。公司长报告打印跨页，审计页仍密集，不能视为最终用户体验验收。

当前 C 盘正式文件仍为 `879e9c44a5d7c429ca9fd4702f084972af9a3d4ec91b0d59ac6756df04fd922b`。仅在用户批准上述新候选精确字节后，使用已有保护发布器备份并替换；发布不修改经济审批、行情准入或组合状态。

## 阶段边界

已完成共享模型实际消费候选、完整已结束公告查询窗口、分组审核材料和显示验证。7/1–10/10 茅台 7 条、伊利 33 条公告已绑定原件；完整查询不等于材料性批准，亦不证明 10/11 全天覆盖。

经济判断/G3、公告材料性与模型有效性、当前价格准入仍未通过。生产授权、实际数据库隔离恢复、20 个连续真实交易会话及用户实际使用验收亦未通过；69 文件加密恢复仅证明研究证据组件可恢复。

新增伊利完整窗口影响矩阵见 `docs/current/600887-full-window-event-impact-20261011.md`。澳优渠道调整、募投效益不足、半年不分配、回购获批但未实施等事实已形成有页码的复核问题。`runtime/d2-event-candidate-review-binding-20261011-v1/review-input.json` 精确绑定实际候选包、workbench、政策、扫描与矩阵，SHA-256 为 `6c1d3e7386af22e23357b0290ca3ab0fadff7501f050b657c4157e1d927ad5cf`；状态仅为 PREPARED_NOT_CONSUMED，没有代替材料性审核或回写候选参数。

`D2=IN_PROGRESS`；`TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`；`INITIAL_ASSISTED_USE=NOT_REACHED`。不将工作包工程完成表述为总目标完成。
