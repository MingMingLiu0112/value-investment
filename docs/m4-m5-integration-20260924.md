# M4/M5 联合检查点候选

更新：2026-09-24。本候选把已计算的 M4 组合基线与 M5 有界依赖失效结果汇合为
一个只读产品状态，不重新计算仓位、不连接生产数据、不创建订单。

## 为什么做这个联合候选

M4 已经分别交付组合风险、仓位与股息收入候选；M5 已经交付事件账、水位、依赖图和
有界重算。单看两边只能证明“模块存在”，不能证明一个事件发生时会精确暂停哪个
组合产品。联合候选把这两层接到同一 Application 输出上，是 Checkpoint C 前的
离线契约验证。

## 联合语义

- 输入：显式模拟 `PortfolioInputBundle`、`PositionGuidanceResult`、
  `PortfolioDividendIncomeProjection` 和 M5 事件批。
- 输出状态：
  - `READY`：无事件失效，基线可直接阅读。
  - `PARTIAL`：基线本身有缺口或冲突，但本轮没有新事件命中。
  - `PAUSED`：一个或多个依赖节点被事件失效，等待有界重算。
  - `NEGATIVE`：相关事件是关键论点破坏或严重事件，需要人工处理。
- `POSITION_RISK_CHANGED` 只失效组合风险与共同仓位边界。
- `DIVIDEND_CHANGE` 失效分配历史、股息可持续性与共同仓位边界。
- 无关公司的 `NEW_FINANCIAL_REPORT` 只失效该公司的财务链，不误伤组合仓位。
- 所有状态仍为 `SIMULATED`、`action=no_order`。

## 交付文件

- 联合读模型：`src/value_investment_agent/m4_m5_integration.py`
- 展示层：`src/value_investment_agent/m4_m5_integration_workbook.py`
- 构建脚本：`scripts/build_m4_m5_integrated_candidate.py`
- WPS 只读验证：
  `scripts/verify_m4_m5_integrated_candidate_wps.ps1`
- 控制夹具：`tests/fixtures/m4_m5_integrated_demo.json`
- 回归测试：`tests/test_m4_m5_integration.py`

## 2026-09-24 M4 Decision Binding v2

M4 guidance fixture 的正向 BUY/ADD 候选已改为强绑定 M3 Decision Artifact 后，
重新生成联合检查点，保证 M4/M5 展示层与收紧后的领域合同一致：

- 文件：`A股价值投资_M4M5联合检查点候选_v2_20260924.xlsx`
- SHA-256：
  `470c73209ee87b3855387eb47a890eb0187b3fc83d5cd15cf145d6e2eef9c10a`
- WPS 只读收据：
  `runtime/m4m5-joint-wps-v2-20260924/wps-verification.json`，`passed`。
- WPS 云盘同名副本与仓库候选逐字节一致。
- 联合状态仍为 `NEGATIVE`、`SIMULATED`、`action=no_order`；未增加正向结论。

## 场景

控制夹具包含四个显式模拟事件：

1. 600519 仓位风险变化。
2. 000333 分红变化。
3. 601088 新财报，作为无关财务事件。
4. 600519 论点破坏，作为负向事件。

预期结果是 10 个产品进入 `PAUSED/NEGATIVE`，600519 财务事实保持 `READY`；
仓位边界由事件 1 和 2 共同暂停，但事件 3 和 4 不会出现在其触发事件列表中。

## 验证

- 定向回归：`tests/test_m4_m5_integration.py` 4 passed。
- M4/M5 联合回归：72 passed。
- WPS 只读收据：
  `runtime/m4m5-joint-wps-20260924/wps-verification.json`，`passed`。
- 候选工作簿字节数：13,162。
- 候选 SHA-256：`353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612`。
- GitHub 发布：release commit `d6a3abd`，已推送 `origin/main`。
- GitHub Core Research Gates：
  [run 35939972803](https://github.com/MingMingLiu0112/value-investment/actions/runs/35939972803)，
  `success`。

## 边界

本候选不包含真实 IPS、真实持仓、真实账户或真实披露结论；不提供 BUY/ADD/仓位；
不修改 canonical、WPS 生产原表、服务器服务、计划任务或 PTA。联合状态只是让用户在
Checkpoint C 前看到“发生了什么，哪些产品需要重算”，所有后续动作仍由人工确认。
