# 600887 有限成本与衰减敏感性实跑（2026-10-11）

已按用户授权完成三个隔离、未准入对照。固定600887 v5实际财务锚、原估值时刻、base增长0及留存15%，使用现有共享 `current_projection` 和 `ResidualIncomeEquityValuationModel` 同步重建1年盈利段+3年全资本ROE衰减，terminal_roe=Ke、terminal_growth=0。未改既有policy/package/candidate、经济文档或Excel，未创建正式新候选、研究审批或价格/仓位结果，action=no_order。

## 实际结果与解释

| 条件成本 | 条件值（CNY/股） | 相对v5 base（CNY/股） | 相对变化 |
| --- | ---: | ---: | ---: |
| 7.74173173% 行业参照 | 10.2645764419 | +0.1894390889 | +1.88026309% |
| 9% 原base基准 | 10.0751373531 | 0，完整Decimal值精确相同 | 0% |
| 11% 成本压力 | 9.7871378155 | -0.2879995375 | -2.85851723% |

成本高档的逐年盈利较高、价值却较低：这是衰减至更高Ke使后续ROE更高，而要求回报与资本费用同时上升的综合结果，不是计算错误。仅在本次固定输入与1+3路径下实测价值严格下降；不推定任意模型/期限都必然满足同样单调关系。

较低行业参照仅使条件值增加约1.88%，11%压力使其下降约2.86%。这说明本次短优势期路径在所测有限区间的成本/衰减综合敏感性，不证明盈利锚、持续期限或现金分配经济假设正确，也不能由这三个点推断伊利真实Ke分布或完整上下界。未使用市场价，没有Margin of Safety、买点、仓位或订单。

## 真正保持与改变的输入

固定归母权益53711364981.99元、披露普通股6325360667股、历史扣非归母TTM代理9647734710.01元；不是已批准正常化盈利。base income_growth=0、retention=0.15、payout=0.85、growth_years=1、fade_years=3，全部继承同一选定short-advantage条件。其他原bear/bull情景的留存20%/10%不进入本次比较。

财务基期=`2026-06-30T23:59:59+08:00`；保留v5实际生成/估值时刻=`2026-10-11T08:21:25.089557+00:00`（北京时间16:21:25.089557）；实际敏感性执行完成=`2026-10-11T08:49:14.484523+00:00`。结果分别记录这两个时刻，不将新分析伪称在v5生成时已知，也不回填历史PIT。首个完整年付款基点仍为2027-06-30，不把第一预测期称为FY2026已观测利润。日期因子由现有 `valuation_time_factor` 消费，不把基期权益冒充10/11实测净资产。

| 成本 | 年1 ROE | 年2 ROE | 年3 ROE | 年4/终端ROE | 基期至原估值时刻因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7.74173173% | 17.96218494% | 14.55536720% | 11.14854947% | 7.74173173% | 1.0211986483 |
| 9% | 17.96218494% | 14.97478996% | 11.98739498% | 9% | 1.0245397127 |
| 11% | 17.96218494% | 15.64145662% | 13.32072831% | 11% | 1.0297936976 |

因此本次**不是纯贴现率实验**：成本、衰减后的盈利/权益/分红路径、终端ROE及日期运输因子同步变化。全部终端超额收益为0，终端增长为0；终端分红路径对账仍有非零终端股权价值，不能把“终端剩余收益贡献为0”解释成“终端股票价值为0”。模型假设的85%分配仅为代数路径，不证明母公司可支付、DPS政策下限或股东现金可得性。

7.74173173%按用户指定使用八位百分数；已核验China Food Processing 167家levered beta与冻结Rf/ERP公式的未舍入结果为0.07741731727957272242，本次decimal成本为0.0774173173，差小于5e-11。该行业点非伊利发行人beta；9%是既存base，11%是+200bp条件压力，不是信用点差或统计置信限。来源适配与限制详见既有 `600887-equity-cost-evidence-gap-20261011.md`，本次不改该文档。

## 执行与核验范围

临时执行入口：[run_600887_equity_cost_sensitivity_20261011.py](D:/GPTProject/value-investment/.tmp/run_600887_equity_cost_sensitivity_20261011.py)。使用apply_patch创建，只调用现有共享投影、typed Facts/scenario/model和年度算术函数；不新增金融公式，不运行collector或正式候选构造器。proposal rebase编译入口原有8%成本下限保持不变；7.74173173%是明确隔离敏感性，不是放宽该准入合同后提交的政策。

同一对照在共享模型所需bear/base/bull槽位中填入相同scenario，三槽位仅是调用合同适配，不是新增三个经济情景；输出按industry_reference/retained_base/higher_cost_stress三个真实对照分别保存actual_calculation_inputs及其SHA-256、完整model result和annual_arithmetic。没有生成package.json、candidate.json或DecisionRecommendation。

实际自动检查全部通过：

- 原v5通过 `verify_pending_research_candidate`，真实消费、来源及model_context一致。
- 9%重建forecast_roes与v5 base逐项相同，每股基准完整Decimal差额为0。
- 每个对照模型base值与 `_shared_scenario_calculation` 值精确相同；均为conditional_research_only。
- 四年ROE路径、最后一期/terminal_roe=Ke及零终端超额收益符合原共享合同。
- 共享模型剩余收益/分红路径对账差额为3e-37、0、1e-37元，均在原0.01元容差内。
- 三个条件值严格递减且为正；全部直接输入在计算前后hash不变。
- 独立第二次只读manifest核验：11个直接来源绑定及2个输出hash全部匹配。没有假称全仓回归或CI重跑。

## 新结果与精确绑定

新目录：[600887-equity-cost-sensitivity-20261011-v1](D:/GPTProject/value-investment/runtime/600887-equity-cost-sensitivity-20261011-v1)。运行脚本的相同字节另存execution-script.py，供主代理在临时目录之外复核；脚本只接受首次生成，不覆盖既存结果。

| 新制品 | SHA-256 |
| --- | --- |
| result.json | 47c91f919e642fb4e9054cf2e3fc0a07169e34625f2f196e2dd151f8bee841bb |
| manifest.json | fed4f2150868b6909b228cd13ba7a573d6874bfd7ef3b917723079a8081f6384 |
| execution-script.py及.tmp执行入口 | d5d8d7aa0996e0ab5be5b4c2a26cc07fafc117d6df1b5d6bc35af5126e5bcc15 |

直接来源路径相对 `D:/GPTProject/value-investment/`；完整11项绑定见result/manifest，包括执行脚本及共享模型/builder代码hash。

| 关键来源 | SHA-256 |
| --- | --- |
| runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/package.json | 3ec6e2c955343ccf287dcbeafc4beff7ac49f114f5ddc85679845e69422a25b5 |
| 同目录candidate.json | 410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299 |
| config/research-proposals/600887-20261011-v3.json | fc7dba372686f7fefb17364546046ae9bc8b2cd9eef29431a3ad2d83e6aa0edb |
| runtime/valuation-research/damodaran-regional-beta-20260909T120634559642Z/betaChina.xls | ff9187e1ca2dc5ee697e240d368f5c8f1956bc00c4ff8e8b0b0d46c698f2aee9 |
| 同行业原件目录manifest.json | 4a50688bd156ab748716a58aa25b93aaf15342de30f2240b54f6b9d62cb01fb9 |
| runtime/valuation-research/moutai-discount-basis-20260909T120002401955Z/evidence.json | 6dea599866140d28b7058d60b7c9a0d235aaed1def4df902011fc46e854de709 |
| runtime/valuation-research/damodaran-country-premium-20260909T115741948194Z/original.html | ea30d57fc0858072c520930e2e5b8a5e5affdce81f7f2e1f9054efab79959dbc |
| runtime/valuation-research/cfets-curve-20260909T080004856262Z/curve.raw | e364688dc8a866c53e19b733b9672fb1059bddeb5aae5b5804fc7bb8258b948f |

## 主代理核验交接

可核验提交的交付是新文档和上述新runtime证据及执行脚本副本；现有policy/包/Canonical保持冻结。主代理可先重算manifest输入/输出hash，再对照原candidate的base值及完整ROE数组，审阅result的日期、零终端超额收益和非准入布尔字段。本次未自行提交或推送。

本工作包完成的是用户已授权未准入敏感性实跑，不需要再次经济批准才能计算；同时没有产生任何经济/G3、材料性/模型有效性、当前价格、私人仓位或正式新候选审批。新runtime状态明确为UNAPPROVED_SENSITIVITY_NOT_A_NEW_RESEARCH_CANDIDATE，注册当前研究未改变。
