# Excel 工作簿版本记录

更新：2026-09-24。本文件只记录公开仓库中工作簿快照与 WPS 云盘字节核对结果，
不改变投资逻辑，不生成交易指令。当前项目状态为 `M2 / PARTIAL`，`action=no_order`。

## 基线

- 本地 Git：`main @ 1c57462391d5a506f708dac7a006e45e57f7cc4f`
- 对应提交：`Add preregistered M2 coverage audit`
- GitHub 远端：`https://github.com/MingMingLiu0112/value-investment.git`
- 公开工作簿快照共 6 个，与 WPS 云盘 `价投跟踪` 目录中的同名文件字节一致。

## 工作簿清单

| 文件 | 字节数 | SHA-256 | 最近提交 |
| --- | ---: | --- | --- |
| A股价值投资_Agent前端智能跟踪模板.xlsx | 12,210,200 | a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |
| A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx | 13,168,877 | 95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a | 0566ed4197135008648bf3f3046ac49d481aed63 |
| A股价值投资_M2机会发现_20260923.xlsx | 53,299 | a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821 | f4bb55cd686838b874b6a8b0c601492c8bd7aab5 |
| A股价值投资_M2机会发现_v2_20260923.xlsx | 1,020,221 | 4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |
| M1_三公司研究Application候选_20260923_033001.xlsx | 17,357 | 0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbbd51c3d34 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |
| M1_三公司研究Application候选_20260923_122010.xlsx | 17,025 | 2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8 | 71c0ad566e21867ec844eb8d5746b814207ddc37 |

## 最近提交的工程文件

`1c57462` 已公开提交 M2 AC9 分层覆盖审计：

- `.github/workflows/core-research-gates.yml`
- `config/m2-coverage-sampling-v1.json`
- `src/value_investment_agent/m2_coverage_sampling.py`
- `scripts/audit_m2_coverage_sampling.py`
- `tests/test_m2_coverage_sampling.py`
- `docs/m2-ac9-stratified-coverage-audit-20260923.md`
- `CHANGELOG.md`
- `docs/execution-status.md`

## 不上传的本地文件

以下 WPS 云盘文件属于本地故障回退、WPS 校验或人工资料，按公开仓库边界不提交：

- `.A股价值投资_Agent前端智能跟踪模板.p2.stage.xlsx`
- `A股价值投资_Agent前端智能跟踪模板.checks.json`
- `价投跟踪系统_框架逻辑与使用手册.docx`

## 状态

`M2` 仍为 `PARTIAL`。本记录确认工作簿快照已上传、哈希可复核；不将 Excel 上传等同于
估值、买入、仓位或实盘准入通过。
