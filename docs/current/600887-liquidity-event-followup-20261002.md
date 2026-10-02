# 伊利：兑付事实澄清与担保风险更新

核验日：2026-10-02。仅为新增官方披露的研究跟踪；不批准估值、买卖或仓位。`action=no_order`。

## 新证据

巨潮正式索引在 2026-10-01 至 2026-10-02 的有界查询中返回两份公告，发行人均为 600887。已下载 PDF，核对发行人、公告编号、落款日期，并查看兑付公告第 1 页与担保公告第 1、3 页图像。不是根据二手标题认定事实。

1. [兑付完成公告，临2026-071](https://static.cninfo.com.cn/finalpage/2026-10-01/1225591152.PDF)：公司披露 2026-09-29 完成第十、十一期超短期融资券兑付；每期本金 100 亿元，每期本息金额 10,031,454,794.52 元，清算机构代理划付。仅是公司正式披露，不是独立取得银行结算流水的证明。
2. [担保进展公告，临2026-072](https://static.cninfo.com.cn/finalpage/2026-10-01/1225591147.PDF)：新增最高债务本金担保额度 8 亿元，为全资子公司香港金港商贸控股有限公司提供连带责任保证。披露的既有担保余额 87.41 亿元、占最近一期经审计净资产 15.99%，明确不含本次担保。下属内蒙古惠商融资担保有限公司对外担保逾期金额为 0.52 亿元。

金额、范围和口径不可混淆：8 亿元是本次最高债务本金，不是已经发生的损失；87.41 亿元不含本次担保，不能未经分析就相加当作实际债务；0.52 亿元是下属担保公司的逾期担保，不等于伊利母公司的融资券违约。担保额度、实际融资、履约责任、现金损失和合并负债是不同概念。

## 对原研究缺项的影响

已澄清的子问题：此前 SCP010/011 到期后结果尚缺正式原件，现在已有公司兑付完成公告，不应再笼统说两期兑付结果没有披露。

仍未解决：资金来源、再融资安排、兑付后的现金与债务余额、资金受限情况、期限结构，以及新增/逾期担保对普通股现金回报与风险的影响。不能拿半年报的现金减去兑付金额，假装得到了 9 月底余额；其间经营、融资及其他现金变动尚未完整勾稽。

因此原停止项中“兑付结果与流动性桥接”的整体条件并未通过。本轮不删除或改写冻结停止台账，不将同一新证据重复消费为多个准入，不把公告可读当成重大性审批。

新公告提供了继续复核的真实输入，而不是购买理由。下一项研究应明确区分已披露的兑付结果与仍待建立的现金债务桥接，并独立评估担保。不得只因为兑付完成就认定估值有效，也不得只因担保逾期就机械输出退出。

## 时间与覆盖边界

官方索引和落款仅提供 2026-10-01 日期，不提供独立核验的分秒。事件输入采用保守可用上界 2026-10-02 00:00（上海时区）；扫描字段 published_at 在该只读包中承载这个上界，notes 明确其并非真实盘中发布时间。实际获取/观察发生在 10 月 2 日，不回填到 9 月 29 日或 10 月 1 日历史决策。

查询区间只覆盖两天，不证明从原估值日到当前的完整事件覆盖，也不证明当前 ModelValidity、严格 PIT 或当前行情有效。

## 可复现证据

- Official index: `runtime/historical-filing-index/20261002T013816751637Z/600887-1-5778ae14500992aff97ca218aaf60fa976e50d1385421f58683274173d86bac2.json`, SHA-256 `5778ae14500992aff97ca218aaf60fa976e50d1385421f58683274173d86bac2`.
- Settlement PDF: `runtime/public-event-followup-20261002/1225591152.pdf`, SHA-256 `f59267675689f0d77cc142d91e910e2e839adfc0282a260483e0858cc82a1ba3`.
- Guarantee PDF: `runtime/public-event-followup-20261002/1225591147.pdf`, SHA-256 `62815ec8a6fed035e1ead0d11f73ae8ce8d5f783a2c40a1b090259cbf6f4fe19`.
- Existing supported command: `scripts/current/replay_workbench_cutoffs.py` with pinned `runtime/shared-existing-workbench-20261001/result.json`, new pinned event scan, explicit October 2 cutoff and `--event-source-pages`; actual output is `runtime/public-event-followup-20261002/source-review.json` / `source-review.md`.
- Shared projection uses existing `prepare_event_source_review`, `project_company_event_questions` and source-reverified research publication services. Reproducer and verification are retained in the same runtime directory; handoff SHA-256 `2199bfa212d1345424206b2122aec5b7cee9c06e33da726085708ef00ae65627`.
- Prior company gates, valuation, price and safety margins are preserved; other companies, portfolio, events, stage admission and historical execution remain unchanged. Additional event questions are not an applied monitoring event or signed materiality approval.

Current research remains NOT_READY; ModelValidity not admitted; strict PIT not proven; no current PriceBridge or personalized position guidance. Canonical Excel, server/PTA, database and schedules were not modified. The next canonical publication must use the existing backup/preservation/source guard/WPS chain; this report alone does not publish an Excel update.
