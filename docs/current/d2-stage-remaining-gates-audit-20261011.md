# D2 剩余门禁独立审计（2026-10-11）

结论：D2 的两个实际待审候选、分组审核材料、完整已结束公告查询窗口、日常报告及组件恢复演练已有证据；经济/G3、公告材料性、当前 ModelValidity 和 PriceBridge 均未准入。工程可以继续，D2 正式研究决策收口及 INITIAL_ASSISTED_USE 不能标记完成。本文仅审计既有 S1–S8，不新增 Roadmap、模型方案或审批。

## 基线与审计方法

本地 HEAD 与本地缓存 origin/main 均为 `2788d789364c3a61e8426a6c58873c5727dd3489`。未联网刷新远程或核验本 SHA 的 GitHub CI，不将缓存 ref 等同远端实时状态。`src/scripts/tests/config` 的已跟踪差异仅为 renderer 两处日期 header `rowHeight:34 -> 42`；renderer 当前 SHA-256 为 `05fe0cf8a5d908349781ae2c782e1a4d7a3d4970c4ccb7a06c2b408bf926b961`。另有既存治理文档修改及未跟踪研究文档，工作树并非整体干净；本审计不修改它们。

使用显式 PowerShell 7、UTF-8，只读检查本地原件、manifest、receipt、工作簿及共享代码。调用既有 `verify_pending_research_candidate` 核验两份 v5：均通过 source/implementation bindings、descriptor/model_context、实际 workbench 与消费对象一致性检查。未重跑公司研究、下载公告、生成审批或发布。逐项重算两份 daily receipt 的输出 hash（S1 12 项、S5 11 项），全部相符。

## S1–S8 实际状态

| 工作包 | 已证实完成的范围 | 必要但未准入的范围 | 工程是否可继续 |
| --- | --- | --- | --- |
| S1 茅台主估值候选 | v5 实际消费 B_CONTINUITY_ALTERNATIVE；15 年路径、57 项假设绑定；实际研究/估值生成日 10/11，财务基期仍为 6/30；条件中值 587.8829687529 元/股 | 正常化盈利、存量优势与新增资本的独立识别、十年期限、资本成本与现金分配经济判断；精确版本 G3/人工模型批准 | 可以复用现有候选、反证和消费证明核验及准备审核；不能把算术一致性升级为公平价值或买点 |
| S2 人工审核操作材料 | 两份 candidate-review.md 已生成且被 daily receipt 精确绑定；分组问题包含支持、反证、影响及底层 field_paths | 未见这些新候选的 VERIFIED/REJECTED/INSUFFICIENT 正式经济裁决及相应精确版本审批链 | 可继续可读性、引用/版本一致性检查；最终裁决不能由工程执行代填 |
| S3 事件与 ModelValidity | 7/1–10/10 已结束查询窗口完整分页；茅台 7 条、伊利 33 条；received raw 与 metadata、observation sources/scan hashes 均相符；保留并复用原件 | 新候选的完整事件关联和逐项材料性裁决；有效性重算/正式 VALID；10/11 全天覆盖及严格盘中可得性均无证明 | 可以用既有原件完成具体事件影响矩阵和版本关联，不必重下载；必须保留待审/有效性阻塞 |
| S4 价格与证券级决策 | 双源 10/9 最近已完成收盘观察：600519=1263.00，600887=27.66；日常报告明确仅显示；保留历史隔离价格合同与拒绝证据 | 当前研究/模型/事件未通过，当前 PriceBridge/MOS/正式价格吸引力未准入；不能把历史或隔离成功路径迁移为当前批准 | 可继续现有合法历史/合成合同回归和真实当前拒绝解释；不新增折价规则、不强造 BUY |
| S5 伊利独立研究 | v5 short-advantage 共享模型实际消费 FY/H1 两个官方 ID；归母权益 53711364981.99、股数 6325360667、扣非 TTM 9647734710.01；24 项绑定；条件中值 10.0751373531 元/股；legacy issuer alias 经同 PDF hash/新 index 重验证 | 正常化及持续性、减值经济影响、现金/融资/分红可持续性、公司专属权益成本及优势期限；G3 与事件批准 | 来源/身份/rebase 工程缺口已闭合，不再重复核数；可继续具体反证和精确版本审核材料 |
| S6 Agent 研究质量 | 已有离线经营反证 follow-up：茅台/伊利各三个可检验问题，区分原文、支持、反证、未知、下一事实；v5 日常 receipt 的 agent_scope=null | 当前真实 Provider 运行、独立语义裁决或新候选已审核 Finding 不能推定；原件 hash 不证明因果结论 | 可继续已授权离线/Mock 引用、语义和论点一致性检查；不能冒称收费 Provider 已运行或 Agent 批准 G3 |
| S7 Excel 工作台 | 唯一 Canonical 实际 hash 与 v5 指针一致；发布/native receipt hashes 相符；7 页已保存 native PDF hashes 全相符；原发布保留其他工作表 | 当前新 v5 候选没有 Canonical 发布授权/发布证明；renderer 42px 修改不等于新工作簿 native 验收或最终用户验收 | 可做隔离候选及只读排版/数值/导航核验；新内容发布需相应版本授权，旧授权不永久延伸 |
| S8 初步辅助使用准备 | 两公司日常 report/receipt、研究/月度复核产物已绑定；本地实际加密组件演练 receipt 存在，加密包 hash 重算相符 | 私人 IPS/组合、生产授权、生产 DB/全系统恢复、严格 contemporaneous PIT、至少连续 20 个真实交易会话、最终用户验收未通过 | 可继续隔离 DB/恢复工程、回归、只读体验及公共研究；不得自行启动生产 Shadow 或用 replay 折算真实会话 |

上述“已完成”仅限该行证据范围；不是 S1–S8 整包通过，更不是金融研究、投资有效性或总目标批准。

## 候选与日期消费边界

两份 candidate 均为 `PENDING_REVIEW`、`ACTUALLY_CONSUMED`，scheduler 为 `ALLOW_NORMAL_RESEARCH`，最终 `NO_ACTION`；`approval_changed/research_admitted/price_admitted/canonical_written/registered_current_case_changed=false`，`position_guidance=null`。不是绕过 scheduler 的预览值。两份均无 active quote，active ModelValidity events 为空且保留 `pending_complete_event_materiality_review`，strict PIT 为 NOT_PROVEN。

普通 daily receipt 仍分别运行注册旧包（茅台 research_as_of=10/8、伊利=9/22）；10/11 successor 只在隔离 pending-candidate 下生成，不更新注册当前研究。10/11 生成时间证明本次计算发生时间，不能将 6/30 财务事实冒充 10/11 实时财务，亦不能将新 proposal 冒充此前已知输入。587.5702708559 是茅台保留 10/8 日期条件值；587.8829687529 是本次 10/11 时间运输后的条件值，两者均非获批买点。

伊利 operative Facts refs 精确为 pending-economic-proposal、cninfo:1225259562、cninfo:1225511409，path 与 catalog.local_path 一致。财务 supplement 其余五原件保留 lineage/hash 绑定，不因其存在自动成为本次资本/TTM消费证据。legacy FY/H1 aliases 用于原研究/event_scope 的合法身份关联，不替代新 operative Facts IDs，也不删除经济或事件 blockers。

## 事件、价格与恢复的不可替代门禁

全窗口 raw 查询在 10/11 08:09:57–08:09:58 UTC 取得。茅台 window 一页 7/7、hasMore=false；伊利两页 30+3=33、末页 hasMore=false；请求精确限定发行人和 7/1–10/10。这证明已结束日期窗口的查询枚举，不证明 10/11 全天没有公告、每条公告已被材料性审阅，或已审旧记录自动适用于新模型。observation 明确 materiality_approved=false、model_revalidated=false、research_date_advanced=false。茅台复用 7 原件；伊利 observation 记录 reused_original_count=6，不能据此声称 33 条全部新下载或全部审过。

两公司全部本窗口公告仍缺新候选精确版本材料性准入。茅台 7 IDs：1225475868、1225475864、1225475863、1225475862、1225475860、1225475856、1225431263。伊利 33 IDs 的不可变精确清单在两页 received raw/对应 cninfo-index.json，不能以数量或既有财务核读代替逐项裁决。

10/9 收盘 quote bundle/日历观察与旧注册 research cutoff 不同，daily quote_check=`QUOTE_VERIFIED_BUT_RESEARCH_STALE`、`LAST_COMPLETED_CLOSE_DISPLAY_ONLY`、price_admitted=false。新候选 quote=null；取得新 quote 也不能跳过经济/G3、事件/有效性门禁。既有 historical-price-bridge-reverified.json 明确 strict_pit_admitted/current_research_admitted/historical_execution_validated=false；原 index 冲突通过另一保留路径精确相同原件恢复，不覆盖冲突文件。该历史证明不是当前正式准入。

组件恢复 receipt 记录 AES-GCM 解密及 69 文件 hash 验证、67 来源绑定、组件耗时 1.870901 秒、key 单独存放；database_restore_verified/full_system_restore_verified/production_touched/offsite_sync_performed=false，system_rto_seconds/system_rpo_seconds=null。现存目录只有 receipt.json 和 research-evidence.aesgcm，未保留可在本次逐项复验的明文 manifest/恢复树；本次重验的是 receipt 与密文 bytes，不重新解密或访问密钥。故 69 文件验证属于既存 receipt 所载演练结果，不能认定本次独立重新验证全部恢复文件，更不能宣称生产 DB、异地或全系统恢复通过。

## 精确证据索引

下表 SHA-256 均由本次实际本地字节计算；路径相对 `D:/GPTProject/value-investment/`。

| 文件 | SHA-256 |
| --- | --- |
| runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/receipt.json | 901eb43e9f97a8d87979f67c13a40d9541bcaeb91d55d8cd39c39d057a38611b |
| 同 S1 目录 pending-candidate/candidate.json | 56554578776ab8eb7c1269ef2424df58a9cb90673f05c9370f2f792d929c1db2 |
| runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/receipt.json | ddffb04d8f04982e829cfe0be4440e18718f3afc588bcd3c8baf2f41c7506481 |
| 同 S5 目录 pending-candidate/candidate.json | 410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299 |
| runtime/d2-full-event-window-20261011/600519-v1/raw-index-manifest.json | 0f5eebf08ffe2882f3c4f05b726343ac82ddda10f210fd353119f3fb805d1c0b |
| 同 600519 目录 observation.json | e55567719f1d3f1b78530319b1066e61e222cdb395cf376fd61bb8efcc5add9c |
| runtime/d2-full-event-window-20261011/600887-v1/raw-index-manifest.json | 2378d8dac7ef431ab416944b850a2565382f41170cce86fd2153a3ed99c0bd3f |
| 同 600887 目录 observation.json | 32db89adaff1b03bb011aa4fcb172754a639ae58f059c33c9d92b16014714934 |
| runtime/d2-evidence-component-restore-20261011-v1/receipt.json | d4093293b578f4c8235556e9c29432a46a923d11dc4b87135d1953698cab4fbb |
| 同恢复目录 research-evidence.aesgcm | 5d7aae47ea7cc3616c0af986d0802a0e6ae458bbcc47a482320087af91083f47 |
| runtime/publication-receipts/canonical-reviewed-research-20261011T064550Z-ecf3b3ec.json | 16c49f6f601f5c8ce8a9488155301cfdf9688c7a86e2a7b8d61c844bf09fc7f2 |
| runtime/daily-trade-assistant/20261011-protected-research-closure-v1/published-native-review/receipt.json | 609df0bcd5566c7456526faf7e68228a06862c1cce38586a7b16a7101da67b9c |

Canonical 实际文件 `C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪/A股价值投资_Agent前端智能跟踪模板.xlsx` SHA-256=`879e9c44a5d7c429ca9fd4702f084972af9a3d4ec91b0d59ac6756df04fd922b`，与 config/current-trial-workbook.json v5 指针一致。指针仍明确 m6_operational_status=NOT_STARTED、m7_final_user_acceptance=NOT_PASSED、initial_assisted_use=NOT_REACHED。native PDF hash 正确是保存产物完整性，不是本次用户实操接受。

本轮只新增本审计文档，不改 policy/hash-bound 文档、共享代码、事实、审批、Canonical、生产或提交。既有独立 candidate/rebase/daily isolation 47 测试通过属于此前定向测试；本轮执行的是实际证据 verifier/hash 审计，未冒称重新跑全量、干净检出或 CI。指定候选与事件绑定未发现新漂移；恢复证据可复验范围限制和全部必要门禁如上保留。
