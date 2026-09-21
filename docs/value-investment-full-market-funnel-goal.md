# 全市场研究漏斗最终目标

版本：v1.0，日期：2026-09-21。定位：最终产品 North Star；不替代当前
三家公司 Excel MVP 的短期顺序。

## 用户交互范式

系统要将全 A 股逐层压缩为少量值得人工判断的公司，而不是生成一个“买入排行榜”。
最终用户每天在 Excel 首页应依次看到：市场覆盖概览、今日变化、3--10 家高关注公司和
研究队列；只在需要时打开具体 `ResearchCase`。高关注池可以为零，不能为了凑数强制排名。

首页最终回答：覆盖了多少公司、多少通过基础筛选、哪些公司今天状态发生变化、哪些公司
最值得继续研究、进入/退出的理由、最大风险和下一事件。高关注池是 Priority Research
List，不是 Buy List，不产生真实订单、仓位或强制买入价。

## 五层状态机

| 层级 | 名称 | 职责 | 目标规模 |
| --- | --- | --- | --- |
| L0 | Universe | 身份、上市状态、行业、基础行情/财务覆盖及来源健康；不生成投资结论 | 全市场 |
| L1 | 基础筛选池 | 排除数据不完整、严重交易/披露异常、当前不支持路径等明显不适合研究的公司 | 约300--500 |
| L2 | 研究候选池 | 路径、回报来源、初步商业/财务、错价假说、风险与研究缺口 | 约50--100 |
| L3 | 深度研究池 | 完整 ResearchCase、财务五维、资本配置、正反论点、估值与 blockers | 约10--30 |
| L4 | 高关注池 | 数据可靠、模型/价格桥接有效、置信度非低、Thesis 未受重大破坏的优先人工研究对象 | 约3--10 |

每家公司保存 `universe_status`、`screening_status`、`candidate_status`、
`deep_research_status`、`high_attention_status`、原因、变更时间、变更执行者和
`evidence_refs`。允许升级和降级，但每次迁移必须保存理由与证据。

L0--L1 由 Python 和数据规则完成；L1--L2 可以使用 LLM 辅助商业摘要但不能由 LLM
单独升级；L2--L3 执行深度研究；L3--L4 同时要求商业质量、估值、价格桥接、置信度和
反证状态，不以单一总分或“好公司”替代。

## 数据与自动化边界

数据流为 `Raw Evidence -> Validation -> FinancialFacts -> ScreeningResult ->
ResearchCase -> ValuationResult -> PriceBridge -> Funnel State -> Excel -> Human Decision`。
Python 负责采集、校验、指标、筛选、估值、状态机和数值；LLM 只辅助叙事研究、反证、
事件摘要和缺口管理。数据库是事实底座，Excel 是研究 UI。

正式 DCF/剩余收益/周期模型只在 L3/L4 运行。L1 的 PE、PB、EV/EBIT、FCF Yield、
股息率只用于寻找研究候选，不能直接成为正式内在价值或买卖结论。单一公司或接口失败
只使该公司降级为 `DATA_INCOMPLETE` 等状态，不能中止全市场任务。

日常任务以变化驱动：新行情更新 PriceBridge；新财报更新 FinancialFacts/模型；重大公告
触发 ResearchCase 复评；Thesis Breaker 触发降级；没有变化则保留状态。外部数据等待遵循
[外部数据阻塞处理政策](external-data-blocking-policy.md)。

## Excel 最终验收

首页展示 L0--L4 数量、3--10 家高关注公司、今日变化和研究队列。高关注表至少有股票、
路径、当前价、估值状态、基准价值、置信度、研究状态、最大风险和下一事件；研究队列
至少有股票、所在层级、继续研究理由、最大缺口和下一动作。

最终用户应能在五分钟内回答：系统覆盖/筛选/深研/高关注数量，今天哪些状态改变，哪些
公司为何值得关注，最大风险是什么，价格与研究价值的关系如何，以及今天实际需要看什么。

## 分阶段扩展

当前顺序保持：三家公司统一研究/估值 MVP -> 20--50 家固定跨行业样本 -> 50--100 家
研究候选 -> 10--30 家深度研究 -> 3--10 家高关注 -> 事件驱动日常更新 -> 历史与前瞻验证。
在固定样本验证 ResearchCase、ValuationModel 和行业路由可复用之前，不对全市场运行
深度研究或完整 DCF。

## GitHub 调研结论

| 参考 | 可借鉴 | 不引入 |
| --- | --- | --- |
| [scfengv/Stock-Valuation](https://github.com/scfengv/Stock-Valuation) | 显式 FCFF 构成、WACC/终值敏感性、反向求解市场隐含增长；这些应作为通用模型的可审计输出 | Yahoo/yfinance 作为 A 股正式事实源、固定五年预测、固定终值或安全边际直接行动、其市场参数 |
| [kraigochieng/nse-value-screener](https://github.com/kraigochieng/nse-value-screener) | 原件下载、清洗记录、待处理队列和“准备交给 AI”的分层管线；单公司失败不阻塞批处理 | NSE 抓取/字段、正则清洗作为一手财务认证、LLM 直接产出财务事实或升级结论 |

上述仓库仅作结构参考，不安装、复制代码或采用其投资参数。GitHub 名称存在歧义；若用户
指定不同 URL，应重新核对后修订本节。
