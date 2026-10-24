# 项目实际进度复测：2026-10-08

## 结论

当前项目具有可运行的来源保护、公司研究、统一估值及拒绝不合格建议的工程链。尚未证明一只真实公司完成当前有效估值、条件性决策、事件处理和唯一正式 Excel 的完整交付；完整买卖/加减仓建议和个性化仓位尚未集成。D2 与总目标不能标为完成。

本次结论来自读取当前工作树、重新读取 C 盘 Excel 单元格、重新验证来源文件、执行共享研究 CLI、重放结果、实际调用产品 CLI 及针对性测试。Git 提交和文档状态不作为完成证据。未登录服务器，未进行原生 WPS 视觉验收，未修改业务代码、财务参数、正式 Excel 或目标合同。既有独立子代理分别复核建议生成链和研究/历史/运营证据。

## 当前产物与用户能力

| 功能 | 本次检查事实 | 当前判断 |
| --- | --- | --- |
| 全市场候选 | 9/23 实际批次覆盖 5568 证券，quality 通道缺口 4672、通过 0；其他三个通道各通过 50，可能重叠 | 有筛选工程及真实批次；不是当日全市场价值研究或买入推荐 |
| 官方证据与追溯 | 当前 600519 包 17 项原始/派生来源的哈希全部吻合；七公告已有原文解释 | 来源保护存在；原件和哈希不能代替财务口径、商业逻辑及假设论证 |
| 财务与商业研究 | 输入声明仅锚定归母权益、股数，不是完整财务质量；10 项 facts 不等于 10 项独立验证财务指标 | 当前真实研究准入未闭合 |
| 统一估值 | 当前 v5 包经共享 CLI 重新运行、结果再重放成功 | 可计算；现有强衰减压力情景仍非准入的中性主估值 |
| 当前行情 | 留存腾讯/新浪响应及交易所日历，经现有转换器识别为 10/8、1255.79 CNY、verified_close | 本次单票主要障碍不是没有报价，而是研究/模型有效性 |
| 买卖建议 | 当前生成器仅 BUY_CANDIDATE/NO_ACTION；reduce_zone 与 position_guidance 固定为空 | 定义六类建议状态不代表已实现六类决策 |
| 事件到产品 | 当前真实产品 CLI 在 event_followup.py:30 因 EvidenceRecord.location 不存在退出 | 最新事件投影不能宣称已跑通或发布 |
| 正式 Excel | 哈希仍为 5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8；62 页、7 页可见；今日 B4=10/2 01:48；机会页为伊利/美的/神华；事件页无已分类事件 | 后台最新增量未交付唯一正式入口；隐藏历史不是当前建议 |
| 私人组合 | 当前消费者 BLOCKED_PRIVATE_INPUT、position_guidance=null | 未证明真实 IPS/组合已接入；也不能将此作为公共研究整体阻塞 |
| 历史检验 | 实际审计 NOT_PIT_SAFE、NOT_ADMITTED、walk_forward=NOT_RUN | 回放与审计不证明策略有效性、样本外表现或稳定收益 |
| 恢复与运营 | 有数据库组件恢复及匹配表；PG16→18，同主版本/完整系统恢复=false，系统 RTO/RPO=null；所查离线 ledger 不计入真实会话 | 完整恢复、连续真实会话和最终用户验收未获证明；未检查远端，不能断言全环境会话为零 |

## 重新执行的证据

重新运行共享入口：

```powershell
& 'D:/APP/Python313/python.exe' -B scripts/current/build_current_workbench.py `
  --symbol 600519 `
  --package runtime/d2-model-bound-followup-20261008/package-v3-model-bound-verified.json `
  --schedule-request runtime/d2-source-bound-current-20261008/schedule-request.json `
  --output runtime/objective-recheck-20261008/fresh-workbench.json `
  --report runtime/objective-recheck-20261008/fresh-company-card.md
```

输出再次通过 verify_current_decision_workbench：NO_ACTION；ModelValidity=UNKNOWN；PriceBridge=INVALID；entry_zone/reduce_zone/position_guidance 均 null。Bear/Base/Bull 约 404.82/479.88/572.74，仅是低置信度强衰减压力情景，不能作正常公平价值或买卖价。

真实产品 CLI 使用现有受哈希保护的 base-publication-input、workbench-v5 及 event-followup-v2，read-model-only/historical-preview 模式失败，未生成产品输出，更未写 canonical。错误为 presentation/read_models/event_followup.py:30 使用 record.location；EvidenceRecord 实际字段为 path。

六个针对性测试文件实际结果：193 passed、5 failed，12.21 秒。范围：test_decision_recommendation、test_product_cli_entrypoints、test_source_bound_research_inputs、test_d2_source_bound_package_contract、test_d2_conditional_shared_service、test_model_bound_event_followup。未运行当前全套。

失败需区分：事件成功链/CLI 被上述字段错误阻断；一个测试夹具本身也误用 location；未被模型消费的参数未拒绝，构成独立校验缺口。隐藏事件审计测试当前先被字段错误阻断，其后续断言本轮未执行到，不冒称已验证。

旧审查记录中的 162 passed 是其当时子集，不能覆盖当前新增代码或将最新工作树称为全绿。目标文件仍写 D2 READY_TO_START，也不能反向覆盖本次已经运行的部分工程事实。

独立建议链复核补充：现有 exit_conditions 是撤销研究适用性或重新研究的触发提示，不能当作已经实现的卖出规则。合成 BUY_CANDIDATE 测试只证明候选状态和回放工程，不证明真实买入价、加减仓数量或个人资金安排。

## 剩余开发的最短顺序

1. 修复事件消费者和参数消费绑定校验，完成当前真实产品 JSON 到正式 Excel 的保护发布及原生验证。
2. 用正常化盈利、竞争优势持续期、前瞻资本回报、资本分配及七公告影响完成单票有效研究；输出可复核的估值依据及具体条件，允许结论仍是不买。
3. 把原始持仓论点、持有/加仓/减仓/退出规则接入共享建议链；仓位另接真实 IPS、持仓、现金和风险约束。
4. 验证其他经济结构公司的复用，并完成适用规则的真实历史、PIT、样本外与交易成本检验。
5. 完成授权运行、至少 20 连续真实交易会话、真实事件、完整恢复和用户验收。情绪卫星仓为额外策略研究，不能当作已有价值投资链附送完成。

规划区间未经实测吞吐量标定，不是承诺：最新研究/缺项交付 Excel 约 1-3 个集中工程日；单票有效研究及条件决策约 3-7 个集中工程日，取决于证据是否足以界定假设；完整买卖/加减仓、多票及策略验证其后约 10-20 个集中工程日。达到有限辅助使用的完整验收约 6-10 周规划窗口，20 会话只能从合格真实观察启动后计，不能从今日编码计。完整含情绪卫星仓的目标暂无可靠固定完成日期。

不报告缺乏统一验收分母的完成百分比。首要差距是研究与决策闭环、产品交付和验证，不是继续增加框架或文档。action=no_order；最终投资决定由用户作出，工程和回测均不保证收益。
