# 20-50 Fixed Sample Expansion Readiness Review

更新：2026-09-22。范围：C3 W12。

## Final Verdict

```text
NOT_READY
```

当前三公司研究平台基础已经可复用，但从“固定三公司 replay”到“20-50 家固定样本 onboarding”仍缺少一个通用的 manifest-driven input adapter。不能据此宣称可以安全自动扩样本。

## 逐项检查

| 检查项 | 状态 | 实际证据 |
| --- | --- | --- |
| Manifest 入组 | READY | `config/fixed-sample-manifest.json` 支持多公司、版本、profile、模型、证据和显式决策；loader 对未知字段和交易键 fail-closed。 |
| Unsupported profile | READY | `ValuationRouter` 对未注册 profile 返回 `UNSUPPORTED`；Batch 隔离为独立公司状态，不级联失败。 |
| 三种现有模型同一入口 | READY | `ResearchApplicationService.run_company_research()` 只依赖 `ResearchRunSpec`；router/registry 决定模型，无 symbol if/else。 |
| Distribution 同一入口 | READY | `ResearchRunSpec.distribution_result` 接收 typed `DividendResearchResult`，并进入同一 review pipeline。 |
| Artifact 持久化与恢复 | READY | append-only artifact、版本 head、payload SHA-256、typed round-trip 和 PostgreSQL repository 均有离线/CI 测试。 |
| runtime -> PostgreSQL parity | READY | frozen runtime importer 生成 source/database hash 与语义 parity；disposable PostgreSQL integration 覆盖三公司。 |
| Excel boundary | PASSED_WITH_TECH_DEBT | Domain 不依赖 Excel；旧 publisher 仍读旧 runtime JSON，尚未消费新 Application result。 |
| Batch isolation | READY | 单公司 GAP/FAILED/UNSUPPORTED 均隔离，批次状态和错误可审计。 |
| 新公司 onboarding | NOT_READY | `research_e2e_replay.py` 硬编码 `SYMBOLS=("600519","000333","601088")`、`MOUTAI_CURRENT_MODEL_POINTER`，并在 `_facts_for()` 中按 `symbol == "600519"` 选择专用茅台模型载荷。没有通用 facts/assumptions/quote/source descriptor 或 manifest-driven ResearchRunSpec builder。 |
| 新 Profile 成本 | NOT_ZERO | 新经济画像需要新增 Profile、模型 registry、Facts contract 和对应证据；这是明确边界，不是零成本。 |
| 证据采集自动化 | NOT_READY | 新公司仍需人工完成 Evidence、Facts、ResearchCase 和适用模型准备；平台只保证后续复用。 |

## 真实阻断原因

1. 唯一已实现的 runtime -> `ResearchRunSpec` adapter 是三公司验收 replay，不是可扩展 onboarding adapter。
2. 茅台专用 current model 重建仍与 symbol 绑定；新增第二个 quality_compounder 时必须重构输入来源描述。
3. Manifest 能声明 policy，但不能声明 facts/assumptions/quote 的来源；新增公司仍需专用 loader 或 adapter。
4. 新 profile 必须注册新的模型和 Facts contract；这是经济适用性问题，不应靠 symbol 分支绕过。

## 下一阶段唯一建议

```text
NEXT TASK: C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER
```

目标：把三公司 replay 中的 facts/assumptions/quote/source 重建改由 versioned per-company input descriptor 驱动，移除 `symbol == "600519"` 分支，并继续禁止新增第四家真实公司，直到该 adapter 的离线 fixture 和 disposable PostgreSQL replay 全部通过。
