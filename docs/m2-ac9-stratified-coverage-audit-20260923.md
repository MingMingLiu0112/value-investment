# M2 AC9 分层覆盖审计：2026-09-23

更新：2026-09-24。本文保持 AC9 审计当时结论。当天之后，M2 原工作簿已受保护发布为
55 个工作表，其中 `10_逐通道覆盖` 与 `11_研究报告`、`12_研究证据` 进入统一入口；本页
“尚未写入原 Excel”是 AC9 报告生成时的历史状态。

## 状态

- 审计范围：`current-stage-goal.md` 的 AC9，即入选、未入选、数据缺口、不支持、预算外及 legacy 差异的分层审查。
- 审计状态：`MACHINE_CHECKS_PASS`。
- 验收状态：`AC9_REVIEW_PENDING`，即使本文件完成抽检阅读，也不单独宣告整个 M2 毕业。
- 执行边界：`action=no_order`；未连接生产 PostgreSQL、服务器、PTA、调度或 WPS 生产工作簿。

## 固定输入

| 项目 | 值 |
| --- | --- |
| 抽样配置 | `config/m2-coverage-sampling-v1.json` |
| 抽样版本 | `20260923-v1` |
| 收据 | `runtime/m2-live-20260923-v3/receipt.json` |
| 收据 SHA-256 | `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220` |
| run id | `m2-replay-20260923T232854Z` |
| coverage signature | `4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805` |
| candidate signature | `f77fd5f0e139cf0ab283e9aee9fdd2f4f66695071c85816f303c9b31715cbe79` |
| 审计报告 | `runtime/m2-ac9-coverage-audit-20260923-v2/report.json` |
| 报告 SHA-256 | `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695` |

## 预注册抽样规则

1. 抽样框架是每个官方证券在每个通道各一条 evaluation，共 5,568 × 4 条。
2. 选择键为 `SHA256(seed | stratum_id | channel | symbol)`，相同代码时按 symbol 稳定排序。
3. 每个层每通道预注册抽取 6 条；没有该状态的通道保留 0，不跨通道补数。
4. seed 为 `m2-ac9-stratified-coverage-20260923-v1`，在查看结果前写入配置。
5. 禁止收益、回测收益、价格后验或阈值拟合；配置和报告均拒绝交易/仓位键。

## 覆盖矩阵

| 层 | 来源 | 总人口 | 已抽样 | 说明 |
| --- | --- | ---: | ---: | --- |
| selected_leads | candidate | 150 | 18 | Quality 为 0，另外三通道各 50，按通道抽 6 |
| rejected | evaluation | 7,564 | 24 | 四通道明确拒绝原因 |
| data_gap | evaluation | 6,829 | 18 | 保留缺失，不当作拒绝 |
| unsupported | evaluation | 469 | 24 | 金融等不适用画像隔离 |
| budget_excluded | evaluation | 2,255 | 18 | 通过但超出展示预算 |
| not_evaluated | evaluation | 5,005 | 12 | 分红缺失、行业不适用等 |
| excluded_security | explicit list | 186 | 12 | Dividend/Value 显式排除与 missing |
| legacy_set | legacy/new set | 774 | 18 | overlap/new-only/legacy-only 各 6 |

## 逐通道状态

| 状态 | Quality | Dividend | Value | Cyclical |
| --- | ---: | ---: | ---: | ---: |
| PASS | 0 | 50 | 50 | 50 |
| REJECTED | 775 | 3,097 | 3,581 | 111 |
| DATA_GAP | 4,672 | 0 | 1,465 | 692 |
| UNSUPPORTED | 121 | 106 | 121 | 121 |
| BUDGET_EXCLUDED | 0 | 369 | 351 | 1,535 |
| NOT_EVALUATED | 0 | 1,946 | 0 | 3,059 |
| CONFLICT | 0 | 0 | 0 | 0 |
| 合计 | 5,568 | 5,568 | 5,568 | 5,568 |

## 机器勾稽结果

以下检查全部 `PASS`：

- 每通道 evaluation 数均等于官方 Universe 的 5,568，无缺失或额外分母。
- PASS 集合与展示候选集合完全一致：Quality `0=0`，其他三通道 `50=50`。
- 150 个展示对象全部为 `LEAD`，已核候选池为 0。
- 非 Quality 的 150 个线索全部保持 `DATA_PARTIAL`，没有被便宜筛选冒充完整研究。
- BUDGET_EXCLUDED 原因均明确保留“展示预算”，且不进入展示候选集合。
- 全部 evaluation 的 evidence date 与 `quote_date=2026-09-23` 一致。
- Legacy 清单长度与其声明数量一致：747 条 legacy、113 个不重复新候选、86 个重叠。
- Quality 空池被解释为财务证据覆盖不足，而不是全市场没有质量公司。

## 实际抽检结论

### 1. Quality 空池是覆盖限制

Quality 显示 0 个候选，但当前快照只有 873/5,568 个官方证券有财务质量证据；其余 4,672 条是
`DATA_GAP`，另有 775 条 `REJECTED` 和 121 条 `UNSUPPORTED`。因此“Quality 0”不能读作
“A股没有质量公司”，而应读作“当前数据不足以生成 Quality 线索”。该限制是后续深研和
数据源补齐的方向，不是投资结论。

### 2. 预算截断没有被静默删除

Dividend/Value/Cyclical 分别有 369、351、1,535 个通过对象超出单通道展示预算 50。它们仍保留在
5,568 的覆盖率分母，并标记 `BUDGET_EXCLUDED`。抽到的例子包括海大集团、深圳机场、广州酒家、
安徽合力、海信家电等。当前 evaluation 只保留预算原因，不保留触发指标；要复核这些疑似漏筛对象，
必须用同一收据引用的原始输入重放，不能凭名字或后来价格判断。

### 3. 入选样本没有被升级为已核候选

抽到的 Dividend 线索包含华能国际、天地科技、周大生、富安娜等；Value 线索包含华域汽车、中国建筑、
南京高科等；Cyclical 线索包含华友钴业、梅花生物、动力新科等。它们均带“FCF/EV-EBIT/正常化利润
尚未验证”或“低 PE 不等于低估”的显式警告，`candidate_class=LEAD`、`data_status=PARTIAL`。

### 4. 低 PE 风险样本仍在安全边界内

抽到的中成股份 PE 8.16、PB 3.97，公式推导隐含 ROE 约 48.7%；动力新科 PE 2.44。这些数字来自
单一报价快照，不能成为低估证据，但当前仅作为研究线索展示，没有形成估值、BUY 或仓位。
需要记录的非阻断问题：Value 原因文案写“多指标便宜度候选”，实际输入只有 PE、PB 及其推导 ROE，
缺少 FCF Yield/EV-EBIT；下一版 rule text 应改为更准确的表述。

### 5. 数据缺口与不支持被正确区分

Quality 的 4,672 条缺口被保留为 `DATA_GAP`；Value/Cyclical 的缺失 PE/PB/市值同样保留。
121 个金融画像对象在通用通道中显示 `UNSUPPORTED`，抽到的兴业银行、浦发银行、中国平安、
华泰证券等没有进入通用 FCFF/Value 流程。这符合“未知/金融不默认通用模型”的约束。

### 6. Legacy 差异不参与排序

Legacy 影子规则产生 747 个对象，新通道有 113 个不重复候选，重叠 86 个。抽样覆盖 overlap、
new-only、legacy-only；例如马应龙、奥美医疗、尚太科技等只在 legacy 列表，未因此被提升为
新候选。Legacy 只作为差异审计基线，不参与 M2 排序。

## 未完成项

- 本报告是 AC9 的机器与抽样阅读证据，尚未写入原 Excel 的统一展示区。
- BUDGET_EXCLUDED 的触发指标需要原始输入重放才能完整复核，当前收据只保留身份、原因和分母。
- Quality 财务证据覆盖率低，是后续全市场 Quality 通道可用性的主要数据缺口。
- AC9 不能替代 AC1-AC12；M2 仍需完成至少三份新发现研究/否决、原 Excel 发布及最终联合验收。
