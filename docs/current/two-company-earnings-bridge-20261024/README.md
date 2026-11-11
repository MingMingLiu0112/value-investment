# 双公司经营盈利质量桥：作者交付与独立复核入口

基线：`ed46931da0d7fceb1e75985e56f3ccfc75bfa61c`。本任务仅做真实公开原件的经营盈利解释。
不是经济准入批准，不修改现有研究、候选、估值、当前指针、签署链或公司页。
`action=no_order`，独立经济复核状态为 `PENDING_SEPARATE_REVIEWER`。

## 新增了什么，不重复什么

此前已完成扣非 TTM、母公司/合并现金总桥、原生现金时序和敏感性。本次不重做这些研究结论，
而是从四份留存 PDF 的利润表逐行提取当前/比较金额，补上此前未量化的经营驱动桥。
两家公司使用同一计算函数，无 symbol-specific 金融计算分支。

`research-results.json` 保存真实提取金额、原文摘录、source ID、原件路径及原始字节 SHA-256、URL、
物理页、期间、币种、单位、报表/归属范围；每个驱动行带组成事实引用。
`sources.json` 只定义原件及定位，不包含目标利润或应算出的桥结果。

### H1 真实结果（人民币元）

| 项目 | 600519 茅台 | 600887 伊利 |
| --- | ---: | ---: |
| 扣非归母同比变化 | -926,039,977.81 | -1,420,586,985.11 |
| 营业收入变化 | +1,313,906,547.64 | +2,554,189,864.70 |
| 营业成本变化对利润的贡献 | -1,696,271,481.95 | -1,384,881,082.54 |
| 税金及附加变化贡献 | -739,774,871.99 | -53,020,238.64 |
| 财务费用变化贡献 | -243,406,956.91 | +76,634,457.23 |
| 所得税费用变化贡献 | +386,230,707.07 | -751,939,373.03 |
| 少数股东损益变化对归母的贡献 | +67,269,006.22 | +269,901,722.69 |
| 营业收入减成本/税金/销售/管理/研发的描述性小计变化 | -1,049,660,963.09 | +865,462,056.32 |

完整桥还包含利息业务收入及已披露成本、其他收益、投资/公允价值/减值/处置、营业外项目和归母净非经常差额，
不能把上表精选行直接求和当成完整桥。伊利资产减值行同比贡献为 **-2,118,427,686.17 元**，
但它是合并损益行的变动，不是可直接加回的税后归母正常化调整。

两公司 H1 及年度完整驱动贡献之和均精确等于对应扣非归母变化；FY2025 对比 FY2024 的扣非归母变化分别为
茅台 -3,947,798,322.17 元、伊利 +5,057,046,749.20 元。
所有打印总额与已选明细的收入/成本/营业利润残差均为 0.00。
这只证明所选表内金额的勾稽，不证明空白行是已披露零、不证明完整经济归因、未来利润或公司没有其他义务。

## 对盈利锚的实质约束

- **伊利：** 商业费用前述小计改善与扣非归母下降同时成立。不能把销售恢复等同于股东盈利恢复；
  也不能因商誉非现金就恢复全部利润。资本损失、税负、少数股东归属和其他收益必须分开；
  本桥把少数股东变动明确列出，但不把其整体变化当成某一项减值的归母分配比例。
- **茅台：** 营业收入增长未覆盖成本及税金的增加；商业小计反而下降，金融业务收入与财务费用也不能忽略。
  因此不应把全部披露扣非利润理解成单一酒类经营能力，更不能把伊利减值加回逻辑移植到茅台。
- **共同限制：** TTM 仍是历史锚。`normalized_parent_profit_cny`、`normalized_range`、逐项税后归母调整、
  税率假设及归母份额均不推断；未知不是零。现有 RI 模型可继续作低置信条件研究，不能由本桥升级为中性主估值。
- **现金/模型适用性：** 合并归母盈利不是母公司法定可分配利润、可上划现金或支付日资金。
  本桥不修改权益、不把历史减值再次扣权益、不从已含分配的估值外加股息，也不建立第二金融引擎。

### 有限重开条件

只有能改变盈利锚或经营路径的明细才重开：明确的损失税后归母归属/扣非重叠、分部可持续利润、
新增资金收益贡献或下一期经营与资本损失变化。现有财报未披露的归属不能用默认 25% 税率或整体持股比例补造；
没有新信息时，不重复抓同一 PDF、重复总现金桥或强行填出正常化数值。

## Root 只读接线合同

模块：`value_investment_agent.application.research.operating_earnings_bridge`。

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from value_investment_agent.application.research.operating_earnings_bridge import research_from_retained_sources

spec = json.loads(Path("docs/current/two-company-earnings-bridge-20261024/sources.json").read_text(encoding="utf-8"))
symbol = "600887"  # 600519 uses exactly the same function
items = [dict(row, fields=spec["common_fields"] + row["extra_fields"])
         for row in spec["companies"][symbol]]
review = research_from_retained_sources(
    root=Path("D:/GPTProject/value-investment/.tmp/vv1"), specs=items,
    now=datetime.now(timezone.utc))
```

输出：`h1_change`、`annual_change`、`ttm.lines_cny`、`commercial_subtotal`、
`normalization_open_items`、`unallocated_balances_cny`、`original_statements`、`source_bindings`。
Root 可将这一读模型加入现有经济评估，不应将它直接当作 G3、模型适用性批准或候选输入。
`build_operating_earnings_bridge()` 是已核事实的纯计算合同；外部消费者应使用上述原件冷读入口，
而不是接受用户提供的任意事实字典或信任保存的结果 JSON。

原件在提取前、每份提取后及整次计算结束重查原始 Hash。
出版日仅提供事后研究的日期下界；原始实际取得时间未从本材料独立确定，保留 null，
不把今天能读到旧报告冒充历史时点已取得、生产完整事件覆盖或 PIT 通过。
研究规范与新实现采用显式 UTF-8/LF 指纹，以兼容 Git 换行转换；**PDF 原件仍按原始字节 Hash 校验**。

## 验证与复核分工

作者测试含：真实四份 PDF 重算、保存结果冷回放、独立 Fraction 勾稽、错误期间/范围/币种、
空金额/NaN、倒置列、重复定位、空白比较列不得借下一行、未来来源时点、来源漂移末次拒绝。
合成解析器负例明确是 TEST_ONLY，不用它们证明真实经济结论。

作者没有可用的独立 subagent 工具，不自行冒充第二审阅人。
Root 应另派独立复核者核读真实原件、核查经济解释与未识别项，再决定是否接线；本材料不记录经济批准。
共享 product/API/Web、冻结事实提取工具和旧包均未修改。

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:EARNINGS_BRIDGE_REAL_ROOT='D:/GPTProject/value-investment/.tmp/vv1'
$env:TEMP=(Join-Path (Get-Location) '.tmp')
$env:TMP=$env:TEMP
& D:/APP/Python313/python.exe -B -m pytest tests/test_operating_earnings_bridge.py tests/test_value_economic_assessment.py tests/test_source_native_economic_review_v1.py -q -p no:cacheprovider --basetemp=.tmp/eb-check
```

不设置真实原件根目录时，相关测试会明确 skip，不得将纯合成测试通过称为真实研究复算通过。

## 378 后继：两项 P2 提取边界修复

独立审阅指出的两项 P2 均先在 378 实现上复现：伊利摘要删去比较扣非金额仍被接受，
以及两家年度原件只改 periods 冒充半年均未拒绝；对应三项测试修前实际失败。

- 摘要现在先限定“主要会计数据”表，再按扣非完整行与下一现金流行边界截取。
  全行必须符合当前值、比较值、百分比及年度第三年值的完整列结构；不再向下一行搜索第二个金额。
- 仅允许明确列举的年度/半年合同：periods 与 column_labels 固定匹配，原报告标题、
  合并利润表实际起止月份及摘要表头同时匹配。旧规范未写 report_type 时只能由该固定合同确定；
  若显式提供 report_type，必须等于对应类型，未知类型拒绝。
- 新负例仅破坏真实 PDF 解析后的内存文本，不修改原件，包括四份摘要删比较值、年度冒充半年、
  同时伪造期间与标签、类型不符、未知类型和实际表内月份被改写。

当前修后冷复算材料为 `research-results-v2.json`。旧 `research-results.json` 与 `sources.json` 字节保留，
旧实现指纹仅解释旧版本，不重封。专用测试从原件重新计算，并逐一断言全部 **204 个打印金额**、
两家公司年度/H1 完整桥、TTM、商业小计及残差与旧结果相同。
P2 修复不更改任何经济结论、正常化金额、准入、模型阈值或 Web/API。
作者回归不等于独立复核通过，仍由 Root 指派独立审阅者验收此后继。
