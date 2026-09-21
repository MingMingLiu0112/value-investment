# 服务器源码与数据库公开范围

更新日期：2026-09-21

生产服务部署在 `/opt/value-investment-agent`。该目录不是 Git 工作树，因此本仓库是后续维护的唯一源码版本库：

- 应用源码：`src/value_investment_agent/`
- 运维与研究脚本：`scripts/`
- 容器与 systemd 部署定义：`deploy/server/`、`deploy/systemd/`
- 数据库结构和迁移：`sql/`

服务器盘上的 `runtime/`、`exports/`、`deploy-staging/`、`deploy-backups/`、原始证据、数据库、日志、配置文件及任何带有真实凭据的数据均不进入公开仓库。服务器中用于紧急回退的 `.before-*`、`.staged` 文件同样不是源码版本。

`sql/server-schema-20260921.sql` 是 schema-only 导出，仅用于重建表、索引、约束和权限定义；它不包含任何行数据。生产或研究数据的备份应保持加密，并通过受控渠道恢复。
