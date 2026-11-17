# VALUE-MAINLINE-P0 · G1 / Web 只读审计

## 范围与证据级别

- 工作树：D:/GPTProject/value-investment/.tmp/vf1；本次实际读取 HEAD：283c7212d832f52118705bb095e046e0c36dcbfc。
- 本次开始 git status --short 仅有 config/current-research-drafts.json 用户既有修改；未读取其内容，未改写。
- 本报告仅源码、路由、类型、直接测试源码审计。没有调用任何 API、浏览器、模型、私有接口、数据库或部署；没有重放研究计算，没有运行测试。既有回执/页面文案不是本轮运行证据。
- 唯一写入：.tmp/value-mainline-p0/g1-web-audit.md。Root负责合同/domain/基线及阶段1A+B；合同冻结前不建路由、页面、状态平台。
- 12维口径与同目录其他审计对齐：domain / application / schema / independent / CLI / run / tests / errors / provenance / Web / hardcoded / dependencies。
- 本文G1是目录“公司研究API与页面”，不是旧ResearchGate的财务G1批准门。

## 结论

已有可复用公司研究消费者与任务控件，不是空壳；但不存在“11个节点各自都有统一独立运行协议”的证据。/strategy/value与/project是同一静态目录组件，展示16个主链/共享模块；点击节点只切换React选中项和滚动，不读取运行结果、不执行研究、不批准业务。

公司详情才有实际API读模型：公开画像、既有包经营草案、首次编译，以及显式打开后的live公开研究/独立主研究重验。页面展示、工程执行成功、经济采纳、当前可比、生产部署、用户确认必须分别表达，不能合并为一个完成灯。

确定的静态漂移：catalog G2仍称“仅GET，没有开始、取消、恢复及任务检查点接线”，而现有ResearchTaskPanel和LiveOperatingResearchPanel确实有任务创建/历史/刷新/取消/恢复接线。StageDetail对D1/D2/E/F/G仍一律显示NOT_CONNECTED，含义只能是“目录未接运行状态读取”，不能当作这些模块没有Web消费者。这是后续合同冻结后应最小纠正的展示问题，不在本次修改。

## 11主节点映射（现状，不是新增状态协议）

所有目录节点定义均在web/src/config/strategyArchitecture.v1.ts的catalog.value.stages；入口共用web/src/pages/StrategyArchitecture/Value.tsx → index.tsx。

| 主节点 | 现有Web消费者 / 实际读取 | 可操作性与限制 |
|---|---|---|
| A 公开资料与证据 | /system → PublicEvidencePanel；api.publicEvidence → GET /api/v1/public-evidence；SystemStatus另读runtime-identity、research-funnel-status、packet/snapshot | 展示请求范围来源状态，不是全市场当前完整；目录只提供跳转，无采集按钮 |
| B 四通道筛选与队列 | /daily → DualStrategySelection；strategySelection/Page → GET strategy-selection?limit=10及分页/查询参数 | 候选读取与分页，不是点击目录就重新筛选/入队/补证；覆盖范围、日期、排除不得被进度灯吞掉 |
| C 企业画像/模型适用性 | /decisions/:id?strategy=value → CompanyProfilePanel → GET research-profiles/{symbol} | 挂载即读公开API；固定五家有限审核边界，不是第六家自动准入；不启动模型 |
| D1 受限研究执行 | LiveOperatingResearchPanel；另有AgentResearchPanel → ResearchTaskPanel | 两种明确执行模式：LIVE与SAVED_RESPONSE，不能混称新LLM；显式任务操作，公开读取与私有控制分开 |
| D2 经营假设与反证 | OperatingAssumptionDraftPanel → GET research-assumption-drafts/{symbol}；live公开结果内research_draft、operating_driver_bridge、completeness/review | 既有包草案挂载即读；live仅显式打开后读；三角色成功/typed桥算术不代表经济批准；UNKNOWN/反证误述保留 |
| E1 已有研究更新重放 | api.detail → GET decisions/{id}?strategy=value的research_analysis及公司详情既有现金/研究展示 | 已有包消费者，不是目录上的独立重放按钮；GET读取可调用后端冷校验/计算，不等于只读静态JSON |
| E2 新公司首次编译 | FirstResearchInputPanel → GET first-research-inputs/{symbol} | 挂载即读，NOT_STARTED可不占首屏；读模型可冷重放；不把首编成功升级C准入/主区间 |
| F1 经营—股东现金—估值 | 旧detail研究/现金；live公开结果中的cash_consumption、parent_funding_review及main_valuation_revalidation → MainValuationRevalidationPanel | 现有纯展示组件消费后端结果，不在Web重算金融公式；三情景30行账与条件估值不等主估值采用 |
| F2 价格对齐与条件决策 | detail中的策略/当前价格资格与价格计划；main重验price_policy、dated_research_review_thresholds | 日期、当前可比、未批准、无numeric规则必须原样呈现；有估值数值不等有当前买价，无订单/个人数量 |
| G1 公司研究API/页面 | 既有/decisions/:id；DecisionDetail及公开各panel；/project现有000568链接 | 聚合公开研究，不需要账户解锁；当前页面仍额外请求packet/daily，应把公开子模块隔离与整页耦合分别评估 |
| G2 研究任务操作 | ResearchTaskPanel与LiveOperatingResearchPanel复用现有API | 已有按symbol历史可发现任务、选择、刷新、取消、恢复；无自动持续轮询；不支持任意主节点统一run，不能杜撰 |

E1/E2是两条输入路径，不能绘成必须先E1才能E2的串行门；F2目录dependencies列E1与E2等，不应解释为两条路径同时必需。关联模块不等于全部共同前置。

## 五个共享节点分列（保留，不冒充主链前置）

| 共享节点 | 既有位置 / 边界 |
|---|---|
| S1 共享现金与组合风险 | /portfolio与riskContext/riskPreview等；公开风险参考与私有账户操作分开，不为读取公开公司研究解锁 |
| S2 人工成交与持仓对账 | /portfolio及现有成交入口；私有输入，不在本轮读取、验收或扩展 |
| S3 分红现金与收益 | 既有持仓/收益及对账展示；不能用公司分红计划当个人实际到账，本次未检私人数据 |
| S4 事件与持有逻辑 | /alerts → conditionAlerts；既有观察/提醒动作；公开研究Event有限期间不是完整当前事件扫描 |
| W1 模块进度与证据 | /strategy/value与/project同一目录；静态catalog/review/valueVerticalScope；/system为独立运行身份读者，不能把两者合成自动实时状态 |

## 实际读取、路由与操作合同

### 入口与首屏

1. web/.umirc.ts两条路径均component ./StrategyArchitecture/Value；没有第二个project页面或目录。Workbench导航使用/strategy/value；/project是同组件别名。
2. ArchitectureView只import静态catalog/review/valueVerticalScope，useState选择节点；selectStage仅setSelected及scrollIntoView。无API hook、自动轮询、运行按钮或持久store。刷新会回到首节点A；节点选择未写URL/hash，不支持每节点直接深链。
3. 现有公司路径/decisions/:id，策略取query strategy=value|hotspot。数值六位id且strategy !== hotspot时挂CompanyProfile/OperatingAssumption/FirstResearchInput/Live四组件；这比“仅明确strategy=value”稍宽，还接受省略strategy，后续合同应明确意图。
4. CompanyProfile/OperatingAssumption/FirstResearchInput用useApi挂载即GET。Live没有effect自动请求，初始只有“新Agent经营研究”按钮；点击才并行读model-status及companies/{symbol}。不要误报“公司页全部零请求”：只有live任务区零隐式请求，整页及前三公开组件有GET。
5. DecisionDetail本体useApi(detail)、useApi(packet)、useApi(daily)。其主公开组件在主详情之前渲染，可有局部独立错误；这不证明整页完全不受旧packet/daily/UI决策条件影响。
6. 老AgentResearchPanel在OnDemandSection“加载AI研究材料”后才挂载，但打开即读私有agent-research/{symbol}与agent-research-status；ResearchTaskPanel本身只有点击操作才请求。老入口与live入口不可混同。
7. /project已有/decisions/000568?strategy=value链接，点到公司页后仍需显式展开live；不应为方便审计偷偷自动启动或发模型请求。

### 现有live与保留响应操作

| 操作 | API / 授权 | 现状 |
|---|---|---|
| 公开model配置 | GET operating-research/model-status | 不返回秘密；READY才允许start/resume；缺配置不代表用户从未授权预算 |
| 公开研究结果 | GET operating-research/companies/{symbol} | latest真实状态+公开补充；无private授权可读；与model读并行且独立处理失败 |
| live历史/选任务 | GET operating-research/tasks?symbol=... | getPrivate；点击读取，不自动请求；选中task只在组件state |
| live开始 | POST operating-research/tasks {symbol,request_key} | local_auth、显式操作、预算；不是public GET附带行为 |
| live手动刷新/取消/恢复 | GET tasks/{id}；POST tasks/{id}/cancel或resume | local_auth；已有任务才可操作；无polling；恢复不等于必定付费或经济通过 |
| saved-response历史/开始/刷新/取消/恢复 | research-tasks同类路径，create body workflow=legacy | 与live分开；SAVED_RESPONSE只重放登记响应，0新付费；已有历史找回任务不靠localStorage |

关键路由源码：presentation/web_api/live_operating_research_routes.py:register_live_operating_routes。public company handler附加current_capital_observation、fiscal_distribution_review、parent_funding_review及read_main_valuation_revalidation结果，单项异常投影UNASSESSABLE；浏览器get不等于纯文件回显。任务history/read/control走denied(local_auth)，public availability/company不走该授权；后端执行与费用合同归Root，本报告没有运行这些调用。

### 12维G1审计

| # / criterion | 实际依据 | 审计判定 / 不可外推 |
|---|---|---|
| 1 domain | Web消费application/readmodel与types，Main/Parent/Live是展示；金融公式应留后端 | 有消费者；未新建Web金融计算域。具体经济合同由Root冻结 |
| 2 application | app.py decisions handler、company_research.py，live_operating_research_routes.py聚合独立公开结果 | 实际编排存在；不要以页面有内容替代逐模块application验收 |
| 3 schema | services/api.ts具各公开/任务DTO；main_valuation_revalidation为Record<string, unknown>，组件做边界检查 | 合同分散、部分动态record；并非统一11节点schema，待Root最小合同，不新建平台 |
| 4 independent | 公开panel可独立渲染；main可在老live NOT_STARTED/UNASSESSABLE时独立展示；私有任务与public读分离 | 独立读者成立；11节点独立run不成立，目录点击仅导航 |
| 5 CLI | Web脚本test/typecheck/build/format；业务CLI属于既有后端模块 | 无G1单独业务运行CLI需要被补齐的证据；不得为审计凑统一CLI |
| 6 run | 本次只读源码；catalog/manual receipts及旧运行说明存在 | 本轮未调用API/模型/浏览器，不给新runtime/deployment PASS |
| 7 tests | architecture.test.tsx、main-valuation-revalidation、live-operating、parent-funding、research-task等直接测试 | SSR与mock任务按钮测试覆盖合同；不是浏览器/当前后端/真实模型运行证据，本次未重跑 |
| 8 errors | NOT_STARTED/UNASSESSABLE/PARTIAL、wrong symbol/flags、独审绑定失效隐藏旧review、401单条提示、局部补充隔离 | 有明确失败展示；必须保留“数据损坏不回退旧success”与任务成功不等可信 |
| 9 provenance | research_as_of、source_bindings/fingerprint、source/implementation/spec hash、review pins及折叠详情 | 有呈现；浏览器显示hash不是自行验证原件，仍依赖后端校验；不得冒称PIT/经济采用 |
| 10 Web | 同一value/project目录 + 既有公司详情 + system/daily/alerts/portfolio | 足够复用；本次无需新route/page。公开研究结果不应藏在长来源明细之后 |
| 11 hardcoded | catalog是手工状态、固定000568直达；main schema/version及status白名单、bear/base/bull语义、fixed5边界 | 这些是显式边界，不是通用自动研究证明；G2/NOT_CONNECTED静态文本已落后于实际源码 |
| 12 dependencies | E1/E2并行输入、F1共用计算；S1–S4/W1共享；live公共读不依赖私有授权 | 保留关联非共同前置；不能为公开研究强制先完成组合/私人账户/所有16模块 |

## 展示差异与风险（供Root阶段1A+B选最小项）

1. 高优先展示纠偏：G2静态“没有操作”与已实现控件矛盾。最小方式是修正人工目录文字/证据链接，不重写任务系统；本次不代改。
2. StageDetail的runtime行只为A/B/C分支给system/daily链接，其余统一NOT_CONNECTED；应命名为“本目录运行状态未接”或按已冻结reader显示真实status，不能否认D/F/G实际消费者。
3. /project标题及16节点平铺容易被当成必须顺序做完的门。现已有“关联非共同前置”与currentBlocker/futureExtensions，最小设计复用这些而非再建流程引擎。
4. /project的source commit/日期/业务版是人工回执，不追踪服务更新。/system实际runtime-identity可读当前服务；手工快照不能自动变成当前PASS。旧C验收、用户未确认与生产部署须保留各自范围。
5. 直接测试多为SSR/源码断言与mock hook；可验证格式/分支，不替代stage1A+B真实后端与浏览器按版本核验。不得将旧120passed写成本轮测试结果。
6. task/public不同入口对新main字段的可达性应按真实wrapper核：不能要求旧live成功才显示独立冷重验，也不能缺model配置就遮public成果。现有PublicOperatingResearchView已有独立候选逻辑，可复用。
7. 现有api.detail的策略显式性、旧AI材料可出现在不同策略决策下、packet/daily耦合，需要合同界定，而不是本轮随意改gate或绕过失败。
8. /project节点没有URL选中态；如合同要求节点直达，可在既有页面使用query/hash，不新route/state。当前仅记缺口，不实现。
9. 根目录catalog的G1历史样本/证据日期较早；不能仅改文案就认定G1全链当前验收。运行、经济、价格、部署、用户确认分别保留。

## 最小设计建议（待合同冻结后实施）

- 继续用/strategy/value（/project同组件别名），不新建平台、路由、页面、store、数据库或通用运行框架。
- 一个现有页面内分两组：主链11节点A/B/C/D1/D2/E1/E2/F1/F2/G1/G2；共享5节点S1/S2/S3/S4/W1。只复用catalog IDs、StageButton、StageDetail及现有CSS/可访问性语义。
- 先显示本轮纵向链输入输出、当前阻断与未来扩展；11主节点允许选中查看输入/输出/来源/可用读者，5共享节点单列，不作为公共研究解锁条件。E1或E2可进入同一F1，不画成AND前置。
- 保留“人工回执”块（复核基线、日期、路径）与“运行读取”块独立。后者只能来自冻结合同中的既有reader；无reader就明确未接，不能映射人工字符串为成功，不伪造更新时间/进度百分比。
- 不默认发11路请求或自动轮询。目录选中可只导航；明确“读取现有结果”才接既有只读消费者。读可能冷重算，应按合同标注只读不付费；任务start/resume仍独立显式按钮与原local_auth/预算合同。
- 原公司页负责可读详细内容：Q3实际与Q4/H1预测分开、30行账折叠、估值优先、条件草案无数值规则不出买价、母义务清偿不算新分红。目录只摘要/链接，不重复金融算法或复制整包。
- reuse已有GET结果的schema/status/as_of/source_binding/current_comparable/formal_eligibility等已验证字段；最终哪些是最小公共合同由Root决定。本报告不创建或承诺一个尚未冻结的统一DTO。
- 限定验收建议：11+5计数/分组；两入口同组件；E1/E2替代关系；人工与runtime分离；节点未读不声称成功；lazy零模型/任务请求；public不被401遮挡；PARTIAL/坏来源不回退；误绑review隐藏；main false/no_order/quantity null；共享私有非public前置；旧路线及hotspot不回归。沿用现有directtests增补，实际API/浏览器由Root统一验收。

## 交接

可立即用于Root合同/基线与stage1A+B裁剪；不需要先补齐全16模块、不需要新平台。当前可证明的是已有读取/展示/任务动作的接线与明确限制，不是全链经济采用、当前价格资格、用户确认或本轮生产通过。本次未修改任何源码/配置/旧回执/私有指针；未付费、未提交、未部署。
