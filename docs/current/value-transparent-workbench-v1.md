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
