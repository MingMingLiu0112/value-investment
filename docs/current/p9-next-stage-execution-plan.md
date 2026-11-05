# TL11-P9 下一阶段执行任务（按最短真实使用路径）

本文件是 2026-10-16 实测后的任务脚本，不是对正式投资准入的授权。当前 `action=no_order`、正式准入 0、本人的组合 NOT_CONNECTED。先让公开观察可连续复核，再接本人事实；经济研究、策略优势和人工审批各自验收，不能互相抵扣。已有 209+67 个定向 Python、196 个 Web 测试通过仅作工程基线。

## 执行顺序

`UX-ACTIONS-001（本轮实现并完成本地浏览器验收，远端 CI 待提交）` 与 `DATA-WINDOW-001` 可并行；`PERSONAL-ONBOARD-001` 的隔离部分可并行，但真实账户需要用户本人。之后 `VALUE-CASE-001 → VALUE-PRICE-001 → REVIEW-HANDOFF-001`；热点独立 `HOTSPOT-QUALITY-001 → HOTSPOT-PIT-001`；连续运行 `DAILY-DRILL-001` 横跨后续真实交易日。任何路径都不能以“0 候选”为由调低门槛。

## DATA-WINDOW-001 · P0 · 中

- **业务问题/复现**：`/system` 显示 10-15 双源价值收盘，但 600519/600887 `PRICE_NOT_ADMITTED`；读取 `config/current-quote-bridge.json` 可见原包 10-16 02:32 采集，超出 B1 同日收盘后窗口。
- **根因/证据**：`scripts/current/run_daily_workbench.ps1` 的晨间 SAFE_REFRESH 仅复用或采集；它不能回溯生成“10-15 收盘后当日采集”的证据。公开包 `pub-6167d094c68f6d8105c1` 正确 fail closed。这是采集时点与运维任务缺口，不能修成放松校验。
- **依赖/接口/文件**：复用 `collect_quote_sessions.py`、`pin_current_quote_bridge.py`、`refresh_current_price_conditions.py` 及 `daily_public_packet.py`。预计修改 `scripts/current/run_daily_workbench.ps1` 及其测试，必要时增加**只读**健康报告；任何实际调度必须单独授权。
- **步骤**：在独立测试时钟模拟收盘前、同日收盘后、次日补采、网络失败和重试；严格输出采集资格与具体下一次可执行时间。真实下一交易日收盘后人工运行现有入口并保存来源/时点/SHA；只有同日满足 B1 的新记录才允许价格桥继续评估，旧引用不改写。
- **测试/浏览器**：`python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/p9-data tests/test_daily_public_packet_identity.py tests/web_api`；`/system` 检查行情日、采集时点、逐证券资格；`/decisions/600887` 检查未通过时仍无正式价。负向：次日采集、双源分歧、来源 Hash 改变、发布失败必须保留旧版本且 `no_order`。
- **完成判据/外部约束**：自动化时间判断与审计正确，且至少一次真实同日收盘采集可复算；生产计划任务仍需授权，自然时间不可伪造。脚本实现与真实采集分开报告。

## UX-ACTIONS-001 · P1 · 小（本轮代码已实现，待浏览器验收）

- **业务问题/复现**：旧 `/system` 将 30 余条重复原始 blocker 和英文长句逐条铺开；用户难以找到证券、责任人及下一步。
- **根因/证据**：`web/src/pages/SystemStatus/index.tsx` 使用 `data.blockers.map(describeCode)`，未利用数据包 `company_statuses[symbol].pending_actions`。
- **依赖/接口/文件**：仅 `web/src/pages/SystemStatus/index.tsx`、`web/src/utils/system-actions.ts`、`web/tests/system-actions.test.ts`；复用现有公开包，不改后端字段、估值或门禁。
- **步骤**：按证券列已发布 `label` 和估值状态，链接决策页，去除同公司重复文案；原始诊断留在展开区域。未知行动标签不改写、不解释为审批完成。
- **测试/浏览器**：`npm run format --prefix web; npm test --prefix web -- --run; npm run build --prefix web`。实际打开 `/system` 桌面和 390px 手机，核对 600887 的材料性、模型、G3 待办链接；负向：公开包不可用时不得显示旧待办，`formal_admission_count` 仍为 0。
- **完成判据/外部约束**：用户首屏能看到逐公司待办，原始证据仍可追；这是可用性修复，不等于审核链通过。无外部批准。

## PERSONAL-ONBOARD-001 · P1 · 中（真实验收受本人输入阻塞）

- **业务问题/复现**：解锁 `/portfolio` 后是 NOT_CONNECTED，而非已确认现金/持仓；`/daily` 无持仓风险。不能把空白当空仓。
- **根因/证据**：缺用户本人 IPS、账户范围、现金、数量、成本、资金池和对账回执；`private_portfolio_service.py` 与 `private_routes.py` 有隔离流水和会话安全，不应新建第二套账本。
- **依赖/接口/文件**：复用 `PortfolioSetupForm`、`FillPanel`、`PrivateJournal`、`private_risk_preview.py`、`judgment_snapshot.py`；可能修改 `web/src/pages/Portfolio/index.tsx`、`web/src/pages/DailyDecisions/index.tsx` 及 `tests/web_api/test_private_portfolio_api.py`，只在实际复现 UI 接线缺陷时修改。
- **步骤**：先用 `.tmp` 独立账户走初始事实 → IPS 草稿/确认 → 买/部分卖草稿与确认 → T+1 → 重启重放 → 每日持仓风险；逐步比较现金、成本、资金池与哈希链。真人阶段由用户本人输入并核对券商对账单，不由 Agent 填写或上传。
- **测试/浏览器**：`python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/p9-private tests/web_api/test_private_portfolio_api.py tests/test_private_judgment_snapshot_service.py tests/test_private_risk_held_marks.py`；隔离服务浏览 `/portfolio`、`/daily`、`/history`。负向：错版本、重复成交、费用缺失、卖出超过可卖数、台账 Hash 破坏都应拒绝。
- **完成判据/外部约束**：隔离账本全部通过后仅标 ENGINEERING；只有用户本人完成真实事实和 IPS 确认、并核对重启后的数值，才可将 PORTFOLIO_FACTS 提升。不得用 SIMULATED 股数替代。

## HOLDING-DRILL-001 · P1 · 中

- **业务问题/复现**：当前无真人持仓；不能证明某只持仓退出每日 Top5 后仍持续看到风险、事件、退出条件。
- **根因/证据**：`private_risk_experience.py` 有持仓投影，`test_private_risk_held_marks.py` 仅证明隔离路径；自然多日和真实对账未验收。
- **依赖/接口/文件**：依赖 PERSONAL-ONBOARD-001 的隔离链。复用 `private_portfolio_service.py`、`private_risk_experience.py`；可能改 `application/product/daily_public_packet.py` 或 Web `/daily` 持仓块，先复现再改。
- **步骤**：隔离账户持有一只不在每日 Top5 的证券；变更下一日行情与公告快照，验证持仓不丢、风险/价格可降级、部分卖出后股数/成本/T+1 一致；再等待真人持仓场景。
- **测试/浏览器**：`tests/test_private_risk_held_marks.py`、`tests/web_api/test_private_risk_projection.py`、Web 持仓测试；`/daily → /portfolio → /history`。负向：无已准入价只显示已确认事实，不计算正式个人仓位或浮盈。
- **完成判据/外部约束**：隔离跨日通过及真人后续复核分别记状态；无实际持仓时不得标真实持仓监控 PASS。

## VALUE-CASE-001 · P1 · 大（聚焦 600887，一只完成后再复制方法）

- **业务问题/复现**：`/decisions/600887` 显示 9.80/10.08/10.30 条件情景和 28.10 收盘，却无可靠当前公允价值；当前低值主要来自一加三年全资本 ROE 快速侵蚀。
- **根因/证据**：`config/current-company-research-registry.json` 与 `artifacts/current/tl11-p8-20261016/research/judgments.json` 指出正常化利润、金融/工业现金范围、短融偿付、资本成本和优势期缺口。P8 原件/audit Hash 已核对，但经济判断仍需独立论证。
- **依赖/接口/文件**：复用现有剩余收益模型、`ResearchCase`、估值审核导入与公告材料性路径；可能新增版本化 `application/research` 输入包、`artifacts/current/` 回执、针对性测试；不改旧冻结结果和价格政策。
- **步骤**：以最小决定性证据清单审净利润正常化、权益/现金桥、维护投入、分红现金、短融到期、ROIC/增量回报与竞争优势期；给出 Bear/Base/Bull 敏感性及强反证。经济证据不足就维持 `CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED`，记录停止点，而非套用股价反推参数。
- **测试/浏览器**：现有估值和 P8 计算回放、来源时点/Hash/口径负向测试；`/decisions/600887` 解释为何仍不能当建仓价。负向：财务公司现金重复加、历史扣非 TTM 直接当正常化、金融融资算可用现金、未经批准的全资本衰减必须阻断正式结论。
- **完成判据/外部约束**：可独立重算、完整反证和适用模型后才称“经济合理待审”；G3 签署和当前价格另验，不在本任务代签。量级大且结论可以仍是不可可靠估值。

## VALUE-PRICE-001 · P1 · 中

- **业务问题/复现**：本人价格政策与公开估值、B1 当前收盘、模型有效性不能混成一个“买价”；`/daily` 明示两只尚无获准价位。
- **根因/证据**：VALUE-CASE-001 未确立主估值，DATA-WINDOW-001 未确立 B1 时点，G3 未批准；不是缺一个前端公式。
- **依赖/接口/文件**：依赖 DATA-WINDOW-001 和 VALUE-CASE-001；复用 `PriceBridge`、`value_action_policy_inventory`、Web 政策面板；可能改价格桥应用适配与 `tests/test_p8_decision_chain.py`，只修真实接线错。
- **步骤**：对研究事实、经济估值、价格政策、公开价格、本人政策与组合风险分别存状态；已获权限政策确认后只刷新其所在私人范围。开/加/减/退四类条件均需明确理由和反证；未获正式准入保留 null。
- **测试/浏览器**：六只真实负例 + 隔离正例；旧版本、过期行情、来源冲突、未授权 IPS/政策不得形成价位。浏览 `/daily`、`/decisions/600887`、`/portfolio`，验证公告与个人政策刷新不修改历史判断。
- **完成判据/外部约束**：条件性价格仅在所有相应门满足时展示；研究情景不被误称下单价，仍 `no_order`。经济与审批不能由工程绕过。

## REVIEW-HANDOFF-001 · P1 · 中（正式结果需有权人）

- **业务问题/复现**：600887/600519 已有增量公告原件，浏览器有审核交接按钮，但 `event_materiality`、G3 和模型有效性仍 `UNKNOWN`。
- **根因/证据**：材料采集与签署是两件事；`daily_public_packet.py` 将事件和估值待办分层，实际无有效签署回执。
- **依赖/接口/文件**：VALUE-CASE-001 后正式复核；复用 `application/product/research_materiality_reviews.py`、`application/decision/value_review_replay.py` 与既有私有签名/回执导入服务。只在发现消费错误时改应用层与测试。
- **步骤**：列审核对象、原件 Hash、模型及假设版本、授权身份来源、签名/拒绝、导入消费、重算、Web 刷新；允许 TEST_ONLY 的正负演练，不创建虚假真实审核人。
- **测试/浏览器**：`tests/test_p8_decision_chain.py` 和现有事件/G3 审核测试；拒绝伪造身份、错 Hash、旧材料、错日期。浏览 `/decisions/600887` 与 `/system` 观察仍未批准/批准后真实状态。
- **完成判据/外部约束**：隔离签署链通过只能标工程；真实 G3、重大性必须有权本人完成且可复核。

## HOTSPOT-QUALITY-001 · P1 · 中

- **业务问题/复现**：10-15 五只观察全是非银金融，601318 和 600030 的局部突破同时处于日线下降；“活跃”不能解释为值得入场。
- **根因/证据**：`domain/hotspot/daily_selection.py` 先按行业强度与成交额取 Top5，`current_price.py` 之后才评估日线/60m 结构；Web 已诚实标注结构不满足，候选质量层仍偏活跃排名。
- **依赖/接口/文件**：复用 `domain/hotspot/daily_selection.py`、`confirmed_price_structure.py`、`application/hotspot/daily_selection.py`、`current_price_case.py`；可能改 `web/src/pages/DailyDecisions/index.tsx`。不在现有五只上优化参数。
- **步骤**：独立区分活跃证券、结构合格、冲突/拒绝三层；用冻结规则在多个完成日期评估日线+60m+15m，不选择性删除失败样本；明确候选到期与结构失效。新排名如需更广股票池，应先验证数据覆盖和费用，不虚构全市场分钟数据。
- **测试/浏览器**：`tests/test_hotspot_daily_selection.py`、价格行为/回放测试；真实 601318 与 300059 必须保留负面分类。浏览 `/daily` 和两只详情，确认无“买入”措辞。负向：单周期触发、单源、下跌趋势、次日过期不能升级。
- **完成判据/外部约束**：用户能区分“为什么活跃”和“为什么不具备交易结构”；未证明策略优势仍观察层。

## HOTSPOT-PIT-001 · P2 · 大

- **业务问题/复现**：回放存在价格变化，但缺独立严格 PIT/OOS、复权、交易限制、滑点与重叠事件，不能声称可重复优势。
- **根因/证据**：现有 `event_replay.py`、`structure_replay.py` 验证计算流程，历史证券池/行业归属和 minute available-at 不足。
- **依赖/接口/文件**：HOTSPOT-QUALITY-001 规则冻结后；复用上述回放契约与现有证据仓；新数据输入/缺口报告放 `application/historical_validation`，不改冻结历史验证文件。
- **步骤**：先列可得历史原件及缺口，预注册样本日期与排除规则；按严格可得时点运行，计费用/滑点/T+1/停牌/涨跌停，做时间切分 OOS，再等待自然时间 Shadow。证据缺口不以合成收益填补。
- **测试/浏览器**：PIT 未来函数、幸存者偏差和重复样本负向测试；`/history` 标明可用范围和未证明项。完成标准是可审计的质量结论，可为失败；绝不以最大历史收益作为验收。

## DAILY-DRILL-001 · P2 · 中，跨真实交易日

- **业务问题/复现**：一次 SAFE_REFRESH 成功不能证明连续稳定、备份恢复或个人持仓跨日维护。
- **根因/证据**：10-16 本轮一次重复执行仅复用了 10-15 数据；正式 Excel 仍是独立旧快照。`scripts/current/run_daily_workbench.ps1` 是唯一日常入口。
- **依赖/接口/文件**：DATA-WINDOW-001；复用当前启动器、发布回执和只读健康 API；`scripts/current/audit_p9_readonly.ps1` 为验收器，不是第二启动器。
- **步骤**：在数个真实已完成交易日保存运行前后指针、来源 SHA、耗时、退出码、失败恢复与 Web 页面；隔离做私人流水重启、恢复核验，不接生产数据库。若需实际调度或生产恢复，先获单独授权。
- **测试/浏览器**：P9 只读脚本、Core/Web CI、每日 `/daily` `/system` `/history` 实际浏览器记录；负向：网络失败保留旧发布且标旧，不把上次 SUCCESS 冒充本次。
- **完成判据/外部约束**：逐日证据显示时间前进、失败可恢复和状态未误升级；自然日、真实用户及生产授权不能由测试替代。

## 退出边界

本阶段可达到“公开观察与个人组合事实有限辅助”，但正式买卖资格需要经济估值/策略有效性、真实 B1 行情、事件/G3、本人的 IPS/持仓风险共同成立。任何一项缺失保持观察或不可评估。不存在为了把正式候选从 0 变为非零而调参的任务。
