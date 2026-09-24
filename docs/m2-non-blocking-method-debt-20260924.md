# M2 非阻断方法债 Backlog

更新：2026-09-24。M2 Checkpoint A 已由用户正式记录为
`M2_CHECKPOINT_A = HUMAN_PASS`。以下两项是用户在签收时明确保留的非阻断方法债，
不改变 M2 收口，也不阻塞 M3-M7 原总 Goal。它们只在对应通道第一次准备产生
`VERIFIED_FOR_DEEP_RESEARCH` 前强制执行。

| ID | 通道 | 前置条件 | 状态 |
| --- | --- | --- | --- |
| `BL-20260924-001` | Dividend / Cash Return | 校正 payout ratio 与 cash-conversion 语义，补真实派息率证据 | OPEN |
| `BL-20260924-002` | Value | 评估并补 `EV/EBIT` 或 Profile 适用的等价估值指标 | OPEN |

## BL-20260924-001

```text
blocking = false
status = OPEN
milestone = M2
channel = dividend_cash_return
```

在 Dividend / Cash Return 通道第一次产生
`VERIFIED_FOR_DEEP_RESEARCH` 前，必须让验证政策能够区分：

- 宣布、实际支付与一次性股息；
- 历史派息率证据与预测派息率；
- 基于已实现现金流的覆盖，而不是把单一财报现金流字段直接当作 cash-conversion。

验收时每个计算输入必须绑定报告期、来源 URL、抓取时间和 SHA-256，不能仅以字段
非空代替证据。

## BL-20260924-002

```text
blocking = false
status = OPEN
milestone = M2
channel = value
```

在 Value 通道第一次产生 `VERIFIED_FOR_DEEP_RESEARCH` 前，验证政策必须包含：

- `EV/EBIT`；或
- 对当前 Profile 更适用的等价资本结构/估值指标，并书面说明为什么等价；
- 对应指标的报告期、来源、口径和可用时间边界。

不得仅凭单期 PE/PB 或隐含 ROE 把 Value 线索升级为已验证深研候选。
