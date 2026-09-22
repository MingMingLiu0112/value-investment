# 数据与证据政策

生效：2026-09-22。本文件集中强制数据底线；具体来源见 [覆盖矩阵](data-source-and-financial-coverage-matrix.md)，外部等待见 [等待政策](external-data-blocking-policy.md)，原件热冷存储见 [存储协议](evidence-storage-tiering.md)。
阶段目标只能缩小工作范围，不能放宽本政策。

## 来源与观察对象

交易所、发行人/IR、巨潮法定披露为财务和资本事件原件依据。公共结构化接口用于发现、补充与差异报警；源码仓库、LLM 和二手转述不是正式财务事实来源。
记录 security_id/symbol/exchange、field、原始/标准化值与单位、currency、period_start/end/basis、statement_scope、profit/share_basis、source_id/URL、published_at、available_at/依据、fetched_at、行情会话时点、document_hash、页码/表头/摘录、parser_version、validation_status/method、reviewed_at、input_fact_ids、formula_version、supersedes_id、run_id。

日期级披露只有保守上界时明确记录，不能臆造分秒。报告期不等于信息可用日；抓取日不证明历史可用性。
合并/母公司、FY/YTD/TTM、币种、单位、复权/未复权、普通股/少数股东范围不混用。

## 验证、缺失与更正

E0 缺失/冲突/隔离不能进入正式计算；E1 为聚合观察或候选；E2 有定位清楚的一手事实；E3 按该字段已登记方法完成必要勾稽和独立核验。
两个网站镜像同一报告不算独立来源，两个解码器不算两份法定披露。确定性单一正式公告可用有版本的唯一来源核验方法，不能凑错误口径“双源”。
缺失不填 0；真实零值需证据。quarantine 不进入正式估值；来源冲突保留各版本，不投票抹平。
更正触发依赖失效和重算，旧原件/判断不删除。文件 Hash 证明字节未变，不单独证明财务事实正确。

## 快照与身份

每次结果可追溯：Excel 数值 -> 结果版本 -> 输入 Facts/Assumptions -> 源文件页码/URL/Hash。
不可变 Snapshot 与可变 latest 指针分离；指针解析须验证目标 Hash。模型、报价、研究对象不能跨公司、跨版本混配，重放只能消费快照内当时可用的信息。
旧无身份字段载荷以明确版本适配和重新核验处理，不通过填默认值升级为 READY。

## 生产数据与工程状态

分别记录 Engineering、Research、Valuation、Dividend Research、Current Data 和 Price Assessment，不用一个总 READY 混淆全部能力。
行情/未来披露等待为 PENDING_EXTERNAL_DATA；已存在但口径无法成立为 MODEL_NOT_APPLICABLE / FACT_CONFLICT / ASSUMPTION_MISSING 等具体问题，不能全部伪装为外部等待。
旧快照可验证工程，不冒充今日结论；模型状态 conditional_research_only 不因测试通过或桥接 READY 升为正式合理价值。

行情须核对交易所时区、真实交易会话、股票状态、报价口径和收盘最终状态。日历失败不自动判休市；新报价需要模型有效性扫描覆盖该日。
分红历史只使用研究时点已知方案；预案/批准/实施/支付、更正/替代分开，未来分红不能回填历史股息率。
等待外部数据时完成可独立验证的当前工程任务，不轮询自然时间以制造进度，也不自动扩展到未经阶段准入的工作。

## 运行资产与公开仓库

PostgreSQL 数据文件不得放 WPS 云盘并由多机直接共享；服务器提供受控数据库访问。WPS 只同步展示工作簿，一台指定发布端写回，多端查看。
GitHub 保存源码、schema、无敏感 fixture 和文档，不存 .env、口令/私钥、生产数据库导出、个人持仓/交易、未授权原件或未加密备份。
MVP runtime JSON 可暂存新研究产物，但必须有 Hash、版本、恢复清单与后续持久化责任；不声称所有新领域对象已经落库。
本次文档审查未连接服务器，不把历史服务器记录当成当日生产健康证明。

## Excel 发布

复用原 WPS 工作簿，保留所有手工和历史记录；先生成候选、验证结构与数据，保存回退副本，再以源 Hash 防覆盖和原子方式发布。
布局/导航/公式改变时做实际 WPS 只读验证；普通数据刷新按受影响范围验证。文件占用或被用户修改时保留候选，不能强制关闭或覆盖。
openpyxl 保存成功不证明公式缓存已重算；本地 runtime 路径不能成为跨设备用户依赖。
核心计算不读取 Excel 作为唯一事实源；人工输入经显式导入、验证与审计后才进入领域流程。

## 服务器与恢复

保护现有 web_app_integrated.py / web-app-pta；部署前核对资源，采用有界并发、内存和任务预算，不改 PTA 服务，不因研究扩张造成 OOM。
沿用至少 2 GiB 磁盘储备和已存在的备份预检；容量不足停止对应写入，不降低阈值或删除证据掩盖问题。
每日加密备份包含一致性数据库、原始证据清单/Hash、配置清单、代码版本、Excel 和解密依赖位置；密钥分开保存，WPS 同步不是不可变备份。行情失败不阻断备份。
恢复到隔离数据库，校验源/目标身份、按稳定主键规范化的表行数/Hash、原件/配置/Excel，并记录真实 RPO/RTO。目标 RPO <= 24 小时、RTO <= 4 小时是待测目标，不是当前通过声明。
重试有预算，既有调度和锁避免重复 worker；子任务失败不得被退出 0 掩盖。此文档不授权部署、停服务、清理服务器或创建新任务。

