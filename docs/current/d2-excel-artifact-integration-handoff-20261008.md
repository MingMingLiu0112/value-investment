# D2 Excel 工具包接入交接（2026-10-08）

本轮修复的是既有七页产品数据到原表结构的候选交付链。D2 和总 Goal 均未完成；C 盘唯一正式表没有写入。上一轮状态汇报没有改变工程状态，本轮重新核对实际文件后推进导出、来源校验、原件研究和候选验证，属于 PROGRESS。

## 实际代码路径

- `scripts/current/prepare_product_display_text.py`：读取现有 source-verified publication input，复用 `presentation/excel/product_workbench.py` 的文字展示规则；保存输入与规则文件 hash，不计算投资指标。
- `scripts/current/render_product_artifact_pages.mjs`：托管 `@oai/artifact-tool` 只生成七个管理页，读取现有公司、决策、事件和证据数据。共享 workbench 从已绑定的 read-model 取得，无公司专属估值代码。渲染与导出在同一 Node 进程时可复现原生退出 1；分离后导出实际 exit 0。本轮用独立 WPS PDF 输出做视觉检查，没有覆盖退出码。
- `scripts/current/prepare_research_handoff_excel.py --authored-pages ... --authored-pages-sha256 ...`：沿用既有候选入口，核验工具包工作簿、生成收据、文字快照与展示规则的四项绑定。
- `build_protected_research_preview`：复用 `scripts/stage_frontend_package.py:replace_sheet` 替换七管理页；保留历史页原始 OOXML 字节。继续使用 `_snapshot/_assert_retained`、源 hash 防漂移和既有正式来源 verifier。默认旧入口不变，没有新发布器、current pointer、研究或交易系统。
- authored 输入拒绝错公司集合、缺页/额外页/错顺序、全局及局部命名范围、外部 worksheet relationships、财务公式和未登记导航。来源 verifier 精确比较原 handoff 的全部绑定加上可重验的四项 authored 绑定，拒绝少原来源、任意扩充、显示规则漂移和错误 input/proof hash。
- `retained_research.py` 与 `decision_surface.py` 的健康提示改为实际公司数量。内部状态翻译增加私人输入和空仓位说明，不改变建议状态。

托管 Node 用于工作簿作者；项目 Python 用于调用现有 application，因为托管 Python 未安装项目依赖 psycopg。PDF 图片检查使用托管 Python。未修改托管依赖、生产数据库或服务器。

## 最新实际产物与验证

研究链保持 `package-v4-financial-evidence-bound.json -> workbench-v6.json -> event-followup-v4.json`。重新运行现有产品 CLI，生成 `product-read-model-v6.json` 和 `product-publication-input-v6.json`，四家公司、181 个研究来源绑定，审批与参数不变。

最新整合目录：`runtime/d2-canonical-integration-20261008-v4/`。这是明确的工程候选，不是用户 current 入口。

| 实际证据 | 结果 |
| --- | --- |
| 正式表原 hash | `5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`，保持不变 |
| 七页工具包 donor | `c55b1d942cc611eb1e6dc7f19382c60e0ba81b125c90228751c082107c2c33ca`，实际导出 exit 0 |
| 最新整合工作簿 | `db47bb6bda7b42c48cc2d1083ccb29f150ee02bd5d9e3bb0f1bf6989fe9b265b` |
| 保留证据 | 55 历史/手工页 XML 字节不变，workbook 结构 XML 不变，既有完整保留校验 PASS |
| 来源重验 | 186 项唯一绑定，源集合 hash `852f1942e14393587685c09877fd6a7b03c19dd0ad541845054f2babc98dcd51` |
| 原生 WPS | 七页只读重开、计算与 PDF 导出通过；工作簿 hash 不变 |
| 可读性检查 | 七页无裁切行；B4 冻结通过 |
| 页面修复 | 原候选横向拆列；现管理页 A3 横向、宽度一页。今日/机会/组合/事件各 1 页，决策 4 页，公司 19 页，审计 7 页 |
| 相关回归 | 129 passed、0 failed、62 个既有弃用 warnings，31.70 秒；XML 为 `.tmp/d2-artifact-publication-final-20261008.xml` |

129 项包括 25 个 authored 集成/对抗用例及既有来源、历史保留、Excel、决策和 CLI 消费者测试。本轮没有重跑完整 4,000+ suite；前轮 4018 passed/41 skipped 是此前代码的独立记录。

七页首个原生 PDF 页面和公司末页已人工查看；机器记录为 `delivery-recheck.json`。这是抽样视觉检查，不能证明全部 34 个 PDF 页面逐页视觉通过，也不能替代用户验收。不要为该抽样生成正式发布所要求的全量 `visual-review.json`。

## 财务研究交接

独立 subagent 已保存 `600519-d2-economic-assumption-gap-20261008.md`：核对同一模型 42 项参数绑定、官方页码与输入 hash，明确正常化利润、分配能力、留存资本回报和优势持续期的最小事实桥。半年报 p101 的两只基金未实缴承诺合计 60 亿元，付款时点未知，不当作已发生现金扣款。旧报告、原件、估值参数和审批保持不变。

当前研究事实有具体验证，但完整投资准入没有通过：茅台仍 NO_ACTION，ModelValidity UNKNOWN，PriceBridge INVALID，买入/减仓区间和个人仓位为空。404.82/479.88/572.74 是低置信度条件压力情景，不是认可的中性合理价或买点。本轮新增研究报告没有被伪装为模型审阅批准。

## 未完成项与最短后续

1. 先收尾展示：部分存量模型词仍为英文；另外三家首页主要原因仍回退到下一触发文本；官方 URL 在审计页为文本，不能宣称所有链接已点击验证。候选内部导航目标受合同检查，尚无逐链接原生点击收据。完成这些实际可用性检查再准备正式发布审阅。
2. 按新增假设缺口交接，先核对正常化调整项目的税后归母归属与重复扣除，再构造分配资金/资本用途桥；给预测区间经济理由、反证和失效条件，不要求未来预测成为已观测事实，也不为生成 BUY 调参。
3. 按现有精确版本合同完成研究、模型有效性和价格评审，再生成完整非个性化建议。真实私人输入只约束个性化仓位和金额；ADD/HOLD/TRIM/SELL 的完整生成链仍未完成。
4. D1/D5 继续沿用既有五库审查和适配方案，不扩展全市场排名或情绪信号。本轮未授权/执行正式 Excel 发布、生产调度、部署、数据库迁移或真实 Shadow。

| 状态 | 本轮准确范围 |
| --- | --- |
| CODE_IMPLEMENTED | 工具包作者与既有受保护整合入口接通；展示仍有明确收尾项 |
| AUTOMATED_TEST_PASSED | 上述 129 项及实际 donor 导出、来源重验、WPS/可读性检查通过 |
| REAL_DATA_ADMITTED | 历史财务核对有证据；完整 D2 投资准入仍为 false |
| USER_ACCEPTED | false；正式表未发布，最终用户验收未通过 |

永久 `action=no_order`。本轮未提交或推送 GitHub，不把当前工作树与远端提交等同。
