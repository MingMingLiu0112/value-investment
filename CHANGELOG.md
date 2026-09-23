# Changelog

## v2026.09.23-m2-v2-coverage

### Release Scope

将 M2 机会发现协议升级到 `m2-opportunity-discovery-v2`，把候选列表与完整覆盖账分开，
修复未来披露泄漏、源外证券混入、跨通道原因丢失和预算截断分母不可对账问题。
本版本继续执行 `action=no_order`，不生成估值、BUY、ADD、仓位或订单。

### Git Commits

- `0ba4660 Expand active goal from M2 through M7 with stage gates` 后继续本地开发。
- 本条目提交 M2 v2 协议、引擎、运行脚本、回归测试、Excel 快照与版本记录。

### New Capability

- 每个官方证券在每个通道保留 `PASS / REJECTED / DATA_GAP / CONFLICT / UNSUPPORTED / NOT_EVALUATED / BUDGET_EXCLUDED` 覆盖记录。
- `coverage_signature` 覆盖完整分母，`candidate_signature` 只覆盖展示候选；收据冷重放同时校验两者。
- 官方 Universe 外的行情只计入健康异常，不进入候选池、覆盖账或 Legacy shadow。
- 同一证券跨通道进入时保留全部通道原因，不再使用字典覆盖。
- 超出 `max_per_channel` 的通过者记为 `BUDGET_EXCLUDED`，保留原因和分母。
- 复用原始输入时保留各 payload 自己的 `fetched_at`，不再用当前时间重新盖章。
- 分红公告日期晚于运行 `known_at` 的未来披露会在进入证据层前被排除。
- 新增 `10_逐通道覆盖` 工作簿页，展示完整分母、状态、原因、画像和证据日期。

### Real Run Summary

- 输入来源：2026-09-23 真实全市场 5,568 家官方证券快照。
- 行情匹配 5,568 家；缺失 0；源外 0；双源冲突 0。
- 展示候选：Quality 0、Dividend 50、Value 50、Cyclical 50；合并去重 113。
- 覆盖账：Quality 5568（PASS 0 / DATA_GAP 4672 / REJECTED 775 / UNSUPPORTED 121）。
- 覆盖账：Dividend 5568（PASS 50 / BUDGET_EXCLUDED 369 / NOT_EVALUATED 1946）。
- 覆盖账：Value 5568（PASS 50 / BUDGET_EXCLUDED 351 / REJECTED 3581）。
- 覆盖账：Cyclical 5568（PASS 50 / BUDGET_EXCLUDED 1535 / NOT_EVALUATED 3059）。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- `candidate_signature=f7442de45283c4d3a21b17a846bb7b0028c3219b15617af3ed17848245ba4d0a`。
- 收据字节和原始输入冷重放均一致。

### Artifacts

- 新增 `A股价值投资_M2机会发现_v2_20260923.xlsx`
  - SHA-256：`4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63`
- 更新 `A股价值投资_Agent前端智能跟踪模板.xlsx` 至 WPS 2026-09-23 版本
  - SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- 新增 `M1_三公司研究Application候选_20260923_033001.xlsx`
  - SHA-256：`0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbd51c3d34`
- 新增 `M1_三公司研究Application候选_20260923_122010.xlsx`
  - SHA-256：`2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`

### Verification

- M2 定向测试：10 passed。
- 仓库内隔离 basetemp 全量回归：2122 passed、6 skipped。
- `compileall`、`git diff --check` 通过。

### Status

`PARTIAL`。本次修复 M2 覆盖账与时点重放合同，不等于 M2 或 M2-M7 总目标完成；
M2 的实质研究报告、原 Excel 统一发布、用户可见验收和后续 M3-M7 阶段仍按
`docs/current-stage-goal.md` 与 `LONG-TERM-GOAL.md` 继续。

## v2026.09.23-m2-partial

### Release Scope

完成 POST-M1 稳定化后的首个真实全市场 M2 机会发现 run-once，并发布独立候选工作簿快照。
本版本只负责主动发现深研候选，不生成估值、BUY、ADD、仓位或订单，`action=no_order`。

### Git Commits

- `f26f726 M2.0 complete post-M1 stabilization`
- `6658b14 M2.1-M2.6 multi-channel opportunity discovery run-once`
- 本条目提交：新增仓库内 Excel 快照与版本记录。

### New Capability

- 官方证券 Universe 快照与腾讯、新浪行情合并，支持价格冲突检查。
- Quality、Dividend/Cash Return、Value、Cyclical 四个独立筛选通道。
- 每条候选记录通道、进入原因、证据日期、数据状态、画像状态和缺失指标。
- 银行、保险、券商等不支持画像进入 `UNSUPPORTED` 隔离，不进入通用通道。
- Legacy PE/PB screen 仅保留 shadow 对比，不参与 M2 候选排序。
- 原始快照、收据、候选签名和 SHA-256 可重放。
- 生成展示专用 `A股价值投资_M2机会发现_20260923.xlsx`。

### Real Run Summary

- 官方 Universe：5,568 家；行情匹配：5,568 家。
- 价格冲突：0；行业映射：5,568 家。
- 财务证据：873 条；股息证据：3,622 条；不支持金融画像：121 家。
- 通道候选：Quality 0、Dividend 50、Value 50、Cyclical 50。
- 合并去重候选：113 家；Legacy shadow：747 家；重叠：86 家。
- Quality 为空是证据门禁失败关闭结果，未降低门槛强制放行。

### Artifact

- `A股价值投资_M2机会发现_20260923.xlsx`
- SHA-256：`a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`
- 与 WPS 云盘“价投跟踪”目录中的用户可见文件字节一致。

### Verification

- M2 定向测试：6 passed。
- 仓库内隔离 basetemp 全量回归：2118 passed、6 skipped。
- `compileall` 与 `git diff --check` 通过。
- 原始输入和收据重放候选签名一致。

### Status

`PARTIAL`。M2 验收第 1-6、8-10 项已有真实证据；第 7 项“从新发现候选中形成至少 3 份实质研究或否决报告”尚未完成。
