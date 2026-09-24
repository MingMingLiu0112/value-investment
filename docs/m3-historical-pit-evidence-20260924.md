# M3 Strict Historical PIT Evidence Search: 2026-09-24

更新：2026-09-24。本文件记录对“是否存在真实 contemporaneous-rule Historical
Research Replay”的仓库证据检索，不修改研究结论，不创建交易、仓位或订单。

## 结论

```text
STRICT_CONTEMPORANEOUS_RULE_PIT = NOT_PROVEN
```

当前仓库不能合法证明任何一条 M3 Historical Research Replay 同时满足：

```text
当时可知 Facts
当时可知 Filings
当时 Quote
当时已注册 Rule Version
```

唯一可重放的 600519 / 2024-06-21 案例满足事实、公告和行情 PIT，但其 Median-PE
规则于 2026-09-12 才在本仓库注册，只能标记为
`RETROSPECTIVE_RESEARCH_EXTENSION`。因此该案例仍为诚实的追溯研究重放，不是
strict contemporaneous-rule PIT。

## 检索证据

- 当前 Git 仓库首个提交：`61710f6`，提交时间 `2026-09-01`。
- 目标 replay 日期：`2024-06-21`。
- 已登记规则版本：`moutai-pe-mid-paper-contract-v2-2025-extension`。
- 规则登记时间：`2026-09-12T05:27:47+00:00`。
- 重放收据：`runtime/m3-historical-research-replay-20260924-v1/replay.json`。
- 重放规则状态：`RETROSPECTIVE_RESEARCH_EXTENSION`。
- 重放结果：`WAIT`、`future_facts_used=false`、
  `future_rule_version_used=true`、`action=no_order`。
- 仓库检索未发现任何 `runtime/strategy-validation` 历史制品使用
  `CONTEMPORANEOUS_RULE`；现有 `registered_at` 均为 2026-09-09 或更晚。
- `CONTEMPORANEOUS_RULE` 目前只出现在领域枚举、测试和纠偏文档中，用于表达
  合法登记状态，不代表当前已有真实同期规则制品。

## 与人工审查验收项的关系

2026-09-24 人工审查验收标准第 11 条要求“至少一条真实 Historical PIT Decision
Replay”。在缺少可验证的历史规则登记证据前，该项保持：

```text
NOT_ACHIEVED
```

不伪造 2024 年规则登记，不把追溯 Median-PE 扩展写成当时规则，也不为了满足数量
制造正向决策。

## 解除方式

需要用户提供至少一项可独立验证的、早于目标 replay 日期的规则登记证据：

```text
带日期的规则文件或版本记录
带日期的公开文档、研究笔记或源码提交
可核验的来源 URL 与 SHA-256
```

或者改用仓库中真实存在、且登记日不晚于目标决策日的另一个历史时点。证据补齐前，
当前 retrospective replay 继续作为唯一诚实可用的版本，`action=no_order`。
