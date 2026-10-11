# 两家公司用户工作流独立审计（2026-10-11）

范围：附件9ce4f59b-b90a-414b-bf24-ec252c475a75的C/D/E；读取现有对象与发布snapshot，不生成候选、PDF、情景或批准，不修改共享源码、Excel或日期。审计读取时HEAD为`6fd7ed9cb3b0a4034dbc5084095bebffab31b4f4`。结论始终为待审研究、`no_order`，不等于HumanReview。

## 1. 优先修复：历史基线与待审候选不能共用无版本标题

Root确认的新view与本次snapshot/源码核查一致：主`valuation/scenarios`保留历史条件研究，而后面的`decision_review`描述v5。两者数值不同并非算错；缺的是展示身份、顺序和精确版本关联。

| 公司 | 主区历史条件基线（元/股） | 实际v5待审candidate_valuation（元/股） | 不可混用的另一时间口径 |
| --- | --- | --- | --- |
| 600519 | 404.82 / 479.88 / 572.74，压力用途 | 437.66 / 587.88 / 812.27，B_CONTINUITY_ALTERNATIVE，15年 | 同一提案B的retained_date_valuation为10/8，437.40 / 587.57 / 811.89 |
| 600887 | 8.05 / 11.02 / 13.13，既有登记情景 | 9.80 / 10.08 / 10.30，short-advantage，1+3年 | 同一提案短方案的retained_date_valuation为9/22，9.75 / 10.03 / 10.26 |

v5两者`candidate_valuation.valuation_date=2026-10-11`，财报锚仍为6/30。提案`choices[].valuation`保留原研究时刻；不能从该字段取数却标10/11，也不能把时间折算变化解释为新经营事实。默认摘要优先待审候选是合适的展示选择，不能覆盖登记`valuation`、改状态或接价格。

最小presentation修复：

1. 复用`presentation/research_supplement_surface.py:11`的`project_research_supplements(payload, root, symbol, bindings)`。在已调用`verify_pending_research_candidate`且来源Hash校验通过的分支，把`candidate_valuation`、`selected_choice`、候选路径/Hash及日期投影到有明确标题的`decision_review`研究摘要；不要只写“完整主估值候选待审”而省略实际数字。现有字段足够，不要求另建估值引擎或审核框架。
2. UI默认首屏先展示“当前待审研究候选（未批准，不能作为买卖价格）”，下方展示“历史登记条件基线”。不能将前者命名为“当前正式合理价”。历史`valuation/scenarios`值原样保留，版本和用途明确；主估值是否准入仍读既有门禁。
3. Excel的`presentation/excel/product_workbench.py:795`直接读`company.valuation`，`:882`及`:903`直接读`company.scenarios`，`:950`以后才逐行展开`decision_review`。公司页主区标题“估值”因此有混淆风险。最短修复是把该主区及旧情景表加“历史登记条件基线”标签，在其前插入上述已验证候选摘要与待审状态；首页`:556`/`:592`同样加基线标签/待审入口。只改标题、顺序和引用，不改数值、不重算、不把候选写入旧assessment。
4. `latest_change`茅台仍为10/8、伊利仍为旧低置信度研究说明，`next_trigger`伊利仍要求“不重复搜索停止证据集”。保留这些历史含义，但当前摘要另显示10/11研究准备及具体待审组；不要把“现在可审”写成“等待未来新披露才可审”。

## 2. 真缺与已有字段

本次读取`runtime/daily-trade-assistant/20261011-d2-admission-review-v6/product-read-model.json`的`/snapshot/companies`，不是wrapper顶层companies。SHA-256：`d7aab9d4c0c00dbfbdb17becd85f14591ad692dfa89a7436732961bc43476d84`。此为审计对象版本，不宣称后续Root发布仍为同一Hash。

| 已有内容，不应重复建设 | 实际差距及Root可改的数据 |
| --- | --- |
| `decision_review`已有五组茅台、四组伊利经济问题，支持/反证/影响/待审文字齐全 | 把组ID、editable-response引用、具体用途/整模型区别放到摘要附近；审核未填写仍为null，不把“支持”当接受结果 |
| 两家公司有完整窗口数量、事件重点、研究变化归因及审核入口；茅台已有逐ID旧模型影响行 | 旧影响行明确标旧登记模型；当前v5入口绑定七项/八机制原对象、candidate/model_context/scanHash，不因“同一公告已研究”继承旧裁决 |
| 伊利有18格历史敏感性与原网格Hash，茅台已有条件研究备选说明 | 缺v5所属敏感性/备选的直接摘要。伊利当前敏感性行属9/29旧网格；不能当v5结果。茅台snapshot没有“估值敏感性”行，不等于没有A/B/C研究 |
| `sections`、`next_trigger`、`decision_review`、`events`、`audit_evidence`、`event_audit_decisions`已可承载解释 | 缺版本合适的投影与导航，不是缺所有经济read-model字段。先复用CompanyCard（`read_models/product_workbench.py:679`）和EvidenceRecord；不必新增一套研究状态 |
| 当前研究/模型/价格/组合门仍阻塞，位置指导未准入 | 摘要需把“已核原件”“经济用途待审”“事件材料性待审”“当前价格未准入”分开。不得为了显示新候选清除历史研究门 |

`read_models/conditional_expectations.py`现有敏感性投影只接受原网格`arithmetic_match=true`，可复用其证据/范围约束，但不能把其历史expectations入口直接冒充v5。`read_models/event_followup.py:project_event_followup`会核对显示workbench绑定；其旧影响不可未经新绑定转贴到v5。

## 3. 现有证据能支持的经济判断与破坏线

下表是对既有有界研究的复核归纳，不是新增量化结论。原文事实与机制推断分开；未知不能填零。

| 公司/机制 | 已有事实与支持 | 最强反证、未知 | 实际参数用途与人工重开触发 |
| --- | --- | --- | --- |
| 茅台直营净贡献 | FY2025物理p9-11、H12026 p7-9已有产品/渠道收入及成本；支持研究渠道变化 | 直营份额/收入不证明净贡献；渠道成本、费用归属及组合未分离。H1成本增速高于收入、毛利走弱 | `forecast_roes.0..14`、`retention`及优势期的条件用途；下一可比披露若直营迁移伴随持续毛利恶化及维护费用上升，撤销净获益解释，重审盈利路径 |
| 茅台核心/系列酒、成本品牌维护 | 原经营页区分产品；核心品牌支持研究存量利润延续，而不是证明15年寿命 | SKU税后归母盈利未披露；系列酒、组合变化、成本与品牌维护不能从收入增速识别因果。维护/扩产投入未拆分 | 核心收入、毛利、扣非持续同口径恶化时重开增长/优势期；不能把新增资本低回报直接解释成所有存量利润永久侵蚀 |
| 茅台现金分配及财务公司 | 保留原件核对母公司现金变化、派息/回购、基金未实缴义务；不是单看集团现金 | 合并CFO、财务公司存款不等于普通股可分配现金；提款、上划及认缴时点未定 | `retention`及权益成本用途；出现资金无法提取、减损、上划限制或新增承诺须重审分配，不能由历史现金证明75%持续派息 |
| 伊利盈利/澳优减值 | H1扣非同比-20.25%；商誉/存货减值及澳优渠道恢复问题有原公告证据。液奶量/利用率及份额支持继续研究 | 份额和收入不证明归母净贡献；减值非现金不等于无资本损失；96.48亿元历史TTM非正常化。分业务到税后归母、库存处理现金成本未知 | 盈利锚、4年ROE路径及优势期；下一可比报告扣非继续下降、再次减值或澳优预测恢复未兑现，暂停恢复解释/重审，不税前全额加回、不重复扣已含减值的权益 |
| 伊利新渠道、CFO及外部融资 | FY p15、H1 p11-12及经营公告p1-2有新渠道增长；已有集团/母公司CFO和票据解释、兑付公告 | 新渠道不等于直营；毛利到净利润未桥接；付款基数影响CFO恢复；内部抵销不免外部银行义务。6/30现金不能减9/29兑付推算现余额 | `retention`、现金分配及成本用途；若续融资依赖、银行义务/担保上升、渠道库存及付款压力恶化，重审流动性/分配；兑付事实不自动闭合资金来源 |
| 伊利政策/资本成本/期限 | FY p49、5月股东会与分配实施页、H1 p30有年度政策/已实施股息/H1不分配；已有1+3与3+5条件研究 | 政策不证明未来现金能力；普通/特别分类未定。公司专属Ke与两个资本池衰减未识别，行业参考不等于issuer beta | 留存、Ke、terminal_roe、优势期；能否接受短方案仅是用途审核。维护后母公司可用现金或新增资本回报证据反驳时重开，不以中方案更贵作为选取依据 |

茅台原材料与机制的完整分离见`runtime/d2-600519-event-review-closure-20261011-v1/operating-countercases.json`（SHA `3f2d8cc58c022f8a5ae029e16f6c76467f9124365c53e7fe4ab86d21271f4e67`）；其FY原件`runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf` SHA `474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288`，页码为物理页，不补造SKU结果。

伊利见`runtime/d2-600887-event-review-closure-20261011-v1/operating-review.json`（SHA `f47d9df8ca07b03b9e7b099a8f1ab465e3b0d57606b0ed70e45458504b6df4d4`），页级原文取`evidence-pages.json`（SHA `49362281901a52e5027a659c62bf33df3111741d0ec39efbd27316eb1737b237`）及`mechanism-fact-anchors.json`，展示时保留其PDF路径、official URL、Hash与physical_page，不把解释替代原文。

## 4. 敏感性展示：复用实跑，不造新情景

茅台A/B/C已在v5绑定提案内：A压力、B持续性备选、C缓慢侵蚀备选。提案各choice保留10/8估值时刻；当前候选B另有10/11结果。最小展示为“用途/优势期机制/原日期/结果/反证/待审”，不是三个同概率预测，不借低市场价挑高结果。bear/base/bull还改变其他假设，不能全称单一Ke敏感性。

伊利`docs/current/600887-equity-cost-sensitivity-20261011.md`与`runtime/600887-equity-cost-sensitivity-20261011-v1/`已有实跑：base Ke9%为10.0751373531；行业参考7.74173173%为10.2645764419，压力11%为9.7871378155。固定原v5财务锚/时刻/增长0/留存15%/1+3，但同步改变Ke、fade、terminal ROE及日期因子，必须标题“成本与衰减联合条件对照”，不能标纯折现实验。结果Hash `47c91f919e642fb4e9054cf2e3fc0a07169e34625f2f196e2dd151f8bee841bb`；manifest Hash `fed4f2150868b6909b228cd13ba7a573d6874bfd7ef3b917723079a8081f6384`。本次published additional_evidence_bindings未直接列该敏感性结果，虽列equity-cost-review；Root可验证现有result/manifest与v5绑定后补摘要及审计入口，不重跑、不把行业参考升级为公司专属Ke。

## 5. 公告与九组审核：研究已准备，裁决仍空

茅台七公告已归并七项，399关联有完整追溯及57字段（15年逐年ROE和四个全局字段，三情景）；伊利33公告已归并八机制。不能让用户再手工处理399个机械关联，也不能从归并自动得出不重要。

最小数据入口：茅台`review-items.json`（SHA `32c4caa45ea539db8fa5ce37e2c16ec25af848abbf969a53807e064851e47834`）/`association-trace.json`；伊利`event-review.json`（SHA `27bac56b48e6aabcb6144d75d8bf8fd4bde026dbad3f5c7e20825e3bb4912fb7`）的`mechanisms/events/registered_assumption_fields`。按机制显示问题、支持、反证、未知、field范围和观测触发；展开保留每ID官方页码/URL/Hash。未判断field保持`NOT_ASSESSED`及decision/reviewer null，纯程序性项不默认无影响。

九组已有editable-response真实输入：`runtime/d2-human-review-inputs-20261011-v1/{600519,600887}-editable-response.json`。茅台为EARNINGS、DURATION、DISTRIBUTION、COST_TERMINAL、EVENT_MODEL；伊利为EARNINGS_IMPAIRMENT、CASH_FINANCING、CAPITAL_DURATION、EVENT_MODEL。显示其candidate_binding/model_context/valuation_artifact_sha256，不另造回答格式。具体用途接受不等于whole_model_approval，更不等于事件材料性。现有`application/product/research_reviews.py:59`准备入口与`:237`消费入口已有身份、签名、历史冲突及上下文约束，不能由UI/Agent代填批准。

茅台候选SHA `56554578776ab8eb7c1269ef2424df58a9cb90673f05c9370f2f792d929c1db2`；伊利候选SHA `410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299`。旧十年茅台/旧伊利裁决不得跨context复用。扫描窗口7/1-10/10与candidate valid_from10/11差异继续保留；不存在10/11全天覆盖证明，不生成另一EventScan、不改日期去满足合同。

## 6. 人工买卖复核与验收边界

当前两家公司不能生成正式BUY_CANDIDATE/ADD_CANDIDATE或个性化HOLD/TRIM_CANDIDATE/SELL_CANDIDATE；保留NO_ACTION。10/9归档收盘不是10/11候选的已准入PriceBridge，MOS不得按展示候选自行计算。Entry Thesis、真实持仓及组合容量缺失时，减仓/卖出只展示“研究重开线索”，不伪称已验证个人买卖一致性。

Root可将上述具体breaker投影到现有`next_trigger`与`decision_review`的人工复核条目：盈利/优势期假设破坏先暂停加仓及重审；资金分配受限重审留存/流动性；事实更正、再次减值、重大融资或模型失效撤销旧模型适用性。单期经营压力、股价涨跌和候选更高估值均不自动成为交易动作。不新增策略阈值。

拒绝/证据不足保留受影响用途和门禁阻塞；不要求对无关历史已核事实反复采集。真实身份registry目前为空；本审计没有注册身份、生成密钥、签名或审批。刊登“可以审什么”可以现在完成，“可正式买卖什么”必须走既有HumanReview/材料性/有效性/PriceBridge/私人输入合同。

验证记录：对上述两家公司经营/事件对象、伊利source-ledger/evidence-pages/mechanism-fact-anchors内的PDF path+sha256引用去重核对，48/48文件存在且Hash一致，无网络下载。此为文件完整性验证，不是新PDF抽取、会计计算复核或经济批准。Root展示验收至少核对：历史数字不变；候选摘要取candidate_valuation而非retained_date_valuation；九组null未升级；7/33逐ID仍可追溯；敏感性版本清晰；价格/MOS/仓位未越权。
