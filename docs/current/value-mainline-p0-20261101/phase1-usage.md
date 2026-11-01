# 阶段1调用与验收范围

这些是原生入口，不是新的任务队列。仅公开留存来源离线操作；不改current、不调用模型、不批准投资。
使用PowerShell7，工作目录为本仓库，先设置 `$env:PYTHONPATH='src'`。

## A：既有CLI新增两模式

```powershell
python -B scripts/current/collect_public_evidence.py --mode archive --bundle runtime/public-evidence/20261030T110724-accepted/bundle.json --bundle-sha256 ab4d528f7f30144ac451a33d2326e9d143d7496f4d376a22a8a12800f877034a --output runtime/public-evidence-archives/<new-id>
python -B scripts/current/collect_public_evidence.py --mode restore --manifest runtime/public-evidence-archives/<new-id>/manifest.json --manifest-sha256 <returned-manifest-sha256> --destination .tmp/public-evidence-restore/<new-id>
```

尖括号为本次输出身份，不是可以原样执行的参数。源文件必须已经通过既有公开证据交付机制保留在机器上。
归档对象只含显式依赖闭包；恢复目标只能位于独立.tmp内。复用相同目标仅允许逐字节一致；
冲突、损坏、链接、路径越界或不完整闭包拒绝，不静默修复。不是全数据库或个人数据备份。

## B：同一选择内核独立运行

```python
from pathlib import Path
from datetime import datetime, timezone
from value_investment_agent.application.discovery.value_module_adapter_v1 import ValueModuleAdapter

adapter = ValueModuleAdapter(Path.cwd())
request = {
    "manifest_binding": {
        "path": "runtime/daily-marketwide/g1-restored-20261028-v4/manifest.json",
        "sha256": "c0b25d950bef78b880891b0fb3e74c4bf367b1fca38ef98f23d7246d0f79c633",
    },
    "evaluation_at": datetime.now(timezone.utc).isoformat(),
    "limit": 30,
}
adapter.validate(request)
run = adapter.run(request, output_dir="runtime/value-module-runs/<new-id>")
print(run.as_dict())
# 以返回的module-run.json实际SHA构造binding后，调用get_run/replay/explain。
# explain(binding,symbol="000568")仅过滤已保存批量结果，不把批量运行改称单证券执行。
```

八接口均存在于ValueModuleAdapter；显式输出目录必须新建且在runtime内。
get_run读取已绑定记录及其输出，不假称重新验证全部当前原件；replay按原evaluation_at和规则/代码重跑来源消费者。
代码版本不匹配需使用相应Git检出，不把旧结果重新签成新模型。
当前真实回放覆盖5224条留存证券、shortlist30；正式财务采纳0，覆盖/时点缺口仍PARTIAL。
这是历史来源重放，不是当日全A新采集、正式候选批准或买入建议。

## ModuleRun与既有ArtifactRepository

domain/research/module_run_v1.py提供不可变合同与Codec，已注册到既有research_artifact_codecs，
仅增加review scope的module_run类型。Repository仍使用原有save_object/load_by_id/list_versions；
没有新SQL、DB连接、迁移或任务控制器。InMemory测试不能证明实际数据库持久化。

module_run_projection_v1只包装既有D1/D2/G2任务的来源/元数据验证，新的VALIDATE具有独立身份；
原任务时间/代码未知仍保留未知。它不是执行旧任务，不产生新研究，更不构成批准。

## 验证

最终实际命令、SHA、测试计数及隔离构建见本目录的交付回执。
真实来源验收必须显式设置PUBLIC_EVIDENCE_ARCHIVE_REAL_ROOT、
VALUE_MODULE_REAL_ROOT及对应REQUIRED=1；缺少原件不能将skip算真实通过。
8001本轮不发布；页面代码与现有运行版本分别报告。
