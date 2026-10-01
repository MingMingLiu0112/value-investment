# Shared Research Workbook Flow

This is a research-presentation flow, not investment admission. Every command retains `action=no_order`. Unknown model validity, pending prices and unapproved research remain blocked.

## Pinned Single-Company Historical Closure

`scripts/current/build_historical_company_closure.py` turns an existing pinned historical research replay, a reviewed execution clock and a bounded range experiment into one readable source-audited output. It is an engineering integration path, not a new valuation model or strategy approval.

The command requires an input recipe containing the M3 replay/manifest, execution input/summary/journal/manifest and range result/manifest/journal with their SHA-256 bindings. It verifies every file before reading it, rejects any source or manifest drift, and writes only new files under `runtime/`.

The current real-input example is `runtime/historical-company-closure-600519-20261001/`. It binds 2,674 sessions from 2015-01-05 through 2025-12-31, 15 reviewed corporate-action events expanded into 45 execution-journal date rows, and nine range-diagnostic scenarios. The output deliberately remains:

```text
engineering_delivery = DELIVERED
current_research_admission = NOT_READY
strict_pit_admitted = false
historical_execution_validated = false
action = no_order
```

The rendered report is `runtime/historical-company-closure-600519-20261001/company-historical-closure.md`, file SHA-256 `13f4ecd399bc6521a941417132fe94b04676f6101bf78de45a0d5b0080be2092`. A fresh no-overwrite run against the same pinned recipe reproduced the same result JSON after excluding only the generation timestamp and produced byte-identical Markdown. The report now presents the no-decision execution clock separately from the retrospective range diagnostics and translates admission blockers into user-readable Chinese; raw blocker codes remain in the JSON for audit.

The range scenarios are diagnostics only. Their returns do not establish strategy effectiveness, current fair value or a buy/sell signal.

## Reproducible Integrated Preview

Use `scripts/current/build_product_workbench_candidate.py` with all of:

```text
--historical-preview
--integrate-canonical
--base-payload <repository-contained public payload>
--base-payload-sha256 <pinned SHA-256>
--existing-workbench <verified shared research output>
--existing-workbench-sha256 <pinned SHA-256>
--output runtime/<new-review-folder>/canonical-integration-historical-preview.xlsx
```

For an explicitly public serialized read-model snapshot, add `--base-read-model-snapshot`. Private portfolio snapshots are refused by that adapter. The original workbook is resolved through the existing WORKBOOK_PATH configuration, never a new user path. Generation retains non-product sheets and protected OOXML state, rechecks the original hash and creates an exclusive `canonical-preservation.json` only after those checks pass. Existing output/proof paths are refused. Failed previews may remain for diagnosis but do not receive a PASS proof.

Generation does not publish. The source-binding receipt pins research, base input and preservation proof. Actual WPS/readability review must precede the existing `publish_product_workbench_to_canonical.py --reviewed-research-folder ... --reviewed-research-proof-sha256 ... --publish` command. Publication now fails closed unless the source-binding receipt, WPS receipt, readability receipt and `visual-review.json` all exist and match the candidate; the publisher also rehashes every declared local source and the nested closure/execution-replay source sets. The proof must retain `strict_pit=NOT_PROVEN` and `current_price_bridge=NOT_ADMITTED`. If the original workbook changes, regenerate against its new hash; never edit an old proof to fit.

The hardened preview verification receipt is `runtime/publication-receipts/canonical-reviewed-research-verification-20261001-hardened.json` (SHA-256 `cb951cf402ba10039a2eb9f6777be66826cc625c7e91cdf0096095689759ad63`). It verifies 52 unique bound sources and records `canonical_written=false`; it is not an instruction to publish.

## Current Dependency Map

| Requirement | Actual implementation | Missing dependency / next action | Acceptance evidence |
| --- | --- | --- | --- |
| Source-bound single-stock presentation | Existing research loader, workbench application, typed valuation and pending PriceBridge projection | Shared integration now has supported CLI; native review remains per generated artifact | Source hashes, human-readable report, preview proof and publication receipt |
| Current investment conclusion | Separate ModelValidity and PriceBridge contracts | Official event outcome, approved research and compatible verified quote for the affected case | Actual admission, not a preview or passing test |
| Historical decision replay | `m3_historical_research_replay.py` explicitly separates retrospective and contemporaneous rules; `build_historical_company_closure.py` now integrates one real 600519 replay with a reviewed execution clock and bounded range diagnostics | Contemporaneous rule evidence remains missing; the 600519 replay keeps the retrospective-rule blocker | Version-frozen inputs/rules, source hashes, reproducible dated decisions and explicit `historical_execution_validated=false` |
| Three-company contract replay | `research_e2e_replay.py` and frozen manifest runner | Useful regression, not a substitute for real valuation/execution replay | Cross-company semantic equality only |
| Daily production packet | `daily_product_packet.py` rehashes contained quote bundle before frozen packet builder | Current dual-source quote and applicable research needed for current advice | Actual quote binding and applicable decision gates |
| Formal publication safety | Publisher requires source-binding receipt, rehashes 52 bound sources including nested closure/replay sets, requires WPS/readability/visual review, and preserves worksheet OOXML tables/comments | Canonical write authorization and final user acceptance remain separate gates | `runtime/publication-receipts/canonical-reviewed-research-verification-20261001-hardened.json`, 52 sources, `canonical_written=false` |
| Final operational acceptance | Existing M6/restore/user gates | Twenty real sessions, full restore and final acceptance remain outstanding | Actual operational evidence; no replay substitution |

Do not repeatedly reopen stopped research inputs or let them block independent historical/integration work. The canonical publication on 2026-10-01 demonstrates protected research presentation, not completion of current market or investment gates.

## Observed Result Cutoff Replay

`scripts/current/replay_workbench_cutoffs.py` accepts a pinned `--workbench`, `--workbench-sha256`, increasing timezone-aware repeated `--cutoff` values, a new runtime `--output` and optional new runtime `--report`.

It rehashes original evidence and uses the latest of workbench generation and source-observation timestamps. Before that boundary no valuation is shown. After it the existing blocked research is visible without orders, fills, current price or portfolio guidance. Cutoff timestamps are not asserted to be trading sessions.

This contract deliberately does **not** reconstruct earlier public-information availability, run valuation-based decisions, validate execution mechanics, prove strict PIT or measure returns. The old Median-PE replay is a retained retrospective experiment; the old daily simulator still includes legacy 30% margin rules and must not become the default shared path. Full historical execution acceptance remains outstanding.

## Separate Financial Input Reconstruction

The same replay CLI optionally accepts paired `--arithmetic-input` / `--arithmetic-input-sha256` and `--disclosure-index` / `--disclosure-index-sha256`. All four are required together. This adds a separately scoped `reconstructed_financial_inputs` section; it never changes the observed-result timeline or strict PIT verifier.

The application reuses the existing residual-income arithmetic replay, requiring original source hashes and the two reviewed basis inputs. The infrastructure adapter matches announcement ID, security code and official file URL against a pinned CNINFO index. Since the retained announcement timestamp does not establish precise intraday publication, availability is conservatively the following midnight in China time. Later source-review dates are preserved, not rewritten.

Forecast assumptions are explicitly retrospective pinned scenarios, not contemporaneous forecasts or registered historical rules. Source excerpt semantics, complete FinancialFacts admission, current ModelValidity, price and portfolio gates remain unapproved. Model arithmetic agreement plus date-level disclosure reconstruction alone does not validate a trading strategy.

## Historical Quote and Event Integration

The replay CLI accepts paired `--event-scan` / `--event-scan-sha256` for original-reference integrity auditing. Adding paired `--quote-bundle` / `--quote-bundle-sha256` also invokes the existing quote-session validator, ModelValidity and PriceBridge contracts. All quote/event arguments are required together for bridge integration. This is a retained-observation replay, not reconstructed historical decision or execution acceptance.

The application verifies both the event-scan envelope and every original reference. Missing or changed originals produce NOT_READY and prevent ModelValidity/PriceBridge evaluation. A top-level hash alone is insufficient. Earlier cutoffs cannot see a later-captured quote or later-produced valuation; rows retain separate quote and valuation observation states. The original valuation is never overwritten by price or failed event coverage. Even an arithmetic bridge cannot approve research, portfolio guidance or orders.

Real-input evidence: `runtime/historical-bridge-time-verified-20261001/result.json` and `report.md`. The 600887 September 22 quote passes its existing dual-provider close check, but was captured September 23. The retained valuation was produced October 1. The event index original has a hash mismatch against its sealed scan reference, so no bridge is admitted. This is an identified integrity gap, not completed historical strategy validation. Do not alter the sealed reference to match the changed file.

Next substantive dependency: obtain or independently reconstruct a separately versioned, source-complete historical event package and an explicitly retrospective valuation/rule basis before historical decision/execution integration. An independent reconstruction must preserve the failed old package and cannot claim original historical capture, preregistration or strict PIT approval.

### Exact Original Recovery

An explicit repeated `--recovered-event-original ID=PATH` can locate a misplaced original without rewriting the sealed scan. The recovered file must match the scan's original SHA-256 exactly; an unknown ID, duplicate binding, out-of-root path or different content fails closed. The receipt records the failed original-path status alongside the recovered path and verified hash. This is content-addressed recovery, not a new source or research approval.

The actual sealed index bytes were found at `runtime/company-research/m1-event-scans/20260923T050735Z/600887/cninfo-index.json`, hash `f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93c9f383349388bbc2d815ceea`. No original file was moved or overwritten. `runtime/historical-bridge-recovered-original-20261001/` demonstrates quote validation plus existing model/bridge arithmetic after result observation. Earlier cutoffs still cannot see the later valuation. Pre-model disclosure review remains outstanding, all decisions remain NOT_READY and this does not establish current advice, contemporaneous rules, historical execution or strict PIT.

### Source-Readable Event Packet

Add `--event-source-pages` with the pinned event arguments to extract physical-page PDF text through the existing PDFium adapter. The application requires all original evidence to pass integrity, checks each announcement binding against the audited scan and rehashes each PDF before and after extraction. A failed scan produces NOT_READY without extracting misleading text. Full pages are retained in JSON; the readable report shows bounded excerpts and pending impact questions.

This packet never signs `EventMaterialityDecision`, marks model inputs incorporated, changes valuation assumptions or emits trades. Empty text requires visual review. Actual 19-announcement output and the bounded initial original-source reading are in `runtime/historical-event-source-review-20261001/`. Buyback approval is not execution/cancellation, and guarantee exposure is not automatically a realized loss; both require explicit economic review before model changes.

## Shared Execution Mechanism Integration

The existing virtual-account engine is reused through paired `--execution-scenario` / `--execution-scenario-sha256`. Only `shared-execution-engineering-input-v1` with explicit `SYNTHETIC_ENGINEERING_FIXTURE` scope is admitted here. Capital, prices, proposals and cash events are fixtures, not real company research or personal accounts. Every proposal needs bounded next-session terms; no live approval is accepted. Every journal row, virtual fill and account snapshot carries the simulation-only marker. No new trading thresholds are introduced.

The existing dated statutory fee calculator is used only inside its frozen 2015-2025 span. The current legacy next-session execution contract is 600519-specific and its separate fee review covers only one 2026 session: neither is silently generalized to 600887 or September 2026. Broker-invoice commission and dividend tax remain unvalidated. Real 2026 execution needs separately dated fee, suspension, price-limit and liquidity evidence, plus admitted retrospective research/decision inputs.

Actual fixture replay: `runtime/shared-execution-scenario-20261001/input.json`, `result.json`, `report.md`. It runs entry/add/hold/reduce/exit proposals, next-session fills, fees/slippage, dividend entitlement/payment and a blocked suspension-session exit. This proves shared execution plumbing, not actual historical decisions or strategy returns; `historical_execution_validated=false`, `strict_pit_admitted=false`, `action=no_order` remain mandatory.

## Conditional Price-Implied Terminal ROE

`--reverse-equity-expectations` uses paired arithmetic and verified quote inputs in the same replay CLI. It replays the pinned existing arithmetic first, then inverts only terminal ROE using the existing residual-income formula and reconciles the result through the original forward model. No Bear/Base/Bull, forecast ROE, retention, growth or cost assumptions are modified. The inverse cannot approve a model or decision; results are a separately scoped retrospective comparison, not backdated observations or contemporaneous expectations.

Actual 600887 inputs in `runtime/shared-reverse-equity-expectations-20261001/` imply terminal ROE about 23.7%-28.9% for the September 22 price of CNY26.77, conditional on each pinned scenario's other assumptions. This is not evidence of overvaluation: different discount rates, reinvestment, growth, capital allocation or an inadequate model could explain the difference. Event review, forecast justification and model admission remain outstanding. Full precision is retained for arithmetic reconciliation; the readable report rounds display values.

### Company-Card Projection

The historical preview CLI supports pinned `--expectations-replay` / `--expectations-replay-sha256`. Its loader rehashes the parent replay, follows explicit original workbench/arithmetic/quote bindings and recomputes the inverse before comparing every semantic output. Only the actual artifact creation timestamp is excluded from recomputation equality. Old expectations without those source bindings are not promoted automatically.

The read model appends historical quote date, conditional implied terminal ROE and interpretation limits to existing company review rows and an audit reference. It does not replace current price, valuation scenarios, model/decision gates or portfolio. An explicit `--presentation-as-of` sets the observation date of this newly prepared historical presentation; original fact and quote dates remain unchanged. It cannot backdate the base presentation or exceed generation date.

`--read-model-only` with a new runtime JSON output prepares the exact projection without exporting or publishing Excel. Actual source-bound inverse and company-card data are in `runtime/shared-reverse-equity-source-bound-20261001/` and `runtime/shared-company-expectations-card-20261001/`. Workbook authoring dependency `@oai/artifact-tool` is currently absent from the configured workspace bundle; no alternative user workbook or unverified canonical publication was made. Source-bound read-model engineering continues independently of that export dependency.

## Disclosed Metric Row Review

Paired `--metric-transcription` / `--metric-transcription-sha256` binds an explicitly transcribed report row to an original source already verified in the workbench. The application verifies the exact original path/hash/URL, physical page, unique normalized excerpt, declared period/unit context and numeric column correspondence. It rehashes the source after extraction and never approves FinancialFacts or model assumptions.

The actual 600887 annual-report review in `runtime/yili-reported-roe-readable-20261001/` verifies twelve values across 2023-2025: reported weighted ROE, recurring weighted ROE, parent profit and operating cash flow. These are comparative figures reviewed from the later 2025 report, not historically available facts on the original 2023/2024 dates. Weighted historical ROE cannot silently replace opening-book forecast ROE, and CFO cannot replace FCF. The readable research note identifies the assumption gap without changing scenarios or creating decisions.

### Consolidated Cash Capex Proxy

`--reported-cash-proxy` requires pinned transcriptions of consolidated CNY CFO and cash capex from the same original and financial period. The row reviewer can bind an adjacent preceding statement-header page for a continuation row; parent-company and consolidated scope are explicit and cannot be mixed. Missing paired facts return NOT_ASSESSABLE rather than substituting zero capex.

The domain calculates only a descriptive CFO-minus-cash-capex residual. It explicitly denies FCFF, FCFE, maintenance-capex identification and distributable-cash proof. The application cannot admit financial quality, dividend sustainability or valuation from this residual. Actual 600887 evidence in `runtime/yili-cash-capex-review-20261001/` gives CNY11,307,276,333.64 for 2025 and CNY17,761,422,072.42 for 2024. Working capital, necessary investment, financial-subsidiary flows, acquisitions and shareholder cash claims remain review dependencies.
### 披露财务解释与单公司卡片集成（2026-10-01）

`scripts/current/build_product_workbench_candidate.py` 支持重复的
`--metric-transcription PATH SHA256`，与已有 workbench、expectations 和
`--read-model-only --read-model-report` 同时使用。每个输入重新核验原 PDF、
披露行、单位、报告期、物理页及报表范围；不信任缓存的数字复核结果。
只有明确合并现金流量表的 CFO 与现金资本开支配对后才计算描述性余额。
领域计算不在 presentation 内进行；presentation 仅展示结果和原件入口。
不会修改 Financial Gate、估值、PriceBridge、建议或仓位。

实际产品产物位于 `runtime/shared-financial-company-card-linked-20261001/`；包含
FY2023–2025 已披露利润、ROE、CFO，FY2024–2025 合并现金资本开支和
条件性历史价格反向估值。后期报告比较数不代表原年份当时可得；现金余额
不是 FCFF、FCFE 或可分红现金。当前行情、正式模型批准、事件有效性与
个性化仓位仍未准入。该路径不写正式 Excel，不绕过发布工具和保护规则。

### 公告原件接入同一公司卡（2026-10-01）

同一入口支持 `--event-scan PATH SHA256`，以及重复的
`--recovered-event-original REFERENCE_ID PATH`。后者只允许原封存 Hash
相同的原件恢复，不修改历史引用。应用重新核验索引、公告 PDF 和提取前后
Hash，再生成来源包；presentation 只展示日期、标题、原件 URL/Hash 和
待判断问题，不能批准重大性或 ModelValidity。原件核验失败时保留失败状态，
不展示可能被变更的公告内容。历史区间不代表当前跨渠道扫描覆盖。

`runtime/shared-company-evidence-closure-20261001/company-card.md` 将伊利
19 份历史公告与财务事实、现金解释、反向估值和原研究门禁集成到一份卡片。
回购提案与实施、担保额度与损失、现金支出与可分红现金仍须分别判断。
当前模型、正式建议、真实历史策略和个性化组合均不因此准入。

本轮实际依赖图：

| 节点 | 已有实现及产物 | 剩余依赖 | 可独立继续 |
| --- | --- | --- | --- |
| 共享研究输入 | workbench 原件重哈希、原 ResearchCase、估值算术 | 正式研究和模型假设批准 | 是，来源绑定解释 |
| 历史价格与事件 | quote 转换、历史 bridge、event_source_review；19 原件 | 人工影响判断、模型纳入证明、当前扫描 | 是，历史来源核验；不批准当前建议 |
| 公司产品数据包 | existing research、conditional expectations、reported financials、company events 合并 | 当前可用模型及事件门 | 是，共享研究可读输出 |
| 历史执行 | execution_scenario 复用虚拟账户 | 真实、可得时点一致的研究决策输入 | 是，输入核验；模拟不计真实策略 |
| 正式 Excel | 受保护 publisher、原件 Hash guard、视觉审核链 | 指定导出工具可用或明确替代授权 | 是，非 Excel 输出；不绕过发布要求 |

下一实质依赖不是再增加卡片字段，而是核验历史研究决策的完整输入合同：
事实、假设、事件判断、行情与规则版本的可得时间能否共同支持一个真实区间。
已有条件性结果和模拟执行分别保留，不相互冒充准入。

### 真实历史决策输入衔接（2026-10-01）

回放入口增加 `--decision-input-review`，须同时提供财务重建和历史桥接的
全部来源绑定。应用按相同 workbench Hash、公司和精确截止时点连接两者，
形成每个时点的公开字段、保留行情/估值观察状态、桥接算术和缺项。
当前版本是输入可行性审查，不批准策略、订单或收益。历史重建可另行冻结
研究性规则与假设，不必伪造历史预登记；严格当时运行证明仍为另一种主张。
实际伊利三时点产物为 `runtime/real-historical-decision-input-bound-20261001/`。
9 月 22 日公开财务基础已经存在，但保留行情与估值都在之后取得；10 月 1 日
能观察保留结果也仍不能证明历史决策门、事件影响和执行输入全部通过。

### CFO 变化与现金质量解释（2026-10-01）

`--cash-change-periods CURRENT PRIOR` 配合已验证的 `cash_bridge_*`
披露行，在回放入口和产品入口生成来源绑定的合并经营现金流变化桥接。
必须完整提供八项收付款、流入流出小计及 CFO；不把空行推定为零。
每期和变动贡献均精确对账，不同来源、范围、币种或缺项失败关闭。
该有限组件合同不自动适用于银行/保险或有额外非空经营项目的公司。

实际伊利来源为 FY2025 年报物理页 89；22 个披露数字重新核验。
2025 CFO 比 2024 少 7,395,819,903.06 元：销售收款少 4,875,858,216.39 元，
其他经营收款少 1,185,685,801.42 元，其余六项贡献合计补足差额。
不能把销售回款减少等同于收入下降，也不能仅凭对账判定一次性或持续性。
共享产品产物为 `runtime/shared-cash-quality-company-card-20261001/`，
保留财报、现金资本开支、反向估值、19 份公告及所有原门禁；不写原 Excel。
预测、现金可持续性、分红覆盖和投资建议均未由此批准。

### 历史分红生命周期集成（2026-10-01）

产品入口支持 `--dividend-package PATH SHA256`。使用现有 typed distribution
转换和全部来源 Hash 核验，不再创建另一套分红领域模型。只提取来源绑定的
生命周期记录；显式丢弃包内旧行情收益率、容量和持续性结论。展示时点是
本次核验时间，不将历史 known_at 当成严格 PIT 证明；不把实施公告当成
用户到账记录，不将提案、批准和实施重复累加。

实际产物 `runtime/shared-dividend-company-reviewed-20261001/` 复用现有伊利包，
保留三条已实施披露记录、来源路径/Hash、unknown 分类及原包待核验事项，
同时保留现金流变化、资本开支、条件性反向估值和历史公告。包内原状态和
措辞是历史研究记录，不自动成为当前政策批准或未来现金预测。
正常化股息、当前股息率、法人可分配现金、严格 PIT 和决策仍未准入；
原 Excel、调度器、数据库和服务器不变。

### 来源冻结的单命令复现（2026-10-01）

`--research-recipe PATH SHA256` 将基础快照、共享 workbench、反向估值、
财务抄录、现金流桥接、事件扫描、精确原件恢复及股息包组织为一个明确配方。
应用层先验证配方范围、公司、全部直接输入 Hash、重复项与恢复依赖；
再通过现有源核验及领域计算链生成公司卡。不能混入单项覆盖参数，不能
通过配方出版 Excel、修改账户或授权交易；仅限 read-model-only。

实际配方 `runtime/shared-company-recipe-20261001/recipe.json` 与逐参数运行
生成的完整 snapshot 逐项相等，所有领域数值与门禁不变。复现命令：

```powershell
$recipe = 'runtime/shared-company-recipe-20261001/recipe.json'
$hash = (Get-FileHash $recipe).Hash.ToLower()
py -3 scripts/current/build_product_workbench_candidate.py --historical-preview --read-model-only --research-recipe $recipe $hash --output runtime/new-recipe-run/read-model.json --read-model-report runtime/new-recipe-run/company-card.md
```

必须从项目根运行且输出目录未被使用。配方与原来源只读保留；输出是一次
新的观察核验，不回填旧时点，也不因此证明历史策略有效或实盘就绪。

### 用户阅读顺序（2026-10-01）

Markdown 公司卡先呈现情景估值、论点、回报来源、最强反证、论点削弱条件、
不能作为买入依据的门禁和现金/股息摘要，再展示详细决策过程、财务明细、
公告及分红原件和审计入口。摘要不新增分析、不删除缺口；完整原始字段和值
仍保留在后续明细。原件路径/Hash 与长英文历史包缺项不占用股息快速摘要。
实际输出 `runtime/shared-readable-company-final-20261001/` 与配方基线 snapshot
逐项相同，仅可读报告的编排改变。此为非 Excel 可读输出，不代替 WPS 验收。

### 估值假设与构成透明化（2026-10-01）

已验证的 expectations 来源包含冻结 arithmetic 输入，应用通过现有模型
和原件核验重新计算估值构成，不修改情景。公司卡显示五年 ROE 路径、
资本成本、留存、终局 ROE/增长，以及账面权益、显式期和终值剩余收益
现值的每股贡献。驱动解释本身不需要市场价格；当前产品入口从已有
expectations 的 arithmetic 绑定取得它，不让行情反向更改内在价值。
剩余收益终值可能为负或零，这不同于终局公司价值为负或零；模型股息
代数对账不证明实际可分红现金。没有新增预测批准或严格 PIT 准入。
## Shared stopped-case research report

To attach an existing stopped-case result to the same company card, the historical
read-model builder accepts repeatable `--research-readiness PATH SHA256` with
`--read-model-only`. It rechecks both result bytes and the referenced current ledger,
compares the registered company questions exactly, and adds source-bound questions
to `decision_review`. A matching existing company card is required; no company,
decision, valuation, price or position is created. Current Excel publication is not
enabled by this argument. It cannot override a recipe's inputs.

The generic current-workbench CLI also supports readable evidence-stop output:

```powershell
py -3 scripts/current/build_current_workbench.py --symbol 000333 --output runtime/research-readiness-example/result.json --report runtime/research-readiness-example/research-readiness.md
```

Use a new output directory per run. This path does not rerun stopped research, consume a reopening request, approve valuation, create position guidance, or write Excel. It preserves the ledger hash, original questions, periods, reviewed evidence IDs and exact reopen conditions. Missing valuation/price results remain null rather than becoming a crash or a fabricated valuation. Existing-result mode still supports its original pinned-manifest report. The readiness report is not an admitted investment recommendation or proof of historical evidence availability.
