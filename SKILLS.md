# value-investment 项目 Skills

技能放在本仓库根目录下的 `.agents/skills/`。在 Codex 中可用下表的 `$vi-…` 指定技能；也可以直接阅读入口文件。它们提炼可重复的做法和反例，不是阶段任务、投资建议、进度台账或额外授权。

| 场景 | 技能 | 覆盖 |
| --- | --- | --- |
| 从公开原件、全市场名单到可重放候选 | [`$vi-public-intake`](.agents/skills/vi-public-intake/SKILL.md) | A/B |
| 企业类型、经营假设、股东现金、三情景估值 | [`$vi-valuation`](.agents/skills/vi-valuation/SKILL.md) | C/D2/F1 |
| 受限 Agent 任务、预算、封存响应、恢复与重试 | [`$vi-research-tasks`](.agents/skills/vi-research-tasks/SKILL.md) | D1/G2 |
| 新公司首编、公告触发、已有候选更新与冷重放 | [`$vi-research-lineage`](.agents/skills/vi-research-lineage/SKILL.md) | E1/E2 |
| 五维价格对齐、分红事件和人工条件价门槛 | [`$vi-price-alignment`](.agents/skills/vi-price-alignment/SKILL.md) | F2 |
| Web 实机验收、发布回退及模块透明度 | [`$vi-web-acceptance`](.agents/skills/vi-web-acceptance/SKILL.md) | G1/W1 |
| 组合、风险、人工成交、分红现金及持有复核 | [`$vi-portfolio-risk`](.agents/skills/vi-portfolio-risk/SKILL.md) | S1–S4 |
| 热点波段的独立验证、样本外与 Shadow | [`$vi-hotspot-validation`](.agents/skills/vi-hotspot-validation/SKILL.md) | HOTSPOT_SATELLITE |

## 更新规则

1. 对照当前分支的 [项目约束](AGENTS.md)、[阶段任务](docs/current-stage-goal.md)、[执行台账](docs/current/web-first-full-product-execution-ledger.md) 和实际代码。从最近一次已审提交开始看新增差异，不仅看 PR 标题或自报完成。初版审阅了默认分支 `ad913f8c977a3ba0eba5e2a7cc5094673b02d0bb` 和 [PR #5 的快照](https://github.com/MingMingLiu0112/value-investment/tree/9bf691202f5cef8a9935d0b4bd8b670a8c9f68d8)；引用未合并行为时注明分支状态，合并或放弃后重新核查。
2. 有可重复的决策规则、真反例或验证手法才更新。把站得住的通用做法放进已有 Skill，较长案例放在该 Skill 的 `references/`。记录公共证据的 commit/test/文档和适用条件。单次股票结果、短期进度、测试数量和未来阈值不是 Skill。外部投资观点先验证候选规则、反例和时点，不直接变成项目标准。
3. 每次至少检查目录名与 YAML 名称一致、仓内链接存在、仅改技能相关文件。用一个正常场景和一个拒绝场景走查新规则；划分代码、CI、Windows 浏览器、业务证据、人工审批五类证明。没有新知识就不改文件。公共仓库只用可公开证据，不写私人 IPS、持仓、成交、原始运行日志、凭证或未公开对话。
4. 小批提交到单独分支／PR。不要为维护技能改估值公式、阈值、受保护回执或线上环境。永远保持 `action=no_order`；不替用户签材料性、估值采纳、生产授权或真实买卖。
