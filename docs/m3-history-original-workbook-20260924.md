# M3 论点连续性历史链叠加候选：2026-09-24

更新：2026-09-24。本批把五页显式模拟的历史链追加到已受保护的 M3 决策复核候选，
形成 60 页公开候选；不读取真实账户、IPS、持仓或真实 Entry，不覆盖 canonical，不生成
仓位或订单。全部动作保持 `action=no_order`。

## 交付物

- 文件：`A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx`
- 字节数：13,208,437
- SHA-256：
  `67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d`
- 工作表：60 个。前 5 页为 `00_历史链`、`01_原Entry`、`02_决策日志`、
  `03_一致性复核`、`04_来源哈希`；后 55 页完整保留 M3 决策复核候选。
- 构建脚本：`scripts/build_m3_history_original_workbook_candidate.py`
- WPS 校验：`scripts/verify_m3_history_original_workbook_wps.ps1`
- 审计命令：`scripts/audit_m3_history_original_workbook.py`

## 输入绑定

- M3 决策复核候选 SHA-256：
  `ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3`
- M3 独立历史链候选 SHA-256：
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`
- 显式模拟历史输入 `tests/fixtures/m3_history_demo.json` SHA-256：
  `4969a5d3b8bb80dfa743807053a75bc4e1595a5081953ecff1a83ba56c8f057c`
- canonical 工作簿 SHA-256 仍为：
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`

## 机器验证

- 定向离线回归：11 passed。
- 审计器机器门 `hoc1-hoc6` 全部 `DONE`；`hoc7` 保持 `PENDING_HUMAN_REVIEW`。
- WPS 只读打开：60 页、前 5 页顺序正确、历史链 `600887` 且 `namespace=simulated`、
  `action=no_order`，`00_决策复核` 仍为三张负向卡；打开前后 Hash 不变。
- WPS 收据：
  `runtime/m3-history-overlay-wps-20260924/wps-verification.json`，`passed`。
- WPS 云盘同名候选与仓库候选逐字节一致，canonical 未被替换。
- GitHub Core Research Gates 运行 `35931101091`：`offline-core` 与
  `postgres-integration` 均为 `success`；公开提交 `d614b5b`。

## 安全边界

- 示例中的买入、持有、减仓只展示人工理由链形态，不代表真实成交或投资建议。
- 公开候选拒绝非模拟命名空间；本批没有真实 Entry、Journal、Consistency 或组合快照。
- Checkpoint B 仍由用户人工验收，本工具不代理通过。
