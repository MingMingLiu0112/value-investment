# M7 只读用户试用

当前唯一试用入口是 `.env` 的 `WORKBOOK_PATH` 指向的 canonical workbook。M7 Product UX 已原位集成在同一份 Excel；`config/current-trial-workbook.json` 只保存逻辑来源 `WORKBOOK_PATH`，不保存 runtime workbook 路径。`runtime` candidate 仅为历史或临时预览，不是用户入口，不代表 M6 已运营，也不是个性化投资建议。

```powershell
python scripts/open_current_trial_workbook.py --open
```

首次打开是五页产品工作台，按以下顺序看，约 5-10 分钟：

1. `01_今日`：先看今天真正需要处理的少量事项，以及个人组合是否已接入。
2. `02_机会`：看系统进入了哪些关注范围、为什么进入、还缺什么证据。候选不等于买入。
3. `03_公司`：看单家公司已封存的研究、估值、安全边际与股息状态，以及 Bear/Base/Bull 情景。
4. `04_我的组合`：看真实组合是否接入；未接入时只显示接入状态，不显示任何模拟资产数字。
5. `05_事件`：看已分类的重大、逻辑风险、股息、组合风险与系统数据风险。

第 6 页 `06_系统与审计` 是次级页面：阶段码、证据路径和 SHA-256 都保留在那里，
正常阅读主产品时不需要打开。

主产品页面只显示中文用户语言；估值不可用时显示「暂不可评估」并附原因与所需证据，
不显示空数字占位。

当前限制：M4 尚无真实私人 IPS/持仓，因此仓位和股息板卡不会产生个人化结论；M6 仅为 preflight，运营验收 `NOT_STARTED`；M7 最终用户验收和 `INITIAL_ASSISTED_USE` 均未通过。
