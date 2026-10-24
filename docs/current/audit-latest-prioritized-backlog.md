# 审计差距与依赖施工清单

2026-10-17；基线 d56ae6517b8121ed5677fa566263faf8db295f67；本轮只审计，以下均为**下一轮待实施**，不得读成本轮已修复。详细执行合同在next-executable-long-run-goal.md，真实反例在artifacts/current/full-audit-20261017三份独立专项中。action=no_order。

## P0：工程可信性与计算事实

| ID / 根因 | 最小文件与动作 | 依赖 | 正向/负向验收 | 专注人日估计 |
|---|---|---|---|---|
| WP00：Web format三文件失败 | DecisionDetail/index.tsx、research-funnel.ts、researchDraftText.ts精确Prettier；测试隔离白名单复制，不带node_modules | 无 | 四本地命令与同SHA Core/Web CI成功；长路径仍执行真实故障保旧包；不靠跳过测试 | 0.5–1 |
| WP01A：登记不是围栏，旧task传递可写Excel | operations/decision_writer_registry.py、product/public_snapshot.py、run_moutai_b1_after_close/Excel发布薄入口；实际状态/动作/目的地审计并在写边界强制权限 | 00 | 当前合法发布成功；ARCHIVE/旧脚本直接及间接写正式目的地均拒绝；非权威采集可归档 | 与01B共1–2 |
| WP01B：组件恢复未证干净全业务恢复 | operations/closure_restore_drill.py、backup.py、既有加密模块；固定代码+Git配置+必需非Git依赖清单，隔离恢复再跑消费者 | 00 | 当前包/研究消费/唯一Excel校验；删必需源/坏包/错key拒绝；异机未证不能PASS | 同上 |
| WP02A：facts锚未约束operating_inputs | product/source_bound_inputs.py、m1_valuation_package_builder.py、research_input.py及source contract测试；逐实际消费字段绑定原件/推导/单位/范围 | 00 | 美的原输入重放原三值；权益×10/股数×10/删必需锚/错单位期间必须拒绝；不能仅检查financial_summary | 1–2 |

先修CI可确保后续变更可信，再并行写入围栏与事实完整性。事实完整性优先于扩更多公司：否则一份“来源verified”标签仍可能对应错误计算数。

## P1：业务闭环

| ID / 根因 | 文件入口及最短动作 | 依赖 | 可见成果和验收 | 人日估计 |
|---|---|---|---|---|
| WP02B：H1/FY错配、汇兑套保未正常化 | scripts/research_cases/midea/build_draft_package.py、publish_research_draft.py；官方H1 p7/注释→税后归母净效应→假设敏感性→共享RI | 02A | 新版本纠正11.33% vs11.29%，保留扣非降幅及解释；不全额加回、不用股价倒参；经济不足有界结案 | 1.5–3 |
| WP03：事件/研究批准缺口与消费断层 | product/research_reviews.py、research_materiality_reviews.py、domain/research/human_research_approval.py、research_gate.py及现有审核Web | 02A/02B包可审 | 4公告材料/支持反证/版本明确；真实有权回执才解门；隔离正向更新、错签/过期/合成生产拒绝 | 1–2 |
| WP04：动作/本人政策/风险尚未完整关联 | domain与application/decision/value_action_plan.py、value_price_policy.py、private_risk_projection/preview | 03合同，真签可后到 | 四动作复核合同、本人确认后叠加更新；REDUCE/EXIT不能靠删硬拒绝；无私人事实不给正式数量 | 1–2 |
| WP05：十池采集及消费三断点 | hotspot/current_refresh.py保行业排名/完成时点；current_registry.py按绑定池验成员；validation_evidence.py消费all assessments | 01，可与02并行 | 原第6–10名提升→真实loader→API正例；10尝试/成功/失败/结构拒绝分开，9案例不算10/10；未来/异日/缺bar拒绝 | 1–2+取得数据 |
| WP06工程：描述回放无可成交/成本净收益 | domain/hotspot/event_replay.py、structure_replay.py、既有Shadow消费；事前规则/采样冻结及有限撮合约束 | 05 | 有成本才出净收益；跳空/停牌/限价/T+1/未成交/同根歧义负例；后验v3不得变PIT | 2–4 |
| WP07：首次使用/持仓公告无生产接线 | private_portfolio_service.py、held_continuity.py、private_routes.py、既有Setup/IPS/对账/Fill/HoldingsAttention | 01/04，公告可并行 | 网页隔离零开始→IPS→买→次交易日部分卖→对账→重启/复盘；离榜仍跟踪、空公告窗不得完整 | 1–2 |
| WP08：已有财务事实不能accepted | financial_quality.py真实生产者、research_funnel_audit.py、value_research_queue.py、research_funnel_status.py | 02A | 873中跨行业≤10小样本补完整债务/同基期增长/资本回报；不改门槛和flag，质量0可保留；下游未知分母明确 | 1–2 |
| WP09：锁定错误待办、正式/草案混淆、Excel旧期 | ConfirmationTasks.tsx、DailyDecisions/DecisionDetail/Portfolio/History/SystemStatus、既有Excel保护发布入口 | 随业务包，主代理独占Web | 不解锁不发15私人请求；解锁后登记结果可见；正式/草案不同版本原因明确；Excel未更新醒目标旧 | 0.5–1.5 |
| WP10：组合E2E及收口 | 既有Windows故障E2E、private HTTP E2E、上述真实消费者和恢复验证器 | 所有自主P0/P1 | 真实负向+TEST_ONLY正向两线，重启/历史/桌面手机/同SHA CI；无可修P0/P1才工程完成 | 1–2 |

所有包统一12步：查输入→复现断点→负例→最小修复→定向测→真实/隔离E2E→API/Web→重启/历史→相关回归→机器回执→用户可见核验→台账/下一包。完整Goal中已逐包具体化，不能只按此简表跳过。

## P2：外部与后续范围

- 异机备份：需明确目的地、独立密钥恢复方式，再真实取回并隔离验包；本机staging不能算。当前PG同版本恢复需隔离服务与明确生产读取范围；不直接跑会重建容器的部署脚本。
- 本人资金/IPS/持仓及券商外部对账：用户在授权网页完成，不能代填或公开Git。工程用隔离账户先走通。
- G3/材料性签署：需有权审核人和已登记身份，不等同本人价格政策；工程应提供可实际交付包及接收验证。
- 规则strict PIT、未来披露、>=20连续真实交易会话/事件观察：自然时间，不能用历史重放/重复run顶替。规则冻结和计数工程先做，等待不阻其他包。
- Agent真实provider：现有OFFLINE/MOCK不算上线，预算/服务授权后才发live；source_requests/有界重试可作小改，非交易辅助最短关键路径。
- 2027/BSE日历属性：实际使用前补官方证据，当前拒绝为正确安全边界；不默认工作日。

## P3：明确不做

不新增Agent Harness、平行估值/账本/风险框架、更多权威Excel、自动交易、无限扩公司/全市场重抓、为盈利调参/放宽批准、装饰性研究组件、以测试数量和报告数量替代业务验收。

## 工期与交付边界

合计约12–23专注工程人日，因并行与共享整合不按人数直接相除。可见改善规划约2–4工程日，工程收口约2–4工作周，均非保证；网络、依赖迁移与研究原件可能增加时间。真人签署/经济是否充分/策略有效性不能承诺日期；真实20会话需要自然交易时间。不得以“工程完成”简写“总Goal完成”。

最终分开验收ENGINEERING_WORKFLOW、VALUE_DECISION_CLOSURE、HOTSPOT_DECISION_CLOSURE、PRIVATE_RISK_CLOSURE、HUMAN_APPROVAL_WORKFLOW、FORMAL_INVESTMENT_ELIGIBILITY、USER_ACCEPTANCE。外部门集中交接，代码缺口仍留工程待办。
