# Changelog

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
