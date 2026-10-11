# 双策略研究辅助产品交付记录

本轮交付研究观察与人工复核产品，不是已准入的实盘买卖信号。
永久 `action=no_order`，最终投资决定由本人作出。

## 实际发布

唯一 C 盘原表已更新，发布后 WPS 只读复核及版本登记通过。
工作簿 SHA-256：
`dd8aa81f15548a7b274fc96173d92401d7bcea593f90f89f36e558568cc9c782`。
原版本自动备份；七张托管页更新，55 张非托管页保护检查通过。
23 个内部链接实际跳转通过；六个候选估值与绑定研究 JSON 一致。
完整本地证据目录：
`runtime/daily-trade-assistant/20261012-productization-canonical-publish-v5`。
该目录是本机证据，不声称 GitHub 干净检出已包含全部财报和运行原件。

## 如何使用

1. 使用 `scripts/current/start_trade_workbench.ps1` 启动本地菜单。
2. 选择“更新并发布”：核验已登记的茅台、伊利，查询官方公告，扫描热点，生成风险状态，完成保护和 WPS 检查后更新原表。
3. 选择“打开工作台”，从 `01_今日` 看机会、风险、变化和待办，点击公司进入详细证据。查看不会重算或修改研究。
4. 价值模块可辅助理解经营质量、现金流、分红、条件估值、反证，以及买入/加仓/减仓/退出的复核前置条件。目前两家公司均暂不进入买入复核。
5. “扫描热点”生成真实来源的市场、行业及证券观察报告。此次覆盖 5573 只证券、31 个行业，观察列表 12 只；13 只证券有 10 月 9 日双源日期报价。
6. 热点入场需催化、价格行为、风险、价值及既有 PIT/OOS/成本/Shadow 门禁共同满足。当前所有入场资格均为 false；热点强弱不自动生成买点。
7. 两资金池通过既有私人 IPS/Portfolio 输入分别设置预算、现金、持仓、风险限额及来源，不预填个人经济参数。当前没有真实私人输入。
8. `04_我的组合` 展示资金池和风险接入状态。私人风险验证入口能检查现金、集中度、风险预算、跨策略重复暴露及数量限制；完整明细留在私人目录。经精确展示授权的聚合摘要可接入每日更新。
9. 公司页展示当前操作依据、加仓边界、减仓与退出依据、下一触发；手工 PLAN/FILL/REVIEW 使用追加 Hash 链，计划不冒充成交，不自动更新持仓。
10. 菜单“研究审核”进入既有版本绑定向导，阅读支持、反证及经济问题，保存草稿或通过真实身份签名。信任根仍为空，Agent 不代替本人批准。
11. 当前待审：经济假设、G3、公告材料性、模型有效性及正式价格；私人组合未接入；生产与真实 Shadow 未授权/未证明。行业交易日期未知，不能以采集日期冒充交易日期。
12. 完整 INITIAL_ASSISTED_USE 还需真实审核、适用行情、本人组合、严格同时点证据、真实事件运行观察、至少 20 连续真实交易会话、隔离恢复验收及最终本人使用验收。自然会话不由历史回放代替。

## 数字及证据边界

茅台当前选定 v5 条件研究：437.66 / 587.88 / 812.27 元/股。
伊利当前选定 v5 条件研究：9.80 / 10.08 / 10.30 元/股。
两者研究日期为 10 月 11 日，尚待审批，不是正式合理价值或买入价格。
两公司双源收盘观察为 10 月 9 日：茅台 1263.00 元，伊利 27.66 元；未形成正式价格准入。

热点历史示例为格力 640 根日线，截止 9 月 22 日：收盘 38.18 元，前五根支撑 37.83 元、阻力 38.79 元。
复权、公司行动及成交量口径未验证；60 分钟和 15 分钟缺原件。
10 月 9 日报价不能拼接上述旧窗口证明当前突破。
行业快照日期未知，资金流、持续性和催化不足，不能称完整当日多周期交易系统。

## 验证与问题处理

已登记核心回归：2302 passed、33 skipped；后续新增登记和架构定向回归：47 passed、3 skipped。
实际 v5 公司页合同回归 5 passed；报告可读性回归 3 passed。
合成双策略风险、签名批准/拒绝/过期/重放、异常恢复验证不代表真实投资批准或真实组合验收。
实际网络采集本次成功；真实网络故障后的恢复不由合成回退测试冒充。

首版发布失败的登记公司列混入热点代码已修复，原校验未放宽。
长表预览 bitmap 分配失败已修复，热点预览现在为 1416×636。
CI 本机运行文件依赖已修复，独立输入覆盖可在干净环境运行。
源码提交 `255448f14a82e407655175c21a918dfb71b4861f` CI 两组均通过：
https://github.com/MingMingLiu0112/value-investment/actions/runs/38158145926

旧新候选准备器午夜时区缺陷仍保留：`KNOWN_NOT_FIXED_NOT_ON_DAILY_V5_PATH`。
旧实现受历史 Hash 绑定，不复制成第二套准备框架；当前两公司日常更新不经过该分支。
本轮没有新增生产服务、调度任务、订单或审核身份。

相同经济输入使用新研究运行身份复跑，返回 `NO_MATERIAL_CHANGE`、`canonical_written=false`。
运行目录：`runtime/daily-trade-assistant/20261012-productization-same-economic-inputs-v1`。
行情与热点证据保持同一版本，官方公告查询和两家公司研究重新执行；不是复用同一 workbench 审计 ID 绕过重放规则。
新旧语义 Hash 均为 `0bd352b715673961246d5de475162f78f1eb459f3384ade2af6aa34c765dfbf4`。

`DAILY_UPDATE_PRODUCT_CLOSED = true`
`VALUE_RESEARCH_WORKBENCH_USABLE = CONDITIONAL_RESEARCH_ONLY`
`HOTSPOT_RESEARCH_MVP_USABLE = BOUNDED_HISTORICAL_OBSERVATION`
`DUAL_SLEEVE_RISK_ENGINE_TESTED = true`
`HUMAN_REVIEW_WORKFLOW_READY = IDENTITY_ENROLLMENT_AND_REAL_APPROVAL_PENDING`

`CANONICAL_EXCEL_PUBLISHED = true`
`SECURITY_DECISION_GATES_PRESERVED = true`
`USER_MANUAL_TRIAL_READY = READ_ONLY_RESEARCH_AND_REVIEW_PREPARATION`
`INITIAL_ASSISTED_USE = NOT_REACHED`
`TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES`
