# 日常研究入口

在项目目录 `D:\GPTProject\value-investment` 使用同一个入口。正式 Excel 仍位于 WPS 云盘，不需要另找候选工作簿。

```powershell
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --symbol 600519
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --symbol 600887 --details
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --open
```

默认显示已发布的当前待审研究、历史报价身份和下一步；`--details` 再展开保留的历史基线和证据。入口逐一核验发布来源及 Excel Hash，来源变化会拒绝读取，不会自动猜测最新文件或重算旧研究。000651、600741 等历史卡不因能阅读而获得当前研究资格。

## 查看和填写研究审核

```powershell
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --mode review --symbol 600519 -- --preview
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --mode review --symbol 600887
```

只读预览不写文件。交互模式逐组显示问题、支持、反证及影响，可选择 VERIFIED、REJECTED、INSUFFICIENT 或 skip。输入 cancel 或中断均不保存；最后明确输入 save 才保存未签名草稿到项目 runtime。草稿不是正式批准，Excel 单元格也不能替代审批。

本人已签名的回应可通过同一入口附加 `--signed-review-response PATH --review-trust-root PATH`。实际文件 Hash 可自动计算，但固定信任根、身份、权限、签名、前驱和候选版本校验依然强制执行。当前正式审核身份清单为空，尚不能把草稿消费成正式批准。整模型 G3、各公告材料性和经济用途审核分别保留，不相互替代。身份指导见 `d2-human-review-usage-20261011.md`，操作细节见 `local-review-wizard-usage.md`。

签名消费参数须放在分隔符 `--` 后，例如：

```powershell
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --mode review --symbol 600519 -- --signed-review-response PATH --review-trust-root PATH
```

## 更新研究

```powershell
& 'D:\APP\Python313\python.exe' -X utf8 scripts/current/use_trade_assistant.py --mode update -- --report-only --agent-mode none
```

转发到现有日报应用，使用明确登记并与发布候选一致的两家公司包；高级选项不能覆盖公司、候选或包登记。`--report-only` 是执行研究但不依赖表格渲染，并非只读查看。运行目录保留真实状态与失败原因；新目录重试，不覆盖旧历史。不会启动服务器、生产服务、定时任务或 Shadow。

## 当前数字怎样理解

600519 当前 v5 待审条件区间为 437.66 / 587.88 / 812.27 元；600887 为 9.80 / 10.08 / 10.30 元。研究日均为 2026-10-11，财报基准为 2026-06-30。这些是指定条件模型的研究输出，不是批准合理价或买入价格。保留的旧基线另有版本，不可混用；运行日期折算差异也不是新增经营事实。

10 月 9 日双源收盘仅作历史观察，不与 10 月 11 日新模型强拼买点。价格比较需要合法经济批准、整模型 G3、对应公告材料性、ModelValidity、PIT 和报价时点全部符合原有合同。缺真实 IPS/持仓时，公共公司研究可用，仓位指导仍为空。永久 `action=no_order`，最终投资决定由本人作出。
