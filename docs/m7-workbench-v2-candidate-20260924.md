# M7 统一工作台 v2 展示候选：2026-09-24

更新：2026-09-24。本批把刚交付的 M4/M5 联合检查点候选作为第七个只读展示层接入
M7 统一工作台，生成独立的 96 页 v2 候选。它不是 M7 产品验收，不替代 Checkpoint
A-D，也不导入真实 IPS、持仓或订单。

## 交付物

- 文件：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx`
- 字节数：13,271,164
- SHA-256：
  `d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc`
- 工作表：96 个
- 构建脚本：`scripts/build_m7_workbench_v2_candidate.py`
- WPS 只读校验：`scripts/verify_m7_workbench_v2_wps.ps1`
- 本地 manifest：
  `A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.candidate.manifest.json`
- manifest SHA-256：
  `43698ed3a4752edd894da916a140edce3e4a9d44f140c3cfbd27ed177a61667d`

## 与 v1 的关系

v2 复用同一 M3 历史链叠加基底、canonical 和六个 M4/M5 候选，只是在原有 90 页
候选上追加：

| 新层 | 工作表前缀 | 页数 |
| --- | --- | ---: |
| M4/M5 联合检查点候选 | `M4M5联合_` | 6 |

原有 v1 文件、90 页顺序、SHA-256 和复现命令保持可用。基础构建器只增加一个向后
兼容的 `manifest_schema` 参数，未传入时仍生成
`m7-workbench-candidate-v1`。

## 输入绑定

- 基底：
  `A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`
- 基底 SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`
- canonical SHA-256：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`
- M4/M5 联合候选 SHA-256：
  `353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`
- 全部七个展示层均在构建前按各自发布 SHA-256 校验，任何输入变化都失败关闭。

## 机器验证

- M7 v1/v2 定向回归：6 passed。
- WPS 实际只读打开：96 页、前 37 个展示页顺序、10 个总览导航入口、公式错误 0、
  `no_order` 文本边界和 canonical 打开前后 Hash 均通过。
- WPS 收据：
  `runtime/m7-workbench-v2-wps-20260924/wps-verification.json`，`passed`
  （收据 SHA-256：
  `4fedb84a4f5da10379f683f9775f30d99899fec41ea896045b80559838fc8056`）
- WPS 云盘同名候选与仓库候选逐字节一致。
- 全量离线回归：2317 passed、6 skipped、0 failed。

## 状态边界

- `M2=PENDING_HUMAN_REVIEW`
- `M3/M4/M5/M7=PARTIAL`
- `M6=NOT_STARTED`
- 所有动作固定为 `action=no_order`

该候选只证明用户能从同一个 M7 入口打开 M4/M5 联合失效映射，不等同 Checkpoint C、
M7 交付或实盘准入。真实组合、IPS、事件观察、生产调度和用户签收仍需后续授权。
