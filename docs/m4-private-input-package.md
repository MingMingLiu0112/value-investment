# M4 私人组合输入包

状态：`READY_FOR_PRIVATE_INPUT`。这只是本地、只读、`action=no_order` 的输入流程；未提供真实资料前，M4 个性化验收仍为 `WAITING_R2`。

## 你需要填写什么

模板为 `config/m4-private-portfolio-input-template.json`，示例为
`config/m4-private-portfolio-synthetic-example.json`。示例固定标记
`SYNTHETIC_EXAMPLE_ONLY`，不能用于个人化结论。

IPS 需要账户范围、投资期限、可投资资产、最低及应急现金、流动性需求、单股/行业/周期上限、是否允许集中、风险承受说明、股息目标与限制项。持仓快照需要日期、现金，以及每只持仓的代码、交易所、数量、成本、市值、数量确认和公司行为调整状态。

`null`、`UNKNOWN`、`DRAFT`、未确认数量和未对账快照都允许保存及加密，但会明确阻断个性化仓位指引。

## 最短流程

在仓库外且不属于 WPS/其他同步盘的位置建立私有目录；密钥必须再放到另一个独立目录。以下命令只输出状态、Hash 和缺失字段名，不输出资产金额或持仓内容。

```powershell
python scripts/setup_private_portfolio.py init --private-root <private-root> --output <private-root>\portfolio-input.json
python scripts/setup_private_portfolio.py validate --private-root <private-root> --input <private-root>\portfolio-input.json
python scripts/setup_private_portfolio.py keygen --private-root <private-root> --key-file <separate-key-root>\portfolio.key --forbidden-sync-root C:\Users\we\WPSDrive
python scripts/setup_private_portfolio.py encrypt --private-root <private-root> --input <private-root>\portfolio-input.json --encrypted <private-root>\portfolio.viportfolio --key-file <separate-key-root>\portfolio.key --forbidden-sync-root C:\Users\we\WPSDrive
python scripts/setup_private_portfolio.py verify --private-root <private-root> --encrypted <private-root>\portfolio.viportfolio --key-file <separate-key-root>\portfolio.key --forbidden-sync-root C:\Users\we\WPSDrive
```

首次对账时，可把“本人填写快照”和“独立核对快照”分别加密，再执行：

```powershell
python scripts/setup_private_portfolio.py reconcile --private-root <private-root> --reported <private-root>\reported.viportfolio --confirmed <private-root>\confirmed.viportfolio --private-report <private-root>\reconciliation.json --report-id <private-report-id> --key-file <separate-key-root>\portfolio.key --forbidden-sync-root C:\Users\we\WPSDrive
```

一致只会得到 `MATCH_PENDING_HUMAN_CONFIRMATION`，仍需本人确认后才能把最终快照标记为 `RECONCILED`。差异报告包含私人数据，只能留在私有目录；公开回执不含金额、数量或证券明细。

## 永久边界

- 不连接券商，不读取账户，不生成订单。
- 私人 JSON、密文和对账报告不进入 Git、WPS、公开 runtime 或 CI artifact。
- 密钥不与密文同目录，不允许覆盖既有密钥或密文。
- 任何未知、过期、账户不一致、数量未确认或对账缺失均失败关闭。
