# M3 Checkpoint B 人工复核包：2026-09-24

更新：2026-09-24。本文件由 `scripts/build_m3_checkpoint_b_review_packet.py` 只读生成，
只汇总 Hash 固定的 M3 证据并列出用户待办；代理不能替用户签收 Checkpoint B。

```text
goal_id=VALUE-INVESTMENT-M2-M7-INITIAL_ASSISTED-USE
action=no_order
checkpoint_b_status=PENDING_HUMAN_REVIEW
strict_contemporaneous_rule_pit=NOT_PROVEN
M2_CHECKPOINT_A=HUMAN_PASS
```

## 三份复核对象

| 产物 | SHA-256 |
| --- | --- |
| `A股价值投资_M3决策卡候选_20260924.xlsx` | `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d` |
| `A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx` | `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3` |
| `A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx` | `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d` |
| canonical 工作簿 | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |

三张卡均为负向且 `action=no_order`：

| 证券 | 名称 | 系统状态 | 原因类别 | 组合输入 | 动作 |
| --- | --- | --- | --- | --- | --- |
| 000651 | 格力电器 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | 缺失 | `no_order` |
| 600741 | 华域汽车 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | 缺失 | `no_order` |
| 600887 | 伊利股份 | `INSUFFICIENT_RESEARCH` | `RESEARCH_INCOMPLETE` | 缺失 | `no_order` |

## 用户要确认什么

1. 三家公司当前均为研究证据不足，不是“看起来便宜”的正向候选。
2. 每张卡都能说明缺失的研究、组合输入或原始 Entry 为何阻断正向决策。
3. 至少抽查一条来源 Hash，并打开至少一条证据引用链接。
4. 全文没有买入、加仓、减仓、目标仓位或订单列。
5. 历史链页面明确 `namespace=simulated`，不是真实交易或收益证据。
6. strict contemporaneous-rule Historical PIT 保持 `NOT_PROVEN`，没有伪造规则登记证据。
7. canonical 工作簿未被任何候选覆盖，三份候选均保持未发布状态。
8. 能逐卡复述最强阻断、反证和重新打开研究的触发条件。

## 机器与治理证据

只读复核明细 v2 位于
`runtime/m3-checkpoint-b-review-detail-20260924-v2/review-detail.md`，它逐卡绑定
冻结研究档案中的反证、论点破坏条件、下一次事件和研究缺口；v1 因 Markdown 展示
缺陷被 v2 替代。该明细不改变三份候选 Hash，不签收 Checkpoint B。

M3 三份审计分别保持 `m3c7 / owc7 / hoc7 = PENDING_HUMAN_REVIEW`，其余机器门为
`DONE`。M2 Checkpoint A append-only 收据仍为 sequence 2，Hash 为
`9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20`。
strict PIT 收据为
`9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c`。

本包只要求用户给出 `M3_CHECKPOINT_B=HUMAN_PASS` 或具体不通过原因；通过后才允许
新增 append-only 人工收据，不自动升级为 M4 READY、M6 AUTHORIZED 或 M7 交付。

运行时可复核包位于：

```text
runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-packet.json
runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-review.md
runtime/m3-checkpoint-b-human-review-20260924-v1/manifest.json
```
