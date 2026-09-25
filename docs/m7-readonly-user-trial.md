# M7 只读用户试用

当前唯一入口由 `config/current-trial-workbook.json` 固定。它是经过 Hash 与 WPS 回执校验的只读候选，不是正式原表，不代表 M6 已运营，也不是个性化投资建议。

```powershell
python scripts/open_current_trial_workbook.py --open
```

首次打开按以下顺序看，约 5-10 分钟：

1. `00_今日总览`：确认 `action=no_order`、当前阶段和待处理事项。
2. `02_候选与重点关注`：看系统发现了什么、进入原因和证据缺口。候选不等于买入。
3. `07_公司研究`：看公司研究结论、反证、模型适用性和仍未知内容。
4. `06_事件与预警`：看新公告、重大变化和仍未完成的复核。600519 当前仍为 `NEED_MORE_EVIDENCE`。
5. `01_全市场与数据健康`：看覆盖日期、数据限制和过期状态。
6. `09_审计与证据`：需要追溯时再看 Hash、manifest 与 M6 预检证据。

当前限制：M4 尚无真实私人 IPS/持仓，因此仓位和股息板卡不会产生个人化结论；M6 仅为 preflight，运营验收 `NOT_STARTED`；M7 最终用户验收和 `INITIAL_ASSISTED_USE` 均未通过。
