# M5 真实披露人工复核回填工作包

更新：2026-09-24。本文件记录真实 CNINFO 待复核队列到人工
`EventMaterialityReview` 的回填入口。它不预填任何材料性结论，不创建 M5 事件，
不写数据库、不通知、不调度、不下单。

## 为什么新增

上一批 `m5_disclosure_queue.py` 已形成 3 家公司、24 条待人工复核候选和 24 份归档
PDF。真正的产品缺口不是继续自动猜标题，而是让用户能够安全、可追溯地逐条输入
`human_decision`，并在输入后由既有 M5 材料性桥消费。

本工作包新增四层：

- 队列绑定：每个回填表保存 `queue_id` 和队列 SHA-256，队列变化后整表失效。
- 候选绑定：每条输入必须覆盖且仅覆盖一个真实待复核候选，不得新增或遗漏。
- 原件绑定：每条判定绑定候选 PDF SHA-256，缺件保持阻断。
- 时间绑定：审核时间采用北京时间，早于公告发布时间时失败关闭。

## 新增产物

### 回填工作簿

- 文件：`A股价值投资_M5真实披露人工复核回填_20260924.xlsx`
- 字节数：13,885
- SHA-256：
  `1ae75325fe02c93011201c3a44af73d739a49680e24af35a8f33fcd362a6c420`
- 工作表：`00_总览`、`01_人工判定`、`02_判定说明`、`03_边界`
- 真实范围：600887、600741、000651，2026-08-27 至 2026-09-24
- 待复核候选：24 条，判定列和复核说明列均从空值开始
- 队列文件：
  `runtime/m5-disclosure-review-20260923T213249Z/queue.json`
- 队列文件 SHA-256：
  `378f5366f76faaf7d9407b321419a40305baccb6126a67a4302526428a75c6b4`
- 队列语义 SHA-256：
  `9ff56ebe8ab2902d4339fda881c0a0d4697a1066014f477053198dd00e4e905d`
- WPS 只读收据：
  `runtime/m5-disclosure-review-intake-20260924/wps-verification.json`，
  `passed`
- WPS 云盘同名副本与仓库工作簿逐字节一致

### 代码与命令

- `src/value_investment_agent/m5_disclosure_review.py`：输入合同、
  队列指纹校验和 `EventMaterialityReview` 构建。
- `src/value_investment_agent/m5_disclosure_review_workbook.py`：生成和读取回填表。
- `scripts/build_m5_disclosure_review_workbook.py`：从固定队列生成空白回填表。
- `scripts/apply_m5_disclosure_review.py`：读取用户填写后的回填表，生成
  `EventMaterialityReview` 和 `MaterialityBridgeBatch`，但不执行事件流水线。
- `scripts/verify_m5_disclosure_review_workbook_wps.ps1`：WPS 只读打开、公式、
  工作表顺序、队列指纹、空判定和 no-order 边界检查。

## 人工填写规则

- 每条公告必须选择：
  `NOT_MATERIAL`、`MATERIAL_SUPPORTING_EVIDENCE`、
  `MATERIAL_ALREADY_INCORPORATED`、`MATERIAL_REQUIRES_RECALCULATION`、
  `MATERIAL_RISK_MONITOR`、`DUPLICATE_OR_DERIVED` 或
  `REQUIRES_DECOMPOSITION`。
- 每条公告必须写至少一行复核说明，包括无重大事项时也要写明判断依据。
- `MATERIAL_REQUIRES_RECALCULATION` 必须至少填写一个受影响领域、事实字段、
  假设或制品；未知领域保留为 `unmapped_domains`，不会被静默映射。
- `MATERIAL_RISK_MONITOR` 和 `REQUIRES_DECOMPOSITION` 不要求先声明全部影响，
  只会进入决策复核和当前状态。
- 表格顶部必须填写北京时间审核时间。

## 失败关闭行为

- 判定为空、复核说明为空、候选覆盖不完全、出现非候选行：拒绝。
- 队列 ID、队列 SHA-256、PDF SHA-256 或审核时间不匹配：拒绝。
- 候选 PDF 缺失：对应扫描保持不完整，不能进入材料性回填。
- 应用命令只写 `intake.json`、`reviews.json`、`bridge_batches.json` 和收据；
  它不调用事件账、依赖失效、outbox、通知或数据库。

## 验证

- 新增定向回归：15 passed。
- 与已有 M5 队列、事件、材料性桥和工作簿联合回归：无失败。
- `python -m compileall` 与 `git diff --check` 通过。
- WPS 只读验证 `passed`：4 页、24 行候选、判定和说明全空、打开前后 SHA-256
  不变。

## 状态边界

`M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，所有动作
`action=no_order`。本工作包只是让下一步人工复核可执行；24 条材料性结论仍需用户
逐条给出，之后才允许显式调用 M5 材料性桥。
