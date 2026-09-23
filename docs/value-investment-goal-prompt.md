# 目标模式启动入口

更新：2026-09-23 / roadmap-v3。按用户最新要求，一个总Goal从当前M2持续推进到M7。
只有范围调整，不表示阶段已经验收，也不授权生产部署/通知/使用未确认个人数据。
该总Goal当前已启动，执行范围与阶段门见 [current-stage-goal.md](current-stage-goal.md)。

## FINAL CODEX GOAL MODE PROMPT

```text
在 D:\GPTProject\value-investment 执行长期总Goal：VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE。
从真实当前基线继续，完成M2、M3、M4/M5、M6、M7，最终交付初步可真实辅助我个人价值投资的系统。
不要在M2或某个工作包完成后退出；阶段验收、客观评估和记录交接后自动继续，不要求我反复建立新Goal。总Goal必须以M7验收为终点。

先读取 AGENTS.md、LONG-TERM-GOAL.md、docs/north-star.md、docs/architecture.md、docs/research-methodology.md、docs/current-stage-goal.md、docs/data-and-evidence-policy.md、docs/execution-status.md、docs/m1-post-review-decision-gate-20260923.md。
按current-stage-goal的总范围/阶段门和LONG-TERM-GOAL第9节各Milestone完整合同执行。旧“完成M2即停止”的历史指令已被本次范围扩展替代，但任何安全/证据/人工授权门都未取消。

每次开始或恢复先核对HEAD、dirty diff、CI、运行收据、冻结Hash、原Excel和最新阶段检查点。审查基线f4bb55c只供参考，不回退已完成成果。
M1与Post-M1稳定化保持DONE；保留原三公司、格力/华域/伊利的真实拒绝/低置信度/STALE结果。不得为了出现BUY放宽规则或重写历史。
当前先完成M2时点/Universe/覆盖/合并/COMPLETE语义等实际缺口，而不是只补三份报告。

M2：执行current-stage-goal的W0-W7和AC1-AC12。补齐官方Universe、逐证券逐通道覆盖、Quality/Dividend/Value/Cyclical、真实会话与PIT、候选多原因合并/Why Now/预算、误放漏筛抽查、至少3份系统新发现公司的实质研究或否决、原Excel统一入口。
M2阶段仍无BUY/ADD/仓位；不做全市场DCF。高息/低PE只能触发线索，缺失不填0，画像不支持不默认FCFF，Legacy只作shadow，旧缓存不重标今日。

M3：复用HumanApproval/EventReview等现有门，建立InvestmentDecisionReview、DecisionEvidenceBundle、买加持减退理由卡、EntryThesisSnapshot、DecisionJournal及InvestmentConsistencyReview。
BUY/ADD至少要求研究与反证充分、有效Human G3、当前Event Review、模型适用/有效、可用估值与置信度、合法PriceBridge/可评估价格、无breaker及明确的最小PortfolioPreconditions。
买入卡解释生意、回报来源、预期差、Bear/Base/Bull、价格、置信度、股息、风险/反证、为什么现在关注和何时不能买。
ADD不能只因跌价；HOLD必须说明为何继续持有；REDUCE/EXIT区分论点破坏、价值损害、极端高估、组合风险和机会成本，并逐条回看原Entry理由。
冻结Entry必须经用户确认；已有持仓无原始理由则标事后重建，不伪造历史。用真实历史信息链和用户理解验收验证，不能只靠合成测试。

M4：建立用户确认的IPS/PortfolioSnapshot、风险与容量、分层PositionGuidance、当前/Forward/Normalized股息收入。
提前明确需要我提供的资产/现金/持仓、期限、现金和集中度上限、流动性、股息目标及风险约束；不得替我猜偏好。私人信息不得进入公开仓库。
仓位是组合共同预算，不是每家公司各算20%，也不是安全边际等于仓位；允许全现金，低置信度不得支持大仓位。缺个人输入时只继续非个人化工程。

M5：事件驱动采集财报/公告/分红/回购/价格和组合变化，Materiality -> Dependency Invalidation -> 有界重算 -> 原Thesis/Decision/Portfolio复核。
保留effective/available/detected时间、扫描水位、更正/重复/晚到、任务锁和通知投递证据。无重要变化静默，源失联必须区别于无事件，不每天重做全市场深研。
M3合同稳定后，M4 Portfolio域与M5事件基础设施可部分并行；联合产品验收必须等两边汇合。

M6：在具体生产方案另获授权后，完成staging/shadow、资源/权限/数据降级、隔离备份恢复、真实RPO/RTO和运行准入。
保留不少于20个连续真实交易会话观察及真实事件验证；20次运行或历史replay不能替代，重大缺陷后的观察按预登记规则处理，不事后降低标准。
保护服务器web_app_integrated.py/web-app-pta，不擅自改生产库、服务、计划任务或通知配置。先提交具体变更、资源预算、回退和验证方案，获确认后实施。

M7：在M6通过后完成个人工作台端到端交付。原Excel统一呈现市场、候选、重点关注、研究/买加持减退理由、组合/股息、变化及数据健康，能回到Evidence、Entry和Journal。
让我实际验证：研究谁、为何买、跌后为何加或不加、为何继续持有、何时减仓退出、原理由哪里变了、组合是否集中、股息是否可持续、今天什么变化需要处理。
形成可回退发布清单、简明使用/故障恢复说明、支持范围和已知限制。复用M3/M6验收，不无故新增另一轮20会话。
代理不能替我签署理解或交付验收；无合格机会时全部WAIT/空池合法，不以真实下单、盈利或出现BUY作为毕业条件。

执行方式：共享合同先冻结，通道/验证/read model可并行；每个阶段都交付用户可读增量并客观评估下一阶段，不能等到M7才展示。
工程、研究、当前数据、决策、组合、运营、用户验收分别记录。外部/人工/自然时间等待不虚标DONE，可继续总范围内依赖已满足的离线工程和展示准备，不发布依赖未验收输入的个人化结论。
有限重试，执行证据Stop Rule，不无限收材料、空转等待或擅自创建长期自动化；需要授权/用户输入或存在方法冲突时明确询问。
维护阶段检查点：代码版本、完成/未完成验收、输入/输出Hash、下一工作包、等待条件、授权和回退信息，以便跨运行续接而不重复建设。

所有Review均requires_human_review=true、action=no_order，永不直连Broker Order。不新增Web、全行业模型、收益拟合或公司专用流水线。
价格不能修改内在价值，LLM不能作为唯一财务计算来源，stress haircut不能当正式估值参数；正式重估必须有版本化输入及新的HumanApproval。
Excel发布必须候选/备份/源Hash/原子替换与实际WPS验证，保留手工和冻结页；占用或冲突不强行覆盖。
按可验证工作流小批次提交，明确路径暂存、检查diff/隐私、不覆盖他人修改，禁止git add .；公开推送须另有明确授权。
每个里程碑同时需要代码、真实公司/数据、PIT/重放、反例与可读展示证据，不能只靠测试数量或几个类型宣称完成。

只有M2-M7全部规定验收通过、用户确认交付、无未关闭关键错误放行或运营安全问题，才能标INITIAL_ASSISTED_USE并完成总Goal。
未满足真实输入、授权、自然时间或人工签收时保留PARTIAL及明确解除条件，不把“工程完成”当“真实可用”。
M7完成后停止，不自动扩展M8、自动交易或新的维护任务。
```
