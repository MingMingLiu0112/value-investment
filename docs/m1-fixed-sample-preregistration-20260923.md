# M1 固定样本预登记

登记日期：2026-09-23。机器可读版本见 `config/m1-fixed-sample-preregistration-v1.json`；本文件是它的可读说明，不是第二套选择标准。

## 设计目的

这 20 家不是买入清单、不是按当前估值便宜挑选，也不是“先找到容易出数值的公司”。它们是用来检验研究流水线的分层样本：成功案例、模型复制案例、模型不支持案例、资料不足案例和经济风险反例都要保留，负面结果同样计入登记。

当前工程只注册了三种经济画像：

- `quality_compounder`：消费品、品牌与渠道，使用剩余收益或权益价值模型；
- `mature_manufacturing`：成熟制造、家电与智能制造，使用 FCFF；
- `cyclical_cash_return`：周期资源、煤炭与综合能源，使用周期正常化模型。

不属于这三类画像的公司明确标为 `unsupported_profile`，不能套用默认 FCFF 凑一个估值。

## 20 家登记

| 代码 | 公司 | 行业 | 画像 | 登记原因 | 初始深度 | 主要已知缺口 |
| --- | --- | --- | --- | --- | --- | --- |
| 600519 | 贵州茅台 | 食品饮料-白酒 | quality_compounder | 保留的冻结首例 | FROZEN | G3、人工批准、当前股本动作 |
| 000333 | 美的集团 | 家用电器 | mature_manufacturing | 保留的冻结首例 | FROZEN | FCFF 输入、普通股分母 |
| 601088 | 中国神华 | 煤炭 | cyclical_cash_return | 保留的冻结首例 | FROZEN | 正常化利润、成本运输口径 |
| 600887 | 伊利股份 | 食品饮料-乳制品 | quality_compounder | 同画像第二家 | DEEP | 可分配现金、优势期 |
| 000651 | 格力电器 | 家用电器 | mature_manufacturing | 同画像第二家 | DEEP | FCFF 输入、渠道与库存 |
| 600188 | 兖矿能源 | 煤炭 | cyclical_cash_return | 同画像第二家 | DEEP | 正常化利润、资源寿命 |
| 000858 | 五粮液 | 食品饮料-白酒 | quality_compounder | 同行业反例对比 | TRIAGE | 完整财报与资本配置包 |
| 600690 | 海尔智家 | 家用电器 | mature_manufacturing | 全球化/治理对比 | TRIAGE | 合并范围、营运资本 |
| 600741 | 华域汽车 | 汽车零部件 | mature_manufacturing | 供应链与周期边界 | TRIAGE | 客户集中度、FCFF |
| 600028 | 中国石化 | 石油石化 | cyclical_cash_return | 炼化周期对比 | TRIAGE | 炼化利润、维护资本 |
| 601857 | 中国石油 | 石油石化 | cyclical_cash_return | 资源周期对比 | TRIAGE | 资源寿命、A/H 股本 |
| 600585 | 海螺水泥 | 建筑材料 | cyclical_cash_return | 国内需求周期 | TRIAGE | 正常化量价 |
| 600036 | 招商银行 | 银行 | unsupported | 银行模型不支持 | TRIAGE | 无银行估值模型 |
| 601318 | 中国平安 | 非银金融-保险 | unsupported | 保险模型不支持 | TRIAGE | 无保险估值模型 |
| 000001 | 平安银行 | 银行 | unsupported | 第二个银行边界 | TRIAGE | 无银行估值模型 |
| 601390 | 中国中铁 | 建筑装饰-基础设施 | unsupported | 高杠杆与项目现金流反例 | TRIAGE | 杠杆、营运资本 |
| 002928 | 华夏航空 | 交通运输-航空 | unsupported | 资料不足与高固定成本反例 | TRIAGE | 燃料、产能、模型不适用 |
| 300750 | 宁德时代 | 电力设备-电池 | unsupported | 成长科技模型不适用 | TRIAGE | 无成长科技模型 |
| 300888 | 稳健医疗 | 医药生物-医疗用品 | quality_compounder | 资料不足案例，保留为非 READY | TRIAGE | 权益、回报、复利证据 |
| 600941 | 中国移动 | 通信运营 | unsupported | 受监管回报模型不适用 | TRIAGE | 监管回报与资本开支 |

## 来源与边界

- 正式财务事实仍以 CNINFO、公司 IR 和交易所原件为主；AkShare/行情仅用于发现、差异报警和明确缺口。
- 登记理由来自公司业务属性、经济画像和已有本地覆盖状态，不使用当前价格、PE、股息率或后验收益选择。
- “FROZEN” 三家保留 C0-C3 已有工程和缺口；“DEEP” 只是 W3 的研究候选；“TRIAGE” 不表示已完成深研，更不表示支持模型。
- 全部登记保持 `action=no_order`，不生成建仓、减仓、仓位、目标权重或实盘准入。

## 下一步

W1 只完成了样本、来源、预算、停止规则和验收口径预登记。接下来进入 W3 的真实研究闭环：从 6 个 `DEEP` 或已有证据的候选开始，形成可阅读的 BusinessQuality、FinancialQuality、CapitalAllocation、Thesis、最强反证、可观察 breaker 和下一事件档案；未支持的案例继续保持缺口，不用占位结果冒充 READY。
