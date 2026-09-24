# M3 Checkpoint B 人工复核结果：2026-09-24

更新：2026-09-24。用户已完成三张负向决策卡的实际阅读、逐卡语义复核和边界确认。
本记录只登记人工结论，不把整体 Checkpoint B 升级为通过，不生成 Entry、Journal、
个人组合、仓位或订单。

```text
M3_NEGATIVE_CARD_HUMAN_REVIEW = PASS
M3_HUMAN_UNDERSTANDABILITY = PASS
M3_NO_FALSE_BUY_ADD = PASS

M3_CHECKPOINT_B = PARTIAL
M3_BLOCKER = STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN

M4_PERSONALIZED_ACCEPTANCE = PENDING_USER_PRIVATE_INPUT
M6_PRODUCTION_AUTHORIZATION = NOT_YET
action = no_order
```

## 人工确认范围

三张卡均保持研究证据不足，且没有因“看起来便宜”而生成正向决策：

| 证券 | 名称 | 系统状态 | 原因类别 | 动作 |
| --- | --- | --- | --- | --- |
| 000651 | 格力电器 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | `no_order` |
| 600741 | 华域汽车 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | `no_order` |
| 600887 | 伊利股份 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | `no_order` |

用户确认三张卡没有 BUY / ADD、目标仓位或订单；现有历史链为模拟研究链，不是实际
交易或收益证据。三项独立子检查已通过，但这不构成整体 Checkpoint B 通过，因为
strict contemporaneous-rule PIT 仍没有可核验的历史规则登记证据。

## Append-only 人工收据

新的收据是原有 `HumanMilestoneReviewReceipt` 链的 sequence 3，绑定 sequence 2
收据文件 Hash，不覆盖历史：

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| sequence 3 人工收据 | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/receipt.json` | `933f81ace48da1119d6afb26c9fc92ddb0e8de142a83d043df8f43122ea62c98` |
| partial 验收包 | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/checkpoint-b-partial-packet.json` | `27c489828cf116e5b1d97473f6cc072fb6bace9ad9cfa396665c7039c56fab7a` |
| manifest | `runtime/m3-checkpoint-b-human-acceptance-20260924-v1/manifest.json` | `f418f7a36c2635507c3c603a3497e4f46e2822c577ef3380996274791c51255a` |

前序 sequence 2 收据 Hash 保持：

```text
9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20
```

收据中的 `supplemental_decisions` 精确记录三项子检查及阻断项；`M3_CHECKPOINT_B`
明确为 `PARTIAL`，不写成 `HUMAN_PASS`。

## Strict PIT Blocker

600519 / 2024-06-21 Historical Research Replay 的事实、公告和行情满足 PIT，但使用的
规则版本是后来注册的 `RETROSPECTIVE_RESEARCH_EXTENSION`，
`future_rule_version_used=true`。因此该案例不能满足 strict contemporaneous-rule
PIT，结论保持 `NOT_PROVEN`。

不伪造历史规则登记证据，也不降低 PIT 标准。该 blocker 不阻止 M4/M5 中依赖已满足的
离线工程继续，但在未来真实规则版本和后续真实事件形成 contemporaneous chain 前，
M3 Checkpoint B 保持 `PARTIAL`。

## 后续边界

- M4 可以继续所有不依赖私人 IPS、持仓、现金或风险偏好的工程、隐私、反例和恢复测试；
  不得编造个人化输入。
- M5 可以继续真实公告材料性队列、人机复核、依赖失效、有界重算、run-once、恢复和
  去重工程；九条 600519 公告仍等待用户逐条 `EventMaterialityDecision`。
- M6 仍只允许 preflight、dry-run、backup/restore、health、emergency-stop 和 shadow
  tooling；不得迁移生产数据库、启用调度/通知或导入真实账户。
- 不新增 M8、新 Roadmap 或新的策略/行业扩展。

```text
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Price Drop != A
Margin of Safety != Position Size
```
