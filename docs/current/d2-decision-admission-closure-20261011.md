# D2 正式决策准入工程收口与实际使用边界

本轮任务为 D2-DECISION-ADMISSION-AND-ASSISTED-USE-CLOSURE，基线为
30f4288bef61fa08196495c815c4326ba4845077。复用已发布的两家公司 v5 候选，
没有重算新候选、重新下载财报或增加估值框架。

## 实际交付

| 工作包 | 实际结果 | 未被工程替代的条件 |
| --- | --- | --- |
| A | 既有公司 CLI 可准备独立回应输入并消费真实签名回应；精确绑定候选、事实、假设、估值与模型上下文；追加历史验证、拒绝重放及冲突身份；整模型使用原有 G3 合同 | 真实审核者身份注册及实际回答均未提供；固定信任根清单仍为空 |
| B | 茅台七份公告与57字段的399关联归并为7项经济审核，保留全部追溯映射 | 人类材料性、十五年模型适用性未批准；旧十年判断未沿用 |
| C | 伊利33公告归并8类机制、24情景字段路径；澳优、票据融资、兑付、分配和稀释分开判断 | 公司专属权益成本证据不足；宽行业beta不作为公司中心成本批准 |
| D | 两家公司真实v5候选及10/9双源收盘通过原有类型回放；原模型窗口从10/11开始，早于它的报价被拒绝 | 模型/G3、材料性和适用的事件窗口仍缺合法批准；保留NO_ACTION |
| E | 六家公司原有入口、九组经济问题、事实/估计/审核/正式决策与变化归因在既有七页展示；21条件数值核对，55非托管页保护 | WPS工程通过不等于最终用户验收；条件值不是合理价或买点 |
| F | 既有v5/v7比较保留研究文件变化，但经实际折算关系验证后明确归因为生成时间；日报/月度比较展示此区别 | 不声称有新财报或经营改善，不伪装一个实际月度观察期 |
| G | 六组渠道、产品/成本、份额/营销经营问题提供原文支持、反证、未知变量和重开条件 | 原文有引用不等于因果已证明；不称为真实外部LLM调用 |
| H | 25文件的实际加密隔离组件恢复，14,608,229字节逐字节一致；解密恢复1.733700秒 | 快照是新版发布前Excel；不是全研究依赖、生产数据库、异地或系统RTO/RPO验收 |

审核说明见 [两家公司人工审核使用方法](d2-human-review-usage-20261011.md)。
精简经济复核见 [茅台公告闭环](600519-event-review-closure-20261011.md)、
[伊利公告闭环](600887-event-review-closure-20261011.md)。
恢复范围见 [组件恢复报告](d2-component-restore-20261011.md)。

## 已运行证据

发布后的本地当前注册 Core：2125 passed、32 skipped，135.30秒；38条已有弃用警告。
其中审核回应及相关聚焦集129 passed。独立代理完成静态对抗复审，未发现剩余P1，
但代理审查不代替主代理实际测试，也不作为人类经济审批。

干净检出c27e57f实际2102 passed、55 skipped，124.04秒。
32项本地跳过包括保留研究/验收资产缺失及2项Windows符号链接权限不足；
干净检出的额外跳过是未随Git提交的本地runtime资产，不代表这些实际验收已通过。
源代码与工作流修正版本00188f53ce5e1cb1915ad1a500239787d8b0914d，
[GitHub CI 38136655909](https://github.com/MingMingLiu0112/value-investment/actions/runs/38136655909)
的offline-core和隔离postgres-integration均success。
初次c27e57f CI因新增清单两行过度缩进而执行中断；00188f5仅修正YAML折叠命令，
未删除测试或放宽断言。实际JUnit与指针回执保存在runtime/d2-admission-final-checks-20261011-v1/。
隔离CI PostgreSQL证明工程合同，不作为生产数据恢复或实际二十会话验收。

CODE_IMPLEMENTED=true；REAL_DATA_VERIFIED=上述既有财报/公告/行情的实际核验范围；
ECONOMIC_REVIEW_PREPARED=true；ECONOMIC_REVIEW_APPROVED=false；
EVENT_MATERIALITY_APPROVED=false；MODEL_VALIDITY_VALID=false；PRICE_ADMITTED=false；
PRODUCT_PUBLISHED=true；USER_ACCEPTED=false；INITIAL_ASSISTED_USE=NOT_REACHED。

真实价格拒绝回执：runtime/d2-actual-price-contract-audit-20261011-v3/receipt.json，
SHA256 8aff9e1e80363558ebfb9ec51add34bc04d70c0a5d265cb3b6b1a319f1873149。
它实际调用原有QuoteSnapshot、ModelValidity、PriceBridge和建议回放器；未调整事件、
valid_from、模型日期或阻塞。技术合成准入及六种建议状态属于核心测试，不能推广为真实BUY。

回应输入目录：runtime/d2-human-review-inputs-20261011-v1/。两份文件真实回答、
审核者、时间及整模型决定仍为空；没有生成签名、私钥或可信身份。
运营事件观察计数未增加，未启动生产服务/Shadow，position_guidance=null。

新版展示目录：runtime/daily-trade-assistant/20261011-d2-admission-review-v6/。
研究发布输入已复核351项绑定，作者导出SHA aecfdd1e7b332f0e7ad6267b8c8a6618da5c6c609ee534b4de8a60063787a7c5。
保护集成候选SHA 83908b2513e1d9cf7dbdc17f0ad6f56b7a213e94f52a3bb0398af60339ab5b29。
该版本已实际替换C盘唯一原表，旧SHA6c90...已由保护发布器备份。
发布回执为runtime/publication-receipts/canonical-reviewed-research-20261011T113627Z-860eef98.json。
发布后再次实际WPS七页、链接及公式核验通过，config/current-trial-workbook.json已绑定新回执。
实际WPS七页、23次内部跳转、17项来源公式显示及可读性通过；首页和公司首页、
四张全部分页联系图经直接视觉检查。公司详情仍较长，九组精简问题放在详情之前。
artifact图像预览的HYPERLINK有显示限制，实际WPS正常；导出后附带图像渲染进程退出异常，
未作为成功运行回执，工作簿字节另外经过上述数值、来源、WPS和完整保护校验。

## 五个使用问题

1. 当前能辅助做什么：查看公司论点、财报原件与数值、条件估值、反证、公告影响和下次重开条件，
   在明确版本上完成有理由的人工研究审核；还不能把未准入的结果当正式买卖建议。
2. 研究可信度改善在哪里：公告与真实模型字段关系更清楚、六个经营反证有原文定位；
   未新增披露事实，也未解决渠道净贡献、正常化盈利、优势期、分配及公司专属成本等全部未知。
3. 买卖复核还差什么：真实G3与精确候选审核、同版公告材料性、适用完整窗口及ModelValidity；
   之后按既有日期/PIT/双源规则准入报价。不能将10/9报价倒接到10/11模型制造有效买点。
4. Excel怎样用：先看01_今日，点击公司定位03_公司；先读事实与估计/正式准入/经济审核，
   再看05_事件和决策过程。格力、华域为缺原件绑定的历史研究，不显示伪造当前估值。
5. 初步使用还缺什么：真实经济/G3/材料性审核与身份、私人IPS/组合、具体生产授权、
   至少20连续真实交易会话及事件观察、独立真实恢复验收、实际用户验收/Checkpoint D。

TOTAL_GOAL_STATUS=IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES；
D2=IN_PROGRESS；INITIAL_ASSISTED_USE=NOT_REACHED；action=no_order。
工程实现、准备审核、发布和投资批准严格区分。生产恢复及最终用户接受均未通过。
