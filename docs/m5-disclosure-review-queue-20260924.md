# M5 真实披露待复核队列

更新：2026-09-24。本轮建立真实 CNINFO 公告索引到人工材料性复核之间的缺失环节。
`M2=PENDING_HUMAN_REVIEW`，`M3/M4/M5=PARTIAL`，所有动作 `action=no_order`。

## 范围

- 选取当前 M1 三家公司 `600887`、`600741`、`000651`。
- 扫描区间为 `2026-08-27` 至 `2026-09-24`。
- 归档每家公司完整原始 CNINFO 索引，并为每个标题规则候选下载官方 PDF 原文。
- 标题规则只生成待人工复核候选，不判定材料性，也不生成 M5 ChangeEvent。

## 新合同

- `m5_disclosure_queue.py` 把原始 CNINFO 索引转换为已存在的
  `EventScanResult` / `AnnouncementReview`：
  - 公告 ID、发布时间、标题、来源 URL、规则类型、原始索引 Hash 和候选 PDF
    SHA-256 均保留；
  - 未知标题保留为候选；
  - 重复 ID、窗口外时间和未来时间失败关闭；
  - 候选 PDF URL 缺失或下载失败时保持
    `SOURCE_UNAVAILABLE` 和 `PENDING_HUMAN_REVIEW`，不降级为无事件；
  - 单家公司源失败返回 `UNKNOWN / INCOMPLETE` 扫描，不阻塞其他公司。
- `DisclosureReviewQueue` 固定 scan window、provider、parser version、
  `retrieved_at` 和 `action=no_order`，并支持完整 round trip。

## 真实运行证据

- 队列 ID：`cninfo-review-2026-08-27-20260923T213249Z`
- 公司数：3
- 待人工复核候选：24
- 候选 PDF：24 份，均归档并绑定 SHA-256
- 来源不可用：0
- 覆盖完整：3 / 3
- runtime queue：
  `runtime/m5-disclosure-review-20260923T213249Z/queue.json`
- runtime queue SHA-256：
  `378f5366f76faaf7d9407b321419a40305baccb6126a67a4302526428a75c6b4`
- 独立工作簿：
  `A股价值投资_M5真实披露待复核队列_20260924.xlsx`
- 工作簿 SHA-256：
  `58b16bf00dd7ea57ee9cdcd6d7d7d00d80c0fc9669cd047f5171f500a9b16ec5`
- WPS 只读收据：
  `runtime/m5-disclosure-review-20260923T213249Z/wps-verification.json`，
  `passed`
- WPS 云盘同名副本与仓库工作簿逐字节一致。

## 验证

- 新增 10 项定向回归：`tests/test_m5_disclosure_queue.py` 与
  `tests/test_m5_disclosure_queue_workbook.py`，全部通过。
- M5 相关联合回归：58 passed。
- 除 PostgreSQL 集成测试外的全量离线回归：2262 passed、2 skipped、
  18 warnings、0 failed。
- 新测试已纳入 GitHub Core Research Gate。

## 边界与下一步

本候选只把真实披露放到人工复核队列。未执行自动材料性判定、事件入账、有界失效、
生产调度、通知投递、数据库变更或任何个人化结论。下一步由用户在 WPS 工作簿中给出
逐条 `EventMaterialityDecision`，随后才能由既有 `M5MaterialityBridge` 精确接入
M5 事件管道。
