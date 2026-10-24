# 全项目独立审计：实际代码、运行与业务差距

审计日：2026-10-17，Asia/Shanghai。只执行审计、安全验证与下一阶段施工方案；未修业务代码、未发布研究、未改正式 Excel、未连接生产服务器。永久 `action=no_order`。

## 1. 基线与可复查证据

- AUDIT_HEAD：`d56ae6517b8121ed5677fa566263faf8db295f67`；分支 `codex/web-d1-investment-workbench`；起始工作树干净，diff check 通过。报告写入后会出现本轮交付，不能倒称起点 dirty。
- CURRENT_PUBLICATION：`pub-cb73f09b88c4150ecf0d`，packet SHA `f0efba54ff69ccc774eba6a9ce4ec43deea2b541488af934cce11606c31b6dff`，发布于 2026-10-17 21:53:57 北京时间。
- 正式研究版本 `canonical-reviewed-research-20261012T113935Z-362d7928`，研究截至 10-11；美的单独草案 `midea-draft-20261017-v2`，不能替换正式研究版本。
- 当前报价会话 2026-10-16，bundle `runtime/quote-sessions/20261016T090031652233Z/bundle.json`；取得时间 17:00:31 北京时间。周末不因没有新交易日阻塞工程。
- 本轮实际重建 Web，构建时间 `2026-10-17T14:54:32.500Z`，源码同 HEAD、source_dirty=false；启动后 API runtime identity 为 MATCHED。重建前的构建身份未捕获，不能补造。
- 审计开始时 8001 端口拒绝连接；本轮通过既有 `start_web_workbench.ps1` 启动本机 Web，再核 API/浏览器。没有运行会重发当前包的 `run_daily_workbench.ps1 -Mode READ_ONLY`。
- 本次固定证据保存于 `artifacts/current/full-audit-20261017/`；原始探索位于 `.tmp/full-audit-20261017/`。启动日志含本机授权秘密，明确不纳入交付。详细专项为同目录 `research.md`、`hotspot.md`、`private-operations.md`，均有独立源码核验，不以旧报告 PASS 作为本次执行结果。

## 2. 本次真实验证结果

| 验证 | 结果 | 能证明什么 |
|---|---|---|
| 当前只读预检 | exit 0，38 绑定通过 | 登记资产及绑定可校验，不是投资批准 |
| GitHub Core run 39039580288 | 同 HEAD SUCCESS，含 Postgres job | 该远端 CI 范围通过，不代表本机真实 PG 恢复 |
| GitHub Web run 39039580294 / 39039576083 | 同 HEAD FAILURE | 不得宣称 CI 全绿 |
| 本地 typecheck / test / build | exit 0 / 0 / 0，Web 210 passed | 编译及该测试集可通过 |
| 本地 format | exit 1 | 三个文件不符合 Prettier：DecisionDetail/index.tsx、research-funnel.ts、researchDraftText.ts |
| 扩展 Core + API 首跑 | exit 1，3113 passed、35 skipped、1 failed、15 errors | 非全仓测试；十五 error 因本审计命令重复收集 API node，不能算十五业务缺陷 |
| API 独立纠正重跑 | exit 0，193 passed | 不重复收集后 API suite 通过 |
| M4工作流内联测试补查 | exit0，3 passed、2 skipped | 两个成功私人输入回放需Git外scratch；本轮在repo临时目录运行故跳过，不作正向回放通过 |
| 私账/恢复/Agent 定向 | 两批 exit 0，288 + 27 passed | 合成工程验证，不是本人使用或真实模型调用 |
| 热点专项 | exit 0，94 passed | 已有验证通过，但存在组合接线遗漏 |
| 桌面/390×844 手机 | 六路由实际打开，截图与 DOM 留存 | 公开读取/锁定边界可见；非真实私人审批/成交浏览器验收 |

首跑额外失败为 `test_safe_refresh_failure_keeps_previous_snapshot_bytes`：隔离复制整个 scripts，连同本机 artifact-tool/node_modules，落入长路径 WASM 文件 WinError 3。它发生在执行断网刷新之前；改用短目录 `.tmp/fa-copy` 定向重跑整个该文件后 exit0，10 passed，41.91秒，含真实Windows隔离故障保留旧包用例。故不是已证业务回归，但应收敛 fixture 复制范围，不能删用户依赖或弱化故障断言。另一次 PowerShell 内联环境变量被外壳展开的探索命令无效，未作为通过证据；正式 API 重跑采用 -File 脚本。现有 API fixture 会临时写用户 home 并 finally 清理，应改为获准隔离测试路径策略，不可弱化生产私账不得进 Git 的约束。

## 3. 实际架构、权威与写入风险

当前路由实际为 `/daily`、`/decisions/:id`、`/historical-price/:symbol/:day`、`/portfolio`、`/history`、`/system`；不是 AGENTS 历史描述中的六个中文导航页面。

现有主链：公开采集/研究 → 确定性估值与门禁 → `application/product/daily_public_packet.py` → `public_snapshot.publish_snapshot` → 当前快照指针 → `presentation/web_api/app.py` → Web。`/daily-public-packet` 优先读校验快照；缺快照时才 live composition，并明确 NO_VERIFIED_SNAPSHOT，不能冒充冻结发布。私账经本机会话及 Origin → `private_routes.py` → `PrivateJournal`，不随公开包传播。

写入者 registry 有 10 管线/6 scopes，但校验器只检查声明和任务存在，未成为统一发布授权围栏。实际四个 Windows 任务中三个 Ready、一个 Disabled。`DailyUpdate` 仍调用已 Disabled 任务对应 postclose 脚本；旧 Excel task 可串到正式 C 盘工作簿。最近一次退出 1 不能证明永久不能写。必须修消费者/目的地围栏；本轮未禁任务、未改服务器，未证明已污染当前包。服务器当前任务和进程状态 UNKNOWN，不将本地部署定义当实时服务器证据。

## 4. 数据、漏斗与六家公司

API 与原件校验一致：全市场历史快照 5573，行业/行情记录各 5573；财务 873 公司、21277 点；分红证据 3622；114 LEAD，队列选 10、延后 104。同报告期完整 0，quality PASS 0，data gap 4677，insufficient 775，unsupported 121。不是“全市场没有好公司”：资本回报点没有通过 accepted 契约，同期证据断裂；该漏斗报价日 10-12 且未独立验交易日，不能与 10-16 B1 局部报价混为全市场已核验。

| 公司 | 当前可用成果 | 不能正式给价的原因 |
|---|---|---|
| 600519 贵州茅台 | 正式链可读的受限情景 437.66/587.88/812.27；参考收盘1329 | 强衰减压力情景不等于中性估值，G3/事件适用/价格政策未闭合 |
| 600887 伊利股份 | 9.80/10.08/10.30 受限研究情景；参考28.20 | 正常化经济研究及事件/模型有效性、G3和政策未完成；不能由数值直接推卖出 |
| 000333 美的集团 | v2草案36.01/45.74/58.17，核验收盘84.60 | G0 PASS/G1 FAIL/G2 PASS/G3 FAIL；PriceBridge INVALID；4公告待审、覆盖不全、严格同期未证 |
| 000651 格力电器 | 档案与路由入口 | 金融/工业边界、现金归属、资本回报与估值输入不足；不填造估值 |
| 600741 华域汽车 | 研究线索与档案 | 客户价格、营运资本、再投资、周期盈利桥未闭合；不把CFO当FCFF |
| 601088 中国神华 | 已有周期路由支持 | 当前归母盈利桥和13项周期经济输入待核验；路由存在不等于估值可用 |

美的财务事实来自巨潮 2025年报、2026H1报告及港交所股本原件；9项财务事实带原件页码，9项假设绑定 memo。9%股权成本、未来ROE、终端增长及留存是经济假设，不是财报事实；股利代数核对并非独立分红可持续性证明。四项公告为10-14股东会决议/法律意见/减资和10-17回购进展。草案披露的 G1 必须追踪具体 checker，不能凭门名称推断一定是缺财务API；详见本次 research 专项。

**决定性研究发现（本次内存变异实测，不改原包）**：`source_bound_inputs._validate_fact_anchors` 比较的是financial_summary，而RI实际消费operating_inputs。权益或股数单独×10、删除fact_anchors均被接受，Base分别变为457.4170、4.57417、45.7417。G1/G3仍拒绝，未发现正式准入绕过，但计算事实完整性存在P0缺陷。九个页锚自身经单位归一化正确不等于计算输入已受约束。

G1实际失败是 `research_status=DRAFT_NOT_APPROVED` 不等于checker要求的financial_scope_approved；不能直接改字符串当研究已完成。G2只检结构完整。美的叙述将H1 ROE11.33%与全年比较声称回落，原件上年同期为11.29%；同页解释扣非下降涉及汇兑损失/套保收益分列。必须形成净效应、归母税后正常化桥；不能简单把汇兑全加回，也不能因此抬高估值。本次重新跑119项研究定向测试通过，同时变异反例证明现有测试遗漏。

六家真实计划本次重载均WATCH、四trigger_price为空、政策registry binding=null。更进一步，领域代码对REDUCE/EXIT始终保留独立论点复核拒绝；其正式辅助资格尚不是与OPEN/ADD对称的已完成链。下一阶段必须定义独立风险退出复核契约，不可只删blocker。

价值动作、私人政策预览确认、风险及成交记录已有代码和隔离测试；正式价值条件为空混合了经济输入、模型、事件、G3、政策与本人组合多种缺口。需要逐因展示，不可一律 UNKNOWN，也不可降低30%阈值制造 BUY。合法隔离批准只证明工程可通，不授予真实资格。

## 5. 热点：真实发现及策略边界

十候选为600150、000338、600176、000560、600667、601857、002008、600019、600127、000333，十行业；实际同日结构仅1/10，结构合格观察0。原当前五只同为军工，与新池仅600150交集。其余九只未取得同日case，不能算模型拒绝。

三个明确代码断点：`current_refresh.select_watch_candidates` 丢 industry/rank；`validation_evidence.load_current_case_bindings` 只消费 final items，不消费 assessed_candidates；`current_registry.load_price_conditions` 成员及名称查找仍限定旧 observation_list。应同时修复、以第6–10名提升进入真实loader/API的组合用例验收，单测94通过未覆盖此组合。

已完成K线、摆点 known_at、60m主周期与15m辅助不能放宽。日线由60m聚合，不是独立第三源；分钟单源限制必须保留。十池来自后来的v3重排旧v2，`future_rule_version_used=true`、RETROSPECTIVE_RESEARCH_EXTENSION；行业历史生效未知、历史证券池不完整、成本/滑点/成交净收益仍null。无合法策略优势、untouched OOS或自然时间Shadow证明。

网页现有中国船舶：参考35.77，入场观察36.45，结构失效34.41，日线上升但尚待60m主周期确认；这是10-16案例观察，不是买单。航发科技、内蒙一机、洪都航空、航发动力均显示结构不满足。不能把这些历史结构与正式当前资格混用。

## 6. 私人组合、Agent、运营和恢复

私账 hash journal、revision/idempotency、共享现金/双池集中度、费用、实际交易日T+1、重启重放与并发拒绝已有可复用实现。默认环境只核存在性：目录存在、journal不存在；运行服务是否另用环境未知，未读取真实资金持仓。真实首次录入、IPS、券商外部对账和本人使用未证明。行情陈旧/未准入只能情景试算，不应给正式可操作股数。

离榜持仓独立保留，不被榜单截断；公告覆盖字段目前只有消费端，没有生产赋值链，所以 UNKNOWN 是真实缺口。2026 SSE/SZSE之外日历仍拒绝，跨年/BSE应按使用范围补官方证据，不默认工作日。

Agent有HTTPS provider、三角色串行、来源引用验证、预算/锁/超时及禁止批准发布边界；现有产物 OFFLINE/MOCK，无本轮真实provider证据。工具调用数0，provider工具调用被拒绝；不是自主联网研究Agent。未见adapter内重试，不将mock算上线，不发付费请求。

本地既有加密恢复包与直接绑定重算匹配，损坏包拒绝在测试中通过；本轮未重新解密/复制正式资产。当前drill只证明列明组件，未做固定代码+递归必需原件的干净机重放。历史10-01 PG dump/恢复回执及dump hash存在，14表/20原件，PG16→18.6，same-major未证，full_system_restore=false。本轮真PG恢复 NOT_RUN。异机copy NOT_CONFIRMED；密钥在本机不同目录不等于独立设备安全恢复。不得宣称当前RPO/RTO达标。

唯一Excel SHA匹配 `aeaa3c7fec2b46d34c0651b0384dec49fb3ca16747dc41fcf675bbd022be82f1`，原快照10-01、登记行情10-09、研究更新登记10-12，excel_sync=null。未本轮修改；与Web不同步必须醒目标注。

## 7. 浏览器实际结果与新增产品缺陷

桌面及390×844均打开daily、美的、伊利、portfolio、history、system；截图与DOM逐页保存。首页、详情、系统可读，抽查手机无横向页面溢出（scrollWidth375 <= innerWidth390）。私人页保持锁定，未代本人初始化、批准或填成交；不声称完整私人浏览器PASS。历史显示2证券4研究版本，不能叫全公司历史。

P1：`ConfirmationTasks.tsx:139` 在connected=false时仍对15公司渲染PersonalPolicyTask，调用私有status导致首页十五条相同失败。应区分锁定/无草案/真实网络失败，只在授权后读取；不是放宽匿名权限。

P1：美的顶部正式卡仍说经济输入未注册/报价待核验，下面草案已显示新9事实与84.60。不同权威层可以不同，但需明确“正式版本未消费草案”的原因与唯一下一步，避免看成数据丢失。首页主要展示旧正式2公司，不能仅有新草案藏在详情下方。

## 8. 总判断与不确定性

ENGINEERING_READINESS=PARTIAL：核心骨架可复用，存在真实CI、写入围栏、恢复范围和热点接线问题。

REAL_USER_WORKFLOW_READINESS=PARTIAL：公开观察可用；锁定/private首次使用及有权审核的完整真人业务尚未验收。

INVESTMENT_DECISION_QUALITY=NOT_PROVEN：没有任何正式获准操作候选，首家公司经济及审批未闭合，热点无合法成本后OOS优势证据。不能承诺稳定收益。

最高影响五缺口：①可靠首家公司经济估值+事件/G3；②十池结构采集到消费三断点及策略证据；③真实账户/IPS/对账+公告监控；④旧发布者可达唯一Excel/恢复未闭环；⑤Web错误待办、版本层混淆与CI失败。施工先清CI和安全权威，再并行做①②③，不等待人工审批才继续其他工作。

未执行：生产SSH/任务停用、真实PG重建、异机取回、付费LLM、真人审批与交易、未来交易会话。各自保留外部门，不虚构完成率。下一阶段目标文件给出文件级施工和正负验收；本轮不宣布总Goal COMPLETE。
