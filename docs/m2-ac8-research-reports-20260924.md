# M2 AC8 实质研究与通道否决报告

更新：2026-09-24。本文记录 AC8 的固定输入、真实产物和验收边界。M2 仍为
`PARTIAL`，AC8 单项目前为 `AC8_REVIEW_PENDING`；`action=no_order`。

## 目标

AC8 要求至少 3 家由系统主动发现的候选形成实质研究或否决报告，并覆盖至少两个通道。
本工具不得为了凑数筛选样本、不得把低 PE/PB 直接写成低估，也不得输出 BUY/ADD/仓位。

## 预注册输入

- AC9 审计报告：`runtime/m2-ac9-coverage-audit-20260923-v2/report.json`
  - SHA-256 `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`
- M2 收据：`runtime/m2-live-20260923-v3/receipt.json`
  - SHA-256 `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`
- 保留财务点：`runtime/m2-live-20260923-v3/retained-financial-points.json`
  - SHA-256 `d0c6184cd5a878997c7065488168519ac55c11fdda7ef45549872c6faeeb12ca`
- 分红快照：`runtime/m2-live-20260923-v3/eastmoney-dividends.json`
  - SHA-256 `41888fcd8339eef12fb963c963b2cbe4e7f0ed90196e9547266c30a0b0a7f19f`

采样层固定为 AC9 的 `selected_leads`，只接受 `LEAD + DATA_PARTIAL`。任何输入 Hash、
日期、报告期或 `no_order` 合同不符都会拒绝运行。

## 真实产物

- 报告：`runtime/m2-ac8-research-reports-20260924-v1/report.json`
- 报告 SHA-256 `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`
- 机器状态：`MACHINE_CHECKS_PASS`
- 验收状态：`AC8_REVIEW_PENDING`

| 指标 | 数量 |
| --- | ---: |
| 总报告 | 18 |
| 实质报告 | 16 |
| 待深研 | 3 |
| 通道否决 | 13 |
| 证据不足 | 2 |

实质通道：`dividend_cash_return`、`value`、`cyclical`。

## 代表结论

- `600011` 华能国际：股息通道 `PENDING_DEEP_RESEARCH`。经营现金流为正，但归母净利润
  同比下降且资产负债率较高，需继续验证派息覆盖与长期现金质量。
- `600582` 天地科技：股息通道 `REJECTED_FOR_CHANNEL`。归母净利润为正，但经营现金流
  与自由现金流为负，不能通过现金可持续性初筛。
- `603799` 华友钴业：周期通道 `REJECTED_FOR_CHANNEL`。经营现金流为正，但资本开支使
  自由现金流为负，且缺少正常化盈利和周期位置证据。
- `000151` 中成股份：固定输入中没有可用的最新报告期核心财务点，报告为
  `INSUFFICIENT_EVIDENCE`，不冒充研究结论或通道否决。

每份报告保留字段名、报告期、值、单位、来源名称、来源 URL、原件 SHA-256、发布时间、
抓取时间、正向证据、反证和缺失证据。

## 安全边界

- 未连接生产 PostgreSQL、未访问服务器项目、未修改计划任务。
- 未覆盖或替换 WPS 生产工作簿，本轮也未新增 Excel 快照。
- 输出不含交易、目标仓位、下单、回测收益或实盘准入键。

## 验证

- M2 AC8/AC9 定向回归：28 passed。
- 仓库全量离线回归：2143 passed、6 skipped、18 warnings、0 failed。
- 未来报告期财务点拒绝测试：通过。
- 输入 Hash 篡改拒绝测试：通过。

## 状态

AC8 的真实证据已经形成，但验收仍为 `AC8_REVIEW_PENDING`；M2 尚未完成。下一项仍应
按 `current-stage-goal.md` 推进原 Excel 统一发布和 W6/W7 联合验收，不因本报告数量
宣告 M2 完成。
