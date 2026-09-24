# M7 Daily Workbench v4：Checkpoint A 后展示候选

更新：2026-09-24。本候选是 M2 Checkpoint A 人工签收后的 M7 只读展示层后继版本，
不覆盖 v3 或 canonical，不构成 Checkpoint B-D、M7 最终签收或真实可用证明。

## 交付物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 工作簿 | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.xlsx` | `569adf26fece3b45666138c050776b40cb077f0e0b9f498a0dd77445a83c2a59` |
| manifest | `A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.m7-daily-workbench-manifest.json` | `f8b461a66f7f5a3274fc517e6232f37848f3d9dead4d109fea8fcda05ceae106` |

- 工作表保持 10 个可见页和 2 个隐藏页，不改变 M7 Daily Workbench 的页面契约。
- 构建入口：`scripts/build_m7_daily_workbench_post_checkpoint_a.py`。
- WPS 只读验证：
  `runtime/m7-daily-post-checkpoint-a-wps-20260924/receipt.json`，`passed`。
- WPS 云盘同名候选与仓库文件逐字节一致。

## 相对 v3 的变化

- M2 状态从历史展示层的 `PENDING_HUMAN_REVIEW` 更新为
  `DONE / HUMAN_PASS`；这只记录用户已完成 Checkpoint A，不扩大后续验收。
- `03_决策复核` 和 `08_买卖逻辑与历史` 接入 600519 的
  `RECONSTRUCTED_EVIDENCE_ONLY` 披露连续性，明确
  `strict contemporaneous-rule PIT=NOT_PROVEN`、无真实 Entry、无人工决策。
- `06_事件与预警` 接入 600519 的真实 CNINFO 队列：16 条公告、9 条待人工复核、
  0 条来源缺失；只登记标题规则候选，不代理公告重大性判断。
- `09_审计与证据` 增加 M3 重建 trace/workbook 和 600519 M5 队列源数据、公开
  工作簿及 WPS 收据的 Hash 审计项。

## 输入绑定

新接入的输入均按冻结 SHA-256 校验：

| 输入 | SHA-256 |
| --- | --- |
| M3 重建 manifest | `7fc43957372adde5a0040e28017b815efe0e8cf64b00b2c3497d821d4ac2bf51` |
| M3 重建 trace | `9e2b5f8e386e9836b1af58234606be3e86327e98dbc00d3cd9e29e5637336103` |
| M3 重建 input payload | `61debe108eb95cb2e992c0f3caea5431a308cf78c0384d90d863e13667fd9896` |
| M3 重建工作簿 | `719725a31749558d21070a1211862e2811d7b688082697ad9faad19ace930ccb` |
| M5 600519 队列源数据 | `026a6e3502b15d8e38e8abdc8af41007a3f2874740d45514067153bd83983915` |
| M5 600519 公开工作簿 | `02cd3499ed4e805f2d76d0f7f0aba89d02be123b02ae3723b43e80f1509eaa3c` |
| M5 600519 WPS 收据 | `b49405347f643419cb69cd866378ffbcf5eee84273018367cb62fb569c3d5ec6` |

构建器同时复算 M3 输入 payload 的策略 Hash，与 manifest 中
`trace_sha256=f49bc61c302e11c70e6ee954768d59389f17b9c2933a9b02364439be74d99cc6`
一致；任何来源变化都会失败关闭。

## 验证

- M7 Daily Workbench 定向回归：14 passed。
- WPS 实际只读打开：10 个可见页、2 个隐藏页、公式错误扫描、M2
  `HUMAN_PASS`、M4/M6 fail-closed、M3/M5 新证据层、全可见页禁词扫描和
  canonical Hash 前后一致均通过。
- canonical 工作簿 SHA-256 保持
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

## 状态边界

```text
M2 = DONE | Checkpoint A = HUMAN_PASS
M3 / M4 / M5 / M7 = PARTIAL
M6 = operationally NOT_STARTED
action = no_order
```

本候选不是 Checkpoint B/C/D、真实 IPS/组合、生产授权、M6 运营验收或 M7
最终交付。600519 的 9 条公告仍由用户逐条决定是否重大，M3 重建结果仍要求人工
研究复核。
