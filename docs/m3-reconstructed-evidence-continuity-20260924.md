# M3 重建证据连续性工作包：2026-09-24

更新：2026-09-24。本文件记录 600519 在冻结历史基准
`2024-06-21` 之后的官方披露连续性重建。它不是 Checkpoint B，不是真实
Entry/Journal，不是个人决策，也不是研究批准、价格结论或交易建议。

## 结论边界

```text
NAMESPACE = RECONSTRUCTED_EVIDENCE_CONTINUITY
CONCLUSION = RECONSTRUCTED_EVIDENCE_ONLY
STRICT_CONTEMPORANEOUS_RULE_PIT = NOT_PROVEN
RULES = RETROSPECTIVE_RESEARCH_EXTENSION
ACTUAL_ENTRY_PRESENT = false
HUMAN_DECISION = null
REQUIRES_HUMAN_REVIEW = true
ACTION = no_order
```

本工作包只比较官方披露中的可复算数值变化，例如归母净利润、归母净资产、
基本每股收益及披露中的可比半年度口径。算术方向不等于原始投资论点已经兑现或
破坏，也不用于生成 BUY/ADD/HOLD/REDUCE/EXIT 或仓位结论。

## 冻结基准与可复核事实

- 基准日：`2024-06-21`。
- 重放 ID：`m3-historical-research-replay-600519-2024-06-21-v1`。
- 规则版本：`moutai-pe-mid-paper-contract-v2-2025-extension`。
- 规则登记时间：`2026-09-12T05:27:47+00:00`，晚于基准日，因此只能标记为
  `RETROSPECTIVE_RESEARCH_EXTENSION`。
- 基准报价：`1471.00 CNY`。
- 2024 年度每股现金分红：`30.876 CNY/share`。

披露中的基础事实：

| 报告期 | 归母净利润 | 归母净资产 | 基本每股收益 |
| --- | ---: | ---: | ---: |
| FY2023 | 74,734,071,550.75 | 215,668,571,607.43 | 59.49 |
| FY2024 | 86,228,146,421.62 | 233,105,984,399.47 | 68.64 |
| FY2025 | 82,320,067,101.68 | 244,637,811,032.18 | 65.66 |
| 2026H1 | 44,516,880,421.86（可比） | 未用于本工作包单独重述 | 未用于本工作包单独重述 |

这些数值用于来源和算术审计，不是对公司的估值或买卖判断。

## 六个工作表

| 工作表 | 内容 |
| --- | --- |
| `00_重建边界` | Trace ID、命名空间、历史基准、同期规则状态、无真实 Entry、`action=no_order` |
| `01_历史基准` | 由冻结重放绑定的事实与报价 |
| `02_官方披露演变` | 各期原始披露中的数值及简单算术变化 |
| `03_一致性观察` | 只描述数值趋势，不签发论点裁决 |
| `04_阻断与结论` | `RECONSTRUCTED_EVIDENCE_ONLY`、`no_order` 与阻断项 |
| `05_来源哈希` | 每条来源的本地原件路径、来源 URL 和 SHA-256 |

## 来源与 Hash

| 来源 ID | 披露编号 / 文件 | SHA-256 |
| --- | --- | --- |
| `annual-2023` | `cninfo:1219506510` | `2125ff97a452ea79b0d784e2432f7d224b6aecc330b644b593477d69e22f4ed1` |
| `annual-2024` | `cninfo:1222993920` | `5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30` |
| `annual-2025` | `cninfo:1225114741` | `474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288` |
| `interim-2026-h1` | `cninfo:1225475868` | `0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6` |
| `distribution-2024` | `cninfo:1220324741` | `626888864d607e51f11f48df3368c496c7dec832f6cdd90244336195b1ef2972` |
| `price-2024` | authenticated price file | `174ab4120f375f8854d843dd2b9f76292b9a513873cb30fcb581ed7ba23083ff` |
| `frozen-replay` | `runtime/m3-historical-research-replay-20260924-v1/replay.json` | `2822dd786a40433ed03eac1e741a82a219cc9c76196b267e3a76290e53a141b9` |
| `equity-evidence` | `runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T115049Z/evidence.json` | `efc4dc37d81e9d4bf54930a5c2bf7cd50305b7b7ce808531ef4bc4138f80891b` |
| `latest-evidence` | `runtime/company-research/600519-latest-20260909T033748190833Z/evidence.json` | `95585241cef0fe72b8edcea6860759e056defce7ff8d4ebd5d23b40412d06937` |
| `reviewed-distributions` | `docs/reviewed-cash-distributions.json` | `ab15bdef761774593cd0a8ea96effe1cefa51424643673de492366c9c492312f` |

## 候选产物与验证

- 工作簿：
  `runtime/m3-reconstructed-continuity-20260924T083028Z/A股价值投资_M3重建证据连续性候选_20260924.xlsx`
- 工作簿 SHA-256：
  `719725a31749558d21070a1211862e2811d7b688082697ad9faad19ace930ccb`
- Trace SHA-256：
  `f49bc61c302e11c70e6ee954768d59389f17b9c2933a9b02364439be74d99cc6`
- 定向测试：`tests/test_m3_reconstructed_evidence_continuity.py`。
- WPS 只读验证：
  `scripts/verify_m3_reconstructed_evidence_wps.ps1`。
- WPS 只读验证收据：
  `runtime/m3-reconstructed-evidence-wps-20260924/receipt.json`，
  SHA-256
  `e4c4c728251d4ef6099322e484b560f5d13f3054be8212f2a59f5d8542907560`。
- 新测试已纳入 GitHub Core Research Gate 的离线任务。

工作簿仅作为候选发布，不覆盖 canonical 原工作簿，不生成私人组合、仓位、通知、
调度、数据库迁移或订单。
