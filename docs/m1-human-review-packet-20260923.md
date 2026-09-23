# M1 人工复核证据包

更新：2026-09-23。本文件由 `scripts/render_m1_human_review_packet.py` 从当前冻结 runtime/config 证据生成，只读、不批准、不改变原 Excel，`action=no_order`。

复核完成后请把结论回复给 Codex，不要直接修改本文件冒充人工记录。任何 G3 批准、事件重要性判断或 Excel 确认都应由 Codex 写入新的可追溯收据。

## A. G3 条件估值批准

以下数值仍是 `conditional_research_only`。人工批准只表示“模型基础可作为条件研究继续使用”，不是合理价、价格吸引力、仓位或买入建议。

| 公司 | 模型 | Bear / Base / Bull | G3 当前值 | 批准 | 补充条件 |
| --- | --- | ---: | --- | --- | --- |
| 000651 | FCFF | 65.6683 / 83.2519 / 97.7513 | `False` | 待填写 | 待填写 |
| 600741 | FCFF | 24.4786 / 33.7466 / 39.9382 | `False` | 待填写 | 待填写 |
| 600887 | residual_income_or_equity_value | 10.3718 / 17.0230 / 24.0717 | `False` | 待填写 | 待填写 |

对每家公司核对：

1. 官方原件、反证、thesis breaker 与 `assumption_bindings` 是否一致。
2. 2026H1 未经审计、ROIC/WACC/增量 ROIC、法人层级现金与股本动作等 blocker 是否仍成立。
3. 事件复核结果是否要求调整输入或让模型 `STALE`。
4. 回复格式：`000651 G3 批准 / 不批准`，并附一句依据或仍需补的数据。

### 000651

- 模型：`fcff`
- 事件扫描：`COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW`，pre-model 状态：`PENDING_HUMAN_REVIEW`
- 当前 blocker：
- `G3 human approval pending`
- `treasury/financial company scope and restricted cash remain unresolved`
- `valuation is conditional_research_only and must never imply a buy decision`
- `pre-model event-scan disclosures require human review`

### 600741

- 模型：`fcff`
- 事件扫描：`COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW`，pre-model 状态：`PENDING_HUMAN_REVIEW`
- 当前 blocker：
- `G3 human approval pending`
- `valuation is conditional_research_only and must never imply a buy decision`
- `pre-model event-scan disclosures require human review`

### 600887

- 模型：`residual_income_or_equity_value`
- 事件扫描：`COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW`，pre-model 状态：`PENDING_HUMAN_REVIEW`
- 当前 blocker：
- `G3 human approval pending`
- `valuation is conditional_research_only and must never imply a buy decision`
- `pre-model event-scan disclosures require human review`

## B. 模型前公告重要性阅读

下表只包含 `pre_model=true` 且 `materiality_candidate=true` 的公告。请逐项打开本地原件或 CNINFO 链接，判断：不重要 / 重要 / 需要拆分。

| 公告 ID | 发布日期 | 标题 | 原件 | SHA-256 前 12 位 | 判断 | 影响字段 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1225542476 | 2026-09-02T00:00:00+08:00 | 关于股份回购进展情况的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-09-02/1225542476.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-02/1225542476.PDF) | `d9a50e5cf086...` | 待填写 | 待填写 | 待填写 |
| 1225515009 | 2026-08-27T00:00:00+08:00 | 关于“质量回报双提升”行动方案的进展公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515009.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515009.PDF) | `77d740065eac...` | 待填写 | 待填写 | 待填写 |
| 1225515008 | 2026-08-27T00:00:00+08:00 | 关于会计政策变更的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515008.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515008.PDF) | `898268243966...` | 待填写 | 待填写 | 待填写 |
| 1225515007 | 2026-08-27T00:00:00+08:00 | 关于子公司之间提供担保的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515007.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515007.PDF) | `a42064366e18...` | 待填写 | 待填写 | 待填写 |
| 1225515005 | 2026-08-27T00:00:00+08:00 | 2026年半年度非经营性资金占用及其他关联资金往来情况 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515005.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515005.PDF) | `45240e9b621e...` | 待填写 | 待填写 | 待填写 |
| 1225515004 | 2026-08-27T00:00:00+08:00 | 2026年半年度报告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515004.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515004.PDF) | `50da2e03fddb...` | 待填写 | 待填写 | 待填写 |
| 1225515003 | 2026-08-27T00:00:00+08:00 | 2026年半年度报告摘要 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/000651/announcements/2026-08-27/1225515003.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225515003.PDF) | `fe7baa0daf4d...` | 待填写 | 待填写 | 待填写 |
| 1225516580 | 2026-08-28T00:00:00+08:00 | 华域汽车关于上海汽车集团财务有限责任公司2026年半年度风险评估报告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600741/announcements/2026-08-28/1225516580.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-28/1225516580.PDF) | `7bde1e894931...` | 待填写 | 待填写 | 待填写 |
| 1225516573 | 2026-08-28T00:00:00+08:00 | 华域汽车2026年半年度报告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600741/announcements/2026-08-28/1225516573.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-28/1225516573.PDF) | `77db47cdf18c...` | 待填写 | 待填写 | 待填写 |
| 1225516560 | 2026-08-28T00:00:00+08:00 | 华域汽车重大信息内部报告制度 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600741/announcements/2026-08-28/1225516560.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-28/1225516560.PDF) | `6390b20afd2b...` | 待填写 | 待填写 | 待填写 |
| 1225516550 | 2026-08-28T00:00:00+08:00 | 华域汽车2026年半年度报告摘要 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600741/announcements/2026-08-28/1225516550.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-28/1225516550.PDF) | `f8ab36088981...` | 待填写 | 待填写 | 待填写 |
| 1225568022 | 2026-09-17T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于以集中竞价交易方式回购公司股份的回购报告书 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-17/1225568022.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-17/1225568022.PDF) | `5e5baa57776f...` | 待填写 | 待填写 | 待填写 |
| 1225568017 | 2026-09-17T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于回购股份减少注册资本通知债权人的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-17/1225568017.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-17/1225568017.PDF) | `65e4ed5f54c2...` | 待填写 | 待填写 | 待填写 |
| 1225559652 | 2026-09-12T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于为控股子公司提供担保的进展公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-12/1225559652.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-12/1225559652.PDF) | `2b0109b9633f...` | 待填写 | 待填写 | 待填写 |
| 1225559649 | 2026-09-12T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于回购股份事项前十名股东持股情况的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-12/1225559649.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-12/1225559649.PDF) | `fed832b763bc...` | 待填写 | 待填写 | 待填写 |
| 1225547701 | 2026-09-05T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司2023年持股计划（第三期）第二次持有人会议决议公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-05/1225547701.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-05/1225547701.PDF) | `382ce62c8019...` | 待填写 | 待填写 | 待填写 |
| 1225547678 | 2026-09-05T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司第六期长期服务计划第二次持有人会议决议公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-05/1225547678.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-05/1225547678.PDF) | `b5ef55521fda...` | 待填写 | 待填写 | 待填写 |
| 1225536213 | 2026-09-01T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于回购股份事项前十名股东持股情况的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-09-01/1225536213.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-09-01/1225536213.PDF) | `6286c438ecc4...` | 待填写 | 待填写 | 待填写 |
| 1225511505 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司2026年半年度报告摘要 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511505.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511505.PDF) | `4bfeb24fa8d2...` | 待填写 | 待填写 | 待填写 |
| 1225511493 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于计提资产减值准备的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511493.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511493.PDF) | `bf3a21d0c92b...` | 待填写 | 待填写 | 待填写 |
| 1225511474 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司2026年半年度募集资金存放、管理与实际使用情况的专项报告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511474.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511474.PDF) | `0a086e25a805...` | 待填写 | 待填写 | 待填写 |
| 1225511473 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于以集中竞价交易方式回购公司股份方案的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511473.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511473.PDF) | `afdd5cf950e7...` | 待填写 | 待填写 | 待填写 |
| 1225511470 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司关于2026年半年度经营数据的公告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511470.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511470.PDF) | `c84f92a52e30...` | 待填写 | 待填写 | 待填写 |
| 1225511409 | 2026-08-27T00:00:00+08:00 | 内蒙古伊利实业集团股份有限公司2026年半年度报告 | [本地原件](../runtime/company-research/m1-event-scans/20260923T051018Z/600887/announcements/2026-08-27/1225511409.pdf) / [CNINFO 原件](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF) | `423af4d63f2b...` | 待填写 | 待填写 | 待填写 |

若某条判断为“重要”，当前 `VALID`/`READY` 不能自动保留；需要先登记新事实/假设并重算。若全部为“不重要”，可以进入下一步。

## C. Excel 人工可用性确认

打开 `A股价值投资_Agent前端智能跟踪模板.xlsx`，确认：

1. 前 6 个 M1 页名称和顺序正确。
2. 内部链接没有错误页面或死链接。
3. `00_M1应用总览` 仍显示“完成，有阻断”、`action=no_order`。
4. 估值、股利、反向估值、阻断/证据、样本页没有写成 BUY/ADD/仓位。

## D. 禁止事项

- 不把 G3 批准解释为买入信号。
- 不把 `READY` 价格桥解释为价格吸引力。
- 不把 LOW 股息可持续性解释为股息可维持。

## 证据摘要

- Application 指针：`runtime/m1-research-application-latest.json`
- Application evidence SHA-256：`f76356886a58ef5a497822ee3b477f4c13f05b6f833114afc063e87bdbea342f`
- 生成时间：`2026-09-23T08:59:06.827067+00:00`
