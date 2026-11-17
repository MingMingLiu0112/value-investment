# 每日使用说明（TL10-RC，2026-10-13）

唯一日常入口：`scripts/current/run_daily_workbench.ps1`。

## 1. 每个交易日（收盘后）

```powershell
pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode SAFE_REFRESH -Open
```

它做四件事：用既有双源采集器抓公开行情 → 只登记通过 B1 校验的收盘 →
重建并发布公开决策快照 → 打开本地工作台。
它不联网改研究、不改正式 Excel、不写私人台账、不产生任何订单
（`action=no_order`）。

## 2. 只看今天的结论（不联网）

```powershell
pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode READ_ONLY -Open
```

## 3. 读输出

| 输出行 | 含义 |
| --- | --- |
| `运行结果 : SUCCESS/PARTIAL/BLOCKED` | 本次数据更新结果 |
| `数据版本 : pub-…` | 本次公开快照版本身份（同一身份对应同一组事实） |
| `内容摘要 : …` | 决策内容摘要（不含生成时间与 Excel 对照） |
| `公开快照 : VERIFIED - pub-…` | Web 正在读取的、已校验的快照 |
| `Excel对照 : MATCHED/DIFFERENT/NOT_VERIFIED` | 磁盘正式工作簿与发布指针的只读比对 |
| `Web 服务 / 整体结果` | Web 结果与最终退出码，分开报告，互不掩盖 |

退出码：`0` 成功；`2` 更新受阻（发布链不可用、身份冲突、刷新失败）；
`3` 部分成功（有提醒）；`4` 更新成功但 Web 启动失败。

## 4. Web 页面要点

- 今日页：快照版本与校验状态、数据截止、行情/研究新鲜度、准入计数、
  Excel 对照（Web 永不覆盖正式工作簿）、SAFE_REFRESH 的能力边界。
- 公司页：条件性估值、模型有效性与价格桥接状态、下一步触发条件。
- 组合页：私人台账状态（锁定 / 未接入 / 已接入 / 输入不完整 / 台账校验失败），
  与今日页共用同一状态来源，不出现互相矛盾的结论。
- 事件与历史：仍为次级视图，不抢主产品视图。

## 5. 出问题时的读法

- `公开快照 : 未更新`：本次没有发布新快照，Web 仍读取上一份已验证快照；
  按输出的阻止事项处理。
- `snapshot_status=NO_VERIFIED_SNAPSHOT`（页面出现"公开快照不可用"）：
  说明本机还没有任何已验证快照，请先跑一次入口脚本发布。
- `Excel对照 : DIFFERENT`：正式工作簿与发布指针不一致；不会自动同步，
  需要人工确认哪一侧是最新。
- `运行结果 : BLOCKED（同一版本出现不同内容…）`：拒绝覆盖并留下冲突回执，
  这是保护机制，不是数据损坏。

## 6. 人工仍必须做的事

重跑某家公司的研究、事件材料性复核、G3 估值门批准、正式 Excel 发布、
私人组合录入与成交确认 —— 这些都不会被入口脚本或 Web 代办。
