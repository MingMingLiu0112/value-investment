# M3 Checkpoint B 只读逐卡复核明细：2026-09-24

本文件记录 M3 Checkpoint B 的人工理解辅助包，不构成 Checkpoint B 通过、研究批准、
Entry、Journal、仓位或订单。

人工结果（2026-09-24）：三张卡的可理解性与无错误 BUY/ADD 子检查通过；整体
`M3_CHECKPOINT_B` 因 strict contemporaneous-rule PIT 未证明保持 `PARTIAL`。
本文以下 `PENDING_HUMAN_REVIEW` 文本是复核前历史快照。

## 产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| JSON | `runtime/m3-checkpoint-b-review-detail-20260924-v2/review-detail.json` | `0d9f938b9fd2c3d003e8d035cd0912f7187ebed63f5f4e089103994b6d8c7a42` |
| Markdown | `runtime/m3-checkpoint-b-review-detail-20260924-v2/review-detail.md` | `fab6040c893ec37752393b624fa07c22e918c08fc53e7e9b96e5f821a1ce9313` |
| manifest | `runtime/m3-checkpoint-b-review-detail-20260924-v2/manifest.json` | `a50eb069c92fb491999731aab2d61216f91c6ae0bdc86e1c85ce1aa804db44ba` |

三张卡分别绑定 `000651`、`600741`、`600887` 的冻结研究档案。明细展示反证、
论点破坏条件、下一次事件、研究缺口和来源 Hash，供用户理解原候选；不改变原候选
或 canonical 工作簿，不代替用户在 WPS 中阅读和签收。

```text
namespace=READ_ONLY_REVIEW_AID
checkpoint_b_status=PENDING_HUMAN_REVIEW
strict_contemporaneous_rule_pit=NOT_PROVEN
action=no_order
```

生成入口：`python scripts/build_m3_checkpoint_b_review_detail.py`。
