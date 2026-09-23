# M3 决策复核原工作簿候选

更新：2026-09-24。本工作包把已经冻结的三张非个人化 M3 负向决策卡接入现有
55 页工作簿的派生页 `00_决策复核`。它不替换原工作簿、不覆盖其他 54 个页面、
不生成任何个人化结论，全部动作保持 `action=no_order`。

## 已完成内容

- 新增 `m3_decision_review_sheet.py`，把不可变 `DecisionCardCollection` 投影为
  单页决策复核内容：当前三张卡、缺失与阻断、来源 Hash、证据引用和人工复核要求。
- 新增发布层 `replace_sheet` 能力：只替换目标工作表 XML 部件，保留其余工作表、
  工作簿关系、样式索引和内容类型；候选生成后校验所有未替换 ZIP 部件逐字节一致。
- 新增 `scripts/build_m3_original_workbook_candidate.py`，从冻结 M1 集成运行和
  M1 预登记生成受 Hash 保护的候选，不自动发布 canonical。
- 三张卡继续为 `000651 格力电器`、`600741 华域汽车`、`600887 伊利股份`，
  均为研究证据不足、组合输入缺失、原始 Entry 本卡不需要，`positive_review_count=0`。
- 新增 WPS 只读校验脚本、4 项定向回归，并纳入 GitHub Core Research Gate。

## 产物与 Hash

- 源工作簿：`A股价值投资_Agent前端智能跟踪模板.xlsx`
- 源 SHA-256：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`
- 候选工作簿：
  `A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx`
- 候选字节数：13,200,586
- 候选 SHA-256：
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`
- 冻结输入：
  `runtime/m1-post-review-20260923T114228Z/integrated-runs.json`
- 冻结输入 SHA-256：
  `b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459`
- M1 预登记 SHA-256：
  `5b7df98f8781080f66e5e053b8d0015f0b7c7eee9e27e8a10f7b0fe7990ab5b1`

## 验证

- 发布层回归和 M3 决策联合回归：18 passed。
- 实际 WPS 只读打开：55 页、`00_决策复核` 存在且可见、公式错误 0、禁止信号扫描
  通过、打开前后候选 SHA-256 不变。
- WPS 收据：
  `runtime/m3-original-decision-review-20260924/wps-verification.json`，
  `passed`
- WPS 云盘同名候选与本仓库候选逐字节一致。

## 边界

本候选尚未原子替换 WPS 生产原表。它只证明 M3 read model 可以安全投影进现有
`00_决策复核` 派生页；Checkpoint B 仍需用户在 WPS 中阅读三张卡并复述理由与反证。
M2 保持 `PENDING_HUMAN_REVIEW`，M3/M4/M5 保持 `PARTIAL`。
