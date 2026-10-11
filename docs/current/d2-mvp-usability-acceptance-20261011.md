# D2 交易辅助 MVP 实际可用性验收

日期：2026-10-11。代码基线：`5b301437e7c9753f6eca5c70f9be0bb339791e47`。
Windows 原件字节保护修复：`4f49d66c6f242eae5c6ae8b5cdb4a98a0b78b796`。
本报告是 P1-P8 本轮交付与差距记录，不是总 Goal 完成声明。

## 当前能做什么

通过现有 `scripts/current/run_daily_trade_assistant.py`，可以手动执行单公司或
注册公司批量研究，核验原件、重放既有研究、校验最近完成交易日收盘价，
输出证券级结论、具体阻塞、待复核 Agent 发现、中文报告、月度研究比较及
来源绑定 Excel 预览。无真实持仓也能运行；不生成订单。

在项目目录使用现有入口执行一次（默认Offline、手动采集，生成新runtime记录）：

```powershell
D:\APP\Python313\python.exe scripts/current/run_daily_trade_assistant.py --symbol 600519 --review-packet --monthly-review --collect-events
```

批量使用 `--all-registered`；增加 `--previous-run` 指定已有不可变运行目录可以
比较前后变化。`--report-only` 不要求Excel渲染运行时；没有它则生成隔离作者页，
不自动发布到WPS。Mock/原文请求须明确选择并提供路径与Hash，默认不开付费API。

Excel 的阅读顺序为：今日 -> 机会 -> 决策过程 -> 公司 -> 事件。
我的组合保持未接入；系统与审计用于追溯，不作为日常入口。
公司页现在先展示结论、经营论点、价格限制与下一触发，而不是完整内部对象。
条件压力情景仍明确标为“非中性合理价值”。

**当前不能据此直接买入、加仓或按金额减仓。** 实际四公司输出均为
`NO_ACTION`，当前正式价格准入为 false，私人 `position_guidance=null`。
这不等于“四家公司都不值得投资”，而是当前研究与审批依赖未满足。

## 真实运行与来源

最终统一批量入口输出目录：
`runtime/daily-trade-assistant/20261011-d2-four-company-final-v2`。
失败公司、必需资产阻塞、产品错误均为 0，四家公司保留独立收据。

| 公司 | 研究截止 | 来源性质 | 10/9 双源收盘 | 本次建议 |
| --- | --- | --- | ---: | --- |
| 600519 贵州茅台 | 2026-10-08 | 当前 source-bound 实际财报研究，主估值仍未批准 | 1263.00 | NO_ACTION |
| 600887 伊利股份 | 2026-09-22 | 原件合法恢复后的历史合同回放 | 27.66 | NO_ACTION |
| 000651 格力电器 | 2026-09-22 | 历史合同回放 | 38.83 | NO_ACTION |
| 600741 华域汽车 | 2026-09-22 | 历史合同回放 | 15.55 | NO_ACTION |

行情原始证据为腾讯/Sina响应与交易所日历；bundle 路径
`runtime/quote-sessions/20261011T003633681771Z/bundle.json`，SHA-256
`16c2e4522f34865897fd026961e7b9181ef20cdb10ecb03e3811c40bd07b827e`。
行情日期、抓取日期与研究截止分别保存。历史收盘展示不是今天实时行情。

600519 官方原件沿用巨潮法定 FY/H1 PDF；既有财务事实、财务范围与14项
估值假设在 `20261011-d2-final-preview-v1/research-review.json` 中由完整
package、descriptor、ResearchCase/Facts/Assumptions 对象及原件 Hash 绑定。
页码缺失会明确记录，文件存在不自动批准其经济解释。

新官方查询实际覆盖10/8至10/9，0条新增公告；解析索引与M5 scan已归档。
它不代替更早窗口审查，不推进研究日，不签署材料性、ModelValidity或G3。
下载适配器拒绝重定向、HTML挑战页、截断/不可解析PDF；日期级元数据不证明盘中可用。

伊利引用的冻结索引没有改写。恢复清单只绑定另一目录保留的完全相同原始
Hash字节；语义相同但字节不同的索引不能冒充原件。缺失原件会列为阻塞，
不靠重算Hash“修好”。

## 价格闭环、Agent 与组合

`runtime/d2-mvp-acceptance-20261011/historical-price-bridge-reverified.json`
由既有历史模块重新运行产生。9/22和9/23决策截止不能看见10/1生成的估值；
10/1截止原始证据与合法价格可进入 READY PriceBridge，但保留pre-model研究
审查阻塞。此证明不授予当前研究、strict PIT、策略或实盘准入。

600519 Mock 三角色实际消费了FY物理页6和H1物理页5的精确片段。
输入是未可信原文数据，不是系统指令。新版本将片段、上下文摘要及每条
Finding的覆盖侧车绑定；删除、替换或降级被拒绝。中文报告列出原件定位和
未覆盖引用，全部标明观点语义未验证、待复核。**Mock不是实际新LLM研究**；
未调用付费模型，也没有通过Agent写回正式参数或审批。

六种 DecisionRecommendation v3 状态、Entry/Consistency连贯性与冲突阻塞
复用既有合同并通过合成测试。组合测试覆盖单股、行业、现金、共享风险预算、
加仓容量和缺失私人输入；不是使用用户实际账户的个性化验收。
已有加密私人输入入口保持未启用。股息/持仓复核使用既有合同，没有新交易规则。

月度比较读取冻结的新旧对象，不重新解释“没有新公告”为“财报已更新”。
历史legacy合同继续显示未取得当前真实输入准入；无对应字段则保持 unavailable。

## Excel 候选及正式发布边界

最终候选：
`runtime/daily-trade-assistant/20261011-d2-final-integrated-v2/canonical-integration-historical-preview.xlsx`

SHA-256：`8f3608702af711e909cd66ee6f3226e6d875d8efe390361361d494d784c6b481`。

正式原件与本地备份 Hash：
`5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`。
备份：同候选目录的 `canonical-before-publication.xlsx`。
正式原件为配置指定的 WPS 文件，未被覆盖。

候选由 artifact-tool 作者页与既有保护适配器整合；保留55个非托管工作表
XML及原工作簿结构。WPS只读打开、公式、中文阅读、链接及来源核验收据
均留在该目录。17次实际内部链接跳转、19条来源链接显示通过，203项来源
绑定冷核验通过；公司页PDF从上一轮约20页减少至7页；今日和机会各1页。
第一次本轮视觉审查发现空结论、私人Entry占位及重复行情，修正版已修正。

本候选是现有研究展示快照的保护更新，重点更新600519；保留的美的/神华/伊利
历史卡并非本轮新增当前研究。格力和华域的本轮结果以各自中文报告交付，
不能宣称所有批量公司均已集成到当前Excel或获得新研究准入。

发布仅替换七个托管产品页，保留其余手工/历史页，不是删除旧研究数据。
按照本轮用户任务P6，“正式发布仍须取得用户批准”。候选工程验收不代表
用户已经签收，不代替经济研究批准。

## 工程验证

最终本地相关回归：1789 passed / 32 skipped / 38 warnings，
`.tmp/d2-p1-p8-core-final-v2-20261011.xml`。含六状态、价格回放、Agent及组合。
第一次扩大CI清单误重复了一个测试模块，导致隔离fixture目录冲突；已删除
重复清单项并完整重跑，没有改测试断言或跳过失败。
定向证据修复测试145项通过。数据缺失导致的跳过不计作真实研究验收。

GitHub Core Research Gates运行 `38099846242`，代码 `5b30143`，及修复版
`38100211582`（`4f49d66`），offline-core与postgres-integration均success。
实际干净检出发现Windows自动换行改变恢复清单Hash；新增 -text 规则保护
原字节，不改变冻结原件或预期Hash。没有访问或更改个人服务器/PTA。
最终远端干净检出4f49d66通过1768项，跳过53项，38 warnings；18个已登记
Python入口help全通过。批量资产检查按预期退出2并列出缺失本地资产，未发生
traceback；清单Hash仍为原始442f4427...，不绕过缺失来源。
完整证据在 `.tmp/d2-clean-final-4f49d66/.tmp/clean-receipt.json`。
最终Excel冷核验与视觉记录为候选目录的 `final-acceptance.json`。

## 尚缺的不可混淆条件

1. **P1真实研究仍partial**：前五年盈利提案尚未消费为完整中性主模型。
   需要选定并绑定存量盈利侵蚀与新增资本回报的尾部/终端制度，独立审阅
   精确版本后再按正式合同审核。现有v8中值的全资本fade使利润显著下降，
   不能将低回报留存资金作为这种存量侵蚀的唯一解释。官方历史财报不能
   唯一决定未来优势期限，缺口不应叫“等待下一交易日”。
2. **P2当前价格准入仍false**：须把完整事件窗口与精确模型/假设绑定，
   完成材料性、模型有效性、研究日期及G3审查。无新增公告查询不等于批准。
3. **P4当前多公司研究仍partial**：格力/华域/伊利的统一技术回放已验证，
   新近正式研究输入与经济审批没有因此完成。
4. **P5语义研究尚未验收**：真实片段与引用覆盖已验证，观点真实性仍待复核；
   未授权付费Provider，不声称Mock代表模型具有独立金融研究能力。
5. **个性化与运营未验收**：真实IPS/Portfolio、生产授权、真实会话、恢复及
   最终用户使用验收保持原有门禁。本轮不启动生产或自动运行。
6. **正式Excel发布及用户签收未完成**：候选与备份已准备，须用户具体批准。

本轮状态：CODE_IMPLEMENTED；AUTOMATED_TEST_PASSED；实际来源/行情在上述
范围REAL_DATA_VERIFIED。RESEARCH_ADMITTED=false；MODEL_VALIDITY_VALID未达；
当前PRICE_ADMITTED=false；HUMAN_APPROVED未达；USER_ACCEPTED=false。
D2与总Goal仍IN_PROGRESS。`action=no_order`，最终投资决定始终由人作出。
