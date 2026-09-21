# Excel MVP 阶段 A 基线

记录日期：2026-09-21。范围仅限 `value-investment-excel-mvp-goal.md` 的阶段 A，
不重新审计历史回测、服务器或实盘准入。

## 固定基线

- Git HEAD：`b790bc48bc1f194db26ab8ba61295a39bf5bd651`。
- 原 WPS 工作簿：`C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪/A股价值投资_Agent前端智能跟踪模板.xlsx`。
- 工作簿 SHA-256：`FB9BC1DCCB18C6AA1CDC7D9F32CF8F9BB248C5A18A75BF78677C85065CABB322`。
- 三公司研究对象：`runtime/excel-mvp-research-cases/evidence.json`，由
  `runtime/excel-mvp-research-cases-latest.json` 的 SHA-256 钉住。

## 三家公司已有覆盖

| 代码 | 研究日期 / 财报期 | 可用研究事实 | 当前估值状态 |
| --- | --- | --- | --- |
| 600519 贵州茅台 | 2026-09-16 / 2026-06-30 | 已归档归母权益、扣非 TTM、白酒量价及研究卡证据 | 估值未就绪；仅保留受限研究模型 |
| 000333 美的集团 | 2026-09-12 / 2025-09-30 | 已勾稽归母 TTM 利润规模 | 估值未就绪；加权股本、A/H 与库存股口径未批准 |
| 601088 中国神华 | 2026-09-12 / 未准入 | 已归档历史执行会话约束 | 估值未就绪；当前财务与商业证据包未建立 |

## 本轮核验

`test_research_case.py`、`test_research_gate.py` 与
`test_excel_mvp_research_cases.py` 于 2026-09-21 运行通过，共 8 项。核验范围
包括三条统一 ResearchCase、ResearchGate、证据 Hash 可寻址性，以及不生成订单/
数量/真实仓位。该结果不证明估值、历史策略或实盘准入。

原表于同日经 WPS COM 以只读方式重新打开；首页和公司总览均检出 600519、000333、
601088 三条 MVP 记录，内部导航和保留仓位汇总公式均通过。回执为
`runtime/excel-mvp-stage-a-wps-reverify-20260921.json`。该复核不保存或修改工作簿。
