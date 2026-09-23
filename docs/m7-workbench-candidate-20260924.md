# M7 统一工作台展示候选：2026-09-24

更新：2026-09-24。本批把已经完成机器保护的 M3 历史链叠加候选与 M4/M5 只读
候选合并为一个本地展示候选，作为 M7 原 Excel 统一入口的展示层准备。它不是
M7 产品验收，也不替代任何 Checkpoint。

## 交付物

- 文件：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.xlsx`
- 字节数：13,262,051
- SHA-256：
  `829f743acc3f628e60bd9e210b196965865ad2306dea7e520d9f9d62b402d582`
- 工作表：90 个
- 第一页：`00_M7总览`，提供 M2/M3/M4/M5/M6/M7 状态说明和 9 个内部入口
- 构建脚本：`scripts/build_m7_workbench_candidate.py`
- WPS 只读校验：`scripts/verify_m7_workbench_wps.ps1`
- 本地 manifest：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_20260924.candidate.manifest.json`
- manifest SHA-256：
  `ac2d3baa12fdb145f6daf4d2d29724c4d1d85ec1264a67ab5b10ee4cc689d7b3`

## 叠加内容

候选以 M3 历史链叠加候选为基底，依次叠加以下已发布候选。每个附加候选都先
重命名工作表，避免与已有页面同名；所有源工作表 XML 部件通过 `graft` 保留，
不重算原有财务、估值或证据公式。

| 来源 | 工作表前缀 | 页数 |
| --- | --- | ---: |
| M4 组合风险候选 | `M4风险_` | 4 |
| M4 仓位与股息候选 | `M4仓位_` | 5 |
| M5 事件监控候选 | `M5事件_` | 6 |
| M5 材料性接入候选 | `M5材料性_` | 6 |
| M5 真实披露待复核队列 | `M5披露队列_` | 4 |
| M5 真实披露人工复核回填 | `M5披露复核_` | 4 |

最后叠加的 `00_M7总览` 只提供导航和状态说明，不含估值、仓位、事件或决策
重算，也不显示任何订单式正向信号。

## 输入绑定

- 基底文件：
  `A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`
- 基底 SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`
- canonical 工作簿 SHA-256：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`
- 六个 M4/M5 输入均按各自已发布 SHA-256 绑定，构建前逐项校验；任何输入变化
  都会失败关闭。

## 可重复构建

```powershell
& 'D:\APP\Python313\python.exe' -X utf8 scripts\build_m7_workbench_candidate.py
```

构建器使用固定的 `generated_at=2026-09-24T00:00:00+00:00`。自修复提交
`fa23f05` 起，`graft` 把新增前端层的 ZipInfo 时间戳固定为
`1980-01-01T00:00:00`，因此后续同一组输入不会因构建秒差而漂移；本文件记录的是
发布时冻结的 SHA-256，不把 SHA-256 当作估值、决策或实盘证据。构建器不会覆盖
canonical，也不会直接写 WPS 生产路径。

## 机器验证

- 定向回归：`tests/test_m7_workbench_candidate.py`、
  `tests/test_stage_frontend_package.py` 和
  `tests/test_m3_history_original_workbook.py` 共 11 passed。
- `rename_workbook_sheets` 只修改 `xl/workbook.xml`，其余 ZIP 部件逐字节保留；
  重复标题和超过 31 字符的标题会失败关闭。
- WPS 实际只读打开：90 页、前 31 页顺序和导航目标正确、公式错误 0、
  `00_M7总览` 无禁用决策文本、canonical 打开前后 Hash 不变。
- WPS 收据：
  `runtime/m7-workbench-wps-20260924/wps-verification.json`，`passed`
  （SHA-256：
  `c237b14482398b4903c13b0447ba406d11ec4688b8a17e3b99b045f1f5210e1e`）
- WPS 云盘同名候选与仓库候选逐字节一致，SHA-256 相同。
- 全量离线回归：2292 passed、6 skipped、0 failed。
- GitHub Core Research Gates run `35933960701` 的两个 job 均为 `success`；
  其中 `fa23f05` 修复了首次 M7 推送 `9e37435` 在 Linux runner 上由新增层
  ZipInfo 时间戳引起的确定性回归，候选内容未改变。

## 状态边界

本候选只证明只读展示层可以叠加，不代表 M7 或总目标完成：

- `M2=PENDING_HUMAN_REVIEW`
- `M3/M4/M5=PARTIAL`
- `M6=NOT_STARTED`
- `M7=PARTIAL`，最终 `Checkpoint D` 仍需用户签收
- 所有动作固定为 `action=no_order`；没有真实 IPS、持仓、自动决策或订单

最终 M7 仍要求 M2/M3 用户复核、真实 IPS/组合授权、M5/M6 生产观察与不少于
20 个连续真实交易会话的运营证据。当前候选不得被解释为可交易结论或实盘准入。
