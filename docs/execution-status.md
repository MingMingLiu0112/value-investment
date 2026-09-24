# 当前执行状态

更新：2026-09-24。本文只记录事实，不制定新任务。唯一活动任务见 [current-stage-goal.md](current-stage-goal.md)。

## 2026-09-24 M5 事件与 canonical outbox 提醒绑定

运行状态此前只验证“outbox 中的提醒必须引用已有事件”，没有验证“已有事件必须有
自己的提醒”。删除提醒或把提醒类型改成 `SYSTEM_HEALTH` 后，状态仍可能显示健康。

- 事件到提醒类型的映射移到 outbox 领域，run 协调器与状态恢复共用同一个 canonical
  映射，避免后续重复维护后漂移。
- `M5EventRunState` 现在逐事件要求 canonical alert、规范 dedupe key、一致严重度和
  人工复核标志；缺失或伪造会失败关闭。
- 系统源扫描事件强制 `requires_human_review=true`，不能通过输入关闭源健康人工复核。
- 新增四项反向覆盖；全部 M5 定向回归 `97 passed`，本地全量离线回归
  `2456 passed, 6 skipped, 18 warnings, 0 failed`。`action=no_order`。

## 2026-09-24 M5 本地 StateStore 与 CAS 持久化

上一批 `expected_revision` 只能检查调用方快照；如果状态只留在内存，进程退出或并发
写入仍可能丢失批次结果。本轮在离线 M5 上新增独立本地状态存储层，不改变
`M5=PARTIAL`，也不接入生产调度或通知。

- 新增 `M5EventRunStateStore` 协议、`InMemoryM5EventRunStateStore` 和
  `JsonM5EventRunStateStore`；commit 同时绑定 `expected_revision` 与
  `expected_sha256`，同一 revision 只允许幂等写入同一状态摘要。
- JSON 存储按 state key 分文件，使用同目录临时文件、文件 `fsync`、`os.replace`
  和本地文件锁；损坏 JSON 失败关闭且不会被静默覆盖。
- 新增 `run_event_batch_persisted()`，重新加载当前状态，以 CAS 执行一个批次并提交；
  陈旧调用方快照在执行前失败关闭，竞争写入不会覆盖较新 revision。
- 新增 8 项存储回归，覆盖往返、重放、陈旧 revision、跨实例 CAS、损坏 JSON、
  陈旧 wrapper 快照和第二批次持久化。全部 M5 定向回归 `96 passed`。
- 本地全量离线回归 `2455 passed, 6 skipped, 18 warnings, 0 failed`。
- 该层只提供本地原子替换和进程内多实例 CAS；它不是外部单调/签名状态存储，不承诺
  完整掉电耐久性，也未完成真实通知投递、生产采集或恢复演练。`action=no_order`。

## 2026-09-24 M5 运行状态与批次重放收口

在 M5 离线事件基础设施上完成状态聚合、批次幂等和恢复边界收口。该工作不接生产源、
不发送通知、不创建常驻服务，也不改变 `M5=PARTIAL` 或人工/运营待办。

- 新增 `M5EventRunState`，把事件账、水位、checkpoint、outbox 与 batch record 作为
  单个可版本化状态导出并失败关闭恢复。
- 事件去重键加入 `source_id`；旧事件 ID 兼容只在缺少来源字段且人工复核/生效时间
  保持安全默认值时启用，禁止通过删除字段降级校验。
- run-once 协调器使用稳定 state lock、批次请求 fingerprint、原始
  `run_id/namespace/generated_at` 和 receipt/checkpoint 交叉绑定。
- 新增 `expected_revision` 以防陈旧快照被调用方误提交；完整原子 StateStore/CAS
  仍属后续工程，本批次不宣称具备生产级并发持久化。
- 新批次即使全部拒绝也保留审计 checkpoint；同 batch ID 仅原 run/原输入可重放；
  watermark 前进后仍可重放旧批次，不再错误拒绝或误报 no-op。
- checkpoint、outbox、watermark、event、batch record 和 receipt 的跨账本引用、
  时间、严重度与人工复核一致性均失败关闭。
- 新增 `tests/test_m5_event_run_state_boundaries.py` 13 项边界回归；M5 定向回归
  `88 passed`。
- 本地全量离线回归：`2447 passed, 6 skipped, 18 warnings, 0 failed`。
- 未接生产、未发送通知、未生成仓位或订单；`action=no_order`。

## 2026-09-24 M4 输入完整性与失败关闭收紧

人工审查 M4 非个人化合同时发现，JSON 加载器使用 `bool()` 会把字符串 `"false"`
解析为真值；组合中未进入候选映射的持仓也不会计入行业和周期暴露，可能高估未来
可加仓空间。

- 组合持仓、风险属性和仓位候选的布尔字段改为严格 JSON boolean，字符串假值失败关闭。
- 组合输入递归拒绝嵌套执行字段，避免 `target_weight` 等字段藏在持仓对象中被忽略。
- 对账组合中的每个持仓必须存在证券风险属性；缺失时仓位指引为 `INCOMPLETE`，不输出
  行业/周期可加仓空间。
- 指引日期必须不早于 IPS、持仓快照和 tier policy 日期。
- 新增五项反向回归；M4 合同/风险/仓位/股息/联合定向回归 `59 passed`。
- 未读取真实账户/IPS/持仓，未生成目标仓位或订单；`action=no_order`。

## 2026-09-24 M6 运营控制历史与恢复完整性

M6 预检的状态文件可导出 JSON，但恢复入口原来只校验当前 mode 与 permissions，
没有确认 history 是否连续、最后一步是否就是当前快照，也会把字符串 `"false"` 当成
真值。该缺口可让审计文件展示一个未经真实状态机产生的生产权限状态。

- `ModeChange` 与状态切换增加模式、方向、时区、原因、操作者和授权校验；时间必须
  严格向前，同一模式不得重复记录为切换。
- `from_dict` 要求 schema/action 精确匹配、permissions 必须是布尔值，并重放整条
  历史链验证 `OFFLINE_ENGINEERING -> STAGING -> SHADOW -> LIMITED_USE`、
  紧急停止和重置授权规则。
- 当前快照必须与历史最后一步的 mode、授权、时间、原因和操作者完全一致。
- 新增四项反向回归；`test_m6_operational_control.py` 为 `9 passed`，M6
  control + readiness 联合回归为 `18 passed`。
- 状态仍为 preflight engineering done / operational `NOT_STARTED`；
  未连接生产、未开启 shadow、`action=no_order`。

## 2026-09-24 M5 事件账重放完整性收紧

Checkpoint B 继续等待人工复核，本轮在 M5 离线事件基础设施上补做序列化重放审计。
原实现只在增量追加时依赖内存状态，没有在 `event_ledger_from_payload` 重放时完整
验证更正/替代链路。损坏或人工篡改的事件账可能带有缺失目标、跨来源更正、活动目标
或没有后继的 `SUPERSEDED` 事件。

- `correction_of_event_id` 现在必须指向相同证券且相同 `source_event_id` 的当前有效
  事件；跨来源变化若确需替代，只能使用语义独立的 `supersedes_event_id`。
- 序列化账本校验目标存在、目标先于后继、证券一致、每目标唯一后继，以及
  `SUPERSEDED` 与引用关系互相对应。
- 同一来源事件的历史版本不得保持活动；`ingested_at` 不得回退，
  `last_observed_at` 必须等于最后一条已接受事件的观察时间。
- 增加 checkpoint 与 outbox 的失败关闭恢复入口：检查点尝试不得重叠、序号不得
  回退；提醒的尝试次数、重试时间和投递时间必须与状态自洽。
- 租约要求 owner 与 token 同时匹配，并拒绝 release/renew 时间倒置。
- 新增八项反向/往返回归；定向回归 `32 passed`，全部 M5 定向回归 `70 passed`。
- 不改变事件类型、生产采集、通知投递、M5 人工材料性结论或冻结候选；
  `M5=PARTIAL`、`action=no_order`。

## 2026-09-24 M3 Checkpoint B 只读逐卡复核明细

在不改变三份冻结候选 Hash 的前提下，新增逐卡明细 v2，绑定基础复核包和二〇二六
年九月二十三日冻结的三家公司研究档案：

- 每家公司保留冻结档案中的反证、论点破坏条件、下一次事件和研究缺口。
- 明细仅作人工理解辅助，状态固定 `PENDING_HUMAN_REVIEW`、`action=no_order`。
- v1 因研究缺口 Markdown 渲染缺陷被 v2 替代；历史 v1 保留，不删除、不覆盖。
- 明细 JSON SHA-256
  `0d9f938b9fd2c3d003e8d035cd0912f7187ebed63f5f4e089103994b6d8c7a42`，Markdown
  SHA-256 `fab6040c893ec37752393b624fa07c22e918c08fc53e7e9b96e5f821a1ce9313`。
- 定向回归 `2 passed`；未生成 Entry、Journal、仓位、订单或人工收据。

## 2026-09-24 M3 公开历史链时序完整性续收

Checkpoint B 继续等待人工复核，不生成新候选或人工收据。在上一轮
Journal/Consistency ID 与 Entry 归属检查基础上，补上公开 `DecisionHistoryChain`
的剩余时序合同：

- 日志更正必须严格晚于被更正的前任；同一时间戳不再作为可排序更正接受。
- 任一日志时间不能早于冻结 Entry 的人工确认时间。
- 一致性复核日期不能早于冻结 Entry 的 Entry 日期。

新增四个反向测试，防止“更正与前任同刻”、日志倒置 Entry 和一致性复核穿越历史。
M3 相关定向回归 `86 passed`。本工作不重算 Checkpoint B 三份冻结候选，不改变其 Hash，
`action=no_order`。

## 2026-09-24 M3 决策日志链完整性收紧

在 Checkpoint B 等待人工签收期间，继续 M3 可独立完成的领域合同工作。复核发现
`DecisionJournalEntry` 尚未强制“人工决定”与“复核状态”同向，`DecisionHistoryChain`
也只检查更正前任 ID 是否存在，没有检查重复日志、Entry 归属和更正时间顺序。该缺口
可能让自相矛盾或错误链接的决策记录进入公开历史链。

- `CONFIRM_BUY/ADD/HOLD/REDUCE/EXIT` 现在必须匹配对应
  `MANUAL_BUY_REVIEW/MANUAL_ADD_REVIEW/HOLD/MANUAL_REDUCE_REVIEW/
  MANUAL_EXIT_REVIEW` 状态。
- 只有 BUY/ADD/REDUCE/EXIT 可以携带确认价；REJECT/DEFER/CANCEL/HOLD 不能再附带
  成交价。
- 公开 `DecisionHistoryChain` 拒绝重复 Journal/Consistency ID、日志绑定其他 Entry、
  未知前任和早于前任时间的更正。
- 新增五个反向测试；M3 定向回归 `53 passed`，GitHub Core Research Gate 同清单本地
  运行 `549 passed、4 skipped、0 failed`。
- 不重新生成 Checkpoint B 候选，不改变其冻结 Hash；`action=no_order`。

## 2026-09-24 M2 全量机器验收复算

在包含真实全量本地回归的隔离 basetemp 下重新执行 M2 AC1-AC12 验收器，结果不再
停留在“部分证据来自旧文本”的状态：

- 本地完整离线回归：`2369 passed、6 skipped、0 failed、18 warnings`，
  耗时约 323 秒。
- AC1-AC7、AC11 全部 `DONE`；AC8-AC10、AC12 保持
  `PENDING_HUMAN_REVIEW`，没有用机器结果代替用户复核。
- 收据：
  `runtime/m2-acceptance-audit-20260924T062704Z/receipt.json`
  SHA-256
  `2fb22e04f38c0ef5563429bf289804769c36c21eac394f13d0b38d992b11a878`。
- `action=no_order`；未修改冻结 M2 输入、原工作簿或生产服务。

## 2026-09-24 M3 strict PIT 证据检索结论

对仓库、`runtime/strategy-validation`、docs 与 config 检索后确认：最早 Git 提交
为 2026-09-01，600519 / 2024-06-21 重放所用 Median-PE 规则登记于 2026-09-12。
不存在可验证的当时已注册规则，因此 strict contemporaneous-rule Historical PIT
保持 `NOT_PROVEN`，人工审查验收标准第 11 条仍未满足。当前重放继续按
`RETROSPECTIVE_RESEARCH_EXTENSION`、`future_rule_version_used=true`、
`WAIT`、`action=no_order` 保存，不升级为 strict PIT。详细检索见
[m3-historical-pit-evidence-20260924.md](m3-historical-pit-evidence-20260924.md)。

同日进一步收紧同期规则合同：`CONTEMPORANEOUS_RULE` 现在必须绑定至少一条
早于 `registered_at` 的独立规则证据，并新增 strict-PIT 证据审计入口。对现有
2024-06-21 案例的真实审计仍为 `NOT_PROVEN`，收据
`runtime/m3-strict-pit-evidence-audit-20260924T080000Z/receipt.json`，
SHA-256
`9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c`。
该收据证明缺证据没有被机器状态美化，也未把追溯规则升级为同期规则。

## 2026-09-24 M3 三份机器验收复算

在同一个干净 HEAD 上分别重新执行 M3 决策卡、原工作簿候选、历史链叠加候选的
验收器，并内嵌对应定向回归证据：

- M3 决策卡：m3c1-m3c6 `DONE`，定向回归 `35 passed`；m3c7 人工。
- M3 原工作簿候选：owc1-owc6 `DONE`，定向回归 `7 passed`；owc7 人工。
- M3 历史链叠加候选：hoc1-hoc6 `DONE`，定向回归 `11 passed`；hoc7 人工。
- 三份收据均保持 `PENDING_HUMAN_REVIEW`、`action=no_order`，未生成 Entry、
  Journal、个人组合或订单。
- 收据目录：
  `runtime/m3-decision-acceptance-audit-20260924T062947Z`、
  `runtime/m3-original-workbook-audit-20260924T063010Z`、
  `runtime/m3-history-original-workbook-audit-20260924T063017Z`。

## 2026-09-24 M4 Decision Binding v2 Excel 候选

在 M4 正向容量绑定收紧后，重新生成并发布两个只读模拟候选，使 WPS 中的展示层与
当前领域合同一致。v1 文件保留，未覆盖。

- M4 v2：`A股价值投资_M4仓位与股息候选_v2_20260924.xlsx`
  - SHA-256 `2f17b4926d8634fd45c8a57335b99b477aa6c9559616e6bd5053dbb506e9a037`
  - 5 页、`BUDGET_CONFLICT`、`action=no_order`。
- M4/M5 v2：`A股价值投资_M4M5联合检查点候选_v2_20260924.xlsx`
  - SHA-256 `470c73209ee87b3855387eb47a890eb0187b3fc83d5cd15cf145d6e2eef9c10a`
  - 6 页、联合状态 `NEGATIVE`、`action=no_order`。
- WPS 云盘副本逐字节一致；两个 WPS 只读验证均 `passed`。
- 公开工作簿 WPS 云盘副本全量审计由 23/23 更新为 `25/25 MATCH`。
- 未修改 canonical、v1 候选、M1/M2 冻结证据、生产原表或生产服务。

## 2026-09-24 M4 BUY/ADD 决策绑定缺口收紧

复核 2026-09-24 人工审查手册第 22、23、41 节时发现，`PositionCandidateInput`
虽然已经提供 M3 binding 字段，但 `decision_binding_required=False` 时仍允许
`BUY_REVIEW` / `ADD_REVIEW` 在满足手工布尔前置后产生新增容量。该路径可以由错误
adapter 绕过真实 `InvestmentDecisionReview`，与 Workstream E 冲突。本轮收紧为
fail-closed：

- `BUY_REVIEW` 必须绑定 `MANUAL_BUY_REVIEW`，`ADD_REVIEW` 必须绑定
  `MANUAL_ADD_REVIEW`；未绑定的正向 intent 在领域对象构造阶段直接拒绝。
- 两个正向 intent 的价格状态必须是 `RESEARCH_ATTRACTIVE`；
  `WAITING_FOR_BETTER_PRICE`、`KEY_OBSERVATION`、`NOT_ASSESSABLE` 均不能进入
  M4 容量层。
- `decision_status` 只接受正式 `DECISION_STATUSES`，避免任意字符串绕过
  `POSITIVE_REVIEW_STATUSES`。
- `allows_new_buy_capacity()` 不再因 `decision_binding_required=False` 放行；
  模拟 M4 fixture 的正向候选同步改为显式 M3 binding，HOLD 仍可无绑定展示。
- 新增未绑定 BUY/ADD、状态不匹配、非 `RESEARCH_ATTRACTIVE` 价格三类反例测试。

定向回归 `51 passed`；仓库内隔离 basetemp 全量离线回归
`2369 passed、6 skipped、0 failed、18 warnings`。
`action=no_order`；未修改 canonical、冻结研究证据、M1/M2 历史产物或生产服务。

## 2026-09-24 M3 历史规则版本一致性加固

人工审查手册要求 Historical Research Replay 的规则、事实、报价和估值分别版本化，
且不得把追溯注册规则冒充严格同期 PIT。本轮在展示层已有 v2 纠偏之外，补上领域合同
级约束：

- `HistoricalRuleBinding` 只接受 `RETROSPECTIVE_RESEARCH_EXTENSION` 或
  `CONTEMPORANEOUS_RULE` 两种登记状态。
- 追溯规则必须显式标记 `future_rule_version_used=true`，同期规则不得误标为未来规则。
- 同期规则登记日不得晚于 replay 日期，日期统一按 UTC+8 折算，避免时区边界误判。
- 固定 Moutai 2024-06-21 输入重放仍为 `WAIT`、`future_rule_version_used=true`、
  `action=no_order`，不把该案例升级为 strict contemporaneous-rule PIT。
- 定向回归 `23 passed`；全量离线回归 `2365 passed、6 skipped、0 failed`。

## 2026-09-24 当前 HEAD 跨阶段复核与人工交接

按当前 HEAD 重新计算 M2/M3/M6 只读验收器。M2 仍为 AC1-AC7/AC11 `DONE`，
AC8-AC10/AC12 `PENDING_HUMAN_REVIEW`。M3 决策卡、原工作簿候选、历史链叠加
候选的机器门均 `DONE`，只保留对应人工复核项。M6 工程预检 `DONE`，运营验收仍
`NOT_STARTED`。

- 修复 M3 历史链审计固定 WPS 收据 Hash 过期问题：当前收据语义 `passed` 且绑定
  正确候选，但代码仍固定旧 Hash，导致 `hoc5` 误报 `PARTIAL`。本轮同步为
  `c446268c31cecbaff42c9589beec660bfe89b47883f385beeeb94ed80970d991`。
- 当前机器审计收据：M3 决策卡
  `runtime/m3-decision-acceptance-audit-20260924T050428Z/receipt.json`、
  原工作簿 `runtime/m3-original-workbook-audit-20260924T050431Z/receipt.json`、
  历史链 `runtime/m3-history-original-workbook-audit-20260924T050601Z/receipt.json`。
- M5 复核结果保持 23 条旧判断 carry-forward、1 条新公告待人工、0 Hash 冲突。
- 新增 [m2-m7-human-review-handoff-20260924.md](m2-m7-human-review-handoff-20260924.md)，
  汇总 Checkpoint A/B、私有组合输入、M5 新公告和 M6/M7 授权边界。
- 修正 README 中过时的单一 M2 目标描述，补齐当前 M2-M7 活动 Goal 与人工状态；
  自动运行章节明确生产调度、通知和服务器资源需单独授权，并保护 PTA 资源基线。
- Core Research Gates run
  [35958629202](https://github.com/MingMingLiu0112/value-investment/actions/runs/35958629202)
  的 `offline-core` 与 `postgres-integration` 均为 `success`。
- `action=no_order`；未修改 canonical、冻结研究证据或生产服务。

## 2026-09-24 M2 历史签名兼容与 M7 使用手册

复核发现，2026-09-24 人工审查纠偏扩展了 `ChannelEvaluation` 的 trigger/policy/rank
字段，但 2026-09-23 生成的真实 M2 冻结收据仍使用旧六字段 coverage signature。这使
`scripts/audit_m2_acceptance.py` 在解码真实 `m2-live-20260923-v3/receipt.json` 时误报
“证据被篡改”。本轮不改冻结收据，而是在 `discovery_receipt_from_payload` 中按原始
payload 是否包含扩展字段选择旧/新签名算法；旧格式继续可解码，未纳入旧签名的后补扩展
字段不会被绕过。

- 定向回归 `25 passed`；真实 M2 审计器已能解码固定 v3 收据并继续完成 AC2-AC12 检查。
- 最终审计：AC1-AC7/AC11 `DONE`，AC8-AC10/AC12 `PENDING_HUMAN_REVIEW`，
  `action=no_order`；收据
  `runtime/m2-acceptance-audit-20260924T045545Z/receipt.json` 的 SHA-256 为
  `327137c49d6c1122e96391cab1ada897cd4ff65c936981c7dab5cc28ea611638`。
- 完整离线回归 `2361 passed、6 skipped、0 failed、18 warnings`。
- 新增 `docs/m7-assisted-use-runbook-20260924.md`，记录 M7 Daily v2 查看顺序、
  Hash 核验、WPS 复核、故障回退、私有数据与授权边界。
- `verify_m7_daily_workbench_wps.ps1` 自动创建收据目录；按手册中的命令实跑为
  `passed`，10 个可见页、2 个隐藏页、canonical Hash 均通过。
- `action=no_order`；未修改 canonical、冻结运行收据或生产服务。
- GitHub Core Research Gates run
  [35957882562](https://github.com/MingMingLiu0112/value-investment/actions/runs/35957882562)
  的两个 job 均为 `success`。

## 2026-09-24 可重复执行 WPS 云盘副本审计

新增只读脚本 `scripts/audit_public_workbook_wps_copies.ps1`，对 Git 跟踪的全部公开
工作簿与 WPS 云盘同名副本逐项计算 SHA-256，并输出可复算 JSON 收据。当前实跑结果为
`23/23 MATCH`，缺失或 Hash 不一致会失败关闭；脚本不含 `Copy-Item / Move-Item /
Remove-Item`。新增 `tests/test_public_workbook_wps_audit.py` 进入 Core Research
Gates，防止脚本退化为写入型操作或丢失 Unicode Git 路径兼容。

- 定向测试：2 passed。
- 本地完整离线回归：2359 passed、6 skipped、0 failed、18 warnings。
- Core Research Gates run
  [35956322034](https://github.com/MingMingLiu0112/value-investment/actions/runs/35956322034)：
  `offline-core` 与 `postgres-integration` 均 `success`。
- 收据：`runtime/public-workbook-wps-audit-final-20260924/receipt.json`。
- `action=no_order`；未覆盖任何工作簿，也未执行生产迁移、计划任务、通知或真实账户导入。

## 2026-09-24 人工审查纠偏收口

本节记录按同日人工审查手册完成的安全门、验证门与 M7 Daily Workbench。全部动作
`action=no_order`，未执行生产迁移、计划任务、通知或真实账户导入。

- M3 正向决策门：`PreDecisionEligibility` 保存
  `positive_price_review_eligible`；只有正向价格状态可进入 BUY/ADD 人工复核。
  `NOT_ASSESSABLE / WAITING_FOR_BETTER_PRICE / KEY_OBSERVATION` 不能产生
  `MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW`。BUY/ADD 状态矩阵回归已覆盖。
- M4 容量门：`PositionGuidance` 强绑定 typed M3 Decision Review 与
  `decision_review_id + decision_review_sha256 + decision_status`；只有有效
  `MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW` 允许新增容量，缺绑定失败关闭。
- M2 二阶段验证：18 条预注册 LEAD 完成 resolution，3 条
  `VERIFIED_FOR_DEEP_RESEARCH`、13 条 `REJECTED_AFTER_VERIFICATION`、2 条
  `INSUFFICIENT_EVIDENCE`、0 条 `UNSUPPORTED`。Quality 覆盖 873/5568，
  状态 `COVERAGE_LIMITED`；Value 文案明确仅 PE/PB/隐含 ROE 初筛；预算外对象
  保留 trigger metrics 与原始触发逻辑。
- M3 Historical Research Replay：600519 / 2024-06-21。当时年报、派息公告与
  收盘价严格取当日可知，`future_facts_used=false`；但所用 Median-PE 规则是
  2026-09-12 注册的 `RETROSPECTIVE_RESEARCH_EXTENSION`，因此
  `future_rule_version_used=true`。最终状态 `WAIT`、
  `valuation_approved=false`、`trade_approved=false`。该制品证明事实/报价
  PIT 与 fail-closed 行为，不冒充估值、交易、历史策略收益或严格同时期规则
  PIT。
- M5 旧人工复核复用：24 条当前候选中 23 条按
  `symbol + announcement_id + source PDF SHA-256` 继承，1 条新公告待复核，
  Hash 冲突 0、被取代待处理 0。
- M7 Daily Workbench 候选：
  `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_20260924.xlsx`。
  10 个可见主页面（今日总览、全市场、候选、决策、持仓、股息、事件、研究、
  历史、审计）加 2 个隐藏技术页；90 页 v2 审计工作台继续保留。
- M7 候选 SHA-256
  `0230877890ad8f2e688e1218cd5707bb4c95b33a70a7da26e4c7afa8c3894409`。
  WPS 只读验证 `passed`：12 页、页签显隐、公式错误 0、fail-closed 状态与
  canonical Hash 通过，收据
  `runtime/m7-daily-wps-20260924/receipt.json`。
- M3/M4/M2/M5/M7 定向回归 84 passed；M3 历史读取器恢复兼容
  `m3-investment-decision-v1` 旧快照，且继续接受 v2 新字段。
- 全量离线回归 2356 passed、6 skipped、0 failed、18 warnings；skip 为既有的
  PostgreSQL/外部服务条件项，warning 来自 Backtrader `utcnow()` 弃用，不改变
  投资结论。
- CI 干净 checkout 不携带本地 `runtime/` 预注册制品，因此 M2 的 4 项真实制品
  复算在 CI 显式 skip；本地工作台仍完整执行并保持 `6 passed`，不把本机专属
  runtime 文件提交到公开仓库。
- M2 Checkpoint A 仅 `READY_FOR_HUMAN_RESUBMISSION`；M3 Checkpoint B、
  M4 个性化、M5 持续运营、M6 运营验收与 M7 用户签收均未批准。

## M7 Daily Workbench v2 时点表述纠偏：2026-09-24

在上一版人工审查收口后复核发现，M7 Daily Workbench 虽然引用的
`m3-historical-research-replay` 收据已正确记录
`future_rule_version_used=true`，但工作簿页签仍写成“真实 PIT 历史重放 /
当时规则”，会把追溯注册的 Median-PE 规则误读成同时期规则。

本轮只修正展示层表述，不改重放收据、研究结论、审批状态或 canonical：

- 生成
  `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx`。
- 统一表述为：财务事实、公告和收盘价为 point-in-time；
  Median-PE 规则为 `RETROSPECTIVE_RESEARCH_EXTENSION`，
  `future_rule_version_used=true`；不声称 strict contemporaneous-rule PIT。
- M7 v2 SHA-256：
  `8d0ee32b463a2612374504bec8f9e0a55ec411adc00b40cef356a763afb77bf6`。
- WPS 只读验证 `passed`：10 个可见页、2 个隐藏页、公式错误 0、canonical
  Hash 不变，收据 `runtime/m7-daily-wps-v2-20260924/receipt.json`。
- M7 定向回归 `8 passed`；全量离线回归留待提交后统一复算。
- WPS 校验脚本 `verify_m7_daily_workbench_wps.ps1` 增加历史回放边界断言，并
  改为读取契约单元格 `B11.Text`，避免 WPS COM 对 `UsedRange.Text` 返回空串。
- 提交 `b654897` 后复算：非神华离线回归
  `2245 passed、6 skipped、0 failed、18 warnings`；跳过项为既有
  PostgreSQL/外部服务条件，不接触神华 PDF 审计尾集。
- GitHub Core Research Gates
  [run 35953368838](https://github.com/MingMingLiu0112/value-investment/actions/runs/35953368838)
  为 `success`，`offline-core` 与 `postgres-integration` 均通过。
- 校验脚本提交 `6b4f335` 后，Core Research Gates
  [run 35953940241](https://github.com/MingMingLiu0112/value-investment/actions/runs/35953940241)
  两个 job 均再次为 `success`。

上一版 v1 候选继续保留，作为人工审查前的历史制品；当前用户验收对象使用 v2。

## WPS 验证器文本扫描加固：2026-09-24

实机复核发现 WPS COM 在本机对 `UsedRange.Text` 返回空串，导致三个统一工作台
验证器的禁止决策文案扫描实际成为 no-op。本轮不降低断言，改为从
`UsedRange.Value2` 物化单元格文本，并在物化结果为空时失败关闭：

- M7 Daily Workbench 改为扫描全部 10 个可见主页面；禁止
  `建议买入 / 建议加仓 / 目标仓位 / 下单`。
- 90 页 M7 工作台与 96 页 M7 v2 工作台总览恢复
  `买入 / 加仓 / 减仓 / 目标仓位 / BUY / ADD` 扫描。
- M3 历史链前 5 页恢复 `目标仓位 / 下单 / 自动卖出` 扫描。
- 新增静态回归 `tests/test_wps_verifier_text_scans.py` 并纳入 GitHub Core
  Research Gate，防止以后重新使用不可靠的 `UsedRange.Text`。
- 四个候选均完成实际 WPS 只读重验，工作簿 Hash 与 canonical Hash 前后不变。
- 本地完整离线回归 `2358 passed、6 skipped、0 failed、18 warnings`，包含神华
  PDF 尾集；warning 仍为 Backtrader `utcnow()` 弃用提示。
- 提交 `45219e9`、`3aab561`、`3bc6b20` 的 Core Research Gates 均通过；
  最后一个运行 [35954917146](https://github.com/MingMingLiu0112/value-investment/actions/runs/35954917146)
  的 `offline-core` 与 `postgres-integration` 均为 `success`。
- 公开工作簿 WPS 云盘副本全量复核：23/23 逐字节一致。本轮补上此前缺少云盘
  同名副本的 `M2候选_20260924`、`M7每日工作台候选_20260924` 和
  `M2通道验证人工复核包候选_20260924`，未覆盖任何已有文件。

## M7 统一工作台 v2 候选：2026-09-24

本节记录把 M4/M5 联合检查点候选接入 M7 只读统一入口的展示层准备。`M2` 保持
`PENDING_HUMAN_REVIEW`，`M3/M4/M5/M7` 保持 `PARTIAL`，`M6` 为
`NOT_STARTED`；全部动作 `action=no_order`。

- 新增 `scripts/build_m7_workbench_v2_candidate.py`，复用 v1 受保护 graft；
  新增 `m7-workbench-candidate-v2` manifest schema 和
  `scripts/verify_m7_workbench_v2_wps.ps1`。
- 新候选把 6 页 `M4M5联合_*` 作为第七层放在 M5 展示层与 M3 基底之间，形成
  96 页统一工作台；原 90 页 v1 候选、构建器和 Hash 保持不变。
- 候选文件
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx`，
  字节数 13,271,164，SHA-256
  `d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc`。
- WPS 只读验证为 `passed`；96 页、37 个展示页顺序、10 个导航入口和 canonical
  Hash 均通过。WPS 云盘同名副本与仓库候选逐字节一致。
- M7 v1/v2 定向回归 6 passed。
- 全量离线回归：2317 passed、6 skipped、0 failed；M2 机器门仍只等当前提交的
  CI 与用户 Checkpoint A，不因离线通过改变人工验收边界。
- GitHub Core Research Gates run `35941189851` 为 `success`；按该 commit 复算后，
  M2 机器门 AC1-AC7、AC11 为 `DONE`，AC8-AC10、AC12 为
  `PENDING_HUMAN_REVIEW`。最新 M2 收据
  `runtime/m2-acceptance-audit-20260924T010927Z/receipt.json`。
- 本候选不替代 Checkpoint C/D、真实组合、真实事件观察或 M6 运营验收。

## M4/M5 联合检查点候选：2026-09-24

本节记录 M4 组合域与 M5 事件失效的只读联合候选。`M2` 保持
`PENDING_HUMAN_REVIEW`，`M3/M4/M5` 保持 `PARTIAL`，全部动作
`action=no_order`。

- 新增 `src/value_investment_agent/m4_m5_integration.py`：把 M5 依赖失效精确
  投影到组合风险、共同仓位边界、分配/股息和财务/决策链。
- 模拟结果：仓位风险变化暂停组合风险与共同仓位边界；分红变化暂停分配、股息
  可持续性与共同仓位边界；无关公司财报不误伤组合产品；论点破坏进入 `NEGATIVE`。
- 新增 6 页只读工作簿
  `A股价值投资_M4M5联合检查点候选_20260924.xlsx`，SHA-256
  `353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`。
- WPS 只读收据 `runtime/m4m5-joint-wps-20260924/wps-verification.json` 为
  `passed`。
- 定向回归 4 passed；M4/M5 联合回归 72 passed，并已加入 GitHub Core Research
  Gate。
- 本候选不构成 Checkpoint C、真实事件观察或实盘准入；真实组合与生产通知仍待
  用户授权。

## M6 运营准入预检与运行控制：2026-09-24

本节记录 M6 的非生产前置审计。`M6` 保持 `NOT_STARTED`，所有动作
`action=no_order`。

- 新增 `src/value_investment_agent/m6_operational_readiness.py`、
  `scripts/audit_m6_preflight.py` 和
  `config/m6-operational-preflight-v1.json`。
- 新增 `src/value_investment_agent/backup_security.py`、
  `scripts/package_encrypted_backup.py` 和
  `config/m6-backup-security-v1.json`：离线 AES-256-GCM 分块封装、密钥
  分离、配置/发布 Hash 清单及 package/verify 命令。
- 工程检查确认隔离恢复目标、事务快照、表级 Hash、原件 SHA-256、磁盘预留、
  256 MiB / 0.5 CPU 演练上限和公开仓库敏感文件扫描均已实现。
- 干净工作树审计收据：
  `runtime/m6-operational-preflight-20260924T000810Z/receipt.json`，
  SHA-256
  `9dadc9bdf3b7dcfb319ce35b5d7003827799a32c9dd4fe67fca74fceaba07dc3`。
- 全量离线回归：2306 passed、6 skipped、0 failed。
- 当前状态：`engineering_status=DONE`，
  `operational_acceptance_status=NOT_STARTED`。
- 待完成：实际云端同步部署与密钥保管授权、真实隔离恢复与 RPO/RTO、20 个
  连续真实交易会话、至少一个真实财务或资本事件、生产迁移/调度/通知授权。
- 本预检未连接生产 PostgreSQL、未修改服务器项目或 PTA、未读取真实持仓，
  也不能把本地测试或 fixture 当作 M6 运营验收。
- 新增 `src/value_investment_agent/m6_operational_control.py` 和
  `scripts/m6_operational_control.py`：版本化
  `OFFLINE_ENGINEERING -> STAGING -> SHADOW -> LIMITED_USE` 授权推进、
  任意阶段紧急停止、从停止状态以新授权先回到离线工程。状态文件位于
  `runtime/`，不会进入公开仓库。
- 定向回归 `tests/test_m6_operational_control.py` 5 passed，并已加入
  GitHub Core Research Gate 的 `offline-core` 作业。

## M2 机器验收最新收据：2026-09-24

完整离线回归后，M2 AC1-AC7、AC11 机器门均为 `DONE`；AC8-AC10、AC12 保留
用户复核。当前 M2 状态仍为 `PENDING_HUMAN_REVIEW`，`action=no_order`。

- 收据：`runtime/m2-acceptance-audit-20260923T234143Z/receipt.json`
- SHA-256：`4d8f20a3c68f5f5424e667bbbb170183e1d56bf7da6cf5c84e77ffb428229f60`
- 用户复核范围：WPS 原工作簿的候选池、逐通道覆盖、AC8 研究报告/反证、
  AC9 分层抽样、证据链接和导航。
- 用户完成 Checkpoint A 评估前，M2 不标 DONE，也不发布个人化正向结论。

## M7 统一工作台展示候选：2026-09-24

本节记录在人工 Checkpoint 与真实 M6 数据尚未满足时，按总目标允许提前完成的
M7 只读展示层工程。M2 保持 `PENDING_HUMAN_REVIEW`，M3、M4、M5 保持
`PARTIAL`，M6 为 `NOT_STARTED`；全部动作 `action=no_order`。

- 新增 `scripts/build_m7_workbench_candidate.py`：绑定 M3 基底、canonical 和
  六个 M4/M5 候选的 SHA-256，先显式重命名附加工作表，再用 `graft` 逐层叠加；
  任何输入变化或重复页名均失败关闭。
- 扩展 `stage_frontend_package.py` 的 `rename_workbook_sheets`：只修改
  `xl/workbook.xml` 的标题，其余 ZIP 部件逐字节保留，并校验 Excel 标题长度和
  重复名。
- 新增 90 页候选
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx`：
  `00_M7总览` + 29 个重命名 M4/M5 页 + 60 页 M3 历史链叠加基底。
- 候选 SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`；
  字节数 13,262,051；89 个源页面和 145 个源 ZIP 部件在最后一层前保持不变。
- 新增 WPS 只读验证脚本和 4 项构建器回归并纳入 GitHub Core Research Gate。
  定向回归 11 passed；全量离线回归 2292 passed、6 skipped、0 failed；WPS 只读收据
  `runtime/m7-workbench-wps-20260924/wps-verification.json` 为 `passed`。
- WPS 云盘同名候选与仓库候选逐字节一致，canonical 未被覆盖。
- GitHub Core Research Gates 首次 M7 推送 `9e37435` 的 `offline-core` 因 Linux
  runner 上新增层 ZipInfo 时间戳导致确定性回归失败；`fa23f05` 将 `graft`
  新增层时间戳固定为 `1980-01-01T00:00:00`，随后 run `35933960701` 的
  `offline-core` 与 `postgres-integration` 均为 `success`。修复只改 ZIP 元数据，
  90 页工作表内容和已发布候选 SHA-256 未改变。
- 本候选不证明 Checkpoint D、M7 交付或实盘准入；真实 M7 仍需 M2/M3 用户复核、
  真实 IPS/组合授权、M5/M6 生产观察和 Checkpoint D。

## M3 论点连续性历史链叠加候选：2026-09-24

本节记录把五页显式模拟历史链追加到已受保护的 M3 决策复核候选。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `scripts/build_m3_history_original_workbook_candidate.py`，绑定 M3 决策复核
  候选、独立历史链候选和 `tests/fixtures/m3_history_demo.json` 三个 SHA-256。
- 扩展 `stage_frontend_package.graft`，附加页复用输入 ZipInfo 时间戳，使公开候选
  跨机器重建字节稳定，不再随本地构建时间变化。
- 新增 60 页候选 `A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`：
  前 5 页为历史链，后 55 页完整保留 M3 决策复核候选；55 个源页面和 111 个源 ZIP
  部件保持不变。
- 新增 WPS 只读验证、7 项审计门 `hoc1-hoc7` 和 4 项回归；`hoc1-hoc6` 机器验证
  `DONE`，`hoc7` 保持 `PENDING_HUMAN_REVIEW`。
- 候选 SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`；
  WPS 只读收据 `runtime/m3-history-overlay-wps-20260924/wps-verification.json`
  为 `passed`，WPS 云盘副本与仓库候选逐字节一致，canonical 未被覆盖。
- GitHub Core Research Gates 运行 `35931101091` 的两个 job 均为 `success`；
  公开提交为 `d614b5b`。
- 示例链仅使用 `600887` 的显式模拟 Entry、Journal 与 Consistency；不读取真实账户，
  不构成 Checkpoint B、投资结论或实盘准入。

## M5 真实披露待复核队列：2026-09-24

本节记录真实 CNINFO 公告索引到人工材料性复核之间的离线队列。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m5_disclosure_queue.py` 与 4 页候选工作簿：标题规则只形成候选，未知标题
  保留，未来/窗口外/重复记录失败关闭，候选 PDF 缺失保持 `SOURCE_UNAVAILABLE`。
- 真实扫描三家 M1 公司，覆盖 2026-08-27 至 2026-09-24：41 条公告、24 条待人工
  复核候选、24 份候选 PDF、0 个来源失败、3/3 覆盖完整。
- runtime queue SHA-256
  `378f5366f76faaf7d9407b321419a40305baccb6126a67a4302526428a75c6b4`；
  工作簿 SHA-256
  `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5`。
- WPS 云盘同名副本与仓库工作簿逐字节一致；WPS 只读收据为 `passed`。
- 新增 10 项定向回归并纳入 CI；M5 联合回归 58 passed；除 PostgreSQL 集成外全量
  离线回归 2262 passed、2 skipped、0 failed。
- 未执行自动材料性判定、事件入账、依赖失效、生产调度、通知或数据库变更；下一步
  由用户逐条给出 `EventMaterialityDecision` 后进入已有 M5 材料性桥。

## M5 真实披露人工复核回填：2026-09-24

本节记录从真实披露队列到人工 `EventMaterialityReview` 的回填入口。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m5_disclosure_review.py` 与 4 页回填工作簿：24 条候选必须覆盖且仅覆盖一次，
  判定和说明从空值开始，缺件、重复、未来审核时间均失败关闭。
- 回填表绑定 `queue_id`、队列语义 SHA-256 和候选 PDF SHA-256；候选 PDF 缺失时对应
  扫描保持不完整，不降级放行。
- 应用命令只输出 `EventMaterialityReview` 与 `MaterialityBridgeBatch`，不执行 M5
  事件账、依赖失效、outbox、通知、数据库变更、调度或订单。
- 工作簿字节数 13,885，SHA-256
  `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420`；
  队列语义 SHA-256
  `9ff56ebe8ab2902d4339fda881c0a0d4697a1066014f477053198dd00e4e905d`。
- WPS 只读收据
  `runtime/m5-disclosure-review-intake-20260924/wps-verification.json` 为
  `passed`；WPS 云盘同名副本与仓库工作簿逐字节一致。
- 新增定向回归 15 passed；M5 联合回归 56 passed。24 条材料性结论仍待用户逐条填写，
  之后才允许显式调用材料性桥。

## M3 决策复核原工作簿候选：2026-09-24

本节记录把三张真实 M3 负向决策卡接入现有 55 页工作簿派生页 `00_决策复核` 的
候选工程。M2 保持 `PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作
`action=no_order`。

- 新增 `m3_decision_review_sheet.py`：三张卡、缺失与阻断、来源 Hash、证据引用
  和人工复核要求集中投影到一个派生页，不新增个人化结论。
- 扩展 `stage_frontend_package.py` 的 `replace_sheet`：只替换 `00_决策复核`
  XML 部件，其余 54 个页面和 113 个未替换 ZIP 部件逐字节保留。
- 新增 `scripts/build_m3_original_workbook_candidate.py`，绑定 canonical、冻结
  M1 输入与 M1 预登记 Hash；候选不自动发布。
- 候选文件 `A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx`，
  字节数 13,200,586，SHA-256
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`。
- 实际 WPS 只读验证 `passed`：55 页、决策页可见、公式错误 0、禁止信号扫描通过、
  打开前后 Hash 不变；WPS 云盘同名候选与仓库候选逐字节一致。
- 新增 4 项定向回归并纳入 CI；M3 决策与发布层联合回归 18 passed。
- 本候选不证明 Checkpoint B；用户仍需在 WPS 中阅读三张卡并复述理由与反证。

## M3 原工作簿候选验收审计：2026-09-24

本节记录把上一批 M3 原工作簿候选纳入受保护、可重复执行的机器审计。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；全部动作 `action=no_order`。

- 新增 `m3_original_workbook_acceptance_audit.py`：固定 canonical、候选、
  manifest、M1 输入、M1 预登记与 WPS 只读收据 Hash。
- 机器门 `owc1-owc6` 覆盖候选身份、三张负向卡重放、55 页/54 原页面/113 未替换
  ZIP 部件、决策页 fail-closed、WPS 云盘副本和生产 canonical 边界。
- 新增命令行 `scripts/audit_m3_original_workbook.py` 与 3 项审计回归，纳入
  GitHub Core Research Gate；M3 原工作簿定向回归 7 passed。
- 候选保持 `candidate_verified_not_published`；`owc7` 为
  `PENDING_HUMAN_REVIEW`，Checkpoint B 仍必须由用户完成。
- 最新收据：`runtime/m3-original-workbook-audit-20260923T223129Z/receipt.json`，
  SHA-256
  `2242450c9f5ee76ce7dc9b4c9bc231448ea55d07d7efea06e99ab5a95ceae0c9`。
- 对应提交 `d6e4179488c11d4833f27fe2f0edde37f4651a46`；GitHub Core Research
  Gates run 35928696898 两个作业均为 `success`。

## M5 人工材料性判定接入：2026-09-24

本节记录把已有人工 `EventMaterialityDecision` 接入 M5 事件管道的离线工程。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作 `action=no_order`。

- 新增 `m5_materiality_bridge.py`：静默判定不产生事件；需重算判定生成高严重度事件
  并按事实、估值输入、模型有效性、估值结果和决策复核精确失效；需拆分只失效决策
  复核与当前状态，风险监控只进入决策复核。
- 未注册领域和制品保留为 `unmapped_domains` / `unmapped_artifacts`，不猜测；
  公告发布时间与人工复核时间分离，复核早于公告失败关闭。
- 扩展依赖失效和 run-once 编排，支持按源事件 ID 应用自定义直接依赖类型，并把策略
  纳入确定性摘要。
- 独立候选 6 页、6 项人工材料性判定、3 项静默、3 个事件、3 条失效记录和 3 条
  outbox 提醒，固定 `action=no_order`；字节数 13,240，SHA-256
  `e976e330ae517f06ddd341220ce71fb9b6c0753ff4c7f421ef39baed5e9ce1df`。
- 材料性桥接定向回归 39 passed；CI 离线清单 405 passed；除 PostgreSQL 集成外的
  全量离线回归 2252 passed、2 skipped、0 failed。
- GitHub Core Research Gates run 37：`offline-core` 与 `postgres-integration`
  均为 `success`。
- WPS 只读收据 `runtime/m5-materiality-wps-20260924/receipt.json` 为 `passed`；
  WPS 云盘同名副本与仓库候选逐字节一致。
- 真实公告采集、生产调度、通知投递、数据库变更、Entry/组合复核和故障恢复尚未建设；
  本批不证明 M5 生产验收。

## M5 事件基础设施离线合同：2026-09-24

本节记录 M5 第一批纯领域与 run-once 离线工程。M2 保持
`PENDING_HUMAN_REVIEW`，M3、M4、M5 保持 `PARTIAL`；所有动作
`action=no_order`，未创建生产调度、通知投递、常驻服务或数据库改动。

- 新增 `m5_event_core.py`：区分 `detected_at`、`effective_at`、`available_at`，
  重复事件幂等，更正/取代显式引用前序事件，晚到事件保留 PIT 顺序，
  未来事件与观察时间回退失败关闭。
- 新增 `m5_event_watermark.py`、`m5_event_checkpoint.py`：扫描水位单调前进；
  单 scope 任务锁带租约、token、续约与释放；检查点支持崩溃后幂等续接。
- 新增 `m5_event_outbox.py`：PENDING/SENT/DELIVERED/ACKNOWLEDGED/retryable/
  terminal 状态机，关键提醒去重，实际投递不在此层执行。
- 新增 `m5_event_dependencies.py`：按事件类型有界失效依赖；价格事件只影响价格桥接
  与当前状态，不把内在价值标记为需要重算。
- 新增 `m5_event_run.py`：run-once 编排固定为 取锁 -> 检查点 -> 入账 ->
  有界失效 -> outbox -> 提交 -> 释放；公开入口只接受 `SIMULATED`。
- 独立候选 6 页、7 个输入、6 个当前有效事件、6 条失效记录、6 条 outbox 提醒，
  固定 `action=no_order`；字节数 14,989，SHA-256
  `2b86953f793df46e199c40c614f3291e19b249cc0e53e2a670b0000506403dae`。
- M5 定向回归 24 passed；WPS 只读收据为 `passed`，WPS 云盘同名副本与仓库候选
  逐字节一致。
- 本仓库除 PostgreSQL 集成测试外的全量离线回归：2244 passed、2 skipped、
  18 warnings、0 failed。
- 真实公告采集、材料性判定、生产调度、通知目标和故障恢复尚未建设；本批不证明
  M5 产品验收。

## M4 分层仓位与股息收入投影：2026-09-24

本节记录 M4 的第二批非个人化领域工程与模拟 Excel 候选。M2 仍为
`PENDING_HUMAN_REVIEW`，M3、M4 仍为 `PARTIAL`；所有动作保持 `no_order`。

- 新增 `position_guidance.py`：人工确认的 Starter/Normal/Max 上限、共同预算、
  行业/周期限制、停止加仓和减仓复核条件；不输出目标仓位、仓位大小或订单。
- 新增 `dividend_income_projection.py`：已到账、已宣告、Forward、Normalized
  四种口径，普通/特别分红分开，未结算税费保持未知，特别分红不自动年化。
- 新增 `m4_guidance_income_workbook.py`、模拟 fixture、构建脚本与 WPS 校验脚本，
  并纳入 GitHub Core Research Gate。
- 独立候选 5 页、4 个仓位候选、4 个股息口径，固定 `action=no_order`；字节数
  11,504，SHA-256
  `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e`。
- M4 合同/风险/仓位/股息/工作簿联合定向回归 36 passed；WPS 只读收据为
  `passed`，WPS 云盘同名副本与仓库候选逐字节一致。
- 真实 IPS/持仓未提供；未修改原 55 页生产工作簿，也未生成个人化建议。

## M4 组合风险与集中度评估：2026-09-24

本节记录 M4 非个人化风险域与模拟 Excel 候选。M2 为 `PENDING_HUMAN_REVIEW`，
M3、M4 仍为 `PARTIAL`；本批只使用显式模拟组合，不读取真实账户、IPS 或持仓。

- 新增 `portfolio_risk.py`，建立 `SecurityRiskAttributes`、`RiskFinding` 和
  `PortfolioRiskAssessment`；单股/行业/周期暴露、现金储备、共同因子和流动性
  分别计算，缺失输入失败关闭。
- 实际评估只接受人工确认且已对账的 `ACTUAL` 快照；公开候选只接受
  `SIMULATED` 评估，真实私人数据不得进入公开仓库。
- 新增 `m4_portfolio_risk_workbook.py`、构建脚本、WPS 校验脚本和模拟 fixture，
  并纳入 GitHub Core Research Gate。
- 独立候选 4 页、3 个持仓、3 项风险发现，固定 `action=no_order`；字节数
  10,060，SHA-256
  `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7`。
- WPS 只读收据 `runtime/m4-portfolio-risk-wps-20260924/receipt.json` 为
  `passed`；WPS 云盘同名副本与仓库候选逐字节一致。
- 本批已以 `324694744b51a3f0c3f2316e1ce206ac6cad6cb2` 提交并推送；
  GitHub Core Research Gates run 35913005217 为 `success`。
- 真实组合风险报告、PositionGuidance 和 DividendIncomeProjection 尚未完成；
  本候选不是个人化风险结论。

## M2 AC1-AC12 完整本地回归复核：2026-09-24

- 在 `d6e4179488c11d4833f27fe2f0edde37f4651a46` 重新执行
  `scripts/audit_m2_acceptance.py --run-tests --ci-status success`，并显式核对
  WPS 生产工作簿；最新收据
  `runtime/m2-acceptance-audit-20260923T223550Z/receipt.json`，SHA-256
  `0342ddbedee1ab9906140e6c6be34742434b7e3c687630a311067a6791254ce4`。
- 全量离线回归 2284 passed、6 skipped、0 failed；AC1、AC2、AC3、AC4、AC5、
  AC6、AC7、AC11 为 `DONE`。
- AC8、AC9、AC10、AC12 保持 `PENDING_HUMAN_REVIEW`；整体状态由 `PARTIAL`
  转为 `PENDING_HUMAN_REVIEW`，下一步仍需用户在 WPS 中完成 Checkpoint A。
- GitHub Core Research Gates run 35928696898：`offline-core` 与
  `postgres-integration` 均为 `success`。

## M3 论点连续性历史链只读模型：2026-09-24

本节记录 M3 历史链的公开离线工程。M2、M3、M4 均仍为 `PARTIAL`；
本批只使用显式模拟数据，不读取真实账户、IPS、Entry 或持仓。

- 新增 `m3_history_read_model.py`，建立 `EntryThesisCard`、
  `DecisionJournalLine`、`ConsistencyReviewCard`、`DecisionHistoryChain`
  和 `DecisionHistoryCollection`。
- 公开链只接受 `simulated` 命名空间；Entry、Journal、Consistency 输入均绑定
  不可变 SHA-256，且日志顺序和更正前驱关系会显式校验。
- 新增 `m3_history_workbook.py`，生成 5 页独立候选：
  `00_历史链`、`01_原Entry`、`02_决策日志`、`03_一致性复核`、`04_来源哈希`。
- 新增 `scripts/build_m3_history_candidate.py` 与
  `tests/fixtures/m3_history_demo.json`；示例链路从模拟 Entry 到持有、削弱、
  破坏和减仓复核，固定 `action=no_order`。
- 新增 4 项回归测试并纳入 GitHub Core Research Gate。
- 独立候选字节数 12,121，SHA-256
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`；
  WPS 只读收据为 `passed`，WPS 云盘副本与本仓库候选逐字节一致。
- 本批未修改原 55 页生产工作簿；候选只演示结构，不等于真实历史链或 Checkpoint B
  已由用户签收。

## M4 组合输入合同：2026-09-24

本节记录 M4 的第一批非个人化输入合同。M2、M3 与 M4 均仍为 `PARTIAL`；
本轮没有读取真实账户，不计算仓位、风险或股息预测，也不生成任何订单。

- 新增 `portfolio_contracts.py`，建立 `InvestorPolicyStatement`、
  `PortfolioHolding`、`PortfolioSnapshot` 和 `PortfolioInputBundle`。
- 所有对象固定 `action=no_order`、`sensitivity=PRIVATE_USER_CONFIRMED`；
  缺失输入失败关闭，不补零值或默认 20% 仓位。
- IPS 人工确认门槛、持仓对账门槛和缺失字段均已显式化，见
  [m4-portfolio-input-contracts-20260924.md](m4-portfolio-input-contracts-20260924.md)。
- 新增 7 项回归测试并纳入 GitHub Core Research Gate。
- `PortfolioRiskAssessment` 已在本日后续批次实现；PositionGuidance、
  DividendIncomeProjection、私有持久化、真实账户导入和原 Excel M4 展示尚未完成。
- 本批未修改任何 Excel 字节，原 55 页生产工作簿和 M3 独立候选 Hash 均保持不变。

## M3 决策卡可重复验收审计与 M2 机器门复核：2026-09-24

本节记录当前 HEAD 的机器证据，不把人工验收改写成已完成。M2 与 M3 仍均为
`PARTIAL`，所有动作保持 `action=no_order`。

- 新增 `m3_decision_acceptance_audit.py`、
  `scripts/audit_m3_decision_acceptance.py` 和
  `tests/test_m3_decision_acceptance_audit.py`，并纳入 GitHub Core Research Gate。
- M3 审计器固定冻结输入、M1 预登记、候选工作簿、manifest、WPS 副本与 WPS
  只读收据；重建三张负向卡，验证 deterministic replay、逐卡来源 Hash 绑定和
  原 55 页生产工作簿未改变。
- 机器门 `m3c1-m3c6` 全部 `DONE`；`m3c7` 保持
  `PENDING_HUMAN_REVIEW`，等待用户阅读三张卡并复述理由与反证。
- 收据：`runtime/m3-decision-acceptance-audit-20260923T190024Z/receipt.json`，
  SHA-256 `2bb49e94df6740330d2713dee03eec1c44bb2be753f3afbbd40b1560797c8259`。
- M3 定向回归 29 passed；本次同时以全量离线回归复核 M2：AC1-AC7、AC11 为
  `DONE`，AC8/AC9/AC10/AC12 为 `PENDING_HUMAN_REVIEW`。全量
  2180 passed、6 skipped、18 warnings、0 failed。
- 提交：`41ac62cf77a1e01aaf123c0809ad4baf4bea2a84`；GitHub CI
  `Core Research Gates` 两 job 均为 `success`。
- 未修改原 55 页生产工作簿、未写入 `00_决策复核`、未连接生产 PostgreSQL、
  未触碰服务器 PTA/Web App，也未创建任何 BUY/ADD/仓位或订单。

## M3.2 Decision Card 只读模型与独立 Excel 候选：2026-09-24

本节记录 M3 决策域的第一批可查看离线工程。M2 与 M3 均仍为 `PARTIAL`；本轮未写入
原工作簿 `00_决策复核`，不生成个人化 BUY/ADD、Entry、Journal 或订单。

- 新增 `decision_read_model.py`：把不可变 `InvestmentDecisionReview` 重建成公开
  `DecisionCard`，固定 `requires_human_review=true`、`action=no_order`，并单独表达
  系统负向状态、个人组合缺失、原始 Entry 缺失和人工决策记录缺失。
- 新增 `m3_decision_application.py`：读取冻结 M1
  `runtime/m1-post-review-20260923T114228Z/integrated-runs.json`，对研究门、人工审批、
  估值、模型有效期、价格桥、价格吸引力和当前研究状态逐段做 canonical Hash 绑定，
  再用缺失组合前置和无决策意图构建失败关闭卡片。
- 三张真实卡片均为 `INSUFFICIENT_RESEARCH`，全部为 `no_order`、无决策意图、
  组合输入缺失、原始 Entry 本轮不需要；未产生任何正向复核。
- 新增独立候选
  `A股价值投资_M3决策卡候选_20260924.xlsx`（15,102 bytes，SHA-256
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`），已复制到
  WPS 云盘同名文件。WPS 只读验证通过：4 页、31 个证据链接、无公式错误、打开前后
  Hash 不变；收据 `runtime/m3-decision-card-wps-20260924/receipt.json`。
- 原 55 页生产工作簿未改变，canonical、M2 候选和 WPS 生产原表继续保持 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 测试事实：M3.2 定向 13 passed；Decision/PreDecision 联合 32 passed；
  Core Research Gates 等价离线清单 330 passed；全量离线回归
  2177 passed、6 skipped、18 warnings、0 failed。
- 下一步先由用户在 WPS 云盘查看三张负向决策卡；完成机器验证后，再受保护地把同一
  read model 并入原工作簿 `00_决策复核`，不能直接覆盖原 55 页。

## M3.1 共享决策域契约：2026-09-24

本节记录 M3 解释性决策域的第一批离线工程。M2 仍为 `PARTIAL`，M3 仍为 `PARTIAL`；
本批契约不是 M3 产品验收，也不生成个人化 BUY/ADD、仓位或订单。

- 新增 `src/value_investment_agent/investment_decision.py`，建立
  Evidence Bundle、Minimal Portfolio Preconditions、Decision Review、
  Entry Thesis Snapshot、Decision Journal 与 Consistency Review 的不可变合同。
- 在 research artifact 类型与 codec 中注册六个决策 artifact，支持哈希、版本和仓库
  追加式保存；新增仓库往返测试与 13 项定向回归。
- `evaluate_investment_decision()` 固定 `action=no_order` 与 `requires_human_review=True`；
  缺容量只返回 `WATCH`，正向复核不得绕过价格、置信度、反证和人工确认。
- 实际/模拟 Entry 必须价格，历史重建必须注明；Journal 只追加更正；Consistency 采用
  `BROKEN > NEGATIVE > all-FULFILLED > CONSISTENT` 的保守聚合。
- 测试事实：决策定向 13 passed；联合 codec 17 passed；CI 等价离线清单 317 passed；
  全量离线回归 2164 passed、6 skipped、18 warnings、0 failed。
- 本批未修改任何 Excel 字节，仓库 canonical、M2 候选与 WPS 生产原表继续保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 下一步仍按总Goal继续：Decision/理由卡 read model 与应用编排、版本化历史 replay 输入、
  原 Excel 展示；Checkpoint B 与 M2 的人工验收均不能由代码自行通过。

## M2 AC1-AC12 可重复验收审计器：2026-09-24

本节记录统一审计入口的代码与本地运行事实。M2 仍为 `PARTIAL`，`action=no_order`；
审计器不能替代用户在 WPS 中的实际研究、导航和证据链接复核。

- 新增 `config/m2-acceptance-audit-v1.json`、
  `src/value_investment_agent/m2_acceptance_audit.py`、
  `scripts/audit_m2_acceptance.py` 和
  `tests/test_m2_acceptance_audit.py`，并纳入 GitHub Core Research Gate。
- 审计器重算固定 M2 run、manifest、policy、两个 PIT 快照、AC8 报告、AC9 分层审计、
  工作簿发布收据和 WPS Hash；任何被固定文件的字节变化都会拒绝。
- AC1、AC6 依赖本地全量离线回归；AC8、AC9、AC10、AC12 的机器证据通过后仍为
  `PENDING_HUMAN_REVIEW`，不自动宣布 M2 完成。
- 本地定向回归 33 passed；仓库全量离线回归 2149 passed、6 skipped、18 warnings、
  0 failed。GitHub Actions 对本次新提交的成功结果将在 push 后单独核对。
- 当前 WPS 云盘生产工作簿、仓库 canonical 和 M2 候选工作簿逐字节一致，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 未连接生产 PostgreSQL、未触碰服务器 PTA/Web App、未修改计划任务，也未生成估值、
  BUY、ADD、仓位或订单。
- 详细版本记录见 [CHANGELOG.md](../CHANGELOG.md)；工作簿清单见
  [excel-artifact-version-record-20260924.md](excel-artifact-version-record-20260924.md)。

## M2 AC8 研究报告并入原 Excel 统一入口：2026-09-24

本节记录把 AC8 实质研究/否决报告并入 M2 原表候选、真实 WPS 校验和受保护发布的证据。
M2 仍为 `PARTIAL`，AC8 仍为 `AC8_REVIEW_PENDING`，AC10 为机器检查通过、用户可见审核
待完成；`action=no_order`。

- 代码新增研究页与证据页：`11_研究报告`、`12_研究证据`，并在 `00_M2总览` 加入内部
  导航；候选构造器、发布脚本和 WPS 校验脚本同步补齐，相关文件在本次 Git 版本中公开。
- 发布前原工作簿 SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。
- 新候选及发布后 WPS 原工作簿 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 55 个工作表：13 个 M2、6 个 M1 Application、36 个原工作簿页；42 个原有工作表被
  保留，96 个原始部分未变化。
- 研究报告 22 行、研究证据 245 行、228 个来源链接；AC8 报告 JSON Hash 保持
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- WPS 发布前与发布后只读收据均为 `passed`，实际引擎路径
  `D:\WPS Office\12.1.0.28505\office6`；只验证只读打开/计算、公式错误、工作表顺序和
  链接数量，不冒充人工逐链接或视觉点击验收。
- 受保护发布收据：
  `runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/publication.json`；
  同目录 `before.xlsx` 为回退原件。
- 定向回归 32 passed；最新全量离线回归 2144 passed、6 skipped、18 warnings、0 failed；
  `git diff --check` 通过。
- 未连接生产 PostgreSQL、未触碰服务器 PTA/Web App、未修改计划任务，也未生成估值、
  BUY、ADD、仓位或订单。
- 工作簿版本与 Hash 清单见
  [excel-artifact-version-record-20260924.md](excel-artifact-version-record-20260924.md)。

## M2 AC8 研究报告生成：2026-09-24

本节记录 AC8 的预注册报告工具与真实运行证据。M2 仍为 `PARTIAL`，AC8 单项目前为
`AC8_REVIEW_PENDING`，`action=no_order`。本段是上一阶段报告生成历史；“未生成新 Excel”
只描述当时状态，最新原表集成发布见上一节。

- 新增 `m2_research_report.py`、离线命令、固定输入配置与回归测试；只消费 AC9
  `selected_leads` 已封存样本，不按结果后验选公司。
- 真实报告：`runtime/m2-ac8-research-reports-20260924-v1/report.json`，SHA-256
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 总计 18 份报告，其中 16 份实质报告，覆盖股息、价值、周期三个通道；3 份待深研、
  13 份通道否决、2 份证据不足。证据不足不冒充实质结论。
- 本轮未连接生产 PostgreSQL、未触碰服务器项目或调度、未生成新 Excel，也未覆盖 WPS
  生产工作簿。
- 详细证据见 [m2-ac8-research-reports-20260924.md](m2-ac8-research-reports-20260924.md)。
  AC8 数量门已有机器证据，但仍需与 AC10/W6/W7 一起完成 M2 用户可见验收。

## 用户扩大总Goal至M7：2026-09-23

本节只改变后续执行范围，不改变下方代码审查事实或宣称新增功能。用户最新请求为“把这个目标调整到直接做到m7”。

- 唯一总Goal改为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`；当前聚焦仍是M2/PARTIAL。M1与Post-M1保持DONE，M3-M7未通过产品验收。
- 沿用M1-M6主轴，新增明确定义的M7“个人投资工作台交付与独立使用验收”；M6保留原20连续交易会话/真实事件/恢复等全部实质门，输出运营准入，M7最终用户签收后才标INITIAL_ASSISTED_USE。
- 阶段通过后记录证据、客观审查并在同一Goal继续，不再要求每阶段重建Goal；M4/M5仍仅在依赖成立后有界并行。
- 总范围不授权具体生产迁移、计划任务、通知、私人组合导入或代签G3/IPS/用户验收。这些对应输入和单独授权门保留。
- 本轮仅在上一轮未提交文档修改上增量调整AGENTS、LONG-TERM-GOAL、current-stage-goal、启动Prompt与本状态文件；未启动Goal、未改业务代码/Excel/数据库/服务器/调度，未commit/push。
- 下节“下一Goal只完成M2”的旧范围被本节替代；f4bb55c审查、2118 passed/6 skipped和M2反例仍为上一轮实测，本轮文档调整不冒称重新运行全量测试。

## M2 线索/已核候选边界与未发布原表候选：2026-09-23

本节记录工作树改动与真实候选产物。M2 仍为 `PARTIAL`，没有候选发布为生产工作簿。

- 领域合同：`CandidateReason.candidate_class` 只允许 `LEAD` 或 `VERIFIED_CANDIDATE`；
  当前 Quality/Dividend/Value/Cyclical 筛选输出全部显式标记为 `LEAD`，不能再把便宜筛选结果
  直接表述为已核实候选。`DiscoveryRunReceipt.verified_candidate_pool()` 当前真实运行返回空池。
- 工作簿：新增“研究层级”列和总览计数，明确显示“研究线索/已核候选”；候选签名包含
  `candidate_class`，`action=no_order` 保持不变。
- 原工作簿候选入口：新增 `scripts/build_m2_original_workbook_candidate.py`，要求原工作簿
  预期 SHA-256 与有效 M2 收据，复用受保护 graft，拒绝已有输出或源文件变化，并输出
  `status=candidate_verified_not_published`。脚本不执行 WPS 生产原子替换。
- 真实候选：源原工作簿 SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`；候选
  `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx` SHA-256
  `b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`。
  53 个工作表：前 11 个为 M2，后 42 个原工作簿页保留；`original_parts_unchanged=96`。
- 真实 5,568 家保留输入重放：Quality 0、Dividend 50、Value 50、Cyclical 50；
  `candidate_signature=a4f555b789c3942c690c1e288e5ce3bfa210544cd9ffcc63803d4c1eeb46f4c7`。
- 定向回归 19 passed，`git diff --check` 通过。未连接生产 PostgreSQL、未修改调度、
  未触碰服务器 PTA/Web App，也未替换 WPS 生产原工作簿。

## M2 时点合同与 PARTIAL 证据语义：2026-09-23

本节记录 W1/W2 共同合同加固后的代码、真实冷重放与候选产物。M2 仍为 `PARTIAL`。

- `DiscoveryRunReceipt` 增加向后兼容的 `quote_date`，并拒绝 `quote_date > as_of`、
  `universe.as_of > receipt.as_of` 和 `EvidenceReference.fetched_at > generated_at`。
  Universe 缺少抓取时点直接失败，不再回退到系统今天。
- 财务点只接受带时区且不晚于 `evaluation_at` 的记录；未来或未知时点不会进入
  `FinancialEvidence`。Dividend 证据保存原始输入的实际抓取时间。
- 非 Quality 便宜筛选通道缺少深研证据时全部标 `DATA_PARTIAL`，不再因价格无冲突
  标 `COMPLETE`；当前真实重放中 Dividend 优先级 B，Value/Cyclical 优先级 C。
- `--reuse-inputs` 现在必须读取既有 `receipt.json` 和全部保留输入，并继承原
  `generated_at/quote_date`；新运行 ID 为 `m2-replay-*`，清单记录 `replay_of_run_id`，
  不再把旧快照重标为今天。
- 真实冷重放：从 `runtime/m2-live-20260923-v2b/` 保留输入生成
  `runtime/m2-live-20260923-v3/`。原始时钟仍为 `2026-09-23T15:12:00.735987+00:00`，
  字节收据与原始输入重放均一致。覆盖签名保持
  `4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`；
  候选签名更新为
  `f77fd5f0e139cf0ab283e9aee9fdd2f4f66695071c85816f303c9b31715cbe79`。
- 更新原工作簿候选：SHA-256
  `95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`，
  后 42 个原页和 96 个原始部件不变；同步到 WPS 云盘独立预览，生产原工作簿未替换。
- 定向回归 24 passed；仓库全量离线回归 2131 passed / 6 skipped / 18 warnings / 0 failed；
  `git diff --check` 通过。未连接生产 PostgreSQL、未改调度、
  未触碰服务器 PTA/Web App。

## M2 AC9 分层覆盖审计：2026-09-23

本节记录预注册抽样工具、真实收据审计和抽样阅读结论。M2 仍为 `PARTIAL`；AC9 单项有真实证据，
不等于 M2 或总 Goal 完成。

- 新增 `config/m2-coverage-sampling-v1.json`，固定真实收据 SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`、
  run id、覆盖签名和候选签名，并声明 `action=no_order`。
- 抽样规则在结果观察前登记：`SHA256(seed | stratum_id | channel | symbol)` 稳定排序，
  8 个层每通道各抽 6 条；禁止收益、回测收益和阈值后验键。
- 真实审计输出：`runtime/m2-ac9-coverage-audit-20260923-v2/report.json`，SHA-256
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- 机器勾稽全部通过：每通道 5,568 与官方 Universe 对齐；PASS 与展示候选集合一致；
  150 个展示对象均为 `LEAD`/`DATA_PARTIAL`；已核候选为 0；证据日期与 legacy 记账一致。
- 分层人口：selected 150、REJECTED 7,564、DATA_GAP 6,829、UNSUPPORTED 469、
  BUDGET_EXCLUDED 2,255、NOT_EVALUATED 5,005、显式 excluded/missing 186、legacy 差异 774。
- 抽样阅读结论：Quality 0 的主要成因是财务证据只覆盖 873/5,568，不是全市场无质量公司；
  Value/Cyclical 低 PE 样本仍只作 PARTIAL 研究线索；预算外对象保留分母与原因，但触发指标需
  从原始输入重放才能完整复核；金融画像显式 `UNSUPPORTED`，未进入通用模型。
- 未阻断问题：Value 文案“多指标便宜度”实际输入为 PE、PB 与推导 ROE，下一版规则文本应更精确；
  本版不修改生产签名或历史收据。
- 新增 6 项定向回归并纳入 GitHub Core Gate；未连接生产 PostgreSQL、未改调度、未触碰服务器
  PTA/Web App、未覆盖 WPS 生产工作簿。完整报告见
  [m2-ac9-stratified-coverage-audit-20260923.md](m2-ac9-stratified-coverage-audit-20260923.md)。

## 路线融合复审：2026-09-23，代码基线 f4bb55c

本节是当前状态判断，优先于下方历史记录的“只差三报告”等当时结论。本轮仅审查与文档；未启动Goal、未改业务代码/Excel/数据库/计划任务，未SSH、未commit/push。

- Git：main，HEAD `f4bb55cd686838b874b6a8b0c601492c8bd7aab5`；提交时间21:55:48 +08:00；开始时工作树干净。本轮目标文档修改是未提交工作状态，不算新增已发布功能。
- GitHub本HEAD push run [35870537557](https://github.com/MingMingLiu0112/value-investment/actions/runs/35870537557)：offline-core、postgres-integration均success。CI指定37个离线测试文件及4项一次性PG集成，不是全仓/真实市场/生产可用性证明。
- 本机 `D:/APP/Python313/python.exe -X utf8 -m pytest -q --basetemp runtime/audit-roadmap-20260923-pytest-v2`：**2118 passed / 6 skipped / 18 warnings，290.45s，0 failures**。18条warning来自Backtrader utcnow弃用，不是投资逻辑报警。
- 用 `pytest -q -rs tests/test_postgres_research_artifacts.py tests/test_m1_postgres_cold_replay.py tests/test_moutai_end_to_end_case.py --basetemp runtime/audit-roadmap-20260923-skip-check` 复核：4项无C3_TEST_POSTGRES_DSN、1项无postgresql-binaries、1项已有冻结输出目录，另1 passed。本轮未重跑真实本机PG冷启动，CI一次性PG与历史冷启动收据分开。
- M1与Post-M1稳定化保持DONE；已存在HumanApproval/EventReview/Bridge stress/Interim/PreDecision合同，不重建。三家NOT_ELIGIBLE/STALE或REJECTED结论不提高。
- `runtime/m2-live-20260923/manifest.json` 八项文件Hash均一致，真实收据保留5568匹配、财务覆盖873证券、股息3622、四通道0/50/50/50及113去重候选。Hash一致不证明PIT与研究充分。
- 本轮内存合成反例：未来10月1日宣告仍可进入9月23日Dividend候选；从official删除600004后仍入选，健康仍COMPLETE且含extra blocker；600001入两通道而candidate_pool只保留value；改未来fetched_at/来源Hash后入口仍接受且candidate_signature不变。这些是合成入口缺口，不是实际股票异常。代码定位及修复验收在长期路线第1.4节。
- 源码复核：reuse-inputs重标now/quote_date风险、Dividend/Value/Cyclical以价格无冲突标COMPLETE、FCF/正常化指标仍None、行业存在即SUPPORTED、每通道50截断未保留完整覆盖账。应区分cheap leads与已核候选，不要求全市场DCF。
- 原Excel当前Hash `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，12,210,200 bytes；M2仍在独立工作簿。本轮未做WPS视觉验收，统一原工作台纳入下一Goal受保护发布。
- 本轮调整：LONG-TERM-GOAL更新真实基线/成熟度及M2-M6 DAG；current-stage-goal替换“只差三报告”为W0-W7/AC1-AC12；同步AGENTS、架构、方法/证据政策和启动入口。没有建立第二份Roadmap。
- 当前成熟度：L0 HEALTHY，L1 BASICALLY READY，L2 PARTIAL，L3-L5与INITIAL_ASSISTED_USE均NOT READY。下一唯一Goal完成可信M2，CheckPoint A只帮助研究谁/为什么，不给买卖仓位、不声称每日运营。

## POST-M1 Stabilization + M2 首个真实 run-once：2026-09-23

执行输入是用户复核后的 [m2-current-progress-review-20260923.md](m2-current-progress-review-20260923.md)。
`POST-M1-STABILIZATION` 的 A1-A5 已完成并冻结，当前活动阶段为
`M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`。M1 保持 `DONE`，不重写历史。

- A1：修正茅台旧审计断言，从 P1 v4 契约自带的 hash-bound daily-simulation policy 推导执行政策事实，不删除红测试。
- A2：`build_m1_post_review_receipts.py` 标记为 `ONE_OFF_REVIEW_RECEIPT_GENERATOR`，并增加生产路径防误用测试。
- A3：临时桥接 haircut 增加 `stress_test_only / not_valuation_input / not_price_assessment_input`，域对象可序列化和 round-trip。
- A4：旧十样本估值画像、固定 Universe seed 与 PE/PB screen 明确标记为 legacy；M2 不得复用为候选排序。
- A5：`current-stage-goal.md` 已切换到 M2；本执行手册复制入 `docs/`。
- 稳定化验收：定向回归 14 passed；使用仓库内隔离 basetemp 的全量回归 2112 passed / 6 skipped；`compileall` 与 `git diff --check` 通过；Core 生产路径未新增 `000651 / 600741 / 600887` symbol 特例。

## M2 真实全市场 run-once 结果：2026-09-23

命令 `scripts/run_m2_opportunity_discovery.py` 已完成一次真实运行，
产物目录 `runtime/m2-live-20260923/`。状态为 `PARTIAL`，尚未声明 M2 完成。

- 官方 Universe 5,568 家；腾讯与新浪行情均匹配 5,568 家，缺报/多余/价格冲突均为 0。
- 行业映射 5,568 家；财务证据 873 条；股息证据 3,622 条；金融行业不支持隔离 121 家。
- 四个通道均真实执行：Quality 0、Dividend 50、Value 50、Cyclical 50，合并去重候选 113 家。
- 每份候选保留进入原因、证据日期、`data_status`、`profile_status` 与缺失指标；缺失保留 `None`，不默认为 0。
- Legacy `PE<=25 / PB<=3 / 市值>=50亿` 仅作 shadow：747 家，与新候选重叠 86 家，不参与新候选排序。
- 收据 `action=no_order`；从收据字节和保留原始输入重建的候选签名均一致，`receipt_bytes_match=true`、`raw_inputs_match=true`。
- 独立候选工作簿 `A股价值投资_M2机会发现_20260923.xlsx` 已写入 WPS 云盘“价投跟踪”目录，未覆盖原工作簿；两处 SHA-256 均为 `a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`。
- Quality 为空是证据门禁的失败关闭结果：本轮财务点来自 2026-09-18 前后服务端导出，未达到“验证状态、自动双源交叉核验、完整债务口径、同一报告期年度数据”的门禁，因此未降低阈值强行放行候选。
- 当时曾判断旧验收第1-6、8-10项已有证据、仅差三份报告。**本判断已被顶部f4bb55c复审纠正**：现有收据证明运行/字节重建，不足以证明时点、覆盖、候选质量与统一前台。当前执行范围仅见current-stage-goal，仍禁止symbol专用流水线。
- 本轮 M2 定向回归 6 passed；仓库内隔离 basetemp 全量回归 2118 passed / 6 skipped；未连接生产 PostgreSQL、未改计划任务、未触碰服务器 PTA/Web App 或原 WPS 人工工作簿。

## M1 收口：2026-09-23

- `M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 已达到 `DONE`；AC1-AC10 均由本地产物、隔离 PostgreSQL、WPS 发布收据和定向回归支持，最新审计状态为 `PASSED`、`action=no_order`。收据 `runtime/m1-acceptance-audit-20260923T091447Z/receipt.json`，SHA-256 `f7c71e507585d7660cc9f66320617738525a32abf141f2296ce46ee9ae90d16a`。
- AC4/AC6/AC10 不再被 G3 或事件材料性人工状态阻断。三家公司 G3 研究批准保留到 M3，模型前公告材料性复核保留到 M5，Excel 视觉确认保留到 M6；审计器只登记 `deferred_human_review`，不自动批准。
- 三家正常化股息情景仍 `NOT_READY`、全部估值仍 `conditional_research_only`、价格吸引力仍 `NOT_ASSESSABLE`。M1 完成只表示研究工作台闭环，不表示真实投资或交易准入。
- 未启动 M2，未连接生产 PostgreSQL、未 SSH、未改 PTA 或计划任务。

## M1 后人工复核纠偏与 M3/M5 决策门：2026-09-23

执行输入是用户复核后的 [m1-post-review-decision-gate-20260923.md](m1-post-review-decision-gate-20260923.md)，基线为 `cbec189 Close M1 workbench and defer decision-stage reviews`。M1 仍保持 `DONE`，冻结估值包、历史收据和原 WPS Excel 未修改。

- 新增五个 append-only 领域契约：`human_research_approval.py`、`event_materiality.py`、`valuation_bridge_review.py`、`interim_report_policy.py`、`pre_decision_eligibility.py`；Application、G3、ModelValidity、PriceBridge 和 CurrentStatus 已接入新门禁。
- 三家公司正式人工 G3 回执：`000651=REJECTED_NEEDS_REWORK`、`600741=REJECTED_NEEDS_REWORK + HIGH`、`600887=APPROVED_CONDITIONAL_LOW_CONFIDENCE`。回执绑定估值、ResearchCase、Facts、Assumptions 的 SHA-256，依赖变化会变为 `SUPERSEDED`。
- 24 条公告全部形成 EventMaterialityReview。分类为 2 `MATERIAL_REQUIRES_RECALCULATION`、4 `MATERIAL_RISK_MONITOR`、4 `MATERIAL_ALREADY_INCORPORATED`、5 `DUPLICATE_OR_DERIVED`、7 `NOT_MATERIAL`、1 `MATERIAL_SUPPORTING_EVIDENCE`、1 `REQUIRES_DECOMPOSITION`。格力和华域未解决资金桥接拆分保持 `UNRESOLVED`；伊利成本权益、留存/分红和减值归一化 ROE 仍为 `CONDITIONAL_REVIEW_PENDING`。
- 未经审计半年报默认改为 `CONFIDENCE_MODIFIER`，保留 `previous_classification=HARD_BLOCKER` 和版本链；已核实来源存在冲突、更正、范围不匹配或审计问题时才继续升级 blocker。
- 无有效人工 G3 时 Application 的价格吸引力强制为 `NOT_ASSESSABLE`。PreDecision Eligibility 要求 G0-G3、有效 Approval、当前 Event Review、`VALID`、`READY` 和可评估价格政策同时成立。
- 正式 runtime 收据目录 `runtime/m1-post-review-20260923T114228Z/`，manifest 覆盖 9 个文件 Hash；三家 integrated runs 均为 `action=no_order`，分别保持 `REJECTED/STALE`、`REJECTED/VALID`、`CONDITIONAL_APPROVED/STALE`，均 `NOT_ELIGIBLE`。
- 定向回归 `71 passed`；全量本地回归 `2107 passed, 6 skipped, 1 failed`，唯一失败仍是本文已记录的茅台旧 `daily_simulation_policy_implemented` runtime 指针断言，不在本轮改动路径内。GitHub Core Gate 已加入五个新契约测试文件。
- 未修改 M1 冻结 Hash、生产 PostgreSQL、计划任务、服务器 PTA/Web App 或原 WPS Excel。

## 用户指定的前端调整：2026-09-23 已更新原 Excel

独立于并行 M1 研究任务，本次只调整使用界面，不提升研究或交易准入状态。
原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 已备份并原子更新，新增工作台、研究看板、研究逻辑卡、决策复核、组合与股息、跟踪与数据六页。原30页的worksheet XML逐字节未变，持仓/交易/历史记录保留。

- 本次前台连接3家封存研究样本，含1家条件三情景及2家估值未就绪；不是正式重点关注池，不是今日行情，不是买卖建议。
- 下文 M1 W3 的6份新档案仍在独立候选中，未接入本前台；不能因本次原表发布而宣称M1的研究产品闭环通过。
- 新看板含原生筛选表、冻结导航、内部链接；未来决策、组合和监控区明确“未接入”，未知不填0。
- Excel相关回归：`19 passed`；64个内部链接目标、4个公式缓存和30张原表完整性校验通过；WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 只读打开/计算校验通过。桌面鼠标逐链接点击不在该收据范围内。
- 发布收据：`runtime/workbook-backups/stage-frontend-b65249ffe1874ca1859827665a4a001f/publication.json`；同目录 `before.xlsx` 为回退原件。新文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 保留六页的发布入口修改已在本地测试，未提交/推送；未部署服务器、未改定时任务。现有刷新只保留新页，不自动刷新这些封存快照。
- 构建运行时的退出异常与后续接入约束记录于 [excel-stage-frontend.md](excel-stage-frontend.md)，不把导出文件成功冒充无人值守发布已经可靠。

## M1 当前增量：2026-09-23 格力历史双源收盘价、PIT replay 与新 Application 候选

本节记录当时实际生成的新收据；该时间点的“未完成”只描述当时状态，最终 M1 收口见本文件顶部。

- 格力 `000651` 注入真实历史双源收盘价：腾讯与搜狐均 `38.18`，SZSE 交易日历为 `2026-09-22`；Application 桥接从 `PENDING_EXTERNAL_DATA` 变为 `READY`，当前数据为 `READY`。格力 FY2024 末期与 FY2025 中期派息实施原件也已补齐，见下方“格力股息生命周期”节。
- 三公司最新 Application：`000651 / 600741 / 600887` 全部 `COMPLETED_WITH_BLOCKERS`、`action=no_order`；三家报价桥接均为 `READY`，价格吸引力保持 `NOT_ASSESSABLE`。G3 与事件材料性后来按里程碑边界延后，不作为 M1 阻断。
- 隔离 PostgreSQL 冷启动已用更新后的格力数据包重跑：PostgreSQL 18.6，首轮写入 30 个制品，冷重启后 30/30 验证通过，`semantic_equality=true`。最新收据 `runtime/m1-postgres-cold-replay-20260923T060159Z/receipt.json`，SHA-256 `bd643fc080c82d2c174948067918488ae8c38aee2f6a615d763d7bc9ed9286e8`。
- 新披露 PIT replay：`m1_pit_replay.py` 对格力、华域、伊利三家真实官方 PDF 重放报告期披露可用边界；每家 2 份官方财报、4 个决策边界、3 个未来披露排除点，只按 `published_at` 选择，不用 `retrieved_at` 推断历史可用。收据 `runtime/m1-pit-source-replay-20260923T042556Z/evidence.json`，SHA-256 `f9a19f4da5d06ace7cb5b681e910925f45137f3c17df9e600be0f782ae34bf7f`。
- 原五粮液真实财报更正 replay 继续作为 AC7 的更正反例：`runtime/company-research/000858-revision-replay-20260909T131721971494Z/evidence.json`。
- 新 Application Excel 候选：6 个工作表顺序、WPS 只读打开、公式重算与哈希不变检查通过；候选 SHA-256 `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`。
- 已复制到 WPS 云盘 `M1_三公司研究Application候选_20260923_122010.xlsx`；复制前后哈希一致。原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 未覆盖，AC9 的受保护原表发布仍未完成。

## M1 原 Excel 整合发布：2026-09-23

上一段最后一项已推进为受保护的原表整合发布。这里只是把三公司 Application 六页追加到原 WPS 工作簿，不是 M1 完成，也不是交易建议。

- 修复 `scripts/stage_frontend_package.py` 的关系 ID 冲突：原表与新增 M1 页面都使用过 `stageFrontend1..6`，会导致 WPS 把前六页错误绑定到旧 parts；现在新增页使用独立 `m1Application1..6`，并对每个 `.rels` 做重复 ID、悬空目标和前六页 part 映射 fail-closed 校验。
- 早先 `runtime/m1-integrated-workbook-20260923T043200Z/` 中带重复关系 ID 的候选已判定为结构无效，从未发布；不要把它当作可用 Excel 产物。
- 新候选为 42 个工作表：前 6 个是 M1 Application 页面，原 36 个 worksheet XML 逐字节未变、顺序保留；首屏标题为 `M1 三公司研究 Application 候选`，状态为 `完成，有阻断`，全程 `action=no_order`。
- 集成候选 SHA-256：`36fd26812f84dd0b9931725ebeec93cf5311c17f408974714c434ab5a22970ac`；发布前源文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 发布前 WPS 收据：`runtime/m1-integrated-workbook-20260923T044629Z/wps-integrated-receipt.json`；发布后再次只读打开验证：`runtime/m1-integrated-workbook-20260923T044629Z/wps-published-receipt.json`，42 页、标题/状态、哈希不变检查均通过。
- 发布收据：`runtime/workbook-backups/stage-frontend-3c253a9761bb44489872ce7268e9a933/publication.json`；同目录 `before.xlsx` 为可回退原件。
- 防回归测试：`tests/test_stage_frontend_package.py` `3 passed`，覆盖关系 ID 唯一性、原关系目标保留和重复 ID fail-closed。
- M1 仍未完成：G3 人工估值审批、股息实质评估、更完整的跨模型情景与剩余真实缺口均未结束；发布页明确显示 `完成，有阻断`，没有生成价格吸引力或买入结论。

## M1 事件扫描合同与真实 CNINFO 封存：2026-09-23

上一版把中报原文当作事件扫描证据是不成立的。本轮新增显式 `EventScanResult` 合同，并把三家估值包改绑到真实 CNINFO 公告窗口证据，避免“任意非空引用 = 已完成且无重大事件”。

- 新增 `src/value_investment_agent/event_scan.py`：分别保存扫描窗口、模型有效性窗口、覆盖完整性、公告级规则分类、模型前候选复核状态、阻断和证据引用；扫描窗口必须覆盖报价日，`PENDING_HUMAN_REVIEW` 与不完整覆盖不能生成 `VALID`。
- `scripts/collect_m1_event_scan.py` 从 CNINFO 归档三家 `2026-08-27 ~ 2026-09-22` 共 40 份公告：格力 8、华域 13、伊利 19；每家保留索引 JSON 和全部 PDF，逐份 SHA-256 已校验。收据目录 `runtime/company-research/m1-event-scans/20260923T051018Z/`。
- 三家桥接窗口 `2026-09-22` 均无公告，`ModelValidity` 仍为 `VALID`、`PriceBridge` 仍为 `READY`；但模型构建前分别有 7、4、13 份规则候选标为 `PENDING_HUMAN_REVIEW`，阻断已进入 Application 与 `价格桥` 展示，不冒充全周期事件复核完成。
- 三个估值包的 `model_validity_input.event_scan_ref` 已绑定证据文件 SHA-256，`scan_watermark` 改为 `m1-cninfo-event-scan-v1:<hash16>`；旧 `events=[] + 中报引用` 不再作为新路径的事实来源。
- 新 Application 收据：`runtime/m1-research-application-20260923T051116Z/evidence.json`。新集成候选与原表发布 Hash 均为 `4678b4aa3074f7d4e7c31134a2560326fdcd45f0fb1e367b2bb1c9c971ed0ed7`；原 36 页 XML 逐字节未变。
- 发布前 WPS 收据：`runtime/m1-integrated-event-scan-20260923T051301Z/wps-receipt.json`；发布后再次只读验证：同目录 `wps-published-receipt.json`。发布备份：`runtime/workbook-backups/stage-frontend-1688b2b905714859bc90ca57d9ed7a8c/`。
- M1 仍未完成：事件扫描现在是可审计证据，但模型前披露尚未人工完成材料性复核，G3、股息实质评估和更完整跨模型情景仍未结束。

## M1 AC5 股息生命周期证据与 Excel 发布：2026-09-23

上一版的三家股息包只有不完整除息台账和空收益率快照。本轮为伊利、华域建立真实法定生命周期证据，并把 AC5 的层次直接放进原 Excel 的 `02_股利评估`，而不是只停留在配置 JSON。

- 新增 `scripts/collect_m1_dividend_lifecycle.py`。证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T052056Z/` 共封存 11 份官方 CNINFO PDF：伊利 8 份、华域 3 份；每份保留原 PDF、PDFium 文本提取、来源 URL、发布时间、解析器版本和 SHA-256。清单文件 SHA-256：`974cbf76a327014131e702269aec7279ce9b2398319ee4909f23540c3cdfc89c`。
- 伊利 `600887`：FY2024 末期普通股利 `1.22`，提议 `2025-04-30`、批准 `2025-05-20`、除息/支付 `2025-06-06`；FY2025 中期普通股利 `0.48`，除息/支付 `2025-12-17`；FY2025 末期 `0.90` 仍为 proposal；2025-2027 股东回报计划明确登记为 policy，不是预测；未识别特别股利，未宣称前瞻 payout forecast。
- 华域 `600741`：FY2024 末期普通股利 `0.80`，提议 `2025-04-29`、批准 `2025-06-27`、除息/支付 `2025-07-25`；FY2025 末期 `1.00` 仍为 proposal；长期政策背景为 2009 上市以来每年现金分红，2009-2023 累计 `30.830 billion`；未识别特别股利，未宣称前瞻 payout forecast。
- 两个 package 版本升级为 `20260923.2`：`600887-quality-compounder.json` 有 3 条历史记录、2 个 `READY` 快照和 1 个显式 `NOT_READY` 正常化情景；`600741-mature-manufacturing.json` 有 2 条历史记录、1 个 `READY` 已宣告快照和 2 个 `NOT_READY` 快照。可持续性均为 `LOW`，保留可分配现金、现金流、资本强度和周期敏感等真实阻断。
- `src/value_investment_agent/m1_application_workbook.py` 的股利页扩展为三张连续证据表：可持续性摘要、法定生命周期台账、当前/正常化收益率快照。普通/特别、事实/政策/预测、paid/proposed、current/normalized 均可直接在 Excel 复核；`NOT_READY` 不改成已知。
- 防回归测试 `tests/test_m1_application_workbook.py` 锁定 `02_股利评估` 必须展示生命周期、当前/正常化、特别股利与事实/政策/预测分层。本轮相关聚焦回归：`80 passed, 1 skipped`。
- 新 Application 证据：`runtime/m1-research-application-20260923T053028Z/evidence.json`，SHA-256 `4933cf172f8ba784921ad6146948bd3570a8bf26e56c0cba9026829f92e4b113`。
- 受保护整合发布：42 页，前 6 页为 M1 Application，原 36 页 worksheet XML 逐字节未变；候选及发布 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea`。发布前收据 `runtime/m1-integrated-dividend-20260923T053128Z/wps-integrated-receipt.json`，发布后 WPS 只读收据同目录 `wps-published-receipt.json`，回退原件 `runtime/workbook-backups/stage-frontend-ffa20fa0a1d34a8ab3b41c5cc95759d3/before.xlsx`。
- AC5 已从“PARTIAL 占位”推进为两家有证据的 `LOW` 可持续性结论；但正常化情景仍 `NOT_READY`，格力 `000651` 的 paid 除息/支付台账仍未补全。因此 M1 不因本段完成。

## 当前摘要：M1 W3 已形成 6 份 READABLE 研究档案，估值与产品闭环尚未完成

2026-09-23 已完成 M1 W1 样本与方法预登记、W2 的工程边界，并推进 W3 真实研究档案。当前结果是 `M1 IN_PROGRESS`：已形成 6 份绑定官方原件、反证和下一事件的可阅读研究档案。`READABLE` 仅表示研究已完整呈现且未知项显式可见，不等于估值完成、股息通过、价格合理或可交易。

| 核查项 | 当前事实 |
| --- | --- |
| 新合同 | `research_run_contract.py`、`research_input.py`；版本化 descriptor 为 `m1-fixed-sample-input-v1` |
| PIT 边界 | 分别保存 report/research/valuation/available/computed；拒绝日期掩盖、未来可用时间、未来报告期、来源在可用边界后发布/抓取；三家真实披露边界 replay 已生成 |
| 假设绑定 | 登记 assumption 必须命中实际 `facts.scenario_inputs`；不一致记为 blocker，不生成订单 |
| G3 边界 | `ResearchValuationApproval` 绑定模型、版本、估值日期和结果 SHA-256；旧 `case.valuation_status` 不再自动通过 G3 |
| 依赖失效 | batch 同时比较输入 SHA-256 与 dependency SHA-256；model/parser/scan/profile/requested-model/rule 变化会重跑或隔离失败 |
| 坏输入隔离 | 坏 descriptor、未知 Profile、未来 availability 只进入 `input_failures`，不终止同批其他公司 |
| W1 样本登记 | 20 家分层预登记账在 `config/m1-fixed-sample-preregistration-v1.json`，覆盖原3家、3画像、同画像第二家、不支持、资料不足和风险反例 |
| W1 方法与停止规则 | 来源、字段、深度、预算、20家上限、3次证据尝试后暂停、不伪造 READY、`action=no_order` |
| W3 共享建造器 | `m1_provider_dossier.py` 统一 schema、必需维度、证据 ID 引用、原文件 SHA-256 与 latest pointer 发布 |
| W3 六家证据档案 | 格力 `000651`、五粮液 `000858`、兖矿 `600188`、伊利 `600887`、海尔 `600690`、华域 `600741`；均绑定官方 PDF、来源 URL、发布时间、报告期与 SHA-256 |
| READABLE 语义 | complete 研究章节允许保留显式 `UNKNOWN` 维度；`MISSING/NOT_STARTED/BLOCKED/PARTIAL` 仍阻止可读性；READABLE 不等于估值完成或交易就绪 |
| W3 报告状态 | 20 家：`READABLE=6`、`PARTIAL=0`、`BLOCKED=3`、`NOT_STARTED=11`；全部保持 `action=no_order` |
| 聚焦测试 | 本轮 M1/Research Application/股息/报价相关回归 `80 passed, 1 skipped`；股息页新增 AC5 分层防回归测试 |
| 全量离线套件 | 历史结果为 `2054 passed`、`6 skipped`、`1 failed`；本轮在首个旧失败处停止，失败仍为 `test_moutai_current_valuation_admission.py` 的 `daily_simulation_policy_implemented=false`，与本次 M1 股息文件无依赖 |
| 本地产物 | `runtime/m1-research-dossier-candidate-latest.json`、`m1-research-application-latest.json`、`m1-pit-source-replay-latest.json`、PostgreSQL replay 收据与 Application Excel 候选；原 WPS 工作簿已受保护发布为 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea` |
| 安全边界 | 未连接生产 PostgreSQL/服务器/PTA，未改 WPS 原表，未生成订单或仓位 |

六家 `READABLE` 档案的维度会显式保留 `UNKNOWN`，研究缺口继续显示未审计、ROIC、正常化利润、法人层级现金和模型输入等问题。W3 仍要继续补齐跨模型情景估值、股息可持续性、报价/事件桥接、隔离 PostgreSQL 冷启动 replay 与原 Excel 安全发布；没有这些验收，不能宣称 M1 完成或初步投资就绪。

## M1 格力股息生命周期与 AC 事实矩阵：2026-09-23

本节补齐 AC5 第三家、用更新后输入包重跑 AC8，并把 AC1-AC10 固化为可核对的事实矩阵。所有状态仍是 `action=no_order`。

- 格力 `000651` 新增两份官方派息实施原件：FY2024 末期 CNINFO `1224534765.PDF`、FY2025 中期 CNINFO `1224936369.PDF`。分布包升级为 `package_version=20260923.2`。
- 格力生命周期现在为：FY2024 末期普通股利 `2.00` 已支付，批准日 `2025-06-30`、除息/发放日 `2025-08-29`；FY2025 中期普通股利 `1.00` 已支付，批准日 `2025-11-24`、除息/发放日 `2026-01-23`；FY2025 末期 `2.00` 仍为提议，未批准。无特别股利，无前瞻支付预测。
- 股息快照：trailing paid `3.00 / 38.18 = 0.07857517...` 为 `READY`；声明提议 `2.00 / 38.18 = 0.05238345...` 为 `READY`；正常化情景仍 `NOT_READY`。
- 格力可持续性结论为 `LOW`，不是“可维持”或投资依据；财务公司、受限现金、金融资产与法人层级可分配现金仍未拆通。
- 证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T055500Z/`；清单 SHA-256 `41f2114f7261370984e0219a8ec13aba658ff6f7b32af2b97c2ae7430b97c965`。两份新 PDF SHA-256 分别为 `8d4b488560f9d3ec81c9349757cda9d9bdee4cdbbecb97911761e2f6a93b4b64` 与 `89ab10370d6601c698426eb6a37dba664687ca03ee59a46208e104068d62d3dd`。
- 更新后的三公司 Application 与 42 页集成工作簿再次发布：原 36 页 XML 逐字节保留；发布后 WPS 工作簿 SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。候选、备份与发布前/后 WPS 收据均在 `runtime/m1-integrated-dividend-20260923T055026Z/`。
- AC1-AC10 正式状态与证据见 [m1-acceptance-fact-matrix-20260923.md](m1-acceptance-fact-matrix-20260923.md)。最终：AC1-AC10 `DONE`；G3 研究批准延后到 M3，事件材料性复核延后到 M5，Excel 视觉确认延后到 M6。
- 后续里程碑才需要逐项完成的 G3 估值审批、CNINFO 事件重要性阅读和 Excel 可用性检查见 [m1-human-review-checklist-20260923.md](m1-human-review-checklist-20260923.md)。六份档案的机器可读深度已抽查，人工质量复核可保留，但不阻塞 M1。
- 收束后聚焦回归 `82 passed`；`compileall` 与 `git diff --check` 通过。当前 WPS 工作簿 SHA-256 仍为 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，未再改动。
- 新增可重复执行的本地验收审计器 `scripts/audit_m1_acceptance.py`：只读核对 dossier、输入/估值/股息包、PIT replay、PostgreSQL 冷回放与 WPS 发布收据，并可选重跑 AC1/AC2 回归。审计器 schema v2 区分 M1 机器验收与 M3/M5/M6 后续人工复核；最新运行收据见“机器复算入口”节。
- 新增 `scripts/render_m1_human_review_packet.py`，从冻结 Application/事件扫描包生成 [m1-human-review-packet-20260923.md](m1-human-review-packet-20260923.md)：当前 24 条待人工阅读公告均给出本地原件、CNINFO 原件和 SHA-256 前段，另有三家公司 G3 决策表。生成器只读，`action=no_order`。
- 当前脏工作树按 GitHub offline-core 同款 30 个测试文件重放：`226 passed`。系统默认 `C:\Users\we\AppData\Local\Temp\pytest-of-Ming` 因 Windows 权限拒绝导致 4 个 setup error；使用项目内 `runtime/pytest-tmp-ci-full` basetemp 后全部通过，未修改系统目录权限，未把环境错误写成代码失败。

M1 已在上述口径下完成。`VALID` 或 `READY` 仍不能写成价格吸引力或交易准入；条件研究、正常化股息缺口和后续人工复核状态全部保留。

## M1 Application 与三公司候选展示：2026-09-23

本轮没有把 M1 标为完成。当前三家公司均保持 `action=no_order`，输出状态均为 `COMPLETED_WITH_BLOCKERS`。伊利事实层的三条重复门禁已拆开：前瞻 ROE 保持为登记的低置信度假设，ROIC 缺口保留在研究反证/人工批准项，beta 缺失移到 `cost_of_equity` 假设；伊利因此得到 `conditional_research_only` 的 Bear/Base/Bull 与 `READY` 价格桥，但仍没有人工 G3 批准，不能形成价格吸引力或交易结论。华域股利能力说明改为“提议分配，尚未批准/支付”，不再把未经审计的中报语境误写成分母。

- 新增三公司版本化股利包、共享加载器、有界反向估值与批量 Application runner；新候选展示层只读取已有 Application/股利/反向估值结果，不在 Excel 重算。
- 本地产物：`runtime/m1-research-application-latest.json`、`runtime/m1-research-application-workbook-20260923T033001Z/m1-research-application-candidate.xlsx` 及 manifest/WPS 只读收据。
- WPS 云盘只新增独立候选副本 `M1_三公司研究Application候选_20260923_033001.xlsx`，未修改原工作簿。
- WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 以只读方式打开、重算、扫描公式错误后哈希不变：`status=passed`。

## M1 隔离 PostgreSQL 冷启动 Replay：2026-09-23

本地没有启动 Docker Desktop、常驻服务、生产 PostgreSQL、SSH 或 PTA。本轮使用项目内忽略的 `.m1-postgres-venv` 中 `postgresql-binaries==18.6.0`，在 `127.0.0.1` 随机端口创建一次性 PostgreSQL 18.6 集群，从三份真实 M1 valuation/distribution 配置完整执行共享 Application，停库后从同一数据目录冷启动并逐条恢复验证。

- 新增 `src/value_investment_agent/m1_postgres_cold_replay.py` 与 `scripts/run_m1_postgres_cold_replay.py`；只允许 loopback 地址，不接收外部 DSN。
- 首次运行写入 28 个 typed research artifacts、28 个 head、87 条 reference；三家输出均为 `COMPLETED_WITH_BLOCKERS`、`action` 为 `null` 或 `no_order`，无订单或仓位字段。
- 冷启动后 28/28 artifact 通过 SHA-256 与 canonical payload 语义相等校验；首轮和冷启动 artifact fingerprint 均为 `5635429903544517fccb41826a62c1986a3ae855771d49c4cc3c79e248568a8f`。
- 真实验收收据：`runtime/m1-postgres-cold-replay-20260923T040611Z/receipt.json`；收据 SHA-256 `8ec0f2bfbd18e16f8dc7d0ac647c8cbb6df76443945ef59104b2510d0f16f4f8`，状态 `PASSED`。
- 隔离环境定向测试：`2 passed`；普通离线环境无本地二进制时按设计 skip，不把本机真实验收与 CI synthetic fixture 混为一谈。

## M1 启动前审查基线（2026-09-22）

本轮任务是系统审查与长期目标收敛，只修改文档，没有实施 M1、修改业务代码、Excel、数据库、生产任务或服务器。新增 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md) 规划六个大 Milestones；唯一待启动长期目标为 M1-FIXED-SAMPLE-RESEARCH-WORKBENCH。原独立 C4 adapter 建议被吸收为 M1 输入完整性工作包，不再单独作为产品目标。

以下是本轮重新观察的状态；后面 C0-C3 的测试数、Hash、旧缺口和“下一任务”属于各阶段历史，不覆盖本摘要。

| 核查项 | 本轮事实 |
| --- | --- |
| 开始 Git HEAD | `494d0857c7edb4b76b0527d773065013b7abf2d1`，2026-09-22 20:33:40 +08:00，C3.14 close governance and record green CI receipt |
| 本地/远端 | GitHub main 同一 SHA；开始工作树干净；本轮文档为新增未提交工作，未推送 |
| 当前 HEAD CI | [35727941981](https://github.com/MingMingLiu0112/value-investment/actions/runs/35727941981) 两项 offline-core/postgres-integration 均 success；不是只引用前一提交绿色收据 |
| 本机 CI 同款文件清单 | Python 3.13，`pytest -q -p no:cacheprovider`；173 passed、4 skipped，2.48s；4项因未配置 `C3_TEST_POSTGRES_DSN` 跳过，未连接生产 |
| 冻结历史验收 | `test_moutai_valuation_export.py` + `test_three_company_unified_acceptance.py`：9 passed，0.77s |
| 真实 runtime replay | 调用 `run_three_company_replay` + InMemory Repository：all_semantics_matched=true、no_order；未生成新runtime收据/改latest |
| 三公司 | 茅台conditional/低置信度、VALID/READY桥接；美的/神华not_ready；三家production valuation均NOT_AVAILABLE，cash return均PARTIAL |
| 原Excel当前Hash | `4EA4AB6F291E0D3C8838A1729007C8B29D0825CCF7CA6459BBD16257BEC0188E`，12,138,778 bytes，mtime 2026-09-22 17:30:45；不同于历史冻结Hash，不能回退覆盖 |
| 未验证 | 最新生产数据原件、生产DB/服务/计划任务、全量历史测试、WPS界面与公式重算 |

当前 workflow 本机实测是173项，不沿用旧文档176项。CI PostgreSQL的4项使用自包含fixture；本轮真实runtime是在内存repository重放。两者都不证明生产PostgreSQL已迁移或真实市场研究有效。

### 新发现与复现

- `research_application.py:292`：显式spec.as_of可掩盖facts日期不一致。以既有测试fixture令case/spec为2025-12-31、facts为2024-12-31，仍返回outcome，valuation日期为2024-12-31。
- `research_application.py:266`：可将2025年输入的结果available_at设为2024-01-01；完整PIT约束尚未建立。
- `research_batch.py:310`：相同input hash而rule_version从v1变v2，仍得到UNCHANGED。
- 登记AssumptionSet并不自动证明它驱动了facts.scenario_inputs；G3仍读旧case状态。需在M1同一可信输入链修正/证明，而不是继续堆接口。
- Manifest-driven input adapter和Application结果到Excel仍缺；旧PE/PB screen仍可从CLI调用，必须标legacy后迁移，不能声称已经退役。

复现使用既有测试fixture和纯内存对象，无业务文件改动。明确异常原因和证据在LONG-TERM-GOAL第1节；本轮没有为了让状态变好而修代码。

### 成熟度与下一目标

当前是 L0工程基础已具备、L1研究工具早期/PARTIAL，不是L3决策支持或L4组合支持。架构方向总体对齐；主要风险是平台验收领先于真实研究/产品可用性。
M1计划交付20家分层入组、6家深研、真实跨模型/股息/当前桥接、冷启动replay及原Excel共同展示，具体质量与停止条件以current-stage-goal为准。M2全市场、M3决策/Entry/Journal/一致性、M4组合、M5事件、M6生产验收均NOT_STARTED；本轮没有启动它们。

## 历史阶段记录（保留原验收，不作为当前任务队列）

## C0 已冻结

C0-PRICE-BRIDGE-INTEGRITY：`PASSED_FOR_FREEZE`。

- 提交：`df4d343 C0-price-bridge-integrity`。
- 新增 `QuoteSnapshot` 与显式 `bridge_with_quote()`；收紧 ModelValidity、PriceBridgeResult、JSON 恢复和下游聚合。
- `current_research_status_from_payloads()` 不再用估值 symbol 覆盖冲突身份。
- 定向回归 47 项、Core Gate 102 项通过；旧 runtime 合同显式重验，茅台 READY 恢复不静默洗掉冲突。
- 三公司 runtime Hash 与原 Excel Hash 未变。

C0 只修复共享工程合同，不表示研究、估值、股息能力、生产数据或价格判断已经完成。

## C1 验收基线

- C1 开始 HEAD：`df4d343726f0d49fd5570e30b075cc46faf859d0`，工作树干净。
- 未连接服务器、生产数据库或定时任务；未重做原始财报、行情或重大事项审计。
- 目标：固定样本准入协议与公共编排审查。

## C1 验收结果

C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/fixed_sample_admission.py`，显式区分研究样本准入证据与估值推进证据。
- 新增 `FixedSampleAdmissionPolicy`、`FixedSampleCompanyAdmission` 和 `FixedSampleAdmissionReview`。
- 公共入口 `review_fixed_sample()` 对每家公司复用 ResearchGate、ValuationResult、ModelValidity、PriceBridge 和 CurrentResearchStatus 合同；不按 symbol 猜测 profile。
- 三家公司输出：

| 公司 | 编排合同 | 研究样本 | 有界价值 | 生产估值 | 显式决策 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | REUSABLE | ADMITTED_FOR_RESEARCH | CONDITIONAL | NOT_AVAILABLE | CONTINUE_CONDITIONAL_MODEL |
| 000333 美的集团 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | RESOLVE_MODEL_INPUTS |
| 601088 中国神华 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | PAUSE_PRODUCTION_VALUATION |

- 汇总状态：`engineering_orchestration_status=REUSABLE`，`production_valuation_available=false`。
- 所有记录均为 `human_confirmation_required=true`、`action=no_order`；不含仓位、订单、目标权重或实盘指令。
- 新增本地审查命令：`python scripts/review_fixed_sample_admission.py`。命令读取四个冻结指针，验证 Hash 后生成带 script/evidence Hash 的审查产物和 latest 指针。

验证证据：

- 新增防回归：`10 passed`，覆盖显式政策、条件估值不升级、空情景、缺研究证据拒绝、身份冲突、profile/model 类型失配、公共编排、序列化和三公司冻结回归。
- 更新后的 Core Gate：`112 passed`。
- 全量测试：`1901 passed, 1 skipped, 5 failed, 18 warnings`。5 个失败均是旧验收测试硬编码茅台报价日 `2026-09-21`；后台日更在 C1 验证期间将 current 指针推进到 `2026-09-22`。本轮未改历史验收测试或回退 runtime 日更产物。
- `compileall` 通过；`git diff --check` 通过。
- 美的、神华及研究卡 Hash 与冻结记录一致；茅台 current 已被后台日更推进，Hash 为 `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`。原 WPS 工作簿 Hash 仍为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`。
- 未改动估值参数、原 Excel、生产数据库、计划任务或服务器服务。

## 阶段语义

三公司统一工程/Excel MVP、C0 和 C1 均通过冻结。C1 的 `REUSABLE` 表示共享审查入口可用，不表示任何公司生产估值或现金回报结论可用。

| 维度 | 600519 贵州茅台 | 000333 美的集团 | 601088 中国神华 |
| --- | --- | --- | --- |
| Engineering Complete | READY：研究、估值和 C0/C1 共享合同可用 | READY：FCFF 算术与拒绝边界 | READY：周期算术与拒绝边界 |
| Research Complete | PARTIAL：商业/财务材料与论点存在，G3 未通过 | PARTIAL：事实范围 MODEL_NOT_APPLICABLE | PARTIAL：正常化假设和财务门未通过 |
| Valuation Complete | PARTIAL：低置信度 conditional_research_only | NOT_READY：无三情景值 | NOT_READY：无三情景值 |
| Dividend Research Complete | PARTIAL：有历史分红及分配交叉检查 | PARTIAL：有历史派息与部分财务材料 | PARTIAL：有派息与周期候选材料 |
| Production Data Ready | 2026-09-21 快照 READY；未验证 09-22 当前生产 | PENDING_EXTERNAL_DATA，并存模型适用性问题 | PENDING_EXTERNAL_DATA，并存未注册假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE：低置信度及研究门限制 | NOT_ASSESSABLE | NOT_ASSESSABLE |

三家公司完整 DividendSustainability 评估均未完成。

## 当前可追溯产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司研究卡 | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 茅台条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`（后台日更推进） |
| 美的未就绪结果 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 神华未就绪结果 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |
| 固定样本审查 | `runtime/fixed-sample-admission-review-latest.json` | `1dfe78e330ee45242d71a59a6888774408166fc215ca866816e4aefd6e535b4f` |

茅台估值日期为 2026-09-21，报价日已由后台日更推进到 2026-09-22；条件情景 403.44 / 478.43 / 571.25 元每股。此处仅描述研究模型，不是当前合理价或投资建议。美的、神华载荷日期为 2025-12-31，不能称作今日估值。

## 剩余风险与边界

- C1 是工程与准入协议验证，不替代生产行情、公告、重大事项或人工研究复核；当前价格评估仍为 NOT_ASSESSABLE。
- 后台日更会推进 current 指针；硬编码具体报价日的旧测试在日更后可能暂时失败，需在后续任务中把 current 回归改为对冻结快照的显式版本测试。
- 三家公司政策目前由 `scripts/review_fixed_sample_admission.py` 显式登记，属于受控 adapter；新增公司必须新增政策与证据，不能自动推断。
- 研究准入证据目前验证的是结构与 Hash 可追溯性，不是重新证明财务事实或论点内容正确。
- 固定样本协议尚未迁移到 PostgreSQL；runtime JSON 仍为当前可追溯中间产物。
- 通用多模型运行器与持久化注册表仍需在扩样本前补齐；最小现金回报研究合同由 C2 完成。
- 全市场漏斗、Web 前端和券商接入均未实现，不属于 C1 回归范围。

## C2 验收基线

- C2 开始 HEAD：`357e080b69edfe135eaabcd5d31dc7331e05b9d3`，即 C1 提交 `C1-fixed-sample-admission-orchestration`。
- 未连接服务器、生产数据库或定时任务；未改动估值参数、原 Excel、计划任务或服务器 PTA 服务。

## C2 验收结果

C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/distribution.py`：`DividendRecord`、`DividendHistory`、`DistributionCapacity`、`DividendSustainabilityAssessment`、`DividendYieldSnapshot`、`DividendResearchResult` 与两个合法 yield 构建函数。
- `DividendRecord` 强制区分 proposed / approved / paid，并校验公告、批准、除息、支付和 known_at 的时序；`DividendHistory` 只接受 known_at 不晚于 as_of 的事实。
- `DistributionCapacity` 与 `DividendSustainabilityAssessment` 不依赖价格，按 ResearchProfile 识别；READY 能力及已知可持续性均不允许 UNKNOWN 置信度。
- `DividendYieldSnapshot` 只接受同证券 verified close quote，并强制 DPS / price / yield 可复算；当前收益率与周期正常化收益率是不同对象。
- `FixedSampleCompanyAdmission` 和公共入口 `review_fixed_sample()` 接受可选 typed `cash_return_result`，同时保留旧手工 status/explanation 兼容路径。
- `scripts/review_fixed_sample_admission.py` 使用同一合同读取已审查现金分配注册表和冻结研究/估值载荷，为三家公司生成 typed 结果。
- 旧茅台估值与三公司验收测试改为读取冻结的 2026-09-21 快照并校验固定 Hash，不再依赖 rolling current/latest 指针；干净 checkout 中这些冻结 runtime 快照缺失时显式 skip，不误报为当前生产失败。

三公司 typed 现金回报状态：

| 公司 | 历史分红 | 分配能力 | 可持续性 | Yield 快照 | 现金回报研究 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | PARTIAL | PARTIAL | UNKNOWN | 1 | PARTIAL |
| 000333 美的集团 | PARTIAL | UNKNOWN | UNKNOWN | 0 | PARTIAL |
| 601088 中国神华 | PARTIAL | UNKNOWN | UNKNOWN | 2 | PARTIAL |

三家公司均仍是研究状态；有历史派息不等于分红可持续性或现金回报能力完成。公共审查保持 `REUSABLE`、`production_valuation_available=false`、`human_confirmation_required=true`、`action=no_order`。

验证证据：

- Core Gate 同款离线清单：`124 passed`。
- 冻结历史验收：`tests/test_moutai_valuation_export.py` + `tests/test_three_company_unified_acceptance.py`：`9 passed`。
- Distribution + 固定样本 + 价格桥接 + quote 定向回归：`74 passed`。
- 新离线三画像 typed 合同测试覆盖 600519 / 000333 / 601088 的 quality_compounder / mature_manufacturing / cyclical_cash_return，确认三公司复用同一合同且均为 PARTIAL。
- 审查命令成功生成：`runtime/fixed-sample-admission-review-20260922T101442190293Z`，evidence SHA-256 `022cfd2f501a358ff843799ec227a832d5a23a370cbd3238f238f93f2f4ed0d0`。
- `compileall` 与 `git diff --check` 通过。
- 全量历史测试尝试运行至约 83% 后停在旧网络/外部 fixture 路径，未作为 C2 验收依据；C2 只冻结上述离线 Core Gate 和定向回归证据。

## 剩余风险与边界

- 本任务是共享领域合同和 fail-closed 类型验证，不是三家公司的股息可持续性研究、生产数据核验或未来派息承诺。
- 现金分配注册表目前是受控 JSON adapter；茅台 fiscal attribution、提案/批准日期、税费和结算时点仍列为显式 blocker。
- Distribution 对象尚未迁移到 PostgreSQL；runtime JSON 仍是当前可追溯中间产物。
- ShareholderYield、完整 distribution_profile、行业阈值和回购/稀释口径未实现，不属于 C2。

## M1 Gree dividend lifecycle completion: 2026-09-23

See `docs/m1-gree-dividend-lifecycle-20260923.md` for the complete receipt.
The Gree `000651` distribution package now has official CNINFO implementation
evidence for FY2024-final and FY2025-interim dividends, both paid records now
carry verified ex/payment dates, and the workbook includes READY trailing and
declared yield snapshots. The normalized scenario remains NOT_READY.

Published workbook SHA-256:
`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`.

## C3 验收基线

- C3 开始 HEAD：`d658b92 C2-minimal-distribution-research-contract`；工作树开始时的改动仅包含 C3 的 W1 治理校准。
- C2 的唯一建议后续任务“最小 Distribution 合同迁移到 PostgreSQL”已被 C3 吸收，但 C3 范围扩大到通用 Research Artifact 合同、Repository、Runner、Registry、Manifest、Batch、CI 与三公司 E2E。
- 数据库安全边界：`.env` 中的生产 `DATABASE_URL` 在本阶段不得连接；只使用 disposable/local/test PostgreSQL 或 GitHub CI 一次性实例。

## C3 验收结果

C3-RESEARCH-PLATFORM-FOUNDATION：`PASSED_FOR_FREEZE`。

提交序列：

```text
7903933 C3.1 governance and research artifact contract
6eee08e C3.2 repository and typed artifact round-trip
a89e269 C3.3 frozen runtime parity importer
b787b3e C3.4 profile-driven application research runner
365d845 C3.5 explicit valuation model registry contract
2bfe065 C3.6 versioned fixed sample policy manifest
33590bb C3.7 failure-isolated research batch contract
9d9231b C3.8 offline core and disposable postgres CI
13c5b03 C3.10 three-company frozen replay receipt
412564a C3.11 presentation boundary and expansion verdict
957243f C3.12 isolate postgres CI from ignored runtime data
fc49ab7 C3.13 align postgres import assertion with review scope
```

W1-W12 结果：

- W2-W3：新增 `sql/20260922_research_artifacts.sql`、`research_artifacts.py`、`research_artifact_codecs.py` 和 `research_artifact_repository.py`。新表 append-only，与旧混合语义 `valuation_results` 分离；round-trip、版本 head、Hash 与 fail-closed 均有测试。
- W4：`research_runtime_import.py` 把三公司 frozen runtime 核心 artifact 迁入 repository，输出 source path、source/database SHA-256 和 restored semantic status；缺失 `model_validity` 显式记为缺失，不伪造。
- W5：`research_application.py` 使用显式 `ResearchRunSpec`，按 Profile -> Router -> Model -> Validity -> PriceBridge -> Distribution -> CurrentStatus -> Repository 编排，不按 symbol 猜模型。
- W6：`valuation_router.py` 已表达三种 Profile 与三种模型/Facts 合同；未知 profile 为 `UNSUPPORTED`。
- W7：三公司 admission policy 迁入 `config/fixed-sample-manifest.json`，禁止交易键，loader 做 schema 与 profile/model 校验。
- W8：`research_batch.py` 隔离单公司 GAP/FAILED/UNSUPPORTED，支持 run_id、rule_version、时点和幂等输入 fingerprint。
- W9：GitHub Core Gate 保持离线，另增加 disposable PostgreSQL job；本地未使用生产 DSN。
- W10：`research_e2e_replay.py` 完成三公司 Manifest -> ResearchRunSpec -> Application -> Repository -> Batch replay。真实 frozen runtime 结果为 `all_semantics_matched=True`、`action=no_order`。新增命令行 `python scripts/run_three_company_research_replay.py`，输出独立 JSON 审计收据。
- W11：Application/Presentation 边界审查通过并记录技术债，见 [application-presentation-boundary.md](application-presentation-boundary.md)。Domain/Application 不依赖 Excel 或 PostgreSQL schema；旧 Excel publisher 尚未切换到新 Application result。
- W12：Expansion Readiness Verdict 为 `NOT_READY`，原因见 [fixed-sample-expansion-readiness-review.md](fixed-sample-expansion-readiness-review.md)。核心 pipeline 可复用，但缺少 manifest-driven facts/assumptions/quote input adapter，且 replay adapter 仍含茅台 symbol 专用分支。

验证证据：

- Offline Core Gate 全清单：`176 passed`。
- 新增三公司 replay 自包含 fixture：三种 Profile、三种模型、`no_order`、美的/神华 `not_ready`、神华 current/normalized yield 区分和 Hash 篡改 fail-closed。
- PostgreSQL integration 在本机无 disposable DSN，`4 skipped`；GitHub CI 中由一次性 PostgreSQL service 验证 migration、repository round-trip、frozen runtime import 和三公司 replay。最终验收运行 `35727542158` 的离线 Core 与 disposable PostgreSQL job 均为 success。
- 本机真实 frozen runtime 命令验证：`all_semantics_matched=True`、`action=no_order`、收据约 193KB。
- `compileall` 与 `git diff --check` 通过。
- 未连接生产数据库、未修改旧 `valuation_results`、未改动原 Excel、未调整估值参数、未触碰服务器 PTA 项目或计划任务。

## C3冻结时的后续建议（历史，已被M1吸收）

下面保留C3当时的建议，不是当前执行指令。当前唯一待启动目标见本文开头与current-stage-goal.md；adapter只是M1的前置工作包。

```text
NEXT TASK: C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER
```

先移除三公司 replay 中的茅台 symbol 专用分支，建立 versioned per-company input descriptor，再以离线 fixture 和 disposable PostgreSQL replay 验收。验收前不新增第四家真实公司，也不自动扩样本。

## 2026-09-24 M2 Verification v2 / Checkpoint A 重提

M2 Verification v1 已标记 `SEMANTICALLY_SUPERSEDED`。v2 使用独立的四通道
`ChannelVerificationPolicy`，不再允许
`PENDING_DEEP_RESEARCH + evidence_count > 0 -> VERIFIED_FOR_DEEP_RESEARCH`。
对冻结的 18 条 LEAD 重跑后的真实结果如下：

```text
VERIFIED_FOR_DEEP_RESEARCH = 0
REJECTED_AFTER_VERIFICATION = 13
INSUFFICIENT_EVIDENCE = 5
UNSUPPORTED = 0
PIT = PASS
MACHINE_STATUS = MACHINE_CHECKS_PASS
```

分通道结果：

| 通道 | 进入深研 | 否决 | 证据不足 |
| --- | ---: | ---: | ---: |
| Quality | 0 | 0 | 0 |
| Dividend / Cash Return | 0 | 3 | 3 |
| Value | 0 | 5 | 1 |
| Cyclical | 0 | 5 | 1 |

旧 v1 中被写成 VERIFIED 的 `002327 富安娜`、`002867 周大生`、`600011 华能国际`
现在均按 v2 fail-closed 为 `INSUFFICIENT_EVIDENCE`。0 个 VERIFIED 是允许且诚实的
结果，不降低研究标准，也不构成全市场“没有质量公司”的判断。

关键冻结产物：

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| M2 v2 report | `runtime/m2-channel-verification-20260924-v2/report.json` | `310d56e408655c7c46ef510a4ce3aab44d99ab9aeb021c9ddd41f140a2fb1653` |
| M2 v2 manifest | `runtime/m2-channel-verification-20260924-v2/manifest.json` | `520d175d5a7696b970c091c88be9e8b5996a7627a58828594671f524e360aabe` |
| M7 Daily v3 workbook | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx` | `d423ef1ab0114f97e4a20d2f7f770b85e74b3764d6484b63d2fec03c9da82718` |
| M7 Daily v3 manifest | 同名 `.m7-daily-workbench-manifest.json` | `31f918dbf43b0d9b7faaf1f933dace64c1b449d32b675d1058d330e00161e75b` |

M7 Daily v3 的 WPS 只读验证 `passed`：10 个可见页、2 个隐藏页、公式错误扫描和
禁词扫描均通过，打开前后工作簿与 canonical 的 Hash 未变化。同名候选已复制到
WPS 云盘 `价投跟踪`，与仓库文件逐字节一致；没有覆盖 canonical 原表。

本轮新增版本化、只追加、Hash 绑定的
`HumanMilestoneReviewReceipt`。人工结论只记录为：

```text
M2_CHECKPOINT_A = NOT_APPROVED_PENDING_VERIFICATION_V2
M3_NEGATIVE_CARDS = PASS
M3_CHECKPOINT_B = PARTIAL_NOT_APPROVED
M5_1225578520 = NOT_MATERIAL
M7_SEMANTIC_STRUCTURE = PASS
M4_PRIVATE_INPUT = PENDING
M6_AUTHORIZATION = PENDING
M7_FINAL_UX = PENDING
```

Checkpoint A 重提包目录为
`runtime/m2-checkpoint-a-human-resubmission-20260924-v2`。人工收据
`receipt.json` 的 SHA-256 为
`5a29fad3af4b6c3521236aee6d7cd70884287b318b20d3c95535ba974567bd0a`，
Checkpoint A packet 的 SHA-256 为
`c5317f641a8cf56ee2bfddaf7910d0f6b0088c8a331d1c07255094bd416efc13`。
M5 的 `NOT_MATERIAL` 已绑定
`announcement_id=1225578520` 与 PDF SHA-256
`7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c`。

以上内容不表示 Checkpoint A、Checkpoint B 或 M7 已签收；`action=no_order`，
没有生产操作、数据库迁移、调度、通知、券商连接或 PTA 项目改动。M2 状态保持
`PENDING_HUMAN_REVIEW`，等待用户重新复核 Checkpoint A。

## 2026-09-24 M2 Checkpoint A 人工签收与 M2 收口

用户完成 Checkpoint A 人工复核并给出正式结论：

```text
M2_CHECKPOINT_A = HUMAN_PASS
```

新的 append-only 人工收据为 sequence=2，不覆盖 sequence=1 的
`NOT_APPROVED_PENDING_VERIFICATION_V2` 历史收据，并绑定其 SHA-256：

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 人工收据 | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/receipt.json` | `9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20` |
| Checkpoint A 验收包 | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/checkpoint-a-packet.json` | `b880b74752362deccd1991d23a43f7347f7e5a8348e0ae6ca0603a5931e8f306` |
| 验收 manifest | `runtime/m2-checkpoint-a-human-acceptance-20260924-v3/manifest.json` | `a11552c0dd343564a6024c1feeadcfbca83f97d420aa5519ed4533e09937d501` |

M2 正式状态更新为：

```text
M2 = DONE
M2_CHECKPOINT_A = HUMAN_PASS
OVERALL_PRODUCT = PARTIAL
action = no_order
```

用户同时保留两项非阻断方法债，不影响 M2 收口：

```text
BL-20260924-001: Dividend payout ratio / cash-conversion 语义校正
BL-20260924-002: Value EV/EBIT 或 Profile 等价指标
```

详细条件见
[m2-non-blocking-method-debt-20260924.md](m2-non-blocking-method-debt-20260924.md)。
M3 strict contemporaneous-rule Historical PIT 仍为 `NOT_PROVEN`；Checkpoint B、
M4 私有输入、M6 授权和 M7 用户验收均不因 Checkpoint A 通过而自动签收。下一工作
包回到原总 Goal：继续 M3 Decision Review / Checkpoint B，再按依赖推进
M4/M5、M6、M7。

## 2026-09-24 M3 重建证据连续性工作包

在冻结的 600519 / 2024-06-21 追溯重放基础上，新增一个与真实 Entry、Journal 和
人工决策完全隔离的官方披露连续性候选。它只重建披露数值的算术演变，不签发研究
批准、价格结论、持有决定或执行动作。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 工作簿 | `runtime/m3-reconstructed-continuity-20260924T083028Z/A股价值投资_M3重建证据连续性候选_20260924.xlsx` | `719725a31749558d21070a1211862e2811d7b688082697ad9faad19ace930ccb` |
| Trace | `runtime/m3-reconstructed-continuity-20260924T083028Z/trace.json` | `f49bc61c302e11c70e6ee954768d59389f17b9c2933a9b02364439be74d99cc6` |

边界固定为 `RECONSTRUCTED_EVIDENCE_ONLY`、
`RETROSPECTIVE_RESEARCH_EXTENSION`、`strict_contemporaneous_rule_pit=NOT_PROVEN`、
`actual_entry_present=false`、`human_decision=null`、`action=no_order`。
新增六个展示页：`00_重建边界`、`01_历史基准`、`02_官方披露演变`、
`03_一致性观察`、`04_阻断与结论`、`05_来源哈希`。该候选不是 Checkpoint B；
Checkpoint B 及后续人工/生产验收继续按原边界保持待办。详细来源和边界见
[m3-reconstructed-evidence-continuity-20260924.md](m3-reconstructed-evidence-continuity-20260924.md)。

## 2026-09-24 M5 贵州茅台真实披露队列扩展

在 M3 重建证据连续性候选完成后，继续原总 Goal 中依赖已满足的 M5 离线工作：
使用既有 `scripts/build_m5_disclosure_queue.py` 重建 600519 的真实 CNINFO
公告窗口，不修改既有 3 家公司队列、reconciliation 或 canonical。

- 窗口：`2026-06-01` 至 `2026-09-09`，检索时间
  `2026-09-24T08:47:15Z`。
- 结果：16 条公告，9 条待人工复核，0 条来源缺失，覆盖状态 `COMPLETE`。
- 公开工作簿：
  `A股价值投资_M5真实披露待复核队列_600519_20260924.xlsx`，
  SHA-256
  `02cd3499ed4e805f2d76d0f7f0aba89d02be123b02ae3723b43e80f1509eaa3c`。
- WPS 只读验证 `passed`；WPS 云盘同名副本与仓库文件逐字节一致。
- 标题规则只生成待复核候选；9 条公告仍由用户逐条给出
  `EventMaterialityDecision`，系统不自动判定重大性或产生事件。
- `action=no_order`；不构成 Checkpoint C、生产调度、通知或 M6 运营验收。

九条待复核公告和原件 Hash 见
[m5-600519-disclosure-review-20260924.md](m5-600519-disclosure-review-20260924.md)。

公开工作簿 WPS 云盘全量字节审计已重跑为 `27/27 MATCH`；对应 GitHub Core
Research Gates run `35977515495` 为 `success`。新增文件仍未改变任何公告材料性
结论，所有候选继续等待人工决策。

## 2026-09-24 M7 Daily v4：Checkpoint A 后展示闭环

M2 收口后，继续原总 Goal 中依赖已满足的 M7 展示工程，不覆盖已冻结的 v3 候选或
canonical。新 v4 候选把 M3 重建证据连续性和 600519 真实披露待复核队列接入既有
10+2 页每日工作台，并把 M2 状态在展示层更新为 `DONE / HUMAN_PASS`。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| M7 Daily v4 | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.xlsx` | `569adf26fece3b45666138c050776b40cb077f0e0b9f498a0dd77445a83c2a59` |
| manifest | 同名 `.m7-daily-workbench-manifest.json` | `f8b461a66f7f5a3274fc517e6232f37848f3d9dead4d109fea8fcda05ceae106` |

- 新接入层保持 `RECONSTRUCTED_EVIDENCE_ONLY`、`strict PIT=NOT_PROVEN`、
  9 条待人工复核、`action=no_order`。
- WPS 只读验证 `passed`；WPS 云盘同名候选与仓库文件逐字节一致。
- 定向回归 `14 passed`；canonical SHA-256 保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 隔离 basetemp 全量离线回归：`2403 passed、6 skipped、1 failed`；唯一失败仍是
  仓库既有 `test_moutai_current_valuation_admission.py` 的
  `daily_simulation_policy_implemented` runtime 指针断言，不在本轮 M7 改动路径内。
- 公开工作簿 WPS 云盘全量字节审计更新为 `28/28 MATCH`。
- 详细边界见
  [m7-daily-workbench-v4-post-checkpoint-a-20260924.md](m7-daily-workbench-v4-post-checkpoint-a-20260924.md)。

本候选不构成 Checkpoint B/C/D、真实 IPS/组合、生产授权、M6 运营验收或 M7
最终交付；总 Goal 继续按原依赖推进。

## 2026-09-24 M3 Checkpoint B 版本化人工复核包

M2 Checkpoint A 收口后回到原总 Goal 的 M3 主线，新增只读的 Checkpoint B 人工
复核包生成器，把三份 M3 候选、机器审计、strict PIT 证据和 M2 append-only 收据
合并为同一版本化入口。生成器只汇总证据，不写人工收据，不把 Checkpoint B 标为
通过，不生成 Entry、Journal、个人组合、仓位或订单。

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| Checkpoint B packet | `runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-packet.json` | `fab538fb283b55b449d6c52be908216cbe2df06880a2c66848901371a15c7eb4` |
| 人工复核说明 | `runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-review.md` | `b7d0b16cebb6c98537865a878764617a1c102fb3508cd6564022540966a2c712` |
| manifest | `runtime/m3-checkpoint-b-human-review-20260924-v1/manifest.json` | `76082bb8b359964445954293495208cacf385a44374d717629a77ca5f6f23de4` |

- 三张卡保持 `000651 / 600741 / 600887` 均为 `INSUFFICIENT_RESEARCH`、
  `RESEARCH_INCOMPLETE`、`action=no_order`。
- M3 三份审计保持 m3c7 / owc7 / hoc7 `PENDING_HUMAN_REVIEW`。
- strict contemporaneous-rule Historical PIT 保持 `NOT_PROVEN`。
- M2 Checkpoint A 收据保持 sequence=2 与固定 Hash，没有覆盖历史收据。
- 新增定向回归 `2 passed`，并纳入 GitHub Core Research Gate。

用户实际完成三份候选阅读、逐卡复述阻断/反证/重开条件并明确给出
`M3_CHECKPOINT_B=HUMAN_PASS` 后，才会新增下一份 append-only 人工收据；当前包
不构成 Checkpoint B 通过或后续阶段升级。

## 2026-09-24 M5 600519 Hash 对账与空白人工回填表

在 Checkpoint B 等待人工签收期间，继续原总 Goal 中依赖已满足的 M5 离线工作。对
600519 / 2026-06-01 至 2026-09-09 的真实 CNINFO 队列执行既有人工台账 Hash 对账，
并生成九条公告的空白人工材料性回填表。

- 对账结果：当前候选 9、历史结转 0、待人工复核 9、Hash 冲突 0。
- 对账收据：
  `runtime/m5-600519-human-review-reconciliation-20260924-v1/reconciliation.json`
  SHA-256
  `5b9cea760461fb6821777474b05878a7682f08d85cdcbf5a78b917365e4f27ea`。
- 空白回填表：
  `A股价值投资_M5真实披露人工复核回填_600519_20260924.xlsx`
  SHA-256
  `6451f986c81c4db1277f795e6a0666c22810728d621524070935b21edc4e7f0c`。
- WPS 只读验证 `passed`；WPS 云盘同名副本与仓库文件逐字节一致。
- 判定列和复核说明列均从空值开始，`action=no_order`。
- 公开工作簿 WPS 云盘全量字节审计更新为 `29/29 MATCH`，收据
  `runtime/public-workbook-wps-audit-post-m3-m5-20260924/receipt.json`。

本工作包不判定任何公告重大性，不产生 M5 事件、依赖失效、调度、通知或 M6 运营
验收；九条公告仍由用户逐条给出 `EventMaterialityDecision`。
