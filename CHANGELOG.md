# Changelog

## v2026.09.23-m2-lead-verified-original-candidate

### Release Scope

在保持 `m2-opportunity-discovery-v2` 冷重放语义的前提下，把“便宜筛选产出”与
“已经深研核实的候选”在领域模型中显式分开；同时增加从原工作簿生成受保护
M2 候选工作簿的离线发布入口。本版本继续执行 `action=no_order`，不生成
估值、BUY、ADD、仓位或订单，也不把候选发布为生产工作簿。

### New Capability

- `CandidateReason` 新增 `candidate_class`，只允许 `LEAD` 或
  `VERIFIED_CANDIDATE`；当前所有四通道筛选输出均明确标记为 `LEAD`。
- `DiscoveryRunReceipt.verified_candidate_pool()` 只返回后续深研验证门通过的候选；
  当前真实运行中该池为空，不再用“候选数”暗示研究已经完成。
- 候选签名包含 `candidate_class`，冷重放仍可验证新旧层级字段。
- M2 工作簿新增“研究层级”列，显示“研究线索”或“已核候选”；总览分别展示
  线索数与已核候选数。
- 新增 `scripts/build_m2_original_workbook_candidate.py`：
  - 校验原工作簿预期 SHA-256，源文件变化即拒绝；
  - 只接受 `action=no_order` 的有效 M2 收据；
  - 复用 `stage_frontend_package.graft`，原工作簿页和原始 ZIP 部件保持字节不变；
  - 拒绝覆盖已有输出，并产出 `candidate_verified_not_published` 清单；
  - 不执行对 WPS 云盘原工作簿的原子替换或发布。
- 新增回归测试覆盖源 Hash 变化拒绝、输出已存在拒绝、原页与原公式保留、
  OOXML 关系有效，以及所有屏幕结果是研究线索这一合同。

### Real Run And Candidate Evidence

- 复用 2026-09-23 真实全市场 5,568 家官方证券保留输入生成
  `runtime/m2-live-20260923-v2b/`。
- 展示候选仍为 Quality 0、Dividend 50、Value 50、Cyclical 50；已核候选 0。
- `candidate_signature=a4f555b789c3942c690c1e288e5ce3bfa210544cd9ffcc63803d4c1eeb46f4c7`。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- 原工作簿候选：
  - 源 SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
  - 候选 SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`
  - 53 个工作表，前 11 个为 M2，后 42 个为原工作簿页
  - `original_parts_unchanged=96`，`status=candidate_verified_not_published`
- 候选以独立预览复制到 WPS 云盘，未替换生产原工作簿。

### Artifacts

- 新增 `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`
  - SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`

### Verification

- M2 与原工作簿候选定向回归：19 passed。
- `git diff --check` 通过。

### Status

`PARTIAL`。本版固定了线索/已核候选边界并演示未发布的原工作簿候选阶段，
不等于 M2 验收完成；深研报告、预注册抽样、完整时点重放、用户可见发布验收
与后续 M3-M7 仍按 `docs/current-stage-goal.md` 和 `LONG-TERM-GOAL.md` 继续。

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
