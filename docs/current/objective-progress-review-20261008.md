# 项目进度直接复核：2026-10-08

## 结论和范围

当前是有来源约束、可重放的研究与条件估值原型，尚不是完成验收的买卖及仓位辅助系统。D2 工程已有实质进展；一只真实公司的完整当前研究准入和正式用户交付仍未闭合。不能将文档中的 READY_TO_START 当作当前实际进度，也不能把工程链可运行当作 D2 或总 Goal 完成。

本次直接读取 D 盘工作树、C 盘正式 Excel、模型输入及运行 JSON；重新计算源文件哈希、执行共享研究入口、重放决策和运行针对性测试。两名已有子代理分别独立核验研究/消费者以及运营/PIT/恢复边界。没有依据 GitHub 提交注释判断完成度。未登录服务器，未重新做真实恢复或原生 WPS 验收，未修改正式 Excel、目标合同、财务假设、服务器或数据库，未提交/推送。

当前目标为 [advisory-sentiment-satellite-goal-v1.md](advisory-sentiment-satellite-goal-v1.md)，包含 D0-D6，继承 M2-M7 资产；不能将价值投资最小闭环的工期当作包括情绪卫星仓在内的完整 Goal 工期。

## 实际完成与差距

| 用户需求 | 实际检查的证据 | 判断及剩余差距 |
| --- | --- | --- |
| 全市场发现候选 | `runtime/m2-live-20260923-v3/receipt.json`：5568 个证券身份，quality 的 data_gap_count=4672、pass_count=0；value/dividend/cyclical 各 pass_count=50 | 有筛选工程和真实批次；该批次是 9/23，既不是当日更新，也不是对 5568 家完成价值研究。各通道候选可能重叠，不相加称为独立推荐数量。 |
| 原始财报和公告 | 600519 当前包的16项源文件及派生输入哈希匹配；七公告原文已逐项研究 | 有一手原件及来源保护；不是16份财报，也不能以哈希正确证明财务口径与前瞻假设正确。 |
| 完整公司质量判断 | 当前 source_contract 明示 `source_anchored_parent_equity_and_share_count_not_full_financial_quality` | 当前模型起点的归母权益、普通股已锚定；完整财务质量、商业论点及资本分配尚未获当前准入。 |
| 统一估值与决策链 | 重新运行共享 `build_current_workbench.py`，再次回放；三情景 Decimal 与既有 v3 完全一致 | 工程链确实可运行；600519 仍为低置信度压力研究，不是已批准的中性主估值。 |
| 有效行情 | 再次用共享 converter 验证报价 bundle：2026-10-08、1255.79 CNY、verified_close | 该单票有有效行情观察；当前价格桥 INVALID 的主要缺项是模型与研究有效性，不能笼统归因于取不到行情。 |
| 买卖点 | 共享建议生成器只产生 BUY_CANDIDATE / NO_ACTION；实际600519=NO_ACTION、entry_zone=null、reduce_zone=null | 有买入候选工程合同与拒绝链；完整加仓/持有/减仓/卖出尚未集成。没有当前真实买入价/卖出价。 |
| 仓位管理 | 当前建议明确 BLOCKED_PRIVATE_INPUT、position_guidance=null；本次未打开私人文件 | 真实 IPS/持仓及原始 Entry Thesis 仍需确认；私人输入只阻断个人组合结论，不应阻断公共研究。 |
| 跟踪和事件提醒 | 公告扫描及研究文档存在；正式 `05_事件!A4` 仍为“当前没有已分类的用户事件。” | 来源到事件处置、模型失效/重算和正式提醒尚未完整贯通。 |
| Excel 交付 | 原表62页、7页可见；`01_今日!B4`=2026-10-02 01:48；机会页只含伊利/美的/神华 | 唯一正式入口可定位，当前后台增量尚未同步到原表。不是所有旧工作丢失，部分在隐藏页/审计区，但不能把它们当作当前可交易建议。 |
| 当前产品消费者 | 新版 handoff 验证168项来源绑定，包含原三公司与600519，Today有研究变化及行情项 | 后台集成已推进至产品 JSON；publication_approved=false，未证明正式 Excel 当前发布成功。 |
| 历史验证 | `historical-validation-receipt-audit-latest.json`：NOT_PIT_SAFE、NOT_ADMITTED、walk_forward=NOT_RUN；600519真实输入回放亦不允许业绩结论 | 有回放与成交必要条件验证；没有经准入的策略有效性证据。模拟通过、哈希匹配或 AUDIT_OK 不能替代同期 PIT、样本外及成本检验。 |
| 运营与恢复 | 本机观察 ledger 无可计入真实会话的证据；数据库组件恢复回执有匹配表，但完整系统恢复=false、同主版本=false、系统RTO/RPO=null | 有实际恢复组件资产；不能称真实运营20会话、完整恢复或最终用户验收已通过。本次未检查远端，不能断言所有远端会话均为零。 |
| 情绪卫星仓 | 合同和隔离边界存在，真实策略仍受value/PIT/OOS/成本/Shadow门禁 | 不是已完成的波段策略，完整新 Goal 还有独立实质工作。 |

## 单票直接复验

输入：`runtime/d2-source-bound-current-20261008/package-v2-current-model.json`。
重新运行的输出：`runtime/objective-audit-20261008/fresh-workbench.json` 和 `fresh-company-card.md`。

实际结果：

```text
research_status = COMPLETED_WITH_BLOCKERS
valuation.status = conditional_research_only
confidence = 低
model_validity = UNKNOWN
price_bridge = INVALID
recommendation_type = NO_ACTION
entry_zone = null
reduce_zone = null
position_guidance = null
action = no_order
```

Bear/Base/Bull约404.82/479.88/572.74元，只属于现有强衰减压力假设，不能当作中性公平价值、买入区间或减仓价格。当前行情1255.79元也不能使未准入模型自动变成合法价格判断。

事实与假设处置还需闭合：7/18限定产品/渠道提价如何影响盈利路径；财务公司资金敞口如何影响盈利质量及分配能力；前瞻回报、优势持续期与衰减假设的依据。半年报摘要与全文不是两家独立来源。七公告独立研究文档可以支撑下一步处置，但尚未形成与准确模型/扫描版本绑定的正式审阅结果。

源文档：[600519-full-window-materiality-review-20261008.md](600519-full-window-materiality-review-20261008.md)。

## 本轮验证范围

- 正式原表 SHA-256 再核对：`5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`，与声明入口一致，本轮未改写。
- 最新 workbench-v3 重放通过；16项源文件哈希匹配；新版 handoff 的168项来源绑定由实际 loader 复验通过。
- 从真实现有输入重跑共享入口，三个 Decimal 情景与 v3 完全一致；新输出再次通过决策重放。
- 本轮针对性测试：162 passed in 3.51s，覆盖建议、产品CLI消费者、源合同、公司注册及本地来源声明保护。未重新运行全套；此数不与此前测试相加，也不证明金融有效性或收益。
- Excel 结论来自实际 OOXML 单元格读取。托管工具尝试导入原表未在审查窗口内完成，已停止仅本次审查导入进程；未获得本轮新视觉/WPS验收，因此不冒称完成视觉检查。

可复现研究命令：

```powershell
& 'D:/APP/Python313/python.exe' -B scripts/current/build_current_workbench.py `
  --symbol 600519 `
  --package runtime/d2-source-bound-current-20261008/package-v2-current-model.json `
  --schedule-request runtime/d2-source-bound-current-20261008/schedule-request.json `
  --output runtime/objective-audit-20261008/fresh-workbench.json `
  --report runtime/objective-audit-20261008/fresh-company-card.md
```

输出路径要求不存在；再次运行时指定新的审查目录，不能覆盖已有证据。

## 下一步及工期判断

当前最重要的单个工作包：在既有共享链中，将已取得的600519官方事实、逐项重大事件处置和前瞻假设绑定成可研究复核的当前模型，形成有效/无效理由，再投影并保护发布到唯一正式表。不新增专属估值体系，不为了产生买入候选调整参数。

完成的验收不是必须出现 BUY，而是能够说明：研究通过后价格是否值得复核；或具体哪项研究依据仍不足。随后集成原始持仓论点与加/持/减/退出规则、真实输入回测和其他公司复用。不要把缺私人持仓、下一交易日或自然观察期作为公共研究工程的整体阻塞。

以下是按剩余工作包做的规划区间，未用实测开发吞吐量标定，不是交付承诺：

| 层次 | 规划区间 | 前提和不包含的内容 |
| --- | --- | --- |
| 最新研究/行情/缺项清楚同步到正式Excel | 1-3个集中工程日 | 当前handoff可用，完成导出问题、保留页保护、正式发布和原生视觉核验；不代表交易逻辑通过。 |
| 单票有效研究和条件性决策工作台 | 3-7个集中工程日 | 公开证据足以界定必要假设/事件影响，既有复核合同可完成；不保证该票获正向推荐。 |
| 完整买卖/加减仓、多票复用、真实历史和样本外检验 | 其后约10-20个集中工程日 | 仓位需真实私人输入；回测可能发现策略或规则需要修改。 |
| 核心有限辅助使用的运行验收 | 约6-10周规划窗口 | 实际合格Shadow启动后至少20连续真实交易会话，约4-5个自然周；须另完成真实事件、完整恢复和用户验收。不能从今日编码直接计时。 |

完整当前 Goal 还含独立情绪卫星仓，尚无充分依据给固定完成日期。工程完成不保证稳定收益，也不保证某只股票出现买点。

不提供未经统一验收分母验证的“完成百分比”。长期 Goal 和 D2 尚不能标为 COMPLETE。永久 action=no_order，最终投资决定由用户完成。
