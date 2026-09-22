# 中国神华 B3 周期模型进度

日期：2026-09-21，补充记录 2026-09-22。范围：\`601088\` 的周期正常化工程与事实准入，不是正式估值、交易建议或回测结果。

## Engineering Status

已建立共享 \`CyclicalFacts -> CyclicalNormalizedValuationModel -> ValuationResult\` 合同。
模型只接受显式的中周期正常化情景利润、现金税率、维护资本开支、正常化营运资本变动、
折现率、长期增长率、资源寿命、归母净现金、普通股、低谷利润和单位成本输入。任一项缺失
或事实未验证时，模型显式返回 \`not_ready\`，不把 2025 年利润、低 PE 或期末股本直接外推。

已实现的计算公式是有限资源寿命内的正常化可分配现金现值，加上归母净现金，再除以普通股；
不使用通用 PE 作为主模型。三项情景仅在全部输入验证后生成，且状态只允许
\`conditional_research_only\`，不产生价格桥接、安全边际、仓位或订单。

## 已核验的一手事实

来源为 \`runtime/shenhua-2025-official.pdf\`，SHA-256：
\`460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc\`。

- 2025 年归母净利润 528.49 亿元，经营活动现金净额 750.59 亿元。
- 合并抵销前报告分部利润总额 793.39 亿元；其中煤炭 465.97 亿元、发电 126.27 亿元、
  铁路 129.01 亿元、港口 26.31 亿元、航运 2.69 亿元、煤化工 0.58 亿元、未分配项目 42.75 亿元。
- 报告分部折旧摊销 248.42 亿元，资本开支 446.86 亿元。
- 2025 年末总资产 6,277.61 亿元、总负债 1,463.10 亿元、归母权益 4,091.07 亿元、
  少数股东权益 723.44 亿元、货币资金 967.72 亿元。
- 中国标准煤炭保有资源量 414.1 亿吨，保有可采储量 173.1 亿吨，JORC 可售储量 111.3 亿吨。
- 自产煤销量 332.1 百万吨，不含税均价 472 元/吨；年度长协、月度长协和现货销量占比
  分别为 53.2%、39.4% 和 3.8%；自产煤单位生产成本同比下降 4.8%。
- 董事会提议每股末期现金股利 1.03 元，总额约 223.40 亿元，尚待股东会批准。

这些页码和数值由 \`build_shenhua_cyclical_scope.py\` 固化到
\`runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json\`，并有回归测试
校验原件 Hash。

## 已核验的多年原始时间序列

`build_shenhua_cyclical_time_series.py` 已从 2014--2025 年各年交易所披露原件逐页复核营业收入、
利润总额、归母净利润、经营活动现金净额和购建长期资产现金支出，生成
`runtime/company-research/shenhua-cyclical-time-series-20260921/evidence.json`。每一年都带
原件路径、URL、SHA-256 和页码引用。该产物状态为
`multi_year_raw_series_collected_but_not_approved_as_normalized_inputs`，只用于周期研究，
不是正常化盈利输入。

当前证据包 Hash：
`49cef89ea5309ad556b09132924845f02de79204c75d0ce3467fb3a9bb23f04e`。

序列保留了各年原报数，并单独记录 2024 年原报与 2025 年年报追溯调整的差异：
2024 年归母利润原报 586.71 亿元、追溯后 558.05 亿元。此前 2014--2025 年归母利润最低
161.44 亿元、最高 696.26 亿元；这些描述统计不代表中周期利润。

## 周期输入候选包（未审核）

`build_shenhua_cyclical_candidate_inputs.py` 已把 2025 年报可复算的部分输入整理为候选推导，
生成 `runtime/company-research/shenhua-cyclical-candidate-inputs-20260921/evidence.json`。
状态为 `cyclical_candidate_inputs_compiled_not_reviewed_or_approved`；该产物不进入共享估值模型，
不生成 bear/base/bull、价格桥接、安全边际、仓位或订单。

本轮候选记录：

- 现金税率：2025 当期所得税/税前利润为 20.81%，2024 年重述口径为 21.11%；这是两年历史候选，不是完整周期现金税率。
- 维护资本开支：折旧摊销 248.42 亿元只能作为会计代理；报告分部资本开支 446.86 亿元和现金资本开支 483.98 亿元是上限候选，年报没有维护/发展拆分。
- 营运资本变动：由合并资产负债表原始科目算出 +65.01 亿元现金占用；尚未扣除合并范围、关联往来和非现金影响。
- 资源寿命：JORC 可售储量/2025 自产煤约为 33.5 年，中国标准可采储量/2025 自产煤约为 52.1 年；这是静态比率，不是经评审的矿井服务年限。
- 净现金：合并和母公司层面均有表面候选，但少数股东、财务公司存款、受限现金、关联往来及资产负债表日后收购对价尚未分配。

以下模型输入仍不可从当前年报直接取得：归母税前营业利润、当前股本分母、折现率、长期增长率、
低谷营业利润和绝对单位成本。尤其是模型公式要求“归母税前营业利润”，而年报只披露合并税前利润与
归母净利润，不能把归母净利润直接代入后再次扣税。资产负债表日后收购已发行新增 A 股，且配套募集
资金仍进行中，因此期末股本 198.69 亿股也不能直接作为当前每股分母。

以上是候选包生成时的结论；三项专用桥接包的独立评审结果以下节为准，并会覆盖候选包中的状态。

## 三项阻塞证据包独立评审

`build_shenhua_bridge_independent_review.py` 已把三个桥接包与 2026 年港交所完整中期报告和
公司中文完整中期报告做独立比对，生成
`runtime/company-research/shenhua-2026-bridge-independent-review-20260921/evidence.json`，
证据 Hash `6F4238A5C520CA956E3D72D3EF366CE80E647FC4684A8FDAB897D3BA80A09E44`。
港交所全文 Hash 为 `A270E12BB523350F4066BA78C99B78057A1D82A39A9E0EF2C9A6E4AF46F0AE2E`，
公司中文全文 Hash 为 `7017CFD2F11DD6B4A284D35365950B33FD1EF36EE53C884BEA7A9D90C2602B9D`。

- 当前普通股分母：**批准为 2026-06-30 时点普通股输入**，候选
  `21,689,434,304`。港交所全文直接列示期末总股本、本期新增
  `1,820,914,349` 股、收购发行 `1,363,248,446` 股、配募发行
  `457,665,903` 股、无库存股，Note 26 的 A/H 股本亦完全勾稽；公司中文全文的
  数字令牌独立匹配。该值尚未单独写入 `CyclicalFacts.operating_inputs`，待估值日期与
  其余正常化输入一并确定后再注册。
- 归母税前营业利润：**拒绝作为已验证模型输入**。中期全文仍只披露分部税前利润、
  归母利润与少数股东利润，未披露子公司逐户税前、税费和少数股东分配。原
  `合并营业利润 × 归母净利润/合并净利润` 公式依赖统一税率与统一所有权比例的未支持假设，
  只保留为 dated pro forma 研究区间。
- 归母净现金与受限现金：**拒绝作为模型输入**。中期全文给出合并现金及等价物
  `51,673` 百万元、受限银行存款 `18,197` 百万元、三个月以上定期存款 `65,722` 百万元、
  借款合计 `157,628` 百万元，但未给出母公司/子公司现金债务拆分和少数股东现金分配。
  母公司法人现金不等于集团归母净现金；“current net liabilities `31,619` 百万元”是营运资本
  口径，不是可用于估值的财务净现金。2025 年母公司法人现金区间仅保留为表面参考，不进入模型。

评审后没有输入被注册到 `CyclicalFacts.operating_inputs`；共享周期模型仍为
`VALUATION_NOT_READY`，bear/base/bull 均为 null，不产生价格、安全边际、仓位或订单。

## 子公司归属边界审计（新增证据包）

`build_shenhua_2025_subsidiary_allocation_evidence.py` 已按年报第 340、428、429、439、440 页
生成 `runtime/company-research/shenhua-2025-subsidiary-allocation-evidence-20260921/evidence.json`。
该包固化母公司法人利润表、七家重要非全资子公司的持股、少数股东损益、分红、权益、收入、
净利润、经营现金流、资产和负债，并核验：

- 母公司法人 2025 年营业利润 642.33 亿元包含投资收益 446.07 亿元，其中联营企业投资收益
  32.24 亿元；法人利润不是集团归母税前营业利润。
- 七家重要非全资子公司少数股东损益合计 88.32 亿元，对合并少数股东损益 93.34 亿元仍差
  11.02 亿元；少数股东权益合计 457.23 亿元，对合并少数股东权益 723.44 亿元仍差 266.21 亿元。
- 2025 年煤炭资源领域专项整治非经常项为 -41.18 亿元；合并所得税调节只披露会计利润
  793.39 亿元、当期所得税 165.11 亿元和所得税费用 165.56 亿元，没有逐户税前和税费分配。

该包状态为 `subsidiary_allocation_boundary_audited_no_verified_allocation`，
`normalized_parent_operating_profit.model_input=null`、`attributable_net_cash.model_input=null`。
研究卡已增加该证据，并在 Excel 中显示该边界缺口；不改变 `VALUATION_NOT_READY`。

## IFRS 12 子公司税务披露复核（新增证据包）

为排除中文年报漏译或英文年报补充披露的可能，已下载并锁定 HKEX 英文/IFRS 2025 年报
`runtime/company-research/shenhua-2025-ifrs-annual-review-20260922/2026033003712.pdf`，
SHA-256 `491e701a90b1ece239b95ce3f3de27053f420583f2458d81cbe5b21b4607fdc9`。
`build_shenhua_2025_ifrs_subsidiary_tax_review.py` 已复核第 67、240、294、295、358--361、371 页，
生成 `runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922/evidence.json`。

复核结论仍为 fail-closed：

- IFRS Note 44 对七家重要非全资子公司只列示 Revenue、Expenses 和 Profit and total
  comprehensive income，且明确金额为集团内部抵销前；没有子公司层面的 Profit before income
  tax 或 Income tax expense。
- IFRS 口径七家子公司归入少数股东利润合计 90.94 亿元，对合并少数股东利润 102.85 亿元仍差
  11.91 亿元；少数股东权益合计 462.74 亿元，对合并 728.91 亿元仍差 266.17 亿元。
- Note 10 税务调节列出“不同分/子公司适用税率”影响 -42.28 亿元，证明统一税率或按归母净利
  比例分配税费没有事实依据。
- 董事报告只补充神东煤炭、朔黄铁路和准格尔能源三家主要子公司的营业利润附注，未提供全集团
  逐户税前、税费和少数股东分配。

该包状态为 `ifrs_12_sub_company_summary_reviewed_no_verified_pretax_tax_allocation`，
`normalized_parent_operating_profit.model_input=null`、`attributable_net_cash.model_input=null`。
专注回归测试 6 项通过；该复核随后写入神华研究卡，并通过候选工作簿、WPS 只读导航和原子发布
更新原 Excel。Excel 仍显示“估值未就绪”，不产生价格、安全边际、仓位或订单。

## 2014--2025 运营周期序列（新增证据包）

`build_shenhua_2014_2025_operational_cycle_series.py` 已从 2014--2025 年交易所披露原件逐页锁定煤炭
总销量与混煤均价、自产煤销量与均价、自产煤单位成本、售电量与电价，生成
`runtime/company-research/shenhua-2014-2025-operational-cycle-series-20260922/evidence.json`。
每个值均保留原件 URL、SHA-256、页码和披露修订上下文，并单独记录：

- 2024 年原报数与 2025 年年报对 2024 年的追溯数。
- 2015 年对 2014 年电力数据的追溯数，以及 2021 年对 2020 年单位成本的追溯数。
- 2025 年对 2024、2023 年因同一控制下收购杭锦能源产生的重述数。

关键口径结论：

- 332.1 百万吨是 2025 年产量；2025 年自产煤销量为 332.3 百万吨。
- 2014--2024 年集团混煤均价不能与自产煤单位成本配对反推单位毛利。
- 2019/2020 年售电单价受 2019 年 1 月电力合资公司重组影响，不能与前后年份直接比较。
- 追溯比较数不否定对应披露时点的原报数，两者分别保留。

该包当前状态为
`multi_year_operational_cycle_series_collected_not_approved_as_model_inputs`，
`financial_scope_approved=false`、`valuation_status=VALUATION_NOT_READY`；
公允价值、估值、模拟、交易和实盘字段均为 false 或 null。证据包 Hash：
`923cd297a72d39d20968a577475fb19640b2b8f87fe3ca9aefd353cbaa6ce6ad`。
研究卡已增加该证据；随后独立审查将其升级为“仅作时期事实”的可审计结论，不向
`CyclicalFacts.operating_inputs` 写入任何值。

## 2014--2025 运营周期独立审查（新增证据包）

`build_shenhua_operational_cycle_audit.py` 已对上述十二年期运营序列做独立口径审查，生成
`runtime/company-research/shenhua-2014-2025-operational-cycle-audit-20260922/evidence.json`。
审查状态为 `operational_cycle_series_audited_as_period_evidence_only`，
`registered_cyclical_facts_operating_inputs=[]`，不产生任何公允价值或估值。

七类字段的审查结论：

- 煤炭总销量、自产煤销量、自产煤单位生产成本和售电量：批准为逐页可追溯的时期事实。
- 自产煤均价：2022--2025 年才有可比披露，覆盖率为 4/12，不构成矿井到归母利润的贡献证明。
- 2014、2015、2017、2019 年自产煤销量来自后续年报对比表，时点应为后续披露日期，不能在
  该日期之前的历史模拟中当作当时已知事实。
- 集团混煤均价不得与自产煤单位生产成本相减反推单位毛利。
- 2019/2020 年集团平均售电单价因 2019 年 1 月电力合资公司重组不可比。
- 单位生产成本是历史生产口径，不是全口径交付成本、全现金成本或独立可比成本曲线。

审查同时锁定：2025 年自产煤产量为 332.1 百万吨，自产煤销量为 332.3 百万吨，两者不得混用。
证据包 Hash：`7d21b86914e87be98a95dace75356746ee501309f81be273bf6d1453648da015`。
研究卡已把旧阻塞项改为“运营序列仅批准为时期事实，不构成周期模型输入”，并修正普通股分母
状态为“已批准但尚未与估值日期和其余输入一并注册”。

## 2014--2025 归母利润与现金税候选序列（新增证据包）

`build_shenhua_2014_2025_attributable_profit_series.py` 已把各年合并营业利润、税前利润、
所得税费用、归母与少数股东净利润，以及现金流量表“支付的各项税费”整理为逐页可追溯的候选序列，
生成
`runtime/company-research/shenhua-2014-2025-attributable-profit-series-20260922/evidence.json`。
原报数与后续追溯调整分别保留；每一年同时提供统一所有权比例下的归母税前营业利润 pro forma、
“完全不分摊所得税”的宽边界，以及会计税率和现金税费支付比例。

该包明确记录以下边界：

- 归母税前营业利润是 pro forma，不是已披露法定报表行；统一税率与统一所有权比例假设未独立验证。
- “支付的各项税费”包含资源税及其他税费，不能直接当作所得税现金税率，只能作为保守税负上限。
- 2025 年统一所有权 pro forma 为 `63,580.757` 百万元；2015 年现金税费支付/税前利润为
  `1.132942386`，再次证明不能把该现金流比例当作所得税率。
- 非经营性项目和特别项目尚未正常化，中周期与低谷情景尚未推导。

包状态为
`attributable_profit_and_tax_candidate_series_compiled_not_reviewed_or_approved`，
`financial_scope_approved=false`、`valuation_status=VALUATION_NOT_READY`，没有值写入
`CyclicalFacts.operating_inputs`。证据包 Hash：
`0eb6e930831f19d0e7ab8520dbfd4f67dd2e4afc7183e36233fd4a4ee0191e64`。
研究卡已增加该序列证据和“待与外部价格、电力及运输基准一并评审中周期情景”的下一事件，并把
阻塞项改为“运营、利润与现金税候选序列仅作研究边界，未批准为模型输入”。

## 2014--2025 外部煤价与 2025 成本运输桥接（新增证据包）

`build_shenhua_2014_2025_price_cost_transport_bridge.py` 已从各年年报“煤炭市场环境”和
2025 年分部经营页建立逐页可追溯的候选桥接，生成
`runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-20260922/evidence.json`。
外部价格按披露日期分别锁定环渤海 5,500 大卡指数（2014--2022）与 NCEI 长协指数（2023--2025），
秦皇岛现货均价只记录 2023--2025；2025 内部桥接记录自产煤 472 元/吨、混煤 495 元/吨、
年度/月度长协及现货价、内部售电与煤化工价格，以及铁路、港口、航运单位成本。

该包明确记录不能直接推导模型输入：

- 2023 年外部指标定义从环渤海指数切换为 NCEI，不能拼成单一序列；2018 年无点值，2019 年只有
  550--650 元/吨区间。
- 2025 年 NCEI 均价 680 元/吨、秦皇岛现货均价 703 元/吨，而公司混煤和自产煤实现价分别为
  495 与 472 元/吨；热值、税费、运输、内部销售和合同结构未对账前，外部价格不等于公司利润。
- 煤炭表显示 73.2 百万吨以 447 元/吨售给发电分部，但发电分部燃料动力成本为 47,702 百万元、
  内部耗煤 77.7 百万吨，仍存在库存、采购组合、热值与分部调整的未对账差异。
- 171.6 元/吨是生产口径单位成本，不是路线加权、含铁路 0.082 元/吨公里、港口 11.5 元/吨和
  航运 0.030 元/吨海里的全口径交付成本。

包状态为
`point_in_time_external_price_and_cost_transport_bridge_compiled_not_reviewed_or_approved`，
`registered_cyclical_facts_operating_inputs=[]`。证据包 Hash：
`c99cec17a0b671bb6221dbe3e4a81a5f3bfff090e2e1f582872bb2cbc2e3059e`。
研究卡已增加该证据和新的“外部煤价与成本运输桥接存在指标断点和未对账差异”阻塞项。

## NCEI/BSPI/CCTD 外部指数一手溯源包（新增证据包）

`build_shenhua_external_index_provenance.py` 已把 NCEI 首发公告、NCEI 当前移动页面、
NCEI 历史查询公开壳页、NDRC 的 BSPI 试运行通知和 CCTD 秦皇岛动力煤编制方案逐一哈希归档，
生成
`runtime/company-research/shenhua-external-index-provenance-20260922/evidence.json`。
证据包 Hash：
`3cf0e8e5df004a6166738194564afd0f421b94c897f14e4261815297bcc4b427`。

已固化的一手事实包括：

- NCEI 运营方为全国煤炭交易中心有限公司，首次公开发布日期为 2021-12-31，首发公告同时声明
  独立、公开、透明及独立于直接利益相关方。
- 当前 NCEI 页面只归档两个日期观察：下水煤指数 758、发布日期 2026-09-18；中长期合同价格
  704 元/吨、发布日期 2026-08-31；两者环比均为 +3。这些是即时观察，不是历史序列。
- NCEI、BSPI、CCTD、CECI 历史指数表均显示“成为缴费会员，查看历史指数数据”，导出也需要
  登录及当年缴费权限；因此本次没有取得或伪造任何受权限保护的历史数据行。
- NDRC `办价格[2010]2399号` 固化 BSPI 试运行规则：7 天报告期、上周三到本周二采集、
  每周三 15 时发布、2010 年 10 月中旬起试运行，并由秦皇岛海运煤炭交易市场与中国价格协会组织。
- CCTD 2022-10-28 第五版方案固化 5500/5000/4500 kcal/kg 三类规格品、离岸平仓含税口径、
  综合/现货/年度长协三类价格及周度/日度/月度发布频率，并明确允许在限定情形下使用主观判断。

包状态为
`primary_provenance_archived_historical_operator_archives_membership_restricted`，
`registered_cyclical_facts_operating_inputs=[]`；所有即时指数值均为 `model_input=null`。
研究卡已增加“NCEI/BSPI/CCTD 运营方历史原始档案受缴费会员权限限制且尚未对账”阻塞项。

## CCTD 五个公开历史指数序列（新增证据包）

`build_shenhua_public_index_history.py` 已把 CCTD 指数中心页面引用的五个公开图表端点逐字节归档，
生成
`runtime/company-research/shenhua-public-index-history-20260922/evidence.json`。五个端点均为
`www.cctd.com.cn/Echarts/data/*.php` 返回的 JSON 数组，本次抓取无需登录；每个端点均保留
URL、SHA-256、抓取时间、当前页面标题与单位标注。

- BSPI：802 个唯一日期，2010-06-29 至 2026-09-16，保留值 371 至 854。
- 太原 TCPI/CTPI：130 个日期，2024-01-05 至 2026-09-18。
- 陕西 SCPI：501 个日期，2016-01-08 至 2026-09-18。
- 鄂尔多斯 OSPI：525 个日期，2014-06-10 至 2026-09-18。
- 长江口 YBSPI：379 个日期，2016-04-29 至 2025-11-28。

包状态为
`public_cctd_historical_chart_series_archived_not_reconciled`，
`registered_cyclical_facts_operating_inputs=[]`；所有观察值均为 `model_input=null`。证据包 Hash：
`9a3a5d5e586267e44f668e176eaeb4f73e210f64c442e6d117dbe0de32622fe4`。
该包同时记录 CTPI/TCPI 命名不一致、各单位标注不同、发布时间存在缺口，以及 BSPI 虽由 CCTD
网站托管，仍须与秦皇岛海运煤炭交易市场、中国价格协会及 NDRC 公告中的发布记录对账；不得据此
拼接为单一煤价序列。

## BSPI 公开序列与七份年报年度均价对账（新增证据包）

`build_shenhua_bspi_annual_report_reconciliation.py` 已把 BSPI 端点每个日历年内的未加权简单均值，
与 `shenhua-2014-2025-price-cost-transport-bridge` 中按年报披露日期锁定的年度均价逐项比较，生成
`runtime/company-research/shenhua-bspi-annual-report-reconciliation-20260922/evidence.json`。
证据包 Hash：
`7b4693eaada98ec0716de32d064ef58d2f25a116075ca88758b4231a55680443`。

2014、2015、2016、2017、2020、2021、2022 七个可比年份的均值偏差最大为 0.49 元/吨；
2015、2016、2020、2021、2022 五个年末值与年报完全一致，2014 与 2017 分别相差 2 元和 1 元/吨，
标记为年末发布日期尚未对齐。2018、2019 年报桥接没有可比年度均价；2023 年起公司年报改用
NCEI 长协价格，BSPI 端点均值不能与之直接比较。该结果只佐证序列口径吻合，不证明 2026 年下载
的历史值没有被运营方修订，也不能证明每个历史值在原日期已公开；因此
`registered_cyclical_facts_operating_inputs=[]`，仍不产生任何模型输入。

## BSPI 点-in-time 发布页与转载页证据包（新增证据包）

`build_shenhua_bspi_point_in_time_publications.py` 已把七份 BSPI 发布页按来源层级更正归档：
秦皇岛煤炭网 2017/2021/2022 的 577/737/734 一手文章 API 响应与网页外壳、CCTD
2014/2015/2016 转载页，以及中国能源网页面明确标注来源为“秦皇岛煤炭网”的
2017/2020/2021/2022 转载页。每项均固定 URL、字节数与 SHA-256，并分别记录报告期、页面发布时间、
页面中明确写出的发布日期、运营方 CMS `updateTime` 和端点最后观测。2020 期末 585 再纳入
易航网转载页：该页同样逐字重复 2020-12-23 至 2020-12-29、585 元/吨、OCFI 1257.40 与作者
齐红，并明确写“来源：秦皇岛煤炭网”，作为第二处独立转载证据；仍不是运营方原文。

关键边界如下：

- 2015 的 372 与 2016 的 593 CCTD 转载页和端点最后观测对齐；2017、2020、2021、2022 的
  577/585/737/734 也与对应端点最后观测一致，但中国能源网页面是明确转载，不是运营方一手发布。
- 2017/2021/2022 已找到秦皇岛煤炭网一手文章 80997/110846/114105；这些当前页面带有 2022 或
  2023 的 CMS `updateTime`，只证明地址和当前字节，不证明首次发布后从未修订。
- 2014 页面中的 525 对应 2014-12-17 至 2014-12-23，端点还有 2014-12-31 的 523，因此该页
  不得当作 2014 日历年末最后发布。
- 2017 最终发布为 577，而神华年报中的期末值为 578；端点显示 578 出现于 2017-11-08。两者是
  不同观测，不合并成一个模型端点。
- 2020 期末 585 的运营方原文在当前搜索索引和完整栏目列表中缺失；2020-12-23 的 582 与
  2021-01-06 的 593 均可寻址。中国能源网与易航网两处转载相互印证文本，但缺失状态仍显式保留，
  不从转载页升级或从相邻年份插值。

证据包 Hash：
`9d71ba5c3b4ccad4abcb442ba0735f21c994932e94eb2e8ef97ada790365e4fd`。
所有发布值均为 `model_input=null`，`registered_cyclical_facts_operating_inputs=[]`，仍不进入
周期估值模型。

### 2026-09-22 来源溯源补充与 CEI 登录限制收口

同一 BSPI 点时包继续补齐发布方归属与原始页可得性，不改变任何模型输入：

- 中国能源网 2018-12-27 页面固定 569 与“秦皇岛煤炭网”来源；河北长城网同日
  “河北港口集团秦皇岛海运煤炭交易市场发布”的运营方集团新闻报道作为第二处 569 佐证。
- CCTD 2019-12-26 页面固定 551，但作者是瑞达期货的市场评论，明确不是运营方转载页。
- CEI 2020-12-31 列表页可寻址标题“环渤海动力煤价格指数585元/吨”、日期和文章路径；链接的
  全文页受登录限制，因此只登记为标题/日期/文章路径，不是全文转载，也不构成运营方署名。
- 新增加 `PUBLISHER_PROVENANCE` 与 `ORIGINAL_AVAILABILITY`：BSPI 2018/2019/2020 与
  NCEI 2023--2025 的运营方原文均记录为 `ORIGINAL_NOT_EVIDENCED`；
  `operator_primary_article_missing_years=[2018,2019,2020]`，
  `not_collected_years=[2023,2024,2025]`。

更新后证据包 SHA-256 为
`2b5112abd8814c456874a0ff68704344b3c04b484ed534e809dca513d4bc1af2`。全部发布值仍为
`model_input=null`，`registered_cyclical_facts_operating_inputs=[]`，`financial_scope_approved=false`，
`valuation_status=VALUATION_NOT_READY`，模拟、交易和实盘准入状态仍全部为 false。

### 2026-09-22 六处独立旁证扩充

继续检索后，新增六份 2018/2019/2020 页面，但全部只登记为
`corroborating_publications`，不升级为秦皇岛煤炭网运营方原文：

- CoalChina 2018-12-26 页面，行业协会转载 569，明确标注来源为秦皇岛煤炭网；
- 河北经济日报 2018-12-31 版面，运营方集团新闻稿转载 569；
- 中国能源网与 CWESTC 2019-12-26 页面，各明确转载 551；
- CWESTC 2020-12-31 与国际煤炭网 2020-12-30 页面，各明确转载 585。

新增页面的 provenance 分别为 `industry_association_attributed_republication`、
`print_news_operator_group_report` 与 `secondary_attributed_republication`；总旁证页数由
4 增至 10，其中仍只有 2 处无明确运营方署名。所有新增页继续固定 URL、字节数与 SHA-256，
`model_input=null`。`operator_primary_article_missing_years=[2018,2019,2020]` 保持不变，
六处旁证只能增强文本互证，不能关闭运营方原文缺失。

更新后证据包 SHA-256 为
`a51b71db3fc928979e5c86de5d97704f6f3877f6e138f203b4d17cf048edaa0e`。研究卡已同步重写为
“四处明确转载 + CEI 标题/日期/文章路径”，并再次通过候选工作簿、WPS 只读导航与原子发布验证。

## 2025 内部煤电销售/耗用口径复核（新增证据包）

`build_shenhua_2025_internal_coal_power_reconciliation.py` 已将中文与英文/IFRS 年报交叉核验并
生成
`runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-20260922/evidence.json`。
证据包 Hash：
`8243e55efdff19e8d70389faf3bda510bf0d20c0bb5959525cb1ceae0912f9fb`。

年报披露的 73.2 百万吨是煤炭分部“对内部发电分部销售”，77.7 百万吨是发电分部“耗用本集团
内部销售的煤炭”，两者分别是销售量与耗用量，不是同一口径的算术勾稽项。发电分部共耗煤
97.7 百万吨，其中 79.5% 为集团内部煤；分部政策同时披露发电分部从煤炭分部和外部供应商采购
煤炭。报告没有披露 4.5 百万吨差异的吨数桥接，集团期末煤炭库存 23.4 百万吨及较期初 -2.5%
也不能独立解释该差异。47,702 百万元原材料、燃料及动力成本可能包含外购煤、热值质量、运输、
库存时点和其他能源投入，禁止除以 77.7 百万吨当作内部转移价。

因此该包状态为
`sales_and_consumption_basis_documented_no_explicit_volume_bridge_found`，
`registered_cyclical_facts_operating_inputs=[]`，不写入任何周期模型输入，也不把该口径差异
表述成必须强行相等的数据错误。

## 2014--2025 分线路到港/到厂全成本披露审计（新增证据包）

`build_shenhua_route_delivered_cost_audit.py` 已扫描 2014--2025 十二份中文年报与 2025
英文/IFRS 年报共 13 份原件、3,609 页，核对朔黄、神朔、包神、新朔、大准、准池、巴准、甘泉、
黄万、黄大、塔韩等线路名称、运输周转量/货运量/装船量/单位运输成本指标和“分线路”分配术语，
生成
`runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-20260922/evidence.json`。
证据包 SHA-256：
`f7d681992eb6a64d3bbc29bace836db2c4d168683a1dd2eddb3ee3908aa2d91b`。

结论是 `route_specific_delivered_cost_not_disclosed_or_approved`：

- 2025 年报披露铁路 313.0 十亿吨公里、0.082 元/吨公里，港口 217.0/44.6 百万吨、11.5 元/吨，
  航运 111.3 百万吨、114.9 十亿吨海里、0.030 元/吨海里，以及自产煤生产口径单位成本 171.6 元/吨；
- 这些仅是运输方式总量或平均值，报告未披露任一路线的吨公里、装船量、吨海里、路线成本，
  也未给出矿坑→铁路→港口/航运→客户的路线分配矩阵；
- 因此 `171.6 + 铁路/港口/航运总成本相除或相加` 被明确列为禁止计算，不得作为到港/到厂全成本、
  单位成本曲线或中周期盈利输入；
- `registered_cyclical_facts_operating_inputs=[]`，估值状态仍为 `VALUATION_NOT_READY`。

该审计把“生产单位成本不等于到港/到厂全成本”从边界说明升级为 2014--2025 全报告检索后的
Hash 锁定负向发现；如果未来取得路线分配矩阵、逐线运量与成本，应另建独立证据包评审后再注册。

## 当前缺口

- 原始多年序列与运营价量成本序列已完成口径审查，但全部字段只批准为时期事实；
  归母利润与现金税候选序列也已归档，但归母可分配口径、现金税率、维护资本开支、营运资本、
  价格和单位成本仍未形成任何正常化模型输入。
- NCEI/BSPI/CCTD 的一手首发公告、当前页面和方法论已归档，CCTD 五个公开历史图表序列已逐字节
  归档，BSPI 七份年报年度均价也已完成口径对账；但 NCEI/CCTD/CECI 历史查询表仍受缴费会员
  限制。BSPI 点时包已更正为秦皇岛煤炭网 2017/2021/2022 三个一手文章页、CCTD
  2014/2015/2016 转载页与五个明确转载页（2020 有中国能源网和易航网两处独立转载）；
  2018/2019 只有次级佐证，CEI 2020 只有标题/日期/文章路径且全文登录受限；2018/2019/2020
  运营方原文与 2023 年后 NCEI 原始发布档案仍未取得，修订政策也未核实。
  2025 内部煤电 73.2/77.7 百万吨已确认是销售/耗用两套口径且年报未给桥接；
  2014--2025 分线路到港/到厂全成本披露审计也确认无路线级周转量、成本或分配矩阵，
  因此不能转换为中周期价格或全口径成本输入。
- 年报披露储量吨数，但未给出以年计的矿井服务年限。
- 总资本开支未拆分为维护性与发展性资本开支。
- 普通股分母已评审批准为时点候选，但尚未与估值日期和其他输入一并注册；归母净现金与
  归母税前营业利润已评审拒绝，仍需子公司逐户或法定口径的税前、税费、少数股东与现金债务分配。
- 单位成本曲线和低谷偿债压力尚未与可比对象或历史低谷独立验证。
- 尚无经过评审的折现率、长期增长率和商品价格区间。

因此 \`financial_scope_approved=false\`，估值状态为 \`VALUATION_NOT_READY\`。

子公司归属边界与 IFRS 12 复核完成时，原表 SHA-256 为
`17036d1f8ebc094df9287ab25b4bf256f70b6aa9f1df23dedd16d3e7a98afa9b`。
2026-09-22 加入 2014--2025 运营周期研究卡后，再次通过候选工作簿构建、WPS 只读导航和原子发布
写回原 Excel；发布后原表 SHA-256 为
`0908adc8d280b422464d04be23f4c3a267195ef905e8715001a03d9244daf6e7`。
同日完成运营周期独立审查并更新研究卡后，原表 SHA-256 为
`80bd75d8009c97f58cbb6ee7bfa094f74fb97c8bf1ea30d7ba81ed5617efbd98`。
同日再纳入归母利润与现金税候选序列研究卡后，原表 SHA-256 为
`7564b978542458aa06d24a259f04ebeec4194e1720788b90dff722b9fcdb3304`。
同日再纳入外部煤价与成本运输桥接研究卡后，原表 SHA-256 为
`0a0fccbfbac18e9197d5b47cdcdc1263015b7650923f44c2ae9827ae73630820`。
同日再纳入 NCEI/BSPI/CCTD 外部指数一手溯源研究卡后，原表 SHA-256 为
`a72b1b73e78ddab429e22d58973b1ace220f9d5aa9c984a7ee04bcd90dd7fdd7`。
同日再纳入 CCTD 五个公开历史指数序列研究卡后，再次通过候选工作簿构建、WPS 只读导航和原子
发布写回原 Excel；发布后原表 SHA-256 为
`83119f16f82d7f79f65a07d14dab569986ffb7b015d65ef899c56c676d924668`。
同日再纳入 BSPI 七份年报年度均值对账研究卡后，原表 SHA-256 为
`d91cea2389f0067c6b9940b789ab414b1530602fce926e3296848b6a04402967`。
同日再纳入 2025 内部煤电销售/耗用口径复核研究卡后，原表 SHA-256 为
`7e173b2d32648a5c454be8d8e659cf458c5c44b2350f97465b461536da63a32b`。
同日再纳入 BSPI 点-in-time 发布页与转载页研究卡后，再次通过候选工作簿构建、WPS 只读导航和
原子发布写回原 Excel；发布后原表 SHA-256 为
`60845fda99b73aa9c7a94622c8bdade83e038b4ea020fc32e35d12aa3c4f8b5a`。
同日再纳入 2020 期末 585 的易航网第二处独立转载页后，再次通过候选工作簿构建、WPS 只读导航
和原子发布写回原 Excel；发布后原表 SHA-256 为
`26883e034d23a4a0de7752674ac6b2be5edf61a319484645953cb6931b60465e`。
2026-09-22 再纳入 2014--2025 分线路到港/到厂全成本披露审计研究卡后，再次通过候选工作簿构建、
WPS 只读导航和原子发布写回原 Excel；发布后原表 SHA-256 为
`f08cf8bb5500f136ba81b89053110371315a6a00d8de956fe1c298128e7c4c63`。
2026-09-22 再纳入 BSPI 发布方归属与 CEI 登录限制收口后，再次通过候选工作簿构建、WPS 只读导航
和原子发布写回原 Excel；发布后原表 SHA-256 为
`2203b670ea21b9767e9d831b9289e9d16c80a8685f52fa2930b4569da118359f`。
2026-09-22 再纳入六处独立旁证并同步研究卡表述后，再次通过候选工作簿构建、WPS 只读导航和
原子发布写回原 Excel；发布后原表 SHA-256 为
`acd1637a7ea4ed5bb0b459423f2cb7ecdc35f73efcb6cdf7f0ffed3d27feed0c`。

## Current Data Status

`build_shenhua_cyclical_valuation_result.py` 已生成
`runtime/valuation-results/601088-cyclical-b3/evidence.json` 及哈希锁定指针
`runtime/valuation-results/601088-cyclical-stage-b-latest.json`，状态为 `not_ready`；
bear/base/bull 均为 null。输出同时包含独立 `PriceBridgeResult=PENDING_EXTERNAL_DATA`，
不虚构模型有效性、行情或安全边际。Excel 统一状态行显示 `工程 READY / 数据
PENDING_EXTERNAL_DATA`，研究结论仍为“研究未完成”，不产生价格、仓位或订单。

## B3 Engineering Acceptance

见 [shenhua-stage-b3-engineering-acceptance-20260921.md](shenhua-stage-b3-engineering-acceptance-20260921.md)。
共享周期模型、2025 年报周期范围包和 fail-closed 结果已通过工程验收；生产估值仍未就绪。

## 下一唯一工程任务

下一唯一工程任务：继续补齐 2018/2019/2020 BSPI 运营方原文（中国能源网/易航网转载与 CEI
标题列表只作佐证，不得升级为原文）、
2023--2025 可比较的 NCEI 原始发布档案与修订政策；2014 的 525 与 2017 的 577/578
日期差异保持未对账，不插值。2025 内部煤电 73.2/77.7 百万吨已固化为销售/耗用口径差异，年报
未给桥接；2014--2025 分线路到港/到厂全成本审计也已固化为无路线级披露的负向发现。只有在
未来取得路线分配矩阵或可比的独立成本曲线证据后，才评审路线加权全口径煤炭成本。只有这些输入
对账通过后，才能决定是否写入
`CyclicalFacts.operating_inputs`。普通股分母
`21,689,434,304` 已批准，待估值日期和其余正常化输入具备一致 provenance 后再注册；在全部
输入通过评审前，共享周期模型继续 fail-closed。
