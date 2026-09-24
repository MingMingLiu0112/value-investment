# Changelog

## v2026.09.24-m5-600519-reconciliation-intake

### Scope

M3 Checkpoint B 等待人工复核期间，继续 M5 离线工作：对 600519 真实 CNINFO 队列
执行既有人工台账 Hash 对账，并生成九条公告的空白人工材料性回填表。

### Changes

- 新增运行时对账目录
  `runtime/m5-600519-human-review-reconciliation-20260924-v1/`。
- 新增公开空白回填表
  `A股价值投资_M5真实披露人工复核回填_600519_20260924.xlsx`。
- 更新 M5 披露复核与 M2-M7 人工交接文档。

### Verification

- 对账结果 9 条待人工复核、0 条历史结转、0 条 Hash 冲突。
- WPS 只读验证 `passed`；WPS 云盘副本逐字节一致。
- 空白回填表 SHA-256
  `6451f986c81c4db1277f795e6a0666c22810728d621524070935b21edc4e7f0c`。
- `action=no_order`；未生成事件、调度、通知或材料性结论。

## v2026.09.24-m3-checkpoint-b-review-packet

### Scope

M2 Checkpoint A 已人工签收后回到 M3 主线，新增版本化、只读、Hash 固定的
Checkpoint B 人工复核包，汇总三份 M3 候选、机器审计、strict PIT 证据和 M2
append-only 收据。本包不签收 Checkpoint B。

### Changes

- 新增 `scripts/build_m3_checkpoint_b_review_packet.py`。
- 新增 `tests/test_m3_checkpoint_b_review_packet.py` 并纳入 Core Research Gate。
- 新增
  [docs/m3-checkpoint-b-review-packet-20260924.md](docs/m3-checkpoint-b-review-packet-20260924.md)。
- 更新当前阶段、执行状态与 M2-M7 人工交接清单。

### Verification

- M3 Checkpoint B 定向回归 `2 passed`。
- 复核包 manifest SHA-256
  `76082bb8b359964445954293495208cacf385a44374d717629a77ca5f6f23de4`。
- 状态保持 `PENDING_HUMAN_REVIEW`、`strict PIT=NOT_PROVEN`、`action=no_order`。

## v2026.09.24-m7-daily-v4-post-checkpoint-a

### Scope

M2 Checkpoint A 收口后继续原总 Goal 的 M7 展示工程，生成新的只读 M7 Daily v4
候选，并把 600519 重建证据连续性和真实 CNINFO 待复核队列接入现有工作台。

### Changes

- 新增 `scripts/build_m7_daily_workbench_post_checkpoint_a.py`。
- M7 展示层增加可选的 M3 reconstructed continuity 和 M5 600519 disclosure
  queue read models，均保持 `action=no_order`。
- M2 展示状态更新为 `DONE / HUMAN_PASS`；v3、canonical 和统一工作台均未覆盖。
- WPS 验证器增加 `-PostCheckpointA` 开关并检查两个新证据层。
- 新增文档
  [docs/m7-daily-workbench-v4-post-checkpoint-a-20260924.md](docs/m7-daily-workbench-v4-post-checkpoint-a-20260924.md)。

### Verification

- M7 Daily Workbench 定向回归 `14 passed`。
- WPS 只读验证 `passed`；WPS 云盘同名候选逐字节一致。
- M7 Daily v4 SHA-256
  `569adf26fece3b45666138c050776b40cb077f0e0b9f498a0dd77445a83c2a59`。
- `action=no_order`；未签发 Checkpoint B-D、组合、生产或 M7 交付验收。

## v2026.09.24-m2-checkpoint-a-human-pass

### Scope

记录用户对 M2 Checkpoint A 的正式人工结论：

```text
M2_CHECKPOINT_A = HUMAN_PASS
```

并新增 sequence=2 的 append-only `HumanMilestoneReviewReceipt`，绑定 sequence=1
历史收据，不覆盖旧结论。同时把两项非阻断方法债写入 backlog。

### Changes

- M2 收口为 `DONE`，总 Goal 仍为 `PARTIAL`。
- 新增
  `scripts/build_m2_checkpoint_a_human_acceptance.py`。
- 新收据目录
  `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/`。
- 新增
  [docs/m2-non-blocking-method-debt-20260924.md](docs/m2-non-blocking-method-debt-20260924.md)。

### Verification

- 定向回归 `7 passed`；`compileall` 与 `git diff --check` 通过。
- 新收据 SHA-256
  `9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20`。
- Checkpoint A 验收包 SHA-256
  `b880b74752362deccd1991d23a43f7347f7e5a8348e0ae6ca0603a5931e8f306`。
- `action=no_order`；没有订单、仓位、生产数据库或 PTA 项目改动。

## v2026.09.24-m3-strict-pit-evidence-intake

### Scope

新增 strict contemporaneous-rule Historical PIT 的可审计证据接收入口。真实候选
证据缺失时保持 `NOT_PROVEN`，不会因以后找到证据而把当前状态写成已通过。

### Changes

- `CONTEMPORANEOUS_RULE` 必须绑定至少一条早于 `registered_at` 的独立证据。
- 新增 `src/value_investment_agent/m3_strict_pit_evidence.py`、
  `scripts/audit_m3_strict_pit_evidence.py` 与对应测试。
- GitHub Core Research Gate 纳入 `test_m3_strict_pit_evidence.py`。

### Verification

- 定向回归 `26 passed`；真实 600519 / 2024-06-21 案例仍为
  `NOT_PROVEN`、`action=no_order`。
- 最新审计收据 SHA-256
  `9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c`。

## v2026.09.24-m3-full-acceptance-recompute

### Scope

重新执行 M3 决策卡、原工作簿候选与历史链叠加候选三个验收器，并内嵌对应定向
回归证据，消除旧收据中的 `PENDING_CI`。

### Result

- M3 决策卡：m3c1-m3c6 `DONE`，定向回归 `35 passed`。
- M3 原工作簿候选：owc1-owc6 `DONE`，定向回归 `7 passed`。
- M3 历史链叠加候选：hoc1-hoc6 `DONE`，定向回归 `11 passed`。
- 三份收据仅保留对应人工复核项，`action=no_order`。
- 收据目录：
  `runtime/m3-decision-acceptance-audit-20260924T062947Z`、
  `runtime/m3-original-workbook-audit-20260924T063010Z`、
  `runtime/m3-history-original-workbook-audit-20260924T063017Z`。

## v2026.09.24-m2-full-acceptance-recompute

### Scope

重新执行 M2 AC1-AC12 验收器，并在隔离 basetemp 中内嵌真实全量离线回归证据。
此前 AC1 与 AC6 因审计器未运行本地全量测试而只能显示 `PARTIAL`。

### Result

- 本地完整回归：`2369 passed、6 skipped、0 failed、18 warnings`。
- AC1-AC7、AC11 `DONE`；AC8-AC10、AC12 保持 `PENDING_HUMAN_REVIEW`。
- 收据 `runtime/m2-acceptance-audit-20260924T062704Z/receipt.json`，
  SHA-256
  `2fb22e04f38c0ef5563429bf289804769c36c21eac394f13d0b38d992b11a878`。
- `action=no_order`；未修改冻结 M2 输入、原工作簿或生产服务。

## v2026.09.24-m3-strict-pit-evidence-search

### Scope

人工审查要求至少一条真实 contemporaneous-rule Historical PIT。检索当前仓库
`runtime/strategy-validation`、docs 与 config 后确认：最早提交为 2026-09-01，
600519 / 2024-06-21 所用规则登记于 2026-09-12，不存在可验证的当时规则登记。

### Result

- `STRICT_CONTEMPORANEOUS_RULE_PIT = NOT_PROVEN`。
- 当前 replay 保持 `RETROSPECTIVE_RESEARCH_EXTENSION`、
  `future_rule_version_used=true`、`WAIT`、`action=no_order`。
- 不伪造历史规则登记，不把追溯扩展写成当时规则。
- 新增 [docs/m3-historical-pit-evidence-20260924.md](docs/m3-historical-pit-evidence-20260924.md)
  固化检索范围、证据与解除方式。

## v2026.09.24-m4-decision-binding-v2-workbooks

### Scope

发布 M4 Decision Binding 修复后的 v2 模拟 Excel 候选，让 WPS 可见成果与当前
领域合同一致。v1 文件保留，不覆盖历史版本。

### Artifacts

- `A股价值投资_M4仓位与股息候选_v2_20260924.xlsx`
  - SHA-256 `2f17b4926d8634fd45c8a57335b99b477aa6c9559616e6bd5053dbb506e9a037`
- `A股价值投资_M4M5联合检查点候选_v2_20260924.xlsx`
  - SHA-256 `470c73209ee87b3855387eb47a890eb0187b3fc83d5cd15cf145d6e2eef9c10a`

### Verification

- 两个候选的 WPS 云盘副本与仓库逐字节一致。
- M4 v2 WPS 只读验证 `passed`；M4/M5 v2 WPS 只读验证 `passed`。
- 全量离线回归在绑定修复版本 `b4e73d1` 上为
  `2369 passed、6 skipped、0 failed、18 warnings`。
- `action=no_order`；未修改 canonical、v1 候选或生产服务。

## v2026.09.24-m4-positive-capacity-decision-binding

### Scope

收紧 M4 `PositionCandidateInput` 对 M3 `InvestmentDecisionReview` 的强绑定。
此前未设置 `decision_binding_required=True` 的 `BUY_REVIEW` / `ADD_REVIEW`
候选仍可依靠手工布尔前置产生新增容量，可能绕过真实 M3 决策制品。

### Changes

- `BUY_REVIEW` 只能绑定 `MANUAL_BUY_REVIEW`，`ADD_REVIEW` 只能绑定
  `MANUAL_ADD_REVIEW`；未绑定正向 intent 直接拒绝。
- 正向 intent 必须携带 `RESEARCH_ATTRACTIVE` 价格状态。
- `decision_status` 校验进入正式 `DECISION_STATUSES` 集合。
- `allows_new_buy_capacity()` 删除未绑定时的无条件放行分支。
- 模拟 M4 guidance fixture 为三条 BUY/ADD 候选补齐显式 binding；新增反例测试。

### Verification

- 定向回归 `51 passed`。
- 仓库内隔离 basetemp 全量离线回归 `2369 passed、6 skipped、0 failed`。
- `action=no_order`；未修改 canonical、冻结研究证据、M1/M2 历史产物或生产服务。

## v2026.09.24-m3-historical-rule-version-consistency

### Scope

收紧 M3 Historical Research Replay 的规则版本边界。此前 `HistoricalRuleBinding`
允许任意登记状态，且 `future_rule_version_used` 可以不与登记时间和 replay 日期
一致，未来调用可能把追溯规则误标为严格同期 PIT。

### Changes

- `HistoricalRuleBinding` 只接受 `RETROSPECTIVE_RESEARCH_EXTENSION` 或
  `CONTEMPORANEOUS_RULE`。
- 追溯规则必须标记 `future_rule_version_used=true`；同期规则不得标记该字段。
- 同期规则的登记日不能晚于 replay 日期；日期统一按 A 股时区 UTC+8 折算。
- 新增正反回归测试，覆盖追溯规则误标、同期规则未来登记和未来规则误标。

### Verification

- 定向回归 `23 passed`；全量离线回归 `2365 passed、6 skipped、0 failed`。
- 真实固定 Moutai 2024-06-21 输入重放成功，仍为 `WAIT`、
  `future_rule_version_used=true`、`action=no_order`。
- `action=no_order`；未修改 canonical、冻结收据或生产服务。

## v2026.09.24-readme-goal-and-production-boundary-alignment

### Scope

同步 README 的当前 Goal、人工待办和生产调度边界。原来的 README 仍把当前活动
目标描述为单一 M2，且未明确计划任务需要生产授权与 PTA 资源保护。

### Verification

- README 当前 Goal 更新为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`，
  状态保持 `PARTIAL`，并链接 M2-M7 人工交接与 M7 使用手册。
- 自动运行章节明确：生产调度、通知和服务器资源需单独授权，M6/M7 运营验收
  尚未开始，注册计划任务不等于运营就绪。
- Core Research Gates run
  [35958629202](https://github.com/MingMingLiu0112/value-investment/actions/runs/35958629202)
  的 `offline-core` 与 `postgres-integration` 均为 `success`。
- `action=no_order`；未修改 canonical、冻结证据、PTA 或生产服务。

## v2026.09.24-current-head-m3-history-hash-fix-and-handoff

### Scope

按当前 HEAD 重新执行 M2/M3/M6 只读验收，修复 M3 历史链审计中的过期 WPS
收据 Hash，并新增 M2-M7 人工复核交接清单。机器门不替代 Checkpoint A-D，
M6 运营验收仍为 `NOT_STARTED`。

### Verification

- M3 决策卡、M3 原工作簿候选、M3 历史链叠加候选的机器验收项均 `DONE`。
- M3 历史链 `hoc5` 从误报 `PARTIAL` 修复为 `DONE`，固定 Hash 与当前
  `passed` 收据一致。
- M2 保持 AC1-AC7/AC11 `DONE`，AC8-AC10/AC12 `PENDING_HUMAN_REVIEW`。
- M6 工程预检 `DONE`，真实恢复、20 连续会话、真实事件和生产授权仍未开始。
- 新增 `docs/m2-m7-human-review-handoff-20260924.md`。
- 所有输出 `action=no_order`；未修改 canonical、冻结证据、PTA 或生产服务。

## v2026.09.24-m2-legacy-coverage-signature-and-m7-runbook

### Scope

修复人工审查纠偏后 M2 coverage signature 扩展与既有冻结收据不兼容的问题。旧的
`m2-live-20260923-v3` 收据只包含六字段 coverage signature，而新合同增加了
trigger metrics、trigger reasons、policy version 和预算前排名，导致
`scripts/audit_m2_acceptance.py` 解码真实收据时误报篡改。本轮按 payload 实际字段
版本选择签名算法，不修改冻结证据；旧格式可重放，新增未签名字段不能绕过校验。
同时新增 M7 Daily v2 用户运行手册，并让 WPS 验证器自动创建收据目录。

### Verification

- M2 opportunity/acceptance 定向回归：25 passed。
- 本地完整离线回归：2361 passed、6 skipped、0 failed、18 warnings。
- 真实 M2 审计器完成：AC1-AC7/AC11 `DONE`，AC8-AC10/AC12
  `PENDING_HUMAN_REVIEW`；收据为
  `runtime/m2-acceptance-audit-20260924T045545Z/receipt.json`，SHA-256
  `327137c49d6c1122e96391cab1ada897cd4ff65c936981c7dab5cc28ea611638`。
- M7 运行手册中的 WPS 复核命令实跑为 `passed`，候选与 canonical Hash 不变。
- 新增用户手册：`docs/m7-assisted-use-runbook-20260924.md`。
- `action=no_order`；未修改冻结 M2 收据、canonical 工作簿或生产服务。
- Core Research Gates run `35957882562`：两个 job 均 `success`。

## v2026.09.24-repeatable-public-workbook-wps-audit

### Scope

把此前一次性执行的公开工作簿 WPS 云盘副本字节核对固化为只读、可重复的 PowerShell
审计脚本，并增加 CI 静态回归。脚本遍历 Git 跟踪的全部 `.xlsx`，逐项计算仓库文件与
WPS 云盘同名副本的 SHA-256，输出 JSON 收据；缺失或 Hash 不一致时失败关闭，不执行
复制、移动或删除。

### Verification

- 审计脚本实跑 `23/23 MATCH`，收据
  `runtime/public-workbook-wps-audit-final-20260924/receipt.json`。
- 新增审计测试与 WPS 文本扫描回归：2 passed。
- 本地完整离线回归 `2359 passed、6 skipped、0 failed、18 warnings`。
- Core Research Gates run `35956322034`：两 job 均 `success`。
- `action=no_order`；未执行生产迁移、计划任务、通知或真实账户导入。

## v2026.09.24-wps-verifier-text-materialization

### Scope

修复 WPS COM 在本机对 `UsedRange.Text` 返回空串造成的验证盲区。M7 Daily
Workbench、90 页 M7 工作台、96 页 M7 v2 工作台和 M3 历史链验证器原先把
`UsedRange.Text` 拼接为文本再扫描禁止决策词，实际扫描为空。本轮改为物化
`UsedRange.Value2`，物化结果为空时失败关闭，并增加 CI 静态回归。

### Verification

- M7 Daily、90 页 M7、96 页 M7 v2、60 页 M3 历史链四组 WPS 只读验证均为
  `passed`，候选与 canonical Hash 前后不变。
- 本地完整离线回归 `2358 passed、6 skipped、0 failed、18 warnings`。
- Core Research Gates run `35954917146`：`success`。
- 公开工作簿 WPS 云盘副本全量复核：23/23 逐字节一致；补齐 3 个遗漏的同名副本。
- `action=no_order`；未执行生产迁移、计划任务、通知或真实账户导入。

## v2026.09.24-m7-daily-workbench-v2-pit-wording

### Scope

M7 Daily Workbench v1 引用的 M3 Historical Research Replay 收据已经记录
`future_rule_version_used=true`，但工作簿仍把该回放称为“真实 PIT / 当时规则”。
本版新增 v2 展示候选，把事实、公告、报价的 point-in-time 性质与 Median-PE
规则的追溯注册身份分开表述，不补造同时期规则，也不改变研究或审批状态。

### Artifacts

- `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx`
- 候选 SHA-256：
  `8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6`
- manifest 由 `scripts/build_m7_daily_workbench.py` 自动生成。
- WPS 只读验证 `passed`，canonical SHA-256 前后不变。
- WPS 验证脚本进一步断言“规则时点 PIT=NOT CLAIMED”与
  `future_rule_version_used=True`，并拒绝误导性旧文案。

### Verification

- M7 定向回归：8 passed。
- 非神华离线回归：2245 passed、6 skipped、0 failed。
- GitHub Core Research Gates run `35953368838`：`success`。
- 校验脚本强化提交后的 Core Research Gates run `35953940241`：`success`。
- `action=no_order`；未执行生产迁移、计划任务、通知或真实账户导入。
- v1 每日工作台候选保留，当前用户验收对象改为 v2。

## v2026.09.24-manual-review-pit-boundary

### Scope

修正 2026-09-24 人工审查纠偏记录中 M3 Historical Research Replay 的表述边界。
该回放的财务事实、公告和报价是 point-in-time；Median-PE 规则本身是 2026 年
追溯注册，收据必须继续显示 `future_rule_version_used=true`。本轮不补造一条
不存在的同时期规则，也不把它升级为严格 contemporaneous-rule PIT。

### Verification

- 不改变任何投资逻辑、Excel 字节、运行收据或测试结果。
- `action=no_order`；生产迁移、计划任务、通知、真实账户导入均未执行。

## v2026.09.24-m7-workbench-v2

### Release Scope

把刚交付的 M4/M5 联合检查点候选作为第七个只读展示层接入 M7 统一工作台，形成
独立的 96 页 v2 展示候选。原 90 页 v1 候选及其构建器、Hash 和复现入口保持不变。
本版本不发布 canonical、不导入真实组合、不重算研究或仓位，也不创建订单。

### New Capability

- 新增 `scripts/build_m7_workbench_v2_candidate.py`：复用 v1 受保护 graft
  实现，把 `M4M5联合_*` 六个页面放在 M5 展示层与 M3 基底之间，固定
  `m7-workbench-candidate-v2` manifest schema。
- 扩展 v1 基础构建器 `build_candidate()`，增加向后兼容的 `manifest_schema`
  参数；未传参时仍生成原 v1 schema。
- 新增 `scripts/verify_m7_workbench_v2_wps.ps1`：验证 96 页、37 个展示页顺序、
  10 个总览导航入口、M4/M5 联合页、公式错误、no_order 边界和 canonical Hash。
- 新增 96 页候选：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx`。

### Verification

- M7 v1/v2 定向回归：6 passed。
- 候选字节数：13,271,164。
- 候选 SHA-256：
  `d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc`。
- WPS 实际只读验证：`passed`；96 页，canonical 打开前后 Hash 不变。
- WPS 云盘同名候选与仓库候选逐字节一致。
- 全量离线回归：2317 passed、6 skipped、0 failed；最终按当前 commit 复算的 M2
  收据见下方 CI 后审计。
- GitHub release commit `0e922ab`；Core Research Gates
  [run 35941189851](https://github.com/MingMingLiu0112/value-investment/actions/runs/35941189851)
  为 `success`。
- CI 后复算 M2：AC1-AC7、AC11 `DONE`；AC8-AC10、AC12
  `PENDING_HUMAN_REVIEW`。最新收据
  `runtime/m2-acceptance-audit-20260924T010927Z/receipt.json`，SHA-256
  `1445ca85c3e2e8e279c2310b244eef18600d7fbee63e878770a764b50ebb704f`。

### Acceptance Boundary

- `M7` 继续为 `PARTIAL`；v2 只是展示入口准备，不替代 Checkpoint A-D。
- `M4/M5` 继续为 `PARTIAL`；联合页面仍是显式模拟，真实 IPS、持仓、事件观察与
  生产通知仍需用户授权。

## v2026.09.24-m4m5-joint-checkpoint

### Release Scope

新增 M4/M5 联合检查点候选。它把已计算的 M4 组合风险、仓位边界和股息收入基线，
与 M5 有界依赖失效结果汇合为一个只读联合状态，用于验证 Checkpoint C 前的跨域
联动契约。本版本不重新计算仓位、不连接生产数据库、不修改 canonical，也不创建订单。

### New Capability

- 新增 `src/value_investment_agent/m4_m5_integration.py`：
  - 把依赖节点失效精确投影到 `portfolio_risk`、`position_guidance`、
    `distribution_history`、`dividend_sustainability`、财务链与决策链；
  - `POSITION_RISK_CHANGED` 暂停组合风险与共同仓位边界；
  - `DIVIDEND_CHANGE` 暂停分配、股息可持续性与共同仓位边界；
  - 无关公司的财务事件不误伤组合产品，关键论点破坏进入 `NEGATIVE`；
  - 输出固定为 `SIMULATED`、`action=no_order`。
- 新增 6 页只读工作簿 `m4_m5_integration_workbook.py`，明确
  `READY / PARTIAL / PAUSED / NEGATIVE` 四种联合状态。
- 新增控制夹具和构建脚本，绑定 M4 风险、M4 仓位/股息与嵌入 M5 事件批的输入
  SHA-256。
- 新增 WPS 只读验证脚本和 4 项回归测试，并纳入 GitHub Core Research Gate。

### Verification

- 定向回归：4 passed。
- M4/M5 联合回归：72 passed。
- WPS 只读收据：`passed`，候选 SHA-256
  `353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`。
- 联合结果：4 个事件、10 个产品 `PAUSED/NEGATIVE`、1 个无关财务事实 `READY`。
- GitHub 发布：release commit `d6a3abd`，已推送 `origin/main`。
- GitHub Core Research Gates：
  [run 35939972803](https://github.com/MingMingLiu0112/value-investment/actions/runs/35939972803)，
  `success`。

### Acceptance Boundary

- `M4/M5` 继续为 `PARTIAL`；本候选不构成 Checkpoint C、真实组合输入、真实事件
  观察或生产通知授权。
- 真实 IPS、持仓、用户理解与交付签收仍需用户确认。

## v2026.09.24-public-workbook-upload-record

### Release Scope

文档与版本记录提交：确认当前 `main` HEAD 已包含全部 18 个公开 Excel 工作簿，并补齐
最终上传清单、SHA-256、WPS 云盘逐字节核对结果和本地不公开边界。本提交不修改任何
Excel 字节、投资逻辑、数据库、服务器服务、调度或订单。

### Upload Record

- 18 个公开工作簿均已由 Git 跟踪并位于 `origin/main`；WPS 云盘同名公开副本与仓库
  文件逐字节一致。
- 最新 canonical 与 `M2候选_20260924` SHA-256 均为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 最新 M7 统一工作台候选 SHA-256 为
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`。
- 不上传本地 WPS 回退件、checks/manifest/receipt、`runtime/`、密钥或 M3 中间替换页。

### Acceptance Boundary

- 状态边界不变：`M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，
  `M6=NOT_STARTED`，`M7=PARTIAL`，全部候选 `action=no_order`。
- 上传记录不是人工验收、估值正确、真实事件验证或实盘准入证明。

## v2026.09.24-m6-operational-control

### Release Scope

新增 M6 的版本化运行控制状态机与本地命令，用于记录
`OFFLINE_ENGINEERING -> STAGING -> SHADOW -> LIMITED_USE` 的逐级授权
推进，并保证任何阶段都可立即进入 `STOPPED`。本版本只读写 `runtime/` 下的
本地状态文件，不连接生产 PostgreSQL、不修改服务器服务/计划任务、不发布
工作簿、不读取真实持仓，也不创建订单。

### New Capability

- 新增 `src/value_investment_agent/m6_operational_control.py`：
  - 初始状态固定为 `OFFLINE_ENGINEERING`，发布与新增复核均 fail-closed；
  - 非停止模式必须逐级推进，并需要非空 authorization id；
  - 紧急停止始终允许且立即阻断发布与新增复核；
  - 从停止状态恢复必须使用新的 authorization id，并先回到离线工程状态；
  - 权限与模式在反序列化时交叉校验，状态文件原子替换写入。
- 新增 `scripts/m6_operational_control.py` 的 `status` / `advance` /
  `stop` 本地命令，所有输出固定 `action=no_order`。
- 新增 5 项状态机回归测试，并纳入 GitHub Core Research Gate 的
  `offline-core` 作业。

### Verification

- 定向回归：`tests/test_m6_operational_control.py` 5 passed。
- 本地 CLI smoke test：`status -> advance STAGING -> stop` 成功，输出
  `publish_allowed=false` 且最终 `mode=STOPPED`。
- 本版本不修改任何 Excel 文件字节；WPS 云盘与仓库中当前受跟踪的 18 个
  xlsx 工作簿继续逐字节一致，canonical SHA-256 仍为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

### Acceptance Boundary

- `M6=NOT_STARTED`；本状态机只是 M6 授权后的运行控制合同，不代表 staging、
  shadow、真实运营、真实 RPO/RTO 或 20 个真实交易会话已经完成。
- 生产模式推进仍需用户逐次提供真实 authorization id；本地测试使用的授权
  标识只用于状态机回归，不具备生产效力。

## v2026.09.24-m6-encrypted-backup-security-contract

### Release Scope

补齐 M6 的离线加密备份边界。新增流式 AES-256-GCM 备份封装、密钥文件分离
校验、配置/发布文件 Hash 清单和同机解密校验命令。本版本只读写本地路径，
不连接生产 PostgreSQL、不触发云盘同步、不修改服务器服务或计划任务。

### New Capability

- 新增 `src/value_investment_agent/backup_security.py`：
  - 使用 `cryptography` 的 AES-256-GCM，按 1 MiB 分块流式写入，避免整包
    读入内存；
  - 包内包含版本化 `backup-manifest.json`，记录源码、配置、发布 Excel 和
    原件 Hash；Header 固定 `manifest_sha256` 与 HMAC key id；
  - 强制密钥文件位于备份源、输出目录和 offsite staging 之外；
  - 解密到空目录后逐文件校验大小与 SHA-256，篡改或错误密钥 fail-closed。
- 新增 `scripts/package_encrypted_backup.py` 的 `package` / `verify` 本地命令。
- 新增 `config/m6-backup-security-v1.json`，声明配置清单、发布清单和
  `authorized_cloud_sync_required`，但策略不含任何密钥或云端凭据。
- 更新 M6 预检，从字符串探测改为解析真实函数与安全策略，并纳入 CI。

### Verification

- 定向回归：`tests/test_backup_security.py` 与 M6 预检共 14 passed。
- 全量离线回归：2306 passed、6 skipped、0 failed。
- 临时目录命令行 smoke test：加密打包与解密校验均成功，`action=no_order`。
- 干净工作树预检：`engineering_status=DONE`，
  `operational_acceptance_status=NOT_STARTED`。
- 收据：`runtime/m6-operational-preflight-20260924T000810Z/receipt.json`，
  SHA-256：
  `9dadc9bdf3b7dcfb319ce35b5d7003827799a32c9dd4fe67fca74fceaba07dc3`。

### Acceptance Boundary

- 工程能力可离线使用，但 `M6` 仍为 `NOT_STARTED`。
- 尚未实施真实云盘同步、真实隔离恢复、真实 RPO/RTO、20 个连续真实交易
  会话或生产授权；这些不能用本地 package/verify 测试替代。

## v2026.09.24-m6-operational-readiness-preflight

### Release Scope

新增 M6 的非生产运营准入预检，不连接生产 PostgreSQL、不修改服务器服务、
调度、通知或 PTA，不读取真实持仓，也不执行任何订单。它把“工程已具备哪些
恢复/资源/隐私保护”和“还需要哪些真实授权与自然时间”分开记录。

### New Capability

- 新增 `src/value_investment_agent/m6_operational_readiness.py`：
  - 校验隔离恢复目标 `127.0.0.1:5433/value_agent_restore`；
  - 检查恢复脚本的 256 MiB / 0.5 CPU 上限和一次性容器清理；
  - 检查备份代码的事务快照、表级规范化 Hash、原件 SHA-256、磁盘预留和
    `--clean --if-exists --no-owner --no-acl`；
  - 扫描公开跟踪文件中的 `.env`、密钥、dump、口令或个人资产特征；
  - 提供真实 session/restore 证据的 fail-closed 计数和 RPO/RTO 边界检查。
- 新增 `scripts/audit_m6_preflight.py` 和
  `config/m6-operational-preflight-v1.json`，本地输出机器可重放收据。
- 新增说明 `docs/m6-operational-preflight-20260924.md`，明确当前缺口和
  生产授权清单。

### Verification

- 定向回归：M6 预检与备份/恢复相关测试 38 passed。
- 全量离线回归：2300 passed、6 skipped、0 failed。
- GitHub Core Research Gates run `35935194665`：`offline-core` 与
  `postgres-integration` 均为 `success`；公开提交为 `d79afe2`。
- 本地审计状态：`engineering_status=PARTIAL`，
  `operational_acceptance_status=NOT_STARTED`，`action=no_order`。
- 当前明确未完成：M1-M5 产品验收未全部完成、独立加密备份未实现、无真实
  恢复演练、20 个真实交易会话为 0、生产迁移/调度/通知未授权。
- 本次未连接生产数据库、未访问服务器项目、未修改 canonical 或 PTA。

### Repository Sync

- 当前 HEAD 已包含本轮新建的全部 M2-M7 Excel 候选；WPS 云盘同名文件与
  仓库文件逐字节一致，工作树没有未提交的 `.xlsx` 修改。
- canonical SHA-256：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- M7 统一工作台候选 SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`。
- 仓库未提交 `.env`、密钥、数据库 dump 或生产运行时数据。

### Acceptance Boundary

- `M6=NOT_STARTED`，本包只完成非生产前置检查，不构成 M6 或 M7 验收。
- 不能以本地收据、合成 fixture 或代码存在替代真实 RPO/RTO、真实事件和
  20 个连续真实交易会话。

## v2026.09.24-m7-reproducible-zip-timestamps

### Release Scope

修复 GitHub Core Research Gate 在 Linux runner 上出现的 M7 构建确定性回归。
第一次 M7 推送 `9e37435` 的内容检查全部通过，但同一构建两次生成的 Excel
在新增工作层的 ZIP 条目时间戳上不同，导致文件级 SHA-256 漂移。修复只固定
`graft` 新增层的 ZIP 时间戳，不修改工作表内容、页序、样式、公式、证据链接、
canonical、WPS 文件或任何投资/交易语义。

### Bug Fix

- `scripts/stage_frontend_package.py` 新增固定 ZIP 时间戳
  `1980-01-01T00:00:00`，仅用于 `graft` 复制的新增前端层，消除跨秒构建漂移。
- 已交付 M7 候选继续使用发布时冻结的 SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`。
- 修复后用当前代码重建只改变 31 个新增层的 ZIP 元数据时间戳；90 个工作表的
  全部解压 XML 部件与已交付候选逐字节相同。

### Verification

- 定向回归：`tests/test_m7_workbench_candidate.py` 与
  `tests/test_stage_frontend_replace_sheet.py` 共 6 passed。
- 间隔 2 秒的两次独立构建：原始 Excel 字节和 manifest SHA-256 完全一致。
- 全量离线回归：2292 passed、6 skipped、0 failed。
- GitHub Core Research Gates run `35933960701`：`offline-core` 与
  `postgres-integration` 均为 `success`；公开提交为 `fa23f05`。

### Acceptance Boundary

- 不改变 `M2=PENDING_HUMAN_REVIEW`、`M3/M4/M5=PARTIAL`、
  `M6=NOT_STARTED`、`M7=PARTIAL`。
- 本修复只解决构建可复现性，不构成 Checkpoint D、M7 交付、估值结论或实盘准入。

## v2026.09.24-m7-workbench-display-candidate

### Release Scope

把已受保护的 M3 历史链叠加候选与六个 M4/M5 只读候选合并为一个 90 页的 M7
统一工作台展示候选。本版本只准备原 Excel 的统一展示入口，不发布 canonical，
不读取真实 IPS/持仓，不创建决策、仓位或订单。

### New Capability

- 新增 `scripts/build_m7_workbench_candidate.py`：绑定基底、canonical 和六个
  M4/M5 候选 SHA-256，先唯一重命名附加工作表，再通过
  `stage_frontend_package.graft` 逐层叠加，并生成版本 manifest。
- 扩展 `stage_frontend_package.rename_workbook_sheets`：仅改写
  `xl/workbook.xml` 的 sheet title，保留其余 ZIP 部件，校验长度和重复名。
- 新增 `00_M7总览`，说明 M2-M7 状态、no_order 边界和 9 个内部入口；该页
  禁止使用订单式正向决策文本。
- 新增 `scripts/verify_m7_workbench_wps.ps1` 和 4 项构建器回归，纳入 GitHub
  Core Research Gate。

### Verification

- 候选字节数 13,262,051，SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`。
- 工作表 90 个；89 个源页面、145 个未替换源 ZIP 部件在最终叠加前保留。
- 定向回归 11 passed；WPS 实际只读打开 90 页，前 31 页顺序、导航目标、
  公式错误和 no_order 文本校验通过，canonical 打开前后 Hash 不变。
- 全量离线回归 2292 passed、6 skipped、0 failed。
- WPS 云盘同名候选与仓库候选逐字节一致。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，`M6=NOT_STARTED`，
  `M7=PARTIAL`，全部动作 `action=no_order`。
- 本候选只证明只读展示叠加可重复，不替代 Checkpoint A-D、真实 IPS/组合授权、
  M6 运营证据或 M7 最终用户签收。

## v2026.09.24-m3-history-original-workbook-overlay

### Release Scope

把五页显式模拟的 M3 论点连续性历史链追加到已受保护的 M3 决策复核候选，形成 60 页
公开叠加候选。本版本不发布 canonical，不读取真实账户、IPS、持仓或真实 Entry，不生成
仓位或订单。

### New Capability

- 新增 `scripts/build_m3_history_original_workbook_candidate.py`：
  绑定 M3 决策复核候选、独立历史链候选和模拟历史输入三个 SHA-256。
- 扩展 `scripts/stage_frontend_package.py` 的 `graft`，附加页保留输入 ZipInfo
  时间戳，保证候选跨机器重建字节稳定。
- 新增 `src/value_investment_agent/m3_history_original_workbook_acceptance_audit.py`
  与 `scripts/audit_m3_history_original_workbook.py`，固定 source、addon、输入、
  candidate、manifest、WPS 收据和 canonical Hash，执行 `hoc1-hoc7` 审计门。
- 新增 `scripts/verify_m3_history_original_workbook_wps.ps1`，实际 WPS 只读打开
  60 页，核对历史页顺序、模拟边界、决策页 fail-closed 字段和打开前后 Hash。
- 新增 4 项回归并纳入 GitHub Core Research Gate。

### Verification

- 新增候选字节数 13,208,437，SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`。
- 55 个源页面、111 个未替换源 ZIP 部件逐字节保留；前 5 页历史链为
  `600887` 显式模拟，`action=no_order`。
- 定向离线回归 11 passed；全量离线回归 2288 passed、6 skipped、0 failed。
- 机器门 `hoc1-hoc6` 全部 `DONE`；`hoc7` 保持 `PENDING_HUMAN_REVIEW`。
- WPS 只读收据 `passed`；WPS 云盘同名候选与仓库候选逐字节一致，canonical 未改变。
- GitHub Core Research Gates 运行 `35931101091` 的 `offline-core` 与
  `postgres-integration` 均为 `success`。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，全部动作 `action=no_order`。
- 本候选只演示模拟理由链与 M3 决策页叠加形态，不替代 Checkpoint B、真实历史链或
  实盘准入。

## v2026.09.24-m3-original-workbook-acceptance-audit

### Release Scope

为上一批 M3 原工作簿决策复核候选新增受保护、可重复执行的验收审计。本版本不发布
canonical，不生成 Entry、Journal、Consistency、组合结果或订单。

### New Capability

- 新增 `src/value_investment_agent/m3_original_workbook_acceptance_audit.py`：
  固定 canonical、候选、manifest、M1 输入、M1 预登记和 WPS 收据 Hash。
- 机器门 `owc1-owc6` 重放三张负向卡，核对 55 页、54 个原页面、113 个未替换
  ZIP 部件、WPS 云盘副本与生产 canonical 边界。
- 新增命令行 `scripts/audit_m3_original_workbook.py`，支持本地回归、CI 状态和
  版本化 receipt/pointer。
- 新增 3 项审计回归并纳入 GitHub Core Research Gate。

### Verification

- M3 原工作簿定向回归：7 passed。
- 机器门 `owc1-owc6` 全部 `DONE`；`owc7` 保持 `PENDING_HUMAN_REVIEW`。
- 候选状态仍为 `candidate_verified_not_published`；全部动作 `action=no_order`。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`。
- 本版本只证明候选机器证据可重复；Checkpoint B 仍需用户在 WPS 中阅读并复述理由与反证。

## v2026.09.24-m3-decision-review-original-workbook-candidate

### Release Scope

把三张真实非个人化 M3 负向决策卡投影进现有 55 页工作簿的派生页
`00_决策复核`，形成受保护候选。本版本不发布 canonical、不覆盖其余 54 页、不创建
Entry、Journal、组合结论或订单。

### New Capability

- 新增 `src/value_investment_agent/m3_decision_review_sheet.py`：
  在单一 `00_决策复核` 页展示三张卡、缺失与阻断、来源 Hash、证据引用和人工复核
  要求；所有卡保持 `requires_human_review=true`、`action=no_order`。
- 扩展 `scripts/stage_frontend_package.py`：
  新增 `replace_sheet`，只替换目标派生工作表 XML 部件，合并样式并内联共享字符串；
  其余工作表和工作簿关系逐字节保留。
- 新增 `scripts/build_m3_original_workbook_candidate.py`：
  绑定 canonical、冻结 M1 输入和 M1 预登记三个 SHA-256，生成候选和 manifest。
- 新增 WPS 只读校验脚本、4 项定向回归，并纳入 GitHub Core Research Gate。

### Verification

- 源工作簿 SHA-256 保持不变：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 候选字节数 13,200,586，SHA-256：
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`。
- 54 个原工作表保留、1 个派生页替换、113 个未替换 ZIP 部件逐字节一致。
- 三张卡全部为负向状态，`positive_review_count=0`；WPS 只读收据 `passed`，
  WPS 云盘同名候选与仓库候选逐字节一致。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，全部动作 `action=no_order`。
- 本版本不证明 Checkpoint B；用户仍需在 WPS 中实际阅读三张卡并复述理由与反证。

## v2026.09.24-m5-disclosure-review-intake

### Release Scope

建立真实 CNINFO 待复核队列的人工材料性回填入口，发布三公司、24 条候选的 4 页
Excel 回填表。本版本不预填任何判定，不执行 M5 事件、依赖失效、通知、数据库变更
或调度，全部动作保持 `action=no_order`。

### New Capability

- 新增 `src/value_investment_agent/m5_disclosure_review.py`：
  绑定 `queue_id`、队列语义 SHA-256 和候选 PDF SHA-256；24 条候选必须覆盖且仅
  覆盖一次；审核早于公告发布时间时失败关闭。
- 新增 `src/value_investment_agent/m5_disclosure_review_workbook.py`，生成
  `00_总览`、`01_人工判定`、`02_判定说明`、`03_边界` 四页回填表；24 条判定和
  说明均从空值开始，不提供默认结论。
- 新增构建、应用和 WPS 只读校验脚本。应用命令只生成 `EventMaterialityReview` 与
  `MaterialityBridgeBatch`，不调用事件账、outbox、通知或数据库。
- 未注册领域和制品保留为 `unmapped_domains` / `unmapped_artifacts`，不静默猜测。

### Verification

- 回填工作簿字节数 13,885，SHA-256
  `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420`。
- 队列语义 SHA-256
  `9ff56ebe8ab2902d4339fda881c0a0d4697a1066014f477053198dd00e4e905d`；
  WPS 云盘同名副本与仓库文件逐字节一致，WPS 只读收据 `passed`。
- 新增定向回归 15 passed；M5 队列、事件、材料性桥和回填联合回归 56 passed；
  `compileall` 与 `git diff --check` 通过。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，全部动作 `action=no_order`。
- 本版本只让 24 条人工材料性判定可执行；结论仍由用户逐条给出，之后才允许显式
  进入 M5 材料性桥。

## v2026.09.24-m5-real-disclosure-review-queue

### Release Scope

建立真实 CNINFO 公告索引到人工材料性复核之间的有界队列，并发布一个真实三公司、
24 条候选的 4 页 Excel 候选。本版本不自动判定材料性，不生成 M5 事件，也不接入
调度、通知或数据库。

### New Capability

- 新增 `src/value_investment_agent/m5_disclosure_queue.py`：
  - 原始索引、公告时间、来源 URL、规则类型、索引 Hash 和候选 PDF SHA-256 全量保留；
  - 未知标题保留为人工候选；
  - 重复 ID、未来时间和窗口外记录失败关闭；
  - 候选 PDF 缺失或下载失败保持 `SOURCE_UNAVAILABLE` 与阻断，不降级为无事件；
  - 单家公司源失败返回显式 `UNKNOWN / INCOMPLETE` 扫描，不阻塞其他公司。
- 新增 4 页候选：`00_总览`、`01_待复核公告`、`02_来源覆盖`、`03_输入与边界`。
- 新增真实运行脚本、WPS 只读校验脚本和 10 项定向回归，并纳入 GitHub Core
  Research Gate。

### Verification

- 真实扫描：3 家公司、41 条公告、24 条待人工复核候选、24 份候选 PDF、
  0 个来源失败。
- runtime queue SHA-256：
  `378f5366f76faaf7d9407b321419a40305baccb6126a67a4302526428a75c6b4`。
- 工作簿 SHA-256：
  `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5`；
  WPS 云盘同名副本逐字节一致，WPS 只读收据 `passed`。
- M5 相关联合回归：58 passed；除 PostgreSQL 集成测试外的全量离线回归：
  2262 passed、2 skipped、18 warnings、0 failed。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，全部 `action=no_order`。
- 本版本只证明真实披露可以被确定性归档和排队；材料性结论仍需用户逐条给出，
  之后才允许进入已有 `M5MaterialityBridge`。

## v2026.09.24-github-upload-reconciliation

### Release Scope

补齐全部 13 个公开 Excel 工作簿的版本清单和 GitHub 上传对账，不修改业务代码、Excel
字节、数据库或任何投资结论。

### Change

- `docs/excel-artifact-version-record-20260924.md` 的“当前公开工作簿清单”补齐
  M3 历史链、M4 仓位与股息、M4 组合风险三个此前漏列的工作簿，并把提交引用统一为
  实际 Git short hash。
- 新增上传对账说明：仓库 13 个工作簿均已跟踪并推送到公开仓库，WPS 云盘同名副本
  逐字节一致。
- 明确不公开上传 `runtime/`、`.pytest-tmp-*`、顶层 `*.manifest.json` 和 WPS 本地
  回退/人工资料。

### Acceptance Boundary

- `M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，全部候选 `action=no_order`。
- 本版本只是版本记录对账，不改变任何 Excel 或投资状态。

## v2026.09.24-m5-materiality-bridge

### Release Scope

把已经存在的人工 `EventMaterialityDecision` 接入 M5 事件账和有界依赖失效，并发布一个
显式模拟的 6 页 Excel 候选。本版本只负责人工结论到事件的精确映射；不建立公告采集、
生产调度、通知投递、数据库变更或任何实盘动作。

### New Capability

- 新增 `src/value_investment_agent/m5_materiality_bridge.py`：
  - `NOT_MATERIAL`、`MATERIAL_SUPPORTING_EVIDENCE`、`MATERIAL_ALREADY_INCORPORATED`
    和 `DUPLICATE_OR_DERIVED` 保持静默，不生成事件或依赖失效；
  - `MATERIAL_REQUIRES_RECALCULATION` 生成高严重度事件，并可按财务事实、估值输入、
    模型有效性、估值结果和决策复核等类型精确失效；只有该结论允许触达模型有效性
    重算路径；
  - `REQUIRES_DECOMPOSITION` 只失效决策复核与当前状态，不直接使模型失效；
    `MATERIAL_RISK_MONITOR` 只进入决策复核；
  - 未注册的领域和制品保留为 `unmapped_domains` / `unmapped_artifacts`，不猜测；
  - 公告发布时间作为 `available_at`，人工复核时间作为 `detected_at`，复核早于
    公告时 fail-closed。
- 扩展 `m5_event_dependencies.py`：显式列出 `DEPENDENCY_KINDS`，direct node 和
  invalidation 支持限定依赖类型，自定义失效策略纳入确定性摘要。
- 扩展 `m5_event_run.py`：`run_event_batch` 接受按源事件 ID 的
  `direct_kinds_by_source_event_id`，逐事件校验后应用。
- 新增 6 页候选：`00_总览`、`01_材料性映射`、`02_事件账`、`03_依赖失效与重算`、
  `04_Outbox`、`05_输入与边界`。
- 新增模拟 fixture、构建脚本、WPS 只读校验脚本和材料性桥接回归，并纳入 GitHub
  Core Research Gate。

### Verification

- M5 材料性桥接相关定向回归：39 passed。
- GitHub Core Research Gates 离线清单：405 passed。
- GitHub Core Research Gates run 37：`offline-core` 与 `postgres-integration`
  均为 `success`。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2252 passed、2 skipped、
  18 warnings、0 failed。
- 模拟候选包含 6 项人工材料性判定、3 项静默、3 个事件、3 条失效记录和 3 条
  outbox 提醒，固定 `action=no_order`；字节数 13,240，SHA-256
  `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df`。
- WPS 只读收据 `runtime/m5-materiality-wps-20260924/receipt.json` 为 `passed`；
  WPS 云盘同名副本与仓库候选逐字节一致。
- `compileall` 和 `git diff --check` 通过。

### Acceptance Boundary

- M2 保持 `PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`，全部动作
  `action=no_order`。
- 该候选证明人工材料性结论可以精确接入 M5 事件管道，不证明真实公告采集、公告级
  材料性判定、生产调度、通知投递、Entry/组合复核或持续市场监控已上线。

## v2026.09.24-m5-event-infrastructure

### Release Scope

建立 M5 事件账、水位/检查点、锁、outbox 与有界依赖失效的纯领域离线合同，
并发布一个显式模拟的 6 页 Excel 候选。本版本不启动生产调度、不投递真实通知，
也不修改 PostgreSQL 或原 55 页生产工作簿。

### New Capability

- 新增 `src/value_investment_agent/m5_event_core.py`：
  - `ChangeEventInput` / `ChangeEvent` / `EventLedger`；
  - 区分发生、披露可用和抓取时间，重复事件幂等，更正显式引用前序事件；
  - 晚到事件保留 point-in-time 顺序，未来事件与观察时间回退失败关闭。
- 新增 `m5_event_watermark.py`、`m5_event_checkpoint.py`：
  - 扫描水位单调前进；单 scope 任务锁带租约、token、续约与释放；
  - 检查点记录运行状态、水位和已处理事件，支持崩溃后幂等续接。
- 新增 `m5_event_outbox.py`：
  - PENDING/SENT/DELIVERED/ACKNOWLEDGED/retryable/terminal 状态；
  - 关键、源健康和普通提醒分账，只做 outbox 状态机，不执行真实投递。
- 新增 `m5_event_dependencies.py`：
  - 按事件类型有界失效事实、估值输入、股息、模型、论点、Entry、组合或价格节点；
  - 价格变化不失效内在估值，超界依赖显式 deferred，不静默扩大重算。
- 新增 `m5_event_run.py`：
  - run-once 编排固定为 取锁 -> 检查点 -> 入账 -> 有界失效 -> outbox -> 提交 -> 释放；
  - 公开入口只接受 `SIMULATED`，`action=no_order`。
- 新增 `m5_event_workbook.py`，生成 6 页候选；新增 fixture、构建脚本、WPS 校验
  脚本和 24 项定向回归，并纳入 GitHub Core Research Gate。

### Verification

- `tests/test_m5_event_infrastructure.py` 与
  `tests/test_m5_event_workbook.py`：24 passed。
- 模拟候选为 6 页、7 个输入、6 个当前有效事件、6 条失效记录、6 条 outbox 提醒，
  固定 `action=no_order`；字节数 14,989，SHA-256
  `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae`。
- WPS 只读打开、页序、公式错误、模拟标签、行数和 `no_order` 检查通过；
  WPS 云盘同名副本与仓库候选逐字节一致。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2244 passed、2 skipped、
  18 warnings、0 failed。
- 未修改原 55 页生产工作簿，未创建常驻服务、生产调度或真实通知目标。

### Acceptance Boundary

- M2 当前为 `PENDING_HUMAN_REVIEW`，M3、M4、M5 均继续保持 `PARTIAL`。
- 该候选只演示事件基础设施合同；真实公告采集、公告级材料性判定、Entry/组合复核、
  生产调度、通知投递和真实故障恢复仍未建设，不得据此宣称持续市场监控已上线。

## v2026.09.24-m4-position-guidance-income

### Release Scope

建立 M4 非个人化分层仓位边界与四口径股息收入投影，并发布一个显式模拟的 5 页
Excel 候选。本版本不读取真实 IPS/持仓，不生成目标仓位、仓位大小或订单。

### New Capability

- 新增 `src/value_investment_agent/position_guidance.py`：
  - 人工确认的 Starter/Normal/Max 上限，禁止使用默认 20%；
  - 候选前置条件、组合共同预算、行业/周期限制和停止加仓/减仓复核条件；
  - 多个候选争用现金时显式标记 `BUDGET_CONFLICT`，不代替人工分配。
- 新增 `src/value_investment_agent/dividend_income_projection.py`：
  - 已到账、已宣告、Forward、Normalized 四种收入基础；
  - 普通/特别分红分开，特别分红不进入 Forward/Normalized；
  - 税费只在批次取得、登记和处置日期完整时计算，未结算保持未知。
- 新增 `src/value_investment_agent/m4_guidance_income_workbook.py`，生成 5 页
  候选；新增 fixture、构建脚本、WPS 校验脚本和 18 项定向回归并纳入 CI。

### Verification

- M4 合同/风险/仓位/股息/工作簿联合定向回归：36 passed。
- 模拟候选为 5 页、4 个仓位候选、4 个股息口径，固定 `action=no_order`；
  字节数 11,504，SHA-256
  `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e`。
- WPS 只读打开、页序、公式错误、模拟标签、行数和 `no_order` 检查通过；
  WPS 云盘同名副本与仓库候选逐字节一致。
- 未修改原 55 页生产工作簿，未读取真实账户、现金、IPS、持仓或交易记录。

### Acceptance Boundary

- M2 当前为 `PENDING_HUMAN_REVIEW`，M3、M4 均继续保持 `PARTIAL`。
- 该候选只是非个人化工程演示；真实组合报告仍需用户确认真实 IPS/持仓后另出
  私有版本，不得据此自动调仓或交易。

## v2026.09.24-m4-portfolio-risk-assessment

### Release Scope

建立 M4 非个人化组合风险与集中度评估，以及一个显式模拟的 4 页 Excel 候选。
本版本不读取真实 IPS/持仓，不计算目标仓位、仓位大小或订单；缺失输入仍然失败关闭。

### New Capability

- 新增 `src/value_investment_agent/portfolio_risk.py`：
  - `SecurityRiskAttributes`、`RiskFinding`、`PortfolioRiskAssessment`；
  - 单股/行业/周期暴露、最低与应急/流动性现金、共同因子和流动性复核；
  - 实际与模拟评估命名空间分离，公开结果拒绝真实账户命名空间。
- 新增 `src/value_investment_agent/m4_portfolio_risk_workbook.py`，生成 4 页候选：
  `00_组合风险`、`01_持仓与集中度`、`02_风险发现`、`03_输入与边界`。
- 新增 `scripts/build_m4_portfolio_risk_candidate.py`、WPS 验证脚本和
  `tests/fixtures/m4_portfolio_risk_demo.json`。
- 新增 `tests/test_portfolio_risk_assessment.py`、
  `tests/test_m4_portfolio_risk_workbook.py` 并纳入 GitHub Core Research Gate。

### Verification

- M4 风险域定向回归：8 passed；M4 风险/合同/工作簿联合回归：18 passed。
- 模拟候选为 4 页、3 个持仓、3 项风险发现，固定 `action=no_order`；
  字节数 10,060，SHA-256
  `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7`。
- WPS 只读打开、页序、公式错误、模拟标签、行数和 `no_order` 检查通过；
  WPS 云盘同名副本与仓库候选逐字节一致。
- 未修改原 55 页生产工作簿，未读取真实账户、现金、IPS、持仓或交易记录。
- Git 提交 `324694744b51a3f0c3f2316e1ce206ac6cad6cb2`；GitHub
  [Core Research Gates run 35913005217](https://github.com/MingMingLiu0112/value-investment/actions/runs/35913005217)
  为 `success`。

### Acceptance Boundary

- M2 当前为 `PENDING_HUMAN_REVIEW`，M3、M4 均继续保持 `PARTIAL`。
- 该候选只是非个人化工程演示；真实组合风险报告仍需用户确认真实 IPS/持仓后另出
  私有版本，不得据此自动调仓或交易。

## v2026.09.24-m3-history-read-model

### Release Scope

建立 M3 论点连续性历史链的公开只读模型和独立 Excel 候选。本版本只展示显式
“模拟”链路的原 Entry、人工决策日志与一致性复核，不写入原 55 页生产工作簿，
不读取真实账户，也不生成订单、目标仓位或真实成交。

### New Capability

- 新增 `src/value_investment_agent/m3_history_read_model.py`：
  - `EntryThesisCard`、`DecisionJournalLine`、`ConsistencyReviewCard`；
  - 将 Entry、Journal、Consistency 按证券组合为 `DecisionHistoryChain`；
  - 每条输入均绑定不可变 SHA-256，公开链路只接受 `simulated` 命名空间。
- 新增 `src/value_investment_agent/m3_history_workbook.py`，生成 5 页独立候选：
  `00_历史链`、`01_原Entry`、`02_决策日志`、`03_一致性复核`、`04_来源哈希`。
- 新增 `scripts/build_m3_history_candidate.py` 和
  `tests/fixtures/m3_history_demo.json`，示例链路显式标记为模拟。
- 新增 `tests/test_m3_history_read_model.py` 并纳入 GitHub Core Research Gate。

### Verification

- M3 历史链定向回归：4 passed。
- M3/M4 相关定向回归：40 passed。
- 示例候选为 5 页、1 条模拟链，固定 `action=no_order`；
  字节数 12,121，SHA-256
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`；
  WPS 只读收据为 `passed`，WPS 云盘副本与仓库候选逐字节一致。
- 拒绝真实账户命名空间、拒绝覆盖已有文件。
- 未修改 WPS 生产工作簿、未读取真实 IPS/持仓或 Entry。

### Acceptance Boundary

- M2、M3、M4 均继续保持 `PARTIAL`。
- 该候选只演示历史链结构，不等于真实 Entry 已确认，也不能替代用户对
  Checkpoint B 的理解复核。

## v2026.09.24-m4-portfolio-input-contracts

### Release Scope

建立 M4 非个人化组合输入合同：IPS、持仓快照与组合输入包。本版本不读取真实账户，
不计算仓位、风险或股息预测，不使用通用百分比，也不生成任何订单。

### New Capability

- 新增 `src/value_investment_agent/portfolio_contracts.py`：
  - `InvestorPolicyStatement` 保存人工确认的 IPS、集中度上限、现金/期限/风险口径；
  - `PortfolioHolding` 保存数量确认状态、公司行为调整状态和证据；
  - `PortfolioSnapshot` 区分实盘/模拟、对账状态、现金和持仓；
  - `PortfolioInputBundle` 联合 IPS/快照并校验账户范围和时点顺序。
- 所有对象固定 `action=no_order` 和 `PRIVATE_USER_CONFIRMED`；缺失字段失败关闭，
 不补零值或默认 20%。
- 新增 `tests/test_portfolio_contracts.py` 并纳入 GitHub Core Research Gate。

### Verification

- M4 输入合同定向回归：7 passed。
- 覆盖缺失关闭、非法金额/百分比、重复持仓、未对账/模拟快照、JSON 往返、
  账户范围不匹配和时点顺序。

### Acceptance Boundary

- M2、M3、M4 均继续保持 `PARTIAL`。
- 未实现 PositionGuidance、PortfolioRiskAssessment、DividendIncomeProjection、
  私有持久化或真实账户导入。
- 本版本没有读取或提交任何真实持仓、现金、IPS 或账户数据。

## v2026.09.24-m3-decision-acceptance-audit

### Release Scope

为 M3 非个人化 Decision Card 增加可重复机器验收入口，同时复核 M2 AC1-AC12。
本版本不生成 Entry、Journal、Consistency、个人组合或订单，不改原 55 页生产工作簿。

### New Capability

- 新增 `src/value_investment_agent/m3_decision_acceptance_audit.py`，固定冻结 M1
  输入、预登记、候选工作簿、manifest、WPS 副本、WPS 只读收据和原生产表 Hash。
- 重放三张真实负向卡并检查确定性、来源 Hash 绑定、`no_order`、无正向状态、
  无禁止的交易/仓位文本，以及原 55 页生产表未改变。
- 新增 `scripts/audit_m3_decision_acceptance.py --run-tests` 和 3 项回归测试，
  并纳入 GitHub Core Research Gate。
- 机器门 `m3c1-m3c6` 为 `DONE`，`m3c7` 明确保持
  `PENDING_HUMAN_REVIEW`；Checkpoint B 仍需用户实际阅读并复述三张卡。

### Verification

- M3 定向回归：29 passed。
- M2 AC1-AC12 全量离线复核：AC1-AC7、AC11 `DONE`；
  AC8、AC9、AC10、AC12 `PENDING_HUMAN_REVIEW`。
- 仓库全量离线回归：2180 passed、6 skipped、18 warnings、0 failed。
- M3 审计收据：`runtime/m3-decision-acceptance-audit-20260923T190024Z/receipt.json`，
  SHA-256 `2bb49e94df6740330d2713dee03eec1c44bb2be753f3afbbd40b1560797c8259`。
- 独立 M3 候选继续为 15,102 bytes，SHA-256
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`；
  原生产工作簿继续为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- GitHub 提交：`41ac62cf77a1e01aaf123c0809ad4baf4bea2a84`；Core Research Gates
  的 `offline-core` 与 `postgres-integration` 均为 `success`。

### Acceptance Boundary

- M2 与 M3 均继续保持 `PARTIAL`；本次没有新增正向投资结论。
- 未写入原工作簿 `00_决策复核`，也未发布任何个人化决策卡。

## v2026.09.24-m3-decision-card-read-model

### Release Scope

建立 M3.2 的公开非个人化 Decision Card 只读模型、冻结 M1 证据应用编排和独立 Excel
候选。本版本不生成个人化 BUY/ADD/HOLD/REDUCE/EXIT，不合成 Entry、Journal 或
Consistency，不修改原 55 页 WPS 生产工作簿。

### New Capability

- 新增 `src/value_investment_agent/decision_read_model.py`：
  - `DecisionCard` 保持 `requires_human_review=true`、`action=no_order`；
  - 系统状态与个人组合缺失、原始 Entry 缺失、人工决策记录缺失分开表达；
  - 保留决策时点、规则版本、Evidence Bundle、artifact refs、来源 SHA-256 与 blockers；
  - 未提交决策意图时不伪造意图，也不生成任何正向复核状态。
- 新增 `src/value_investment_agent/m3_decision_application.py`，消费已封存 M1
  `integrated-runs.json`，逐证券解析 PreDecisionEligibility、计算七个证据段落的
  canonical SHA-256，并以缺失组合前置和 `decision_intent=None` 失败关闭编排。
- 新增 `src/value_investment_agent/m3_decision_card_workbook.py`，生成独立 4 页
  候选：决策卡、缺失与阻断、来源哈希、证据引用；无公式重算，只做展示。
- 新增 `scripts/build_m3_decision_card_candidate.py` 与
  `scripts/verify_m3_decision_card_wps.ps1`，支持无覆盖、哈希固定的候选生成和
  WPS 只读打开/计算/页序/链接校验。
- 新增 13 项回归测试并纳入 GitHub Core Research Gate。

### Real Artifacts

- 输入收据：
  `runtime/m1-post-review-20260923T114228Z/integrated-runs.json`，
  SHA-256 `b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459`。
- 独立候选：
  `A股价值投资_M3决策卡候选_20260924.xlsx`，15,102 bytes，
  SHA-256 `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`。
- WPS 云盘同名副本与仓库候选逐字节一致；WPS 只读验证 `status=passed`，
  4 个工作表、31 个证据链接、0 个公式错误。
- 三张真实卡片均为 `INSUFFICIENT_RESEARCH`、`reason_kind=RESEARCH_INCOMPLETE`、
  `portfolio_status=MISSING`、`entry_status=NOT_REQUIRED`、
  `decision_intent=null`、`action=no_order`。

### Verification

- M3.2 定向回归：13 passed。
- Decision/PreDecision 联合回归：32 passed。
- Core Research Gates 等价离线清单：330 passed。
- 仓库全量离线回归：2177 passed、6 skipped、18 warnings、0 failed。
- WPS 收据：`runtime/m3-decision-card-wps-20260924/receipt.json`。
- `py_compile` 与 `git diff --check` 通过。

### Acceptance Boundary

- M2 继续保持 `PARTIAL`，M3 继续保持 `PARTIAL`。
- 本版本是 M3.2 的独立展示候选，尚未写入原工作簿 `00_决策复核`，不能代表
  Checkpoint B 或 M3 产品验收。
- 原 canonical、M2 候选和 WPS 生产原表保持 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

## v2026.09.24-m3-shared-decision-domain

### Release Scope

建立 M3 的解释性投资决策共享域基础，把研究证据、人工决策、原始入场论点和一致性复核
定义为不可变版本化契约。本版本只完成离线领域工程，不生成任何个人化买入建议，不连接
券商，不改变 Excel 字节。

### New Capability

- 新增 `src/value_investment_agent/investment_decision.py`：
  - `DecisionArtifactReference` 与 `DecisionEvidenceBundle` 保存证据依赖及 SHA-256；
  - `MinimalPortfolioPreconditions` 把最小容量输入与决策复核分开；
  - `InvestmentDecisionReview` 以 `action=no_order`、强制人工复核为固定边界；
  - `EntryThesisSnapshot` 保存确认后的原始论点、情景估值、风险、反证和 breaker；
  - `DecisionJournalEntry` 采用追加式人工确认/拒绝记录；
  - `InvestmentConsistencyReview` 比较当前事实与原始入场论点；
  - `evaluate_investment_decision()` 聚合前置资格、证据、置信度和容量约束。
- 在 `research_artifacts.py` 和 `research_artifact_codecs.py` 注册六种追加式 artifact：
  `decision_evidence_bundle`、`minimal_portfolio_preconditions`、
  `investment_decision_review`、`entry_thesis_snapshot`、
  `decision_journal_entry`、`investment_consistency_review`。
- 新增 13 项定向测试，覆盖拒绝路径、人工边界、Entry/Journal/Consistency 及仓库
  保存-恢复往返，并把新测试纳入 GitHub Core Research Gate。

### Decision Boundary

- 缺 Portfolio 输入时只返回 `WATCH`，不能产生正向 BUY/ADD；
- 正向复核必须同时满足 `ELIGIBLE`、中/高置信度、完整证据和人工确认容量；
- BUY 不能静默转成 ADD；HOLD 必须有原 Entry 和当前理由；
- REDUCE/EXIT 保留显式人工复核；实际/模拟 Entry 必须价格，历史重建必须注明；
- Consistency 优先级为 `BROKEN > NEGATIVE > all-FULFILLED > CONSISTENT`。

### Verification

- 新决策测试：13 passed。
- 决策与 codec 联合回归：17 passed。
- GitHub Core Research Gate 等价离线清单：317 passed。
- 仓库全量离线回归：2164 passed、6 skipped、18 warnings、0 failed。
- `py_compile` 与 `git diff --check` 通过。

### Workbook Version

- 本轮不修改任何 `.xlsx` 字节。仓库 canonical、独立候选和 WPS 生产原表仍为 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- `A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx` 继续作为同内容独立快照。
- M2 保持 `PARTIAL`，M3 本轮仅标记为共享域工程基础，不等同于 M3 产品验收。

## v2026.09.24-m2-acceptance-auditor-ci-fix

### Fix

- 修复 M2 审计器回归测试对 untime/ 本地证据的隐式依赖。该目录被 Git 忽略，
  因此首次版本在 GitHub 干净 checkout 中执行完整 udit() 时会读取不到固定收据。
- 将依赖真实运行产物的完整审计回归替换为三个封闭单元回归：AC1 本地与 CI 同时绿、
  AC12 人工复核边界保留、任一机器项 PARTIAL 时产生 blocker。
- 	ests/test_m2_acceptance_audit.py 当前为 7 passed。本提交不改变任何 Excel
  文件字节或 SHA-256，不连接生产数据库，不生成交易指令。

## v2026.09.24-m2-ac12-acceptance-auditor

### Release Scope

为 M2 的 AC1-AC12 建立可重复、可回放的统一验收入口。审计器只重算已固定 Hash 的
真实 M2 运行、覆盖抽样、研究报告和工作簿发布证据，不重新采集市场，不写 WPS
原工作簿，不连接生产数据库，不生成估值、BUY、ADD、仓位或订单。

### New Capability

- 新增 `config/m2-acceptance-audit-v1.json`，固定 M2 运行收据、manifest、政策、
  AC9 覆盖抽样、AC8 研究报告、工作簿发布收据、两个 PIT 快照、55 个工作表门和最多
  30 个允许跳过测试的边界。
- 新增 `src/value_investment_agent/m2_acceptance_audit.py`，逐项重算 AC1-AC12：
  - AC1 继承稳定性、Git HEAD、本地全量和 GitHub Actions 结果；
  - AC2 官方 5,568 证券与四通道逐证券覆盖；
  - AC3 四通道真实线索、LEAD/PARTIAL 与空 Quality 成因；
  - AC4 版本化 policy、legacy shadow 和缺失指标不填零；
  - AC5 跨通道原因、画像适用和预算外账；
  - AC6 两个真实 PIT 信息边界、冷重放与未来证据拒绝；
  - AC7 当前真实市场 run、报价日期和完整分母；
  - AC8 实质研究/否决报告；
  - AC9 分层误放与漏筛审计；
  - AC10 原 Excel 发布 Hash、回退、WPS 收据和 55 页检查；
  - AC11 no_order、生产/调度边界、资源上限和无 symbol 专属流水线；
  - AC12 保留用户复核与 Checkpoint A 交接边界。
- 新增 `scripts/audit_m2_acceptance.py`，支持 `--run-tests`、`--ci-status`、
  `--wps-workbook` 和 `--json-only`，输出版本化 receipt 与 latest pointer。
- 新增 5 项审计回归测试并纳入 GitHub Core Research Gate。

### Real Artifacts

- M2 运行收据固定为 `runtime/m2-live-20260923-v3/receipt.json`，SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`。
- AC9 覆盖审计固定为
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- AC8 研究报告固定为
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- WPS canonical、仓库 canonical 和新 M2 候选工作簿继续逐字节一致，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 两个 PIT 快照保留在 `runtime/m2-live-20260923-v2/` 与
  `runtime/m2-live-20260923-v2b/`，用于证明两个真实信息边界及 v3 replay。

### Verification

- M2 定向回归：33 passed、0 failed。
- 仓库全量离线回归：2149 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Acceptance Boundary

- AC8、AC9、AC10 和 AC12 的机器证据通过后仍保持 `PENDING_HUMAN_REVIEW`，不能由
  审计器自动批准。
- M2 继续保持 `PARTIAL`，直到用户在实际 WPS 工作簿完成研究报告、分层样本、导航和
  证据链接复核，并完成 Checkpoint A 交接。
- 本版本不连接生产 PostgreSQL、不改服务器 PTA/Web App、不改计划任务，也不生成
  任何交易指令。

## v2026.09.24-m2-ac10-integrated-workbook

### Release Scope

把 M2 AC8 已形成的实质研究/否决报告并入现有 WPS 原工作簿的统一入口，同时保留 M1
Application 与原有 42 个工作表，受保护发布后把仓库 canonical、独立候选与 WPS 云盘生产
原表对齐为同一 SHA-256。本版继续 `action=no_order`，不生成估值、BUY、ADD、仓位、订单
或回测收益。

### New Capability

- `m2_discovery_workbook.py` 新增 `11_研究报告`、`12_研究证据` 两页，并在
  `00_M2总览` 增加内部导航；报告页保留通道结论、正反证、缺口和下一触发点，证据页保留
  来源 URL、原件 SHA-256、报告期、发布时间和抓取时间。
- `build_m2_original_workbook_candidate.py` 支持把固定 AC8 报告批或报告配置并入候选，
  并把报告 Hash 与统计写入 candidate manifest。
- `publish_stage_frontend.ps1` 新增 `-NewFrontendSheetCount`，允许 M1 的 6 页和 M2 的
  13 页使用同一受保护发布路径。
- 新增 `scripts/verify_m2_integrated_workbook_wps.ps1`，只读打开真实 WPS、计算工作表、
  扫描公式错误、核对工作表顺序、检查研究/证据行数与来源链接数。

### Real Artifacts

- 发布前原工作簿：12,210,200 bytes，SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。
- 新候选：`A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx`，
  13,199,222 bytes，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 仓库 canonical 原工作簿、新候选、WPS 云盘发布后原工作簿三者 SHA-256 相同。
- 55 个工作表：13 个 M2、6 个 M1 Application、36 个原工作簿页；42 个原有工作表被
  保留，96 个原始部分未变化。
- 研究报告 22 行，研究证据 245 行，识别 228 个来源链接。研究报告 JSON 的 SHA-256 仍为
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 发布前收据：`runtime/m2-original-candidate-20260924-v4/wps-prepublication.json`；
  发布后收据：`runtime/m2-original-candidate-20260924-v4/wps-published.json`；
  回退原件：`runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/before.xlsx`。

### Verification

- 定向回归：32 passed。
- 仓库全量离线回归：2144 passed、6 skipped、18 warnings、0 failed。
- 发布前和发布后的 WPS 只读校验均为 `status=passed`；实际引擎路径
  `D:\WPS Office\12.1.0.28505\office6` 已核对为 WPS。
- `git diff --check` 通过。

### Acceptance Boundary

- AC8 仍为 `AC8_REVIEW_PENDING`。
- AC10 机器检查为 `MACHINE_CHECKS_PASS`，但 WPS 脚本只验证只读打开、计算、公式错误、
  工作表顺序和链接数量，未做桌面人工逐链接/视觉点击验收，因此 Excel 用户审核仍标
  `AC10_REVIEW_PENDING`。
- M2 保持 `PARTIAL`；本版不单独宣告 AC8、AC10 或 M2 完成。

## v2026.09.24-m2-ac8-research-reports

### Release Scope

为 M2 AC8 建立预注册、证据绑定的实质研究与通道否决报告。工具只消费 AC9
`selected_leads` 已封存样本和固定 SHA-256 的真实 M2 输入，不按报告结果后验选择公司；
本版本继续 `action=no_order`，不生成估值、BUY、ADD、仓位、订单或回测收益。

### New Capability

- 新增 `config/m2-ac8-research-report-v1.json`，固定 AC9 审计、M2 收据、财务点与
  分红输入的路径及 SHA-256，并声明 3 份实质报告、2 个实质通道的最低门。
- 新增 `src/value_investment_agent/m2_research_report.py`：
  - 只读取 AC9 `selected_leads` 中的 `LEAD + DATA_PARTIAL` 样本；
  - 收据、财务点、分红文件 Hash 不匹配即拒绝，报告期晚于注册
    `latest_financial_period` 的点不进入证据；
  - 输出 `PENDING_DEEP_RESEARCH`、`REJECTED_FOR_CHANNEL` 或
    `INSUFFICIENT_EVIDENCE`，每份保留来源 URL、原件 Hash、报告期、正反证据与缺口；
  - `INSUFFICIENT_EVIDENCE` 不计入实质报告数量。
- 新增离线命令 `scripts/build_m2_research_reports.py`，只写新的 runtime 报告和 manifest。
- 新增 7 项确定性、最低门、防篡改、禁止执行键和未来报告期拒绝回归测试，并加入
  GitHub Core Gate。

### Real Evidence

- 报告：`runtime/m2-ac8-research-reports-20260924-v1/report.json`，SHA-256
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 总计 18 份报告；16 份实质报告，覆盖 `dividend_cash_return`、`value`、`cyclical`
  三个通道；3 份 `PENDING_DEEP_RESEARCH`、13 份 `REJECTED_FOR_CHANNEL`、
  2 份 `INSUFFICIENT_EVIDENCE`。
- 代表案例：600011 华能国际保留为股息深研线索；600582 天地科技因经营现金流或
  自由现金流为负被通道否决；603799 华友钴业因扩张资本开支导致自由现金流为负且缺少
  正常化周期证据被否决；000151 中成股份因固定输入缺少核心财务点而诚实记录为证据不足。
- `machine_status=MACHINE_CHECKS_PASS`，`acceptance_status=AC8_REVIEW_PENDING`；
  全部产物不含 BUY/ADD/仓位/订单键。

### Verification

- M2 AC8 与 AC9 定向回归：28 passed。
- 仓库全量离线回归：2143 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`M2 / PARTIAL`。本版提供 AC8 真实研究报告证据，但不单独宣告 M2 完成；原 Excel 统一
发布、W6/W7 联合验收与用户可见审核仍继续。

### Excel

本轮未生成新的工作簿，也未改动 WPS 生产工作簿。仓库内 6 个已公开工作簿仍与 WPS
云盘同名文件逐字节一致，版本清单继续由
[docs/excel-artifact-version-record-20260924.md](docs/excel-artifact-version-record-20260924.md) 记录。

## v2026.09.24-excel-artifact-version-record

### Release Scope

将仓库内 6 个工作簿快照与 WPS 云盘 `价投跟踪` 目录逐字节核对，并补交独立的
工作簿版本清单。该清单列明文件名、字节数、SHA-256、最近提交和 WPS 一致性，
不把 Excel 上传解释为交易就绪。

### Workbooks

- 原工作簿：12,210,200 bytes；SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- M2 原表候选：13,168,877 bytes；SHA-256 `95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`
- M2 机会发现：53,299 bytes；SHA-256 `a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`
- M2 机会发现 v2：1,020,221 bytes；SHA-256 `4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63`
- M1 三公司候选 03:30：17,357 bytes；SHA-256 `0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbbd51c3d34`
- M1 三公司候选 12:20：17,025 bytes；SHA-256 `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`

上述 6 个仓库快照与 WPS 同名文件均字节一致。详细提交锚点见
[docs/excel-artifact-version-record-20260924.md](docs/excel-artifact-version-record-20260924.md)。

### Verification

- `git status`：提交前工作树无未跟踪的公开源码或工作簿变更。
- WPS/仓库工作簿 SHA-256：6/6 一致。
- `action=no_order` 继续保持不变。

### Status

`M2 / PARTIAL`。本次为版本记录和上传确认，不推进 M2 完成验收。

## v2026.09.23-m2-ac9-stratified-coverage-audit

### Release Scope

为 M2 AC9 建立预注册分层覆盖审计：以固定 seed 和 SHA-256 排名规则抽取入选线索、
拒绝、数据缺口、不支持、预算外、未评估、显式排除和 legacy/new 差异样本，并对真实
2026-09-23 收据执行机器勾稽与抽样阅读。本版本继续 `action=no_order`。

### New Capability

- 新增 `config/m2-coverage-sampling-v1.json`，固定收据路径、SHA-256、run id、覆盖与候选签名。
- 新增 `src/value_investment_agent/m2_coverage_sampling.py`：
  - 8 个预注册层，每通道固定抽样 6 条，不按收益或结果后验挑样本；
  - 收据文件 Hash、run id、日期和两个领域签名不匹配即拒绝；
  - 检查每通道 5,568 分母、PASS/候选对账、预算外可追溯、无已核候选、
    PARTIAL 证据语义、证据日期、legacy 记账和 Quality 空池解释；
  - 报告明确 `MACHINE_CHECKS_PASS`，验收仍为 `AC9_REVIEW_PENDING`。
- 新增离线命令 `scripts/audit_m2_coverage_sampling.py`，只写新 runtime 审计报告。
- 新增 6 项防篡改、确定性、覆盖完整性、禁止执行键回归测试，并加入 GitHub Core Gate。

### Real Audit Evidence

- 收据：`runtime/m2-live-20260923-v3/receipt.json`，SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`。
- 审计报告：`runtime/m2-ac9-coverage-audit-20260923-v2/report.json`，SHA-256
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- 所有机器检查通过。Quality 空池被解释为 873/5,568 财务证据覆盖限制；
  2,255 个通过对象因 50 条展示预算保留为 `BUDGET_EXCLUDED`；150 个展示对象均为
  `LEAD` 和 `DATA_PARTIAL`，已核候选为 0。
- 抽检未发现候选被错误升级为估值、BUY 或仓位。Value 文案“多指标便宜度”在下一版
  rule text 中应更准确描述其 PE/PB 与推导 ROE 输入。

### Artifacts

- `docs/m2-ac9-stratified-coverage-audit-20260923.md`。

### Verification

- M2 分层覆盖审计定向回归：6 passed。
- 仓库全量离线回归：2137 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`PARTIAL`。AC9 已有真实分层审计和抽样阅读证据，但不单独宣告 M2 完成；原 Excel 发布、
至少三份新发现研究/否决和 W6/W7 联合验收仍继续。

## v2026.09.23-m2-pit-and-partial-evidence

### Release Scope

加固 M2 W1/W2 共同合同：旧输入冷重放不得重标为当前时间，未来或未知时点的
证据不得进入历史快照，缺少深研证据的便宜筛选线索不得显示为 `COMPLETE`。
本版本继续执行 `action=no_order`，不生成估值、BUY、ADD、仓位或订单。

### New Capability

- `DiscoveryRunReceipt` 新增可选 `quote_date` 字段；旧 v2 收据仍可向后兼容读取。
- 收据构建时拒绝：
  - `quote_date > as_of`；
  - `universe.as_of > receipt.as_of`；
  - 任一 `EvidenceReference.fetched_at > generated_at`。
- 官方 Universe 缺少 `fetched_at` 时直接失败，不再用系统当前日期补时点。
- 财务点仅保留带时区、且 `available_at/fetched_at/created_at <= evaluation_at` 的记录；
  未来或时区未知的点不会进入财务证据。
- Dividend 证据的 `fetched_at` 使用原始分红输入的实际抓取时间，不再统一盖成运行时间。
- 非 Quality 通道候选在缺少 FCF/EV-EBIT、正常化利润、派息可持续性等深研证据时统一为
  `DATA_PARTIAL`；Dividend 最高优先级降为 B，Value/Cyclical 降为 C。
- `scripts/run_m2_opportunity_discovery.py --reuse-inputs`：
  - 必须有既有 `receipt.json` 和全部保留输入，否则失败；
  - 保留原收据的 `generated_at`、`quote_date` 和源 `run_id`；
  - 新运行使用 `m2-replay-*` ID，并在清单中记录 `replay_of_run_id`；
  - 不再把旧输入重标为当前日历日。

### Real Replay Evidence

- 输入：`runtime/m2-live-20260923-v2b/` 的真实 5,568 家保留输入。
- 输出：`runtime/m2-live-20260923-v3/`。
- 原始时钟保持：`generated_at=2026-09-23T15:12:00.735987+00:00`，
  `as_of=2026-09-23`，`quote_date=2026-09-23`。
- `replay_of_run_id=m2-20260923T231200Z`；新 `run_id=m2-replay-20260923T232854Z`。
- 字节收据重放与原始输入冷重放均一致。
- 覆盖签名不变：`4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- 候选签名更新：`f77fd5f0e139cf0ab283e9aee9fdd2f4f66695071c85816f303c9b31715cbe79`。
- 通道可见数仍为 Quality 0、Dividend 50、Value 50、Cyclical 50；已核候选 0。
- 候选数据状态：Quality 无候选；Dividend/Value/Cyclical 全部 `PARTIAL`。

### Artifacts

- 更新 `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`
  - SHA-256：`95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`
  - 仍保留后 42 个原工作簿页，`original_parts_unchanged=96`
  - 已同步到 WPS 云盘独立预览，未替换生产原工作簿

### Verification

- M2、原工作簿候选、Frontend stage 与发布边界定向回归：24 passed。
- 仓库全量离线回归：2131 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`PARTIAL`。本版修复时点重标、未来证据和证据完整度语义，不等于 M2 验收完成；
预注册抽样、至少三份新发现研究报告、真实 WPS 视觉验收和后续 M3-M7 仍继续。

## v2026.09.23-m2-lead-verified-original-candidate

### Release Scope

在保持 `m2-opportunity-discovery-v2` 冷重放语义的前提下，把“便宜筛选产出”与
“已经深研核实的候选”在领域模型中显式分开；同时增加从原工作簿生成受保护
M2 候选工作簿的离线发布入口。本版本继续执行 `action=no_order`，不生成
估值、BUY、ADD、仓位或订单，也不把候选发布为生产工作簿。

### New Capability

- `CandidateReason` 新增 `candidate_class`，只允许 `LEAD` 或
  `VERIFIED_CANDIDATE`；当前所有四通道筛选输出均明确标记为 `LEAD`。
- `DiscoveryRunReceipt.verified_candidate_pool()` 只返回后续深研验证门通过的候选；
  当前真实运行中该池为空，不再用“候选数”暗示研究已经完成。
- 候选签名包含 `candidate_class`，冷重放仍可验证新旧层级字段。
- M2 工作簿新增“研究层级”列，显示“研究线索”或“已核候选”；总览分别展示
  线索数与已核候选数。
- 新增 `scripts/build_m2_original_workbook_candidate.py`：
  - 校验原工作簿预期 SHA-256，源文件变化即拒绝；
  - 只接受 `action=no_order` 的有效 M2 收据；
  - 复用 `stage_frontend_package.graft`，原工作簿页和原始 ZIP 部件保持字节不变；
  - 拒绝覆盖已有输出，并产出 `candidate_verified_not_published` 清单；
  - 不执行对 WPS 云盘原工作簿的原子替换或发布。
- 新增回归测试覆盖源 Hash 变化拒绝、输出已存在拒绝、原页与原公式保留、
  OOXML 关系有效，以及所有屏幕结果是研究线索这一合同。

### Real Run And Candidate Evidence

- 复用 2026-09-23 真实全市场 5,568 家官方证券保留输入生成
  `runtime/m2-live-20260923-v2b/`。
- 展示候选仍为 Quality 0、Dividend 50、Value 50、Cyclical 50；已核候选 0。
- `candidate_signature=a4f555b789c3942c690c1e288e5ce3bfa210544cd9ffcc63803d4c1eeb46f4c7`。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- 原工作簿候选：
  - 源 SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
  - 候选 SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`
  - 53 个工作表，前 11 个为 M2，后 42 个为原工作簿页
  - `original_parts_unchanged=96`，`status=candidate_verified_not_published`
- 候选以独立预览复制到 WPS 云盘，未替换生产原工作簿。

### Artifacts

- 新增 `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`
  - SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`

### Verification

- M2 与原工作簿候选定向回归：19 passed。
- `git diff --check` 通过。

### Status

`PARTIAL`。本版固定了线索/已核候选边界并演示未发布的原工作簿候选阶段，
不等于 M2 验收完成；深研报告、预注册抽样、完整时点重放、用户可见发布验收
与后续 M3-M7 仍按 `docs/current-stage-goal.md` 和 `LONG-TERM-GOAL.md` 继续。

## v2026.09.23-m2-v2-coverage

### Release Scope

将 M2 机会发现协议升级到 `m2-opportunity-discovery-v2`，把候选列表与完整覆盖账分开，
修复未来披露泄漏、源外证券混入、跨通道原因丢失和预算截断分母不可对账问题。
本版本继续执行 `action=no_order`，不生成估值、BUY、ADD、仓位或订单。

### Git Commits

- `0ba4660 Expand active goal from M2 through M7 with stage gates` 后继续本地开发。
- 本条目提交 M2 v2 协议、引擎、运行脚本、回归测试、Excel 快照与版本记录。

### New Capability

- 每个官方证券在每个通道保留 `PASS / REJECTED / DATA_GAP / CONFLICT / UNSUPPORTED / NOT_EVALUATED / BUDGET_EXCLUDED` 覆盖记录。
- `coverage_signature` 覆盖完整分母，`candidate_signature` 只覆盖展示候选；收据冷重放同时校验两者。
- 官方 Universe 外的行情只计入健康异常，不进入候选池、覆盖账或 Legacy shadow。
- 同一证券跨通道进入时保留全部通道原因，不再使用字典覆盖。
- 超出 `max_per_channel` 的通过者记为 `BUDGET_EXCLUDED`，保留原因和分母。
- 复用原始输入时保留各 payload 自己的 `fetched_at`，不再用当前时间重新盖章。
- 分红公告日期晚于运行 `known_at` 的未来披露会在进入证据层前被排除。
- 新增 `10_逐通道覆盖` 工作簿页，展示完整分母、状态、原因、画像和证据日期。

### Real Run Summary

- 输入来源：2026-09-23 真实全市场 5,568 家官方证券快照。
- 行情匹配 5,568 家；缺失 0；源外 0；双源冲突 0。
- 展示候选：Quality 0、Dividend 50、Value 50、Cyclical 50；合并去重 113。
- 覆盖账：Quality 5568（PASS 0 / DATA_GAP 4672 / REJECTED 775 / UNSUPPORTED 121）。
- 覆盖账：Dividend 5568（PASS 50 / BUDGET_EXCLUDED 369 / NOT_EVALUATED 1946）。
- 覆盖账：Value 5568（PASS 50 / BUDGET_EXCLUDED 351 / REJECTED 3581）。
- 覆盖账：Cyclical 5568（PASS 50 / BUDGET_EXCLUDED 1535 / NOT_EVALUATED 3059）。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- `candidate_signature=f7442de45283c4d3a21b17a846bb7b0028c3219b15617af3ed17848245ba4d0a`。
- 收据字节和原始输入冷重放均一致。

### Artifacts

- 新增 `A股价值投资_M2机会发现_v2_20260923.xlsx`
  - SHA-256：`4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63`
- 更新 `A股价值投资_Agent前端智能跟踪模板.xlsx` 至 WPS 2026-09-23 版本
  - SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- 新增 `M1_三公司研究Application候选_20260923_033001.xlsx`
  - SHA-256：`0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbd51c3d34`
- 新增 `M1_三公司研究Application候选_20260923_122010.xlsx`
  - SHA-256：`2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`

### Verification

- M2 定向测试：10 passed。
- 仓库内隔离 basetemp 全量回归：2122 passed、6 skipped。
- `compileall`、`git diff --check` 通过。

### Status

`PARTIAL`。本次修复 M2 覆盖账与时点重放合同，不等于 M2 或 M2-M7 总目标完成；
M2 的实质研究报告、原 Excel 统一发布、用户可见验收和后续 M3-M7 阶段仍按
`docs/current-stage-goal.md` 与 `LONG-TERM-GOAL.md` 继续。

## v2026.09.23-m2-partial

### Release Scope

完成 POST-M1 稳定化后的首个真实全市场 M2 机会发现 run-once，并发布独立候选工作簿快照。
本版本只负责主动发现深研候选，不生成估值、BUY、ADD、仓位或订单，`action=no_order`。

### Git Commits

- `f26f726 M2.0 complete post-M1 stabilization`
- `6658b14 M2.1-M2.6 multi-channel opportunity discovery run-once`
- 本条目提交：新增仓库内 Excel 快照与版本记录。

### New Capability

- 官方证券 Universe 快照与腾讯、新浪行情合并，支持价格冲突检查。
- Quality、Dividend/Cash Return、Value、Cyclical 四个独立筛选通道。
- 每条候选记录通道、进入原因、证据日期、数据状态、画像状态和缺失指标。
- 银行、保险、券商等不支持画像进入 `UNSUPPORTED` 隔离，不进入通用通道。
- Legacy PE/PB screen 仅保留 shadow 对比，不参与 M2 候选排序。
- 原始快照、收据、候选签名和 SHA-256 可重放。
- 生成展示专用 `A股价值投资_M2机会发现_20260923.xlsx`。

### Real Run Summary

- 官方 Universe：5,568 家；行情匹配：5,568 家。
- 价格冲突：0；行业映射：5,568 家。
- 财务证据：873 条；股息证据：3,622 条；不支持金融画像：121 家。
- 通道候选：Quality 0、Dividend 50、Value 50、Cyclical 50。
- 合并去重候选：113 家；Legacy shadow：747 家；重叠：86 家。
- Quality 为空是证据门禁失败关闭结果，未降低门槛强制放行。

### Artifact

- `A股价值投资_M2机会发现_20260923.xlsx`
- SHA-256：`a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`
- 与 WPS 云盘“价投跟踪”目录中的用户可见文件字节一致。

### Verification

- M2 定向测试：6 passed。
- 仓库内隔离 basetemp 全量回归：2118 passed、6 skipped。
- `compileall` 与 `git diff --check` 通过。
- 原始输入和收据重放候选签名一致。

### Status

`PARTIAL`。M2 验收第 1-6、8-10 项已有真实证据；第 7 项“从新发现候选中形成至少 3 份实质研究或否决报告”尚未完成。
