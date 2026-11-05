# 价值策略透明研究工作台 V1

入口：/strategy/value；原模块地图保留/project。action=no_order。
基线6236d912。公开读取不依赖私人账户；研究任务、人工意见和成交分别保留授权及确认。
本文件是操作验收索引，不是G3批准、投资建议或新长期Goal。

| 用户操作 | 真实接口/消费者 | 边界 |
| --- | --- | --- |
| 开始扫描 | POST /api/v1/value-workbench/tasks；FRESH_PUBLIC_SCAN | 显式联网、原run_once，禁WPS/Excel/current发布，真实覆盖不冒称全A |
| 查看模块 | GET /api/v1/value-workbench/modules | 原生配置/输入输出/能力；不是实时全11模块状态 |
| 独立运行 | VERIFY_EVIDENCE / REPLAY_SELECTION / RECALCULATE_MAIN | 服务器prepare绑定输入；未支持模块保留精确缺口 |
| 查看证据 | GET /value-workbench/evidence/{id}?symbol= | 公开聚合白名单，重新校验Hash，不接任意路径 |
| 重新研究 | 原/operating-research/tasks | 真实模型、来源、预算与新版本；不是保存响应改名 |
| 重新估值 | RECALCULATE_MAIN | 既有共享v4及明确源版本，无输入不伪造 |
| 假设模拟 | SIMULATE_ASSUMPTIONS | 绑定基线副本，用户白名单修改，共享内核独立结果，不写正式候选 |
| 人工意见 | REVIEW_NOTE | 目标版本、意见及服务端actor；COMMENT_NOT_G3_APPROVAL，不签投资批准 |
| 取消任务 | POST /tasks/{id}/cancel | 持久取消及终止本次owned worker，不只取消浏览器请求 |
| 重试/恢复 | POST /tasks/{id}/retry、/resume | 新ID重试保留原失败；中断恢复显式进行 |
| 录入成交 | 原/portfolio，private/fills/prepare→confirm | 本人已发生明细与具体确认，不造实盘成交 |
| 查看决策 | decision分区及既有公司详情 | 原生事实/假设/模型/规则/时点/资格分别呈现，BLOCKED不是NO_TRADE |

## 来源与运行反馈

/companies枚举已登记研究，和当前短名单分开；注册不等于来源已验证。
公司选择来自既有注册和候选接口，不硬编码公司、数量或估值。
保留原ResearchTaskService的版本链、锁和幂等，适配原生操作，不建第二数据库或审批平台。
run_id只在真实attempt开始后形成；未知时间为null，进度仅实际步骤，不预测百分比。
历史成功在输入/源码/输出变化后保留历史，但current_validation失效不可当当前有效结果。
任务列表、详情和history均需原本机授权，避免暴露人工意见及模拟输入；公开研究仍可读。
扫描结果保存在本次任务，不自动替换正式刊发；模拟不更改正式输入、G3或主估值。
无账户个人数量null；历史估值不能未经股本/分配/事件/报价对齐就作当前低估判断。

## 开发验证

新后台/路由/原件显式组合168通过0跳过；相关旧价值链/架构135通过18跳过（未指定旧原件不算真实通过）。
Web全测1553通过28跳过；定向48通过；TypeScript通过。
两项独审已关闭任务版本绑定和终态失效问题；任务GET权限缺陷已修复。
Root联调发现P0新增Codec注册误伤旧候选，恢复原Codec精确05722dc...字节，
ModuleRun分发移到未冻结仓储适配层；不改旧候选/Hash/原件/公式。

## 实机验收

8001发布、真实API/浏览器、桌面/390px截图和每项按钮的执行结果，另存本期runtime验收回执。
未执行项目不得由Mock或HTTP200冒认通过。真实成交待用户提供已成交明细及确认；
工程验证意见不冒充用户投资意见。

## 2026-11-01 本机实机补验
用户明确授权本轮8001更新。已发布660b5cd2，源码/backend/frontend一致；
原publication registry不可用、行情未核验保留，不能将code MATCHED当投资资格。
真实TestClient原件链：证据核验SUCCESS、筛选重放PARTIAL、000568主重算/
假设模拟/工程意见SUCCESS，168项干净检出测试0skip。
真实Edge页面启动000568重算rt-1359a5cbfe5f0426f3b62c1a01d1ab07：
10.712287秒SUCCESS/VERIFIED，页面显示6.20/16.85/27.22条件研究值，
低置信度、未采用、未批准、无当前买价；不是新经济批准。
页面启动有限公开扫描rt-43b4dc7e78b77338e0fd2d409f4519a2，
19.896352秒后用户操作取消，后台CANCELLED/USER_CANCELLED；
不将取消当采集成功。轮询曾停止，手动刷新可恢复真实终态，仍需继续验收。
桌面及390px真实截图已保存；手机scrollWidth375/viewport390，无横向溢出。
实机发现原件下载列表先于研究正文且过长，改为默认折叠；
闭包遍历仅本次调用内去重，保留后续最终Hash重验，不跨请求缓存旧成功。
该补丁16后台+19组件通过，TypeScript通过。
尚未验收：完整新扫描、真实新LLM研究、所有按钮全矩阵与真实成交最终确认。
没有为了验收构造实盘成交或补零费用/时间。
本机回执runtime/value-transparent-workbench-20261101/；
模拟及工程意见不等于用户投资意见。action=no_order。


### 实机收尾补证
7997d894 Core41301900358与Web41301900273均SUCCESS；
Core原始命令包含新任务/聚合测试，9064passed/437skip，skip不算真实验收。
最终干净检出157passed/2skip，随后显式bundle补验2passed，非跳过冒通过。
真实页面取消后重试产生新task rt-61196abedb7e23a0d5cf1eba9c117b92，
原cancel记录保留；真实采集覆盖5223、SZSE/SSE、行情2026-10-30，
BSE缺失/交易日供应商日期未独立核验，因此PARTIAL不称全A完成。
另修复任务只返扫描计数的消费断点：未来FRESH执行对manifest-bound
lead_report逐条核验后投影shortlist；保留原生leads，不含excluded/evaluated。
旧任务输出不改不重签；实现变化按原合同使旧任务仅可作历史。
错误响应新增原始detail；UI显示实际错误及可手动刷新，不假报自动恢复。
整合后任务/API146通过0skip；无策略阈值/来源/G3/账户改动。
新的真实模型任务rt-e6d15d2f9d54e5bb57f9c20e57467685已从页面启动，
截至记录仍RUNNING，已有3次实际调用；不能宣称新研究验收通过。


### 真实模型超时纠偏（运行边界）
实机新研究任务第三角色请求超过9分钟仍未返回；已从页面取消，
保留前两角色原响应、0.122056元估算已结算与0.191278元未结算预留，
金额不是供应商账单，不自动退款/补零或宣称三角色完成。
修复仅在HTTP后台启动适配：原LiveOperatingTaskService.run置于
自建子进程内，整个任务300秒总截止，取消/总超时终止并确认回收该子进程；
终止未证实不伪造完成。运营回执进原任务追加状态，不重签金融输入。
operating_task_v2.py精确Hash05b312611dca14b36a5445864f6910fa099bf2719f502f33f75044b77129b651保持，
原provider、旧任务输入和已绑定主估值不变。
17项监督直测、86项原live/API回归及10项结果组件通过，TypeScript通过。
新的扫描候选明细可直达现有价值详情；不改变当前正式候选或批准。
本轮仍不把部分研究/来源不足当作可交易结果；实盘成交未写。


### 最终独立复核收尾
独审发现并关闭：终态0.05秒锁竞态P1、原生实例判断P2。
已改为终态锁有界重试60秒；仍不可落盘则同任务目录写SHA/input绑定pending，
不宣称原状态已更新。GET只读显示待完成，显式“完成状态写入”幂等处理，
不调用模型、不退款、不改变原角色响应/CANCELLED状态。
仅exact-native服务进入子进程；注入子类保留其行为。
23项监督直测＋65项Live/API=88通过，相关前端95通过，类型/格式检查通过。
独立只读复核已确认两项关闭；原v2 Hash05b312...仍不变。
这是本期任务执行完整性的必要修复，不是新研究/审批平台或策略变更。


### 最终Core分层修复
488458ac Web通过，但Core原始报告在test_agent_research_pilot的
研究层禁止进程IO规则失败。未豁免测试；把同一进程监督迁到
operations/live_task_controller_v1.py，更新路由/测试及子进程模块路径。
旧488源码Hash22d42f...仍可由其Git提交原路径精确重放，
旧运行回执不改不重签；业务模型/provider/v2研究文件不变。
迁移后93项相关用例通过；分层集成以最终提交重验为准。
