# M7 只读用户试用

当前唯一试用入口是 `WORKBOOK_PATH` 指向的 canonical workbook。runtime v3 的 WPS、布局与视觉审核作为历史预览证据保留，不是当前用户入口，不代表已发布到原表或投资准入。以下候选布局及打开记录均为历史说明；显式预览须使用 `--historical-preview runtime/<file>.xlsx --preview-sha256 <SHA256>`，默认命令仅解析原表。

```powershell
python scripts/open_current_trial_workbook.py --open
```

首次打开是五页产品工作台，按以下顺序看，约 5-10 分钟：

1. `01_今日`：先看今天真正需要处理的少量事项，以及个人组合是否已接入。
2. `02_机会`：看系统进入了哪些关注范围、为什么进入、还缺什么证据。候选不等于买入。
3. `03_公司`：看单家公司已封存的研究、估值、安全边际与股息状态，以及悲观/基准/乐观情景。
4. `04_我的组合`：看真实组合是否接入；未接入时只显示接入状态，不显示任何模拟资产数字。
5. `05_事件`：看已分类的重大、逻辑风险、股息、组合风险与系统数据风险。

`决策过程` 是附加的用户解释页；`06_系统与审计` 是次级页面，阶段码、证据路径和 SHA-256 只保留在那里。正常阅读主产品时不需要打开审计页。

主产品页面只显示中文用户语言；估值不可用时显示「暂不可评估」并附原因与所需证据，不显示空数字占位或内部工程状态码。

当前候选：

- workbook: `runtime/m7-product-ux-candidate-v3-20261001.xlsx`
- workbook SHA-256: `7437a155c41d73882d9b5a1c751f690c9d9bd62e6ef484188d04a711793ca769`
- WPS receipt: `runtime/m7-product-ux-candidate-v3-20261001-delivery-wps.json`
- visual review: `runtime/m7-product-ux-candidate-v3-20261001-delivery-visual.json`
- readability: `runtime/m7-product-ux-candidate-v3-20261001-readability.json`

交付复验（2026-10-01）：WPS 重新只读打开并逐页导出全部七页，逐格比对确认 274 个字符串单元格在原生 PDF 导出中完整出现、无截断；`python scripts/open_current_trial_workbook.py --open` 实际打开的是 v3 五页产品工作台，不是 legacy v16，也不是 canonical workbook。62-sheet Canonical 集成预览只保留为历史审计产物。

当前限制：M4 尚无真实私人 IPS/持仓，因此仓位和股息板卡不会产生个人化结论；M6 运营状态为 `NOT_STARTED`；M7 最终用户验收和 `INITIAL_ASSISTED_USE` 均未通过。

```text
M7_PRODUCT_UX = USER_VISIBLE_TRIAL_READY
CURRENT_TRIAL_POINTER = PRODUCT_UX
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```
