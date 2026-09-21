# 首例 600519 闭环就绪度评估

评估日期：2026-09-20。范围：按 `value-investment-goal-prompt.md` 和
`value-investment-goal-framework-v2.md` 核对贵州茅台（600519）是否已经完成研究、估值、历史验证、模拟及 Excel 闭环。

## 总结

首例已经完成可追溯的 R0 研究基础和一条限定范围的当前 P1 条件研究模型；尚未完成 R1 历史策略验证，也没有达到 R2 人工实盘辅助准入。当前 Excel 可以用于查看公司研究、事实链、条件和风险，但不可将其解释为可执行买卖建议。

最重要的事实是：项目并不缺少茅台年报原件。真正尚未证明的是历史每个决策日的资本成本可用性，以及“条件研究模型、报价会话、资本事项查询、执行契约”是否在同一个日期截面闭合。此前历史实验没有在验证期或测试期形成可验证交易，因此不能作为策略收益证据。

## 分阶段判定

| 阶段 | 判定 | 已有证据 | 尚缺或失败项 | 对 Excel / 交易的含义 |
| --- | --- | --- | --- | --- |
| R0 公司研究卡 | 有限通过 | 2014-2024 共 11 份年报逐份核验；2025 年报、2025H1、2026H1 已归档；研究卡工作簿验证通过 | 商业与财务判断仍须随新披露重评 | 可展示事实、商业论点、反证和下一事件 |
| P1 当前条件研究 | 有限通过 | `600519-current-valuation-admission-20260920T060750Z` 的五个限定研究门通过；主模型为合并归母权益剩余收益/分红能力路径 | `formal_fair_value=null`；模型只准用于指定范围的同日研究，非正式合理价值 | 可显示条件研究区间及假设，不能显示“建议买入价” |
| P2 当前模拟执行 | 零单范围通过 | 2026-09-16 的模型、论点、P1 准入、双源收盘、停牌、费用、流动性、执行合同和账户已形成同一输入链；合同 `execution_ready=true`，账户落账后现金100万元、0股、0成交 | 尚未在真实触发价格下观察带拟单的下一会话处理；无已批准估值/订单 | 显示 `watch/no_order`，不生成虚假成交 |
| R1 历史策略验证 | 未通过 | 2,674 个会话的离线研究回放、费用/整手/T+1 机械测试已经完成 | 中国历史资本成本的发布时点未证实；验证期和测试期均无可验证成交；不得将研究区间或 PE 试验当策略表现 | 不显示回测收益、胜率或“策略有效” |
| R2 人工实盘辅助 | 未通过 | 备份恢复演练已通过；原件、运行记录和 Excel 发布具备审计基础 | R1 未通过；当前模型未成为正式合理价值；个人账户/风险预算/券商条件未适配 | 不给真实下单数量、买卖指令或实盘准入结论 |

## 已核验的输入范围

`build_moutai_consolidated_equity_inputs.py` 于本次评估前已生成
`runtime/company-research/600519-consolidated-parent-equity-inputs-20260920T140639Z/evidence.json`。它含 12 个年度/当前披露节点；每个年度节点保留巨潮公告 ID、URL、PDF Hash、归母权益、归母利润、期末已发行股数、EPS 与可用日期。当前 2026H1 节点额外绑定 TTM 归母利润、扣非 TTM、权益滚动和股数依据。

该包是事实输入包，**不是 2026-09-20 的估值准入包**：其中后续资本事项检索的完成时点为 2026-09-14。它可以作为后续日期一致模型的输入，不能因为文件在 9 月 20 日重建就被重新标记为 9 月 20 日的已验证资本状态。

## 接下来应按此顺序推进

1. 在下一个实际完成交易会话，先完成公告/资本事项查询并冻结其 `as_of`，再构建同日模型和同日双源收盘价观察；三者不一致即输出 `no_order`，不补填旧日。
2. 已完成日期一致 P2 零单链：模型、报价、执行合同和账户已联通。下一步仅在真实价格条件触发时验证拟单和下一会话处理，不为制造成交调整价格阈值。
3. 历史研究继续寻找带明确发行/可用日期的人民币利率历史资料；在取得前只保留研究敏感性，禁止将 2014 年 ChinaBond 年度 XLSX 用作当时可知输入。
4. 只有上述首例 P1、P2、P3 和预登记历史连续窗口各自具备强证据后，再扩展美的、神华及模拟组合。不得因为数据量大或 Excel 页面已存在而跳过首例验收。

## 引用证据

- `docs/moutai-financial-report-coverage-20260920.md`
- `docs/data-source-and-financial-coverage-matrix.md`
- `runtime/company-research/600519-current-valuation-admission-20260920T060750Z/evidence.json`
- `runtime/company-research/600519-consolidated-parent-equity-inputs-20260920T140639Z/evidence.json`
- `runtime/strategy-validation/moutai-date-consistent-p2-input-20260920T145000Z/input.json`
- `runtime/strategy-validation/moutai-date-consistent-p2-input-20260920T145000Z/paper-account/summary.json`
- `runtime/strategy-validation/moutai-date-consistent-execution-contract-20260920T150000Z/evidence.json`
- `runtime/strategy-validation/moutai-date-consistent-p2-complete-20260920T150000Z/input.json`
- `runtime/strategy-validation/moutai-date-consistent-p2-complete-20260920T150000Z/paper-account/summary.json`
- `runtime/strategy-validation/moutai-historical-conditional-replay-20260920T092837Z/`
- `runtime/strategy-validation/moutai-historical-range-experiment-20260920T115619Z/`
- `docs/execution-status.md`
