# M3 原工作簿候选验收审计：2026-09-24

本批新增受保护的 M3 原工作簿候选审计器。它只核验上一批
`A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx` 的机器证据，
不发布 canonical、不创建 Entry/Journal/Consistency，也不读取私人账户或 IPS。

## 审计范围

- `owc1`：canonical、候选、manifest、冻结 M1 输入、M1 预登记的 SHA-256 全部绑定。
- `owc2`：从冻结输入重建三张非个人化负向卡，正面复核数必须为 0。
- `owc3`：55 页、页面顺序、目标页路径、54 个原页面和 113 个未替换 ZIP 部件逐字节保留。
- `owc4`：`00_决策复核` 只含三张负向卡、`action=no_order`、`Checkpoint B：未完成`，
  无公式且无买入/加仓/减仓/目标仓位文本。
- `owc5`：WPS 云盘候选与仓库候选逐字节一致；WPS 只读收据为
  `pre_publication/passed`；WPS 生产 canonical 保持未变。
- `owc6`：M3 原工作簿定向回归与 GitHub CI 均通过。
- `owc7`：人工 Checkpoint B 仍保持待复核，机器不能代签。

## 固定产物

| 项目 | SHA-256 |
| --- | --- |
| canonical | `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911` |
| M3 原工作簿候选 | `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3` |
| 候选 manifest | `192dd480b7aa8ef6299e7095014d2ca5a6becca04b4c5a42c1c6c95b375b41b4` |
| 冻结 M1 输入 | `b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459` |
| M1 预登记 | `5b7df98f8781080f66e5e053b8d0015f0b7c7eee9e27e8a10f7b0fe7990ab5b1` |
| WPS 只读收据 | `3f650e05f92f24ec94dfa65eb8b97af041bf309ac1136a84001b2f54eff8a763` |

## 运行与结果

- 新增：`src/value_investment_agent/m3_original_workbook_acceptance_audit.py`
- 命令：`python scripts/audit_m3_original_workbook.py --run-tests --ci-status success`
- 定向回归：7 passed。
- 机器门 `owc1-owc6`：`DONE`；`owc7`：`PENDING_HUMAN_REVIEW`。
- 审计动作：`no_order`；候选状态：`candidate_verified_not_published`。
- 最新收据：
  `runtime/m3-original-workbook-audit-20260923T223129Z/receipt.json`
- 收据 SHA-256：
  `2242450c9f5ee76ce7dc9b4c9bc231448ea55d07d7efea06e99ab5a95ceae0c9`
- 对应提交：`d6e4179488c11d4833f27fe2f0edde37f4651a46`
- GitHub Core Research Gates：[run 35928696898](https://github.com/MingMingLiu0112/value-investment/actions/runs/35928696898)，
  `offline-core` 与 `postgres-integration` 均成功。

## 边界

本审计证明候选在字节和结构上受保护、可重复重放，并能回到 WPS 证据；它不证明三张卡
的经济结论正确，也不替代用户阅读与 Checkpoint B 签收。
