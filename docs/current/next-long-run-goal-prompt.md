# VALUE-INVESTMENT-NEXT-LONG-RUN：从"研究观察系统"到"首个真实辅助决策"

> 这份文件是下一轮 Codex Goal 的完整输入。可直接整份复制给 Codex，无需再引用旧聊天。
> 审计来源：`docs/current/independent-full-project-audit.md`（2026-10-16 独立审计）。
> 永久边界：`action=no_order`；不自动下单；不代签人工审批；不伪造数据/仓位/行情/回测。

## 0. 目标与身份

你是本仓库的 Root / Integrator，唯一长期 Goal：

```
VALUE-INVESTMENT-NEXT-LONG-RUN-FIRST-REAL-ASSISTED-DECISION
```

最终产品：以本地 Web 工作台为主界面，对 A 股价值投资与热点波段两条策略资金池，
能给出**经过授权、可追溯、可解释**的决策辅助：

1. 每天应该关注什么、为什么；
2. 每个标的当前建议动作（BUY_CANDIDATE / ADD_CANDIDATE / HOLD / TRIM_CANDIDATE / SELL_CANDIDATE / NO_ACTION）；
3. 在获得真实 IPS / 持仓 / 现金后，给出价位、分批、目标仓位区间与风险约束；
4. 持续跟踪论点变化（财报、公告、分红、资本动作、价格、事件）；
5. 在独立预算、独立台账、独立退出规则下运行"价值+情绪"热点卫星仓（本阶段只做验证机器与前瞻记录，不允许宣称策略有效）。

本阶段的目标不是再增加一批文档或测试，而是：

**让系统第一次真正能够对一家公司给出"人已授权、证据完整、价格可比"的研究结论，
并让用户在自己的电脑上完成一次真实的私人组合接入与一次可复核的决策解释。**

## 1. 执行起点（2026-10-16 独立审计基线，先核对再动手）

```powershell
Set-Location 'D:\GPTProject\value-investment'
git fetch origin
git status --short --branch
git rev-parse HEAD
```

审计基线（若与现状不同，以实际为准并在台账里记录差异）：

- 分支 `codex/web-d1-investment-workbench`，HEAD `34019fd`（= origin 分支）；
  origin/main `3e6c5b4`；PR #1 仍为 Draft（禁止合并）。
- 工作树：7 个已修改文件（4 个 config 指针 + LONG-TERM-GOAL.md + 2 个 docs）
  + 43 个未跟踪项（P11 证据包 + D2 研究文档）。**先分类处理，不得 reset/checkout。**
- 运行：`scripts/current/run_daily_workbench.ps1 -Mode READ_ONLY` 可复现
  `pub-5f803ec65b6e52fd7de4`；runtime identity `MATCHED`；正式准入 0。
- 测试基线（审计实测）：本地全套 **5684 passed / 44 skipped**；Web **198 passed**；
  浏览器 4 视口 21 项检查 0 失败；P9 只读预检 38 项通过。
- 已知真实缺口：`runtime/` 未入 Git（单机依赖）；legacy Moutai 计划任务仍在运行；
  服务器 DB 管线仍写 `valuation_results`；6 家公司 0 家获得授权估值；
  热点 Top-5 在结构评估之前被截断；人工复核只有 CLI + 部分 Web 政策流。

## 2. 已完成能力（禁止重复建设）

- 每日双源收盘采集 + 内容寻址发布链（`daily-public-packet-engine-v18`）、
  指针/回执/快照校验、runtime identity、只读 Web 工作台（7 个页面）。
- 估值三路由（RI / FCFF / cyclical）+ ResearchGate 分层 + ValueActionPlan，
  全部 fail-closed；模型代码本阶段**不需要重写**。
- 私人组合/风险引擎（journal、prepare/confirm、T+1、双资金池风险、
  集中度/流动性/涨跌停/成本），已有 43 项 TEST_ONLY 测试。
- 研究证据：600519 / 600887 / 000333 / 000651 / 600741 / 601088 六家的
  原件绑定与条件性模型；P8/P11 的证据与回执；M2 漏斗数据。
- 已有入口：`run_daily_workbench.ps1`、`audit_p9_readonly.ps1`、
  `accept_p10_assisted_use.ps1`、`review_research.py`、`review_materiality.py`、
  `value-policy-review` Web 流程。**优先复用，不要新建平行体系。**

## 3. 本轮范围与禁止事项

范围：完成 W1-W8（W9/W10 为可选加分）。每个工作包必须产出**用户可见增量**，
不接受"只更新文档 / 只加测试 / 只解释为什么失败"作为交付。

禁止：

- 不新增大规模路线图或新 Milestone 编号体系；W 编号即为本轮工作包。
- 不改估值公式、不改筛选阈值、不放松任何人工门来制造 BUY。
- 不把 `PENDING_EXTERNAL_DATA` / `BLOCKED_PRIVATE_INPUT` 写成完成或失败。
- 不覆盖正式 WPS Excel（除非执行 W8 的显式策略并保留备份与校验）。
- 不合并 PR、不部署生产调度、不连券商、不写真实私人账本（除 W5 用户在场）。
- 不删除任何被 receipt/hash 绑定的历史证据；Git 已跟踪内容可安全整理，但需分批提交。

## 4. 工作包

### W1（P0）单一决策管道收口：legacy 退休或围栏
- 真实业务问题：Moutai B1 三个 Windows 计划任务 + 服务器 DB 管线仍在写"决策形状"状态，
  今日 Excel publish 任务 exit 1，无人处理；系统存在第二决策来源。
- 证据来源：`Get-ScheduledTask ValueInvestmentAgent-*`（今日运行记录）；
  `runtime/logs/moutai-b1-*`；`runtime/valuation-results/600519-current-equity-stage-b-latest.json`；
  服务器 `task_runs` / `valuation_results`（只读查询）。
- 根因：M 时代管线在新产品链上线后未正式退休。
- 用户可见结果：每天只有一个"今日决策"来源；旧体系被明确标记为历史研究档案。
- 实现步骤：逐任务给出退休/归档决策与理由；禁用时保留恢复说明；
  把 legacy 指针与 DB 表登记为 historical（只读引用）；
  新增校验器：枚举所有决策状态写入者，>1 个即失败。
- 输入/输出：现有计划任务与 DB 只读快照 → `docs/current/legacy-pipeline-retirement.md`
  + 校验脚本 + 任务状态变更记录（禁止动 PTA 项目）。
- 测试：校验器正/负用例（模拟第二写入者必须失败）。
- 依赖：无。可并行。工作量：M。工程退出条件：校验器通过且只有一条激活链路。
- 外部验收：用户确认旧 Moutai 自动化不再需要（一行确认即可）。

### W2（P0）数据托管、指针一致性与恢复演练
- 真实业务问题：全部验证产物在未入 Git 的 `runtime/` 单机上；新克隆无法验证指针；
  identity 的 dirty 检查不含 `config/`。
- 证据来源：`.gitignore:25`；`git ls-files runtime` = 0；committed pointer = `pub-6167d...`
  vs worktree = `pub-5f80...`。
- 用户可见结果：机器损坏后能恢复；仓库状态与运行状态一致。
- 实现步骤：定义恢复集（runtime 快照 + PostgreSQL dump + canonical Excel）；
  生成加密离线副本（密钥不与备份同放）；在隔离位置完成一次恢复演练并留 receipts；
  将 `config/current-*.json` 实际指针提交（或导出可复现快照）；
  扩展 `runtime_identity.py` dirty 检查到 config 指针。
- 测试：恢复演练脚本 + `audit_p9_readonly.ps1` 全绿 + identity 对新 dirty 配置返回不 MATCHED。
- 依赖：无。工作量：M。工程退出条件：恢复后能重新验证今日 publication id 与 SHA。
- 外部验收：用户指定加密副本存放位置。

### W3（P0）首家公司的可信估值输入包 → 草案估值（首选 000333 美的）
- 真实业务问题：0 家公司有可授权估值，一切下游（价格政策、买卖建议、仓位）都被卡住。
- 证据来源：`runtime/company-research/midea-valuation-applicability-20261013-v5/evidence.json`
  （FCFF `MODEL_NOT_APPLICABLE`，RI 已授权，股数 7,464,347,335 已验证，6 项 B 类输入已枚举）；
  `valuation_controls`、`config/m1-valuation-packages-v1/*`。
- 根因：经济输入（正常化盈利、投入资本回报、母公司可分配现金、发行人 COE、优势期）
  未逐项绑定原始文件。
- 用户可见结果：`/decisions/000333` 出现"草案估值（未授权）+ 证据清单 + 反证"。
- 实现步骤：逐项输入 → 年报/中报/公告页码 + hash；用确定性代码计算；
  运行 RI 模型；发布 draft valuation package（明确 NOT_APPROVED）；
  同步生成人工复核包（事实、假设、敏感性、反证、版本）。
- 接口契约：沿用现有 ValuationResult / ModelValidity / 证据绑定字段，不新增私有权重。
- 测试：输入绑定完整性测试、fail-closed 反例（缺任一输入不得出草案）、
  数字与原件交叉核对测试。
- 依赖：无（W4 可并行）。工作量：L。工程退出条件：一条命令可复现草案包 + 全测试通过。
- 外部验收：无（授权在 W4 由用户完成）。
- 备选顺序：601088（13 项输入从 0 开始，作第二验证）；600519（RI 对照）；
  600887 保持观察，等 FY/中报披露母公司可分配现金后再重启。

### W4（P0）人工复核工作流产品化（G3 + 材料性 + 价格政策）＋反伪造
- 真实业务问题：只有 CLI 能签人工门；仓库里存在机器生成的 `*-g3-human-approval-*`
  记录，形似人工批准。
- 证据来源：`scripts/build_m1_post_review_receipts.py`（硬编码 APPROVAL_SPECS）；
  `runtime/m1-post-review-20260923T114228Z/human-research-approvals.json`（untracked）；
  `value_policy_routes.py`（已有 preview/confirm）。
- 用户可见结果：用户能在本机 Web 里完成一次 G3 复核签名，并得到可验证回执。
- 实现步骤：退役/改名合成记录并加拒绝校验；在解锁会话内增加 G3 与事件材料性复核界面
  （展示模型、事实、假设、版本、反证、影响）；写入 append-only 回执
  （复核人身份、精确版本、范围、时间）；负向测试：过期会话、错版本、越权范围、
  合成回执一律拒绝。
- 测试命令（示例）：`python -B -m pytest -q tests/test_p7_signed_review_workflow.py tests/web_api`
  （以实际文件名为准）。
- 依赖：无；与 W3 并行。工作量：L。工程退出条件：签名与拒绝路径均有真实浏览器证据。
- 外部验收：用户完成首次真实签名（可对 W3 草案）。

### W5（P0，需用户一次性输入）私人组合首次真实接入
- 真实业务问题：没有真实现金/持仓/IPS，就没有仓位建议与风险预算。
- 证据来源：`C:\Users\we\value-investment-private\portfolio\` 目前只有 lock 文件；
  `private_routes.py` 15 条 POST；`REAL_PRIVATE_PORTFOLIO=BLOCKED_PRIVATE_INPUT`。
- 用户可见结果：解锁后录入并核对真实账户，风险预览可用。
- 实现步骤：提供一次性录入向导（现金、持仓、成本、可卖数量、IPS 分池）；
  T+1 卖出日期接入交易所日历校验（周六/节假日必须拒绝）；
  持仓公告提醒接入 disclosures 源；与券商对账容差与回执。
- 测试：日历边界（周六）、部分卖出、重复成交、错版本、重启恢复。
- 依赖：W4（签名路径）可先后。工作量：S（用户）+ M（工程）。
- 工程退出条件：测试与浏览器路径全绿；外部验收：用户确认数字与券商一致。

### W6（P1）全市场证据底座与漏斗量化
- 真实业务问题：5,573 家里只有 873 家有财务证据，quality 通道 0 通过。
- 实现步骤：把漏斗每一层的丢弃原因量化并发布（缺口类型分布）；
  提升官方财报获取/解析覆盖率；保持深度研究受产能约束。
- 用户可见结果：`/system` 或日报给出"为什么今天没有更多候选"的真实分布。
- 依赖：W1（避免与 legacy 采集重复）。工作量：L。

### W7（P1）热点：结构优先选股 + 成本化验证 + 前瞻 shadow + 第二数据源
- 真实业务问题：Top-5 是行业强度/成交额截断，结构评估在其后；当日 5/5 同行业；
  验证只有描述性统计。
- 实现步骤：先建候选池（跨行业约束）→ 再评估结构 → 再排序展示；
  成本化执行模型（佣金、印花税、滑点、涨跌停、停牌、T+1）；
  PIT 重构的历史分钟数据；冻结规则版本；每个真实交易日追加一条 shadow 观察；
  接入第二个日内数据源或授权数据（冲突规则显式化）。
- 用户可见结果：每日候选跨行业、每条都带结构层级；shadow 计数器随真实交易日增长。
- 测试：冻结规则的复算一致性；shadow 幂等（同日重复运行不重复计数）。
- 依赖：W1。可并行。工作量：L。外部验收：需自然时间累积（不得伪造）。

### W8（P1）每日产品收口：调度统一、晨报摘要、Excel/Web 一致性
- 真实业务问题：新链路无调度；失败无人知晓；Excel 冻结在 2026-10-01 与 Web 差 15 天。
- 实现步骤：单一调度跑每日链路（收盘后）；生成晨报摘要（上次运行状态、失败原因、
  今日待办、复核清单）；明确 Excel 策略（恢复发布 或 冻结并加版本戳+指向 Web）。
- 依赖：W1。工作量：M（不含自然时间等待）。

### W9（P2，可选）受控 LLM Agent pilot
- 在一家公司上真实运行三角色（基本面/反证/事件），输入必须绑定来源摘录，
  输出仅作非准入的 counter-evidence；记录成本、失败与重试；
  永久禁止 LLM 成为数字来源或批准来源。

### W10（P2，可选）架构瘦身 batch 2
- scripts 瘦身（563 个根脚本不可持续）；目标迁移平铺模块；
  删除重复的 systemd 副本与 `render_dual_strategy_artifact_pages*` 变体；
  清理 `runtime/.pytest-*`；为仓库债务设 CI 预算。行为保持不变，分批提交。

## 5. 依赖顺序与并行规则

```
W1 单一管道 ─┬─> W6 证据底座 ─> （更多公司走 W3 模式）
W2 托管/恢复 ─┘
W3 首家估值 ─┬─> W4 人工复核 ─> 首个授权价格政策 ─┐
W5 私人接入 ─┘                                    ├─> REAL_ASSISTED_USE 候选
W7 热点机器 ─────> 前瞻 shadow（自然时间）────────┘
W8 日常产品 ─────> 每日可用性
```

并行规则：最多 3 个 SubAgent 并发；同一核心文件同一时间只有一个写入者；
Root 负责合同冻结、集成、全量回归、提交与阶段状态。

## 6. 长周期执行规则

- 允许在安全范围内安装依赖、运行隔离测试、真实浏览器验证、有限重试、复用现有模块。
- 每批改动：先跑目标测试，再跑全量（`pytest -q`）+ Web（`npm test --prefix web -- --run`）
  + `audit_p9_readonly.ps1`；通过后小步提交并推送（代理 `-c http.proxy=...`）。
- 每轮结束更新任务台账（实际增量、命令、产物路径、未通过项、剩余 blocker、下一包）。
- 遇到外部条件缺失：完成所有不依赖它的工作，再一次性请求用户（IPS/持仓、签名、授权）。
- 不因单一公司/单一门禁阻塞而停止其它工作包；不因自然时间未到而伪造 shadow 进度。

## 7. 只有用户能做的事（不得代替）

1. 真实私人资金/持仓/成本/可卖数量与 IPS（W5，一次性）。
2. G3 与事件材料性亲笔签名（W4；系统只能准备材料）。
3. 确认 legacy Moutai 自动化退休（W1）。
4. 指定加密恢复副本存放位置（W2）。
5. 最终验收：确认系统在其日常使用中"有用"。

## 8. 两套验收标准（必须分别报告）

- 工程闭环：以上工程包全部实现、测试、集成并通过真实浏览器验证，
  且不依赖外部条件的部分 100% 完成。
- 真实业务资格：经济研究、策略有效性、真实 IPS/持仓、人工审批、
  自然时间前瞻观察、用户签收各自有实际证据。
  工程完成不得替代业务资格；外部缺失不得判工程失败。

## 9. 状态与报告要求

保持并更新：`ENGINEERING_DELIVERY`、`CURRENT_RESEARCH_ADMISSION`、
`FINAL_OPERATIONAL_ACCEPTANCE` 三项独立结论；
每轮报告给出：实际产品增量、可执行命令、用户可见产物路径、
测试范围与结果、未通过结论、剩余 blocker、下一工作包。
禁止用"已新增文档/测试通过/模拟审批"替代产品完成。

## 10. 长期退出条件

```
TARGET_ARCHITECTURE = one decision pipeline, one publication chain, one recovery set
FIRST_AUTHORIZED_VALUATION = 至少一家公司完成 输入->模型->G3 全链
FIRST_AUTHORIZED_PRICE_POLICY = 至少一个 profile 完成注册价格政策
REAL_PRIVATE_ONBOARDING = 完成并核对一次
DAILY_PRODUCT = 单一调度 + 晨报摘要 + 失败可见
HOTSPOT = 结构优先选股 + 成本化验证机器 + 前瞻 shadow 持续累积
action = no_order（永久）
```

## 11. 立即开始

立即从 W1 与 W2 开始（二者不依赖用户、不依赖外部数据），并行推进 W3；
在 W3 草案完成前完成 W4 的签名流程骨架；
在 W3/W5 中任何需要用户输入的节点，一次性汇总后请求，不要反复打断。

不得以"再写一份审查报告"或"再规划一轮"替代执行。
不得以测试通过或模拟审批代替投资辅助决策产品的完成。

立即开始下一阶段开发，按关键路径连续实施，完成工程闭环和真实使用验收。
