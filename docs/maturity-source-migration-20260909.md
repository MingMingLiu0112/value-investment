# 到期现金流证据隔离执行记录

## 范围与依据

六条已读原件的到期现金流来源及十二条显式依赖结果，共18条记录；涉及000027、000550、000729、000786。证据清单为runtime/reviewed-maturity-facts-20260908T201341916878Z.json，依赖清单为runtime/maturity-dependency-audit-20260908T201741212762Z.json。

脚本scripts/migrate_maturity_sources.py与独立evidence_dependencies.py上传deploy-staging，不替换服务器运行模块。执行使用项目共享文件锁、0.5CPU、384MiB内存/512MiB含交换上限、只读代码和原件挂载、3秒锁超时与30秒语句超时。

## 真实回滚演练

运行8857291e-4336-442d-9a69-059e78783a7a，applied=false。
前置条件核对生产依赖闭包、18条记录原元数据、6个候选完整记录、报告身份和服务器原PDF Hash。
隔离18条、退役6候选、同事务重算4家公司财务评分和估值后回滚。
回滚核对data_points、filing_candidates、financial_quality_results、valuation_results的公司范围完整快照一致，并确认演练task_runs记录未保留。
快照SHA-256：5361939ef06ca8fc542bbccef8a9daf65d52fc9c199506900f188eea3c06769a。

## 正式提交

运行728836a8-0e3b-439e-a9ab-277527b165dc，applied=true；同样前置条件再次通过，正式提交18条隔离和6候选退役。保留原值、原元数据和原验证状态，加入superseded_by_parser、evidence_quarantine及运行ID，关闭automatic_cross_source_verification。主指标的最新视图已在事务内确认不再返回这18条记录。

现有生产重算函数用于财务评分及估值；不是新估值模型上线，也不是完整策略回测通过。未部署v31解析器或本地cli其他改动。

服务器已重新生成exports/latest.json，SHA-256为c8e237225c04642adab0ff526068b66dbbf2a583e1107b8ad6c0f6210fa877e0。

## 发布与持久化复查

原Excel发布完成于2026-09-09T04:26:26.8504905+08:00，载荷时间2026-09-08T20:23:35.422518+00:00。现有同步校验确认主要页面738家公司、公司研究744行、已验证数据点4552、年度输入4031、金融专用指标196/328；人工记录及历史保留检查通过，交易所名单核对通过。数据总数变化也包含其他任务期间变更，不全部归因于本次隔离。

发布后重新以openpyxl打开WPS原文件，确认26个工作表、12_提醒及21_决策验证存在。新生产只读快照runtime/candidate-release-inventory-20260908T202636368093Z.json确认18条目标记录均具有本次运行ID的隔离标记、6个候选均为superseded_by_parser。

仍未部署新版解析器、未完成其余14条受保护来源审计、未完成真实交易策略回测。本次只证明上述6条来源及其已记录依赖已隔离和发布，不代表全项目完成。
