# 600887 权益成本证据与可复用边界（2026-10-11）

## 研究结论

已有材料足以形成伊利的**低置信、非批准权益成本敏感性论证**，但不足以给出伊利发行人 beta、公司专属成本中心或统计上下界。可复用的是 CNY 主权收益率代理、同日期中国 ERP、行业原件与校验/回归方法；不能继承茅台股票 beta、茅台选档政策及任何发行人批准。

本次实际发现并核验：已保留的 China/Global XLS 不只有旧脚本摘录的酒类/饮料，还包含 `Food Processing`。中国食品加工 167 家的 levered beta=1.1790723206；与已保留市场输入相乘得到约 **7.7417%** 的条件公式诊断。伊利实际 v5 的 8%/9%/10% 并非由该数据估计的区间，但也不是毫无可比较依据：8% 略高于该行业代理，9%/10% 是更高要求回报条件，尚需发行人风险证据解释差额。不能用该比较宣布 9% 被认证或将 7.74% 自动替换现有政策。

本文件仅新增研究意见；action=no_order。未运行任何 collector/main、下载原件、收费 Provider、生产或修改冻结 policy、旧经济文档、事实及审批。

## 脚本究竟可以复用什么

| 已读脚本 | 可复用的方法 | 不能直接作为伊利结果的原因 |
| --- | --- | --- |
| scripts/research_moutai_market_beta.py | 带截距月收益 OLS、独立 Decimal 协方差核对、同日总收益对齐、多个窗口与 IID 误差诊断 | main/load_inputs 硬绑定 sh600519、15 次茅台分配、2674 日/131 月和茅台年度原件；最新现存输入不是 sh600887。estimate_market_slope 本身可复用，但它不会验证发行人、总收益或基准身份 |
| scripts/assess_moutai_current_cost_of_equity_policy.py | 检查精确来源、注册早于计算、日期范围、bear/base/bull 映射、实际模型消费及+200bp压力 | 固定读取茅台 latest/model/policy，明确 symbol=600519；passed 只证明该条件政策消费一致，不证明伊利权益成本，也不等于 G3 |
| scripts/collect_regional_beta_reference.py | 保留作者原 XLS、来源 URL、获取时刻与 hash；原件可直接只读再解析 | 原摘要只选 Beverage，不能把摘要缺 Food Processing 当作原件无资料；collector 不核验所有行业或发行人样本 |
| scripts/verify_regional_beta_reference.py | typed Excel 日期/datemode、地区与列身份、边际税率去杠杆及现金调整复算 | 固定 Beverage (Alcoholic)，旧验证结论不能搬到乳品。本次对 Food Processing/Soft/Farming 行另作只读算术复核，不修改脚本或原摘要 |
| scripts/collect_industry_beta_reference.py | 保留原 HTML、表头和作者来源；可在原 HTML 定位 Food Processing | 网页明确是 **US**，不是 China；摘要亦只摘 Beverage。美国行业点不能充作第二个中国 beta 认证来源 |

只读核查 `runtime/historical-prices/20260908T061418761988Z/manifest.json`：现有该长样本价格包只有 sh600519、sh601088、sz000333，没有 sh600887 年度系列。故本次不能以改一个 symbol 或复用茅台 monthly.csv 声称已估计伊利 beta。这个结论限定于所审脚本的现存输入链，不声称仓库任何其他目录都不存在伊利行情。

茅台最新市场 beta 包的 29 个 input bindings 和三个输出 hashes 全部匹配；其 2015-02至2025-12、131 月斜率约0.9875344414仍仅属于茅台。立即除权日分数股再投资是假想总收益，不是税费后可执行账户；原始月收益而非逐月无风险超额收益、IID 区间未涵盖序列相关/基准/窗口变化。方法的这些限制对将来伊利计算同样成立，不可继承“前瞻 beta 已被观测”的解释。

## 已有原件的币种、日期与范围

CFETS 原始 `curve.raw` 精确 10 年行：curve_date=2026-09-08、yearTermStr=10.0、maturityYieldStr=1.6813、currentYieldStr=1.6972、futureYieldStr=2.3639；同目录请求 manifest 为 CYCC000/该日国债曲线。百分数转 decimal 后当前选用的 CNY 名义 YTM 代理为0.016813，不是 spot/forward、无信用风险零息曲线或10/11最新报价。把它用于模型年有效 `(1+Ke)^t` 是显式研究约定，不能用单位正确替代复利/期限适配判断。10/11距曲线日33天，只能称冻结基准。

Damodaran 国家原 HTML 页标 Last updated January 5, 2026，9/9取得。China 行为 A1、调整违约利差0.60%、国家溢价0.91%、总权益溢价5.14%、税率25%、主权CDS0.50%、CDS法ERP4.99%；列名直接核读。采用5.14%不是取4.99%或25%，亦不得再加0.91%。它从美国市场隐含回报与跨国风险方法迁移，虽溢价无量纲，不能称直接观测的10/11 CNY/沪深300前瞻 ERP。

两份 regional XLS 的 Industry Averages!B1 均为 typed Excel 日期2026-01-05，F3分别 China/Global；F8为 Marginal，F9分别0.25/0.2537。这是地区平均**边际**税约定，不能拿 E列有效税率代替，也不是伊利实际税率。beta 无量纲，D/E及现金占比是比率（例如0.2071686=20.71686%，不能再除100）；全球 beta 不是美元利率，其地域/基准迁移限制仍存在。

## 直接重读行业行与独立复算

下表来自 China/Global XLS 的 `Industry Averages` 物理 Excel 行，未从旧 Beverage 摘要推断。所有行按作者边际税复核 `betaU=betaL/[1+(1-t)D/E]`、`betaU_cash=betaU/(1-cash_fraction)`，与发布数字差小于1e-12。算术一致不证明样本适合伊利；原件没有在本次核读范围内提供已核验的个股成分、估计窗口和各股基准。

| 地区/行/行业 | 家数 | levered beta | D/E | 去杠杆 beta | 现金占比 | 现金校正 unlevered beta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| China/45/Food Processing | 167 | 1.17907232 | 20.7169% | 1.02050923 | 9.2610% | 1.12466438 |
| Global/45/Food Processing | 1450 | 0.67372445 | 37.1026% | 0.52762645 | 5.8189% | 0.56022535 |
| China/20/Beverage (Soft) | 3 | 1.36978525 | 1.8775% | 1.35076515 | 4.2901% | 1.41131176 |
| Global/20/Beverage (Soft) | 94 | 0.59284847 | 18.7202% | 0.52017539 | 4.0307% | 0.54202266 |
| China/43/Farming/Agriculture | 43 | 1.39736446 | 52.0245% | 1.00516553 | 9.3381% | 1.10869728 |

US 原 HTML Food Processing 行另有78家、levered beta0.61、D/E43.73%、unlevered0.46、现金2.56%、cash-corrected0.47，页上 Data Used: Multiple data services / as of January 2026。该网页只公布四舍五入数，本次不把其四舍五入变换误差当失败。US/China/Global均为同作者聚合，Global与China样本重叠，不能声称独立双源、平均成一个发行人 beta，或以最高/最低点组成伊利统计区间。Global历史 Average (2020-24) 表头与邻列2022–2025不一致，该历史列不使用。

## 伊利的经济适配判断

实际再核 H12026 PDF hash，并直接读物理p11–12、p14、p148、p174。p11将奶粉及奶制品收入列为168.45亿元，亦描述液体乳销量/产能利用；p12还有功能保健食品。**Food Processing 是本次最接近的宽行业主参照**，优于酒类；Soft Beverage 可以反证“全部乳品均等于食品加工平均”，但China只有3家公司，不适合作主中心。Farming适合提示上游/原奶风险，不能把整个合并上市公司归类为牧场，更不能按收入权重直接平均不同聚合 beta。

p14列印尼/菲律宾冷饮、中东及波兰婴幼儿羊奶粉、新西兰基地与中国原料协同；故中国ERP可作为本币上市权益的冻结基准，却不能仅凭A股注册地认定全部国家风险载荷=1或beta。现有材料没有已绑定的跨国风险权重；全球较低行业点不能据此自动“分散风险”并降低公司成本。

p148显示合并短借646.7719303415亿元，其中票据贴现481.4101426249亿元；原文说明是合并范围内企业间未到期承兑汇票向银行贴现。p174现金等价物139.1427757164亿元，另列不属现金等价物货币资金27.0246471869亿元，包含法定准备金/保证金等。内部往来消除不消灭外部银行义务；现金与借款口径不等于可自由上划的净现金。二者支持研究融资/现金风险，但**不足以计算市场价值净债务D/E或固定加100/200bp**：短借不是全部融资，账面归母权益不是市场权益，现金亦不能全部按无风险零beta扣除。

这解释为什么行业 levered beta不能直接作为伊利 beta，而cash-corrected unlevered也不能直接放进当前合并归母权益剩余收益模型：后者是资产风险代理，须说明发行人现金还原、税/融资和relever过程才能转为权益风险。当前模型用的是Ke，不是WACC；不必为本工作包发明新WACC引擎或强行金融剥离。

## 可以提出的非批准敏感性建议

为复核现有8%/9%/10%条件是否遮蔽成本敏感性，使用冻结关系 `Ke_proxy=0.016813+beta_proxy*0.0514` 仅作解释性对照，不选择发行人 beta：

| 代理或现有条件 | 诊断结果 | 合法解释 |
| --- | ---: | --- |
| China Food Processing levered beta | Ke=7.74173173% | 最接近宽行业的研究参照，非伊利测得成本 |
| China Soft Beverage levered beta | Ke=8.72199619% | 小样本/行业差异诊断，非更准确公司中心 |
| Global Food Processing levered beta | Ke=5.14424368% | 使用相同CNY/China输入的跨地区方法诊断，不能作为伊利低档批准 |
| 已有Ke=8%/9%/10% | 公式隐含beta=1.229319/1.423872/1.618424 | 只是代数反解，绝不是观测/拟合到的伊利beta |

9%相对China食品加工诊断多125.8268bp；8%多25.8268bp，10%多225.8268bp。现有发行人融资、海外和混合业务事实能解释为何需要检查这类差额，但不能把具体差额当已证实风险溢价。没有资料证明9%“过高/过低”或8%–10%涵盖真实成本。

**建议保留既有政策不动，允许审核材料提出一个约7.74%的行业参照对照及一个11%的成本压力对照（现有base9%+200bp）**。前者测试更接近已保留本地行业代理时结论变化，后者测试当前成本上档不是风险上界；+200bp只是继承既有可解释压力幅度，不是伊利信用点差或统计置信限。无需新增随机情景，亦不借股价调参。

本次没有跑新的伊利估值或输出新的买点。若后续获授权执行对照，应在同一选定short-advantage、同一历史资本/股数/TTM、增长及留存条件下，用现有共享模型重新生成完整逐年ROE/fade/terminal绑定。v5的bear/base/bull不仅Ke不同，retention也为20%/15%/10%，故不能把现有三档价值差全归因于Ke。现有零永久超额收益约定要求terminal_roe=Ke、terminal_growth=0；只改贴现而冻结旧terminal_roe会改变经济终值，应将成本变化对应的终端与衰减处理明确披露，不能暗称纯贴现实验。

此对照能完成敏感性研究，而非形成批准成本中心。发行人更精确论证的必要证据限于：自己的同日/同币种总收益及分配校正链、明确基准/窗口；或可比成分、发行人融资/现金市场口径及适配的bottom-up beta。当前所审链缺这些输入，不能靠茅台原件补位。需称10/11同期成本时，还须另有该截止前的同期Rf/ERP证据；冻结研究不必伪造刷新。

## 本次实际 hash 核验

路径均相对 `D:/GPTProject/value-investment/`。regional collector五输出、industry/country各两输出、market-beta三输出、discount-range一输出均与manifest相符；另核对basis三输入、regional verifier三输入、range三输入及beta29输入，均无漂移。basis/normalized使用evidence_sha256而非outputs结构，亦核对其记录的实际evidence hash；CFETS curve.raw与请求manifest记录相符。

| 原件/关键制品 | 本次 SHA-256 |
| --- | --- |
| runtime/valuation-research/damodaran-regional-beta-20260909T120634559642Z/betaChina.xls | ff9187e1ca2dc5ee697e240d368f5c8f1956bc00c4ff8e8b0b0d46c698f2aee9 |
| 同目录 betaGlobal.xls | 10c33f46df2a35fa7e4e8c4386c01f9da636fc2ab3e1e98307a52a947c9ab52b |
| 同目录 manifest.json | 4a50688bd156ab748716a58aa25b93aaf15342de30f2240b54f6b9d62cb01fb9 |
| runtime/valuation-research/damodaran-industry-beta-20260909T120253277020Z/original.html | 10993bab71504e2449ccdd9e3d67fa4da983bed380b2f4486e5200a7b258616b |
| runtime/valuation-research/damodaran-country-premium-20260909T115741948194Z/original.html | ea30d57fc0858072c520930e2e5b8a5e5affdce81f7f2e1f9054efab79959dbc |
| runtime/valuation-research/cfets-curve-20260909T080004856262Z/curve.raw | e364688dc8a866c53e19b733b9672fb1059bddeb5aae5b5804fc7bb8258b948f |
| runtime/valuation-research/cfets-normalized-20260909T091701127108Z/evidence.json | 17a99be70a289f1be7d677ba3b63bc4c68c2855f62115e8b204cd1eb8f3f0578 |
| runtime/valuation-research/moutai-discount-basis-20260909T120002401955Z/evidence.json | 6dea599866140d28b7058d60b7c9a0d235aaed1def4df902011fc46e854de709 |
| runtime/valuation-research/moutai-market-beta-20260912T161052067136Z/evidence.json | edb4592aa6a5d81f5f8c5e9c8c48578950d0b59f65b79f9db6f3b173546c7a3c |
| 同目录 monthly.csv | 874e92c7ed22514150c32b57c2f0127792ffb4a5d2956ec20f86f2f92da45d13 |
| runtime/valuation-research/moutai-consolidated-parent-equity-discount-range-20260914T104355Z/evidence.json | d53f204548a2a97c83c046572b93e331af3963e53773f0b3f8d4962a819dd154 |

伊利半年报：`runtime/company-research/m1-valuation-filings-20260923/600887/2026-06-30-interim-6c456d8e5f19ba114b2cac48595f997612f66b337d294265975ed5eb7c3499ab.pdf`，实际SHA-256=`423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2`；官方定位 `https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF`。币种/财务期间为人民币/H12026，获取与本次核读不回填发布时间或历史PIT。

五个脚本本次快照hash：research_moutai_market_beta.py=`bff5f7e191a23fd5ffdcbb11628c1e4b94b8a2faaabbad0fdf5a651a8a23eda8`；assess_moutai_current_cost_of_equity_policy.py=`533be8534d210dd91855a5a516325ceab1e6bc0ba87027a601a4423b878f03e3`；collect_regional_beta_reference.py=`18523d4831734ea742fa7f383d6fce0e7c3c483fd0fb243db964fb8bfb01df21`；verify_regional_beta_reference.py=`56ba8330a90126d6c4a81f9b3885d609f2ff0d8c692744dc46382b2012aae88f`；collect_industry_beta_reference.py=`c20c394bdcd51b17d5a0d869b10e279c7d20459a965d6d5ce0c86ed08412a1bd`。

研究交付范围：实际原件与计算口径已核；食品加工比酒类更合适的宽行业对照已论证；8%–10%解释及非批准敏感性已提出。未估计/批准伊利发行人beta，未选定正式Ke，未批准经济/G3、分红能力、材料性、ModelValidity、价格或交易。
