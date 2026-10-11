# D2 用户闭环阶段验收

任务为 D2-USER-WORKFLOW-RESEARCH-ADMISSION-AND-RELIABILITY，继承真实基线 6fd7ed9cb3b0a4034dbc5084095bebffab31b4f4。本报告记录工程和试用范围，不提升总目标或投资审批。最终集成记录在下方追加，未完成项不以文档声明代替证据。

## 1. 现在能做什么

同一 `scripts/current/use_trade_assistant.py` 提供 view/update/review，复用现有日报、共享模型和来源合同。默认 view 核验唯一发布、每项来源与候选，读当前待审研究；`--details` 展开历史。两家公司实际通过选定 v5 包运行更新，成功 2、失败 0、资产阻塞 0；没有建立新候选或更换估值系统。运行证据为 `runtime/daily-trade-assistant/20261011-user-workflow-actual-update-v1/`。

审核入口实际预览两家公司五组/四组经济问题，取消结果均为 CANCELLED / approval_changed=false。显式 save 只保存未签名草稿。本人签名由原认证机制消费；Hash 自动计算不替代固定信任根。参数别名与缩写不能覆盖入口的公司或候选绑定。

## 2. Excel 的研究价值

保留现有七个托管页和 55 个非托管页。当前待审候选、历史登记条件基线、已核财报、未来假设、历史行情、下一复核问题分别展示，不修改原有投资门禁或数值。公司、决策过程、事件和审计页提供证据与问题导航；私人组合缺失时仓位为空。原生打开和保护结果须以最终发布证据为准，自动检查不等于用户已经接受。

## 3. 经济研究真正推进了什么

本轮是对已有研究的版本核对、反证整理与用户操作收口，没有新 PDF、新未来盈利事实或新经济批准。48 项引用原件 Hash 实际核验一致。600519 的历史扣非 TTM 代理、直营净贡献、维护投入、现金分配及 15 年条件期限继续区分事实与假设；600887 的 H1 扣非下降、减值、CFO、融资、分红与公司权益成本继续保留不确定性。

当前选定 v5：600519 为 437.66 / 587.88 / 812.27 元；600887 为 9.80 / 10.08 / 10.30 元，均是未批准的条件研究，不是合理价或买点。旧基线原值保留；生成日折算不能被说成公司基本面改善。详见独立 `d2-user-workflow-research-audit-20261011.md`，其中列明具体经济破坏线、模型用途和证据页。

## 4. 何时可形成价格与买卖复核候选

必须在原合同内具备合格 FinancialFacts、已批准经济用途、精确候选的整模型 G3、对应事件材料性、ModelValidity、研究/估值/行情时点及 PIT，并通过双源收盘与 PriceBridge。茅台七公告、伊利三十三公告的旧版本审批不能迁移至新模型。当前实际更新均为 NO_ACTION；10/9 报价为 HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY，不与 10/11 候选拼安全边际。个人加减仓另需真实 Entry Thesis、IPS、持仓及组合风险检查。

## 5. 距离正式初步辅助使用

本轮工程改善与真实投资审批分开：正式审核身份登记、真实经济/G3/材料性回应仍未提供；ModelValidity 与 PriceAdmission 不因向导或展示完成而提升。私人 IPS/组合、具体生产授权、真实事件观察、至少 20 个连续真实交易会话、生产隔离恢复及最终用户验收仍需对应真实证据。READ_ONLY_TRIAL_READY 只说明读取研究的产品维度，INITIAL_ASSISTED_USE=NOT_REACHED，D2/TOTAL=IN_PROGRESS。

## 6. 历史和恢复

复用 815 项恢复资产，重新 Hash 核对；恢复代码实际读取两家公司来源绑定候选并生成四份中文报告，新进程逐字复核通过。公司间故障隔离与新目录重试通过。旧 000651/600741 和两个历史 S5 Snapshot 保留 NOT_AGENT_ELIGIBLE，不改历史来源资格。

独立故障实验发现原签名消费先写完成回执、后写历史的缺口。本轮在原消费者内改为追加完整工件、历史及复核后才发布完成回执；新历史绑定回执，未完成审核不能 attach。精确输入的显式恢复、写入故障、链冲突和重放由合成身份测试覆盖，未登记真人或代签。旧不可变历史兼容读取。真实签名历史当前为空，尚不能声称完成真人签名历史恢复。系统 RTO/RPO=null，未触碰生产数据库或 offsite/Shadow。

## 7. 交付与使用

操作方法见 `user-trade-assistant-usage-20261011.md`，审核细节见 `local-review-wizard-usage.md`。唯一指针为 `config/current-trial-workbook.json`，唯一 Excel 为其 WORKBOOK_PATH；runtime 证据保存在本机，不自动上传原始资产、私人数据或秘密。最终 Git SHA、CI 和发布验收将记录在集成段及 `docs/execution-status.md`，不将跳过项算作通过。

永久 action=no_order、position_guidance=null；HumanReview != AgentReview；最终投资决定由本人作出。

## 发布与工程验证记录

正式 Excel 已实际发布：SHA `b630e0198e10d6a8e6bac7a1b4ea91480fd96d51506c22019216aba1b3af7621`，旧版保留备份；唯一指针 SHA `ca726d4e6f2d6c16bcf383ea38396c7872d00764234cca12475d93070bd25bc5`。发布后七页 WPS 只读、23 次内部跳转、17 个来源公式显示通过；55 原页保留、24 数值不变。最终 receipt 为 `runtime/daily-trade-assistant/20261011-user-workflow-preview-v1/published-verification-v2.json`，SHA `5b9f0fdcb8474934e3c9326513cd3b71da6aeaa460cc89d0483268d71c3d11ae`。来源链接未实际向外网逐个点击，此检查仅证明公式显示和内部导航。

统一入口 13 项通过；向导与消费修复定向 141 项通过；第二轮抗降级/跨公司隔离修复后相关 119 项通过，独立静态复查无新阻断。修复前后本机注册 Core 分别 2165/2177 passed，33 skipped；后一轮不包含最后的抗降级修复，以最终干净检出及 CI 补充验证为准。跳过仍不是通过。

CODE_IMPLEMENTED、ECONOMIC_REVIEW_PREPARED、CANONICAL_PUBLISHED 已有对应证据；REAL_DATA_VERIFIED 仅限文中列明原件与行情观察。REVIEWER_REGISTERED/G3_APPROVED/EVENT_MATERIALITY_APPROVED/MODEL_VALIDITY_VALID/PRICE_ADMITTED 未达到；USER_ACCEPTED 未通过；INITIAL_ASSISTED_USE 未达到。自动使用路径与恢复检查不替代最终真人验收，也不证明消费者完全原子串行化。
