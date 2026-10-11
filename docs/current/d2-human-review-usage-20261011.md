# 两家公司 v5 人工研究审核使用说明

本说明对应2026-10-11实际准备的600519五组、600887四组回应，按当前 `research_reviews.py` 与 `run_company_research.py` 合同编写。现状是待审，不是已批准；`action=no_order`。研究意见、整模型G3、公告材料性和价格准入是不同对象，不能用一次勾选替代。

## 先看哪份材料、填哪份文件

先读两家实际候选目录的 `candidate-review.md`，查看每组支持、反证和具体用途；详细参数及条件结果见同目录 `valuation-proposal.json`。茅台七公告的精简研究见 [七公告审核材料](D:/GPTProject/value-investment/docs/current/600519-event-review-closure-20261011.md)，直营、产品盈利、维护成本的反证见 [operating-countercases.json](D:/GPTProject/value-investment/runtime/d2-600519-event-review-closure-20261011-v1/operating-countercases.json)。这些材料不是审核人的答案。

实际可填写的文件是：

- [600519-editable-response.json](D:/GPTProject/value-investment/runtime/d2-human-review-inputs-20261011-v1/600519-editable-response.json)：绑定 `runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/pending-candidate/candidate.json`，候选SHA256 `56554578776ab8eb7c1269ef2424df58a9cb90673f05c9370f2f792d929c1db2`；精确估值artifact SHA256 `71c8c8063285ea016ca0574231ecf744529b66cbfddeb692c5620a89c6ac297c`。
- [600887-editable-response.json](D:/GPTProject/value-investment/runtime/d2-human-review-inputs-20261011-v1/600887-editable-response.json)：绑定 `runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/candidate.json`，候选SHA256 `410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299`；精确估值artifact SHA256 `876bfdf7829c1e8225e3338bd090dd102965ebce8049edc2628bae90c0264b68`。

两份表的 `model_context` 还分别绑定ResearchCase、Facts、AssumptionSet、descriptor、模型和研究日。填写时不要改变这些绑定、`valuation_artifact_sha256`、证券代码、组ID、组顺序或 `field_paths`，也不要在候选本身填写批准。

本说明读到的空白回应文件SHA256分别为 `498b66cba98734eb85b31aa448659d983ec37b09c0b8be0d218fc28b46dc8e7e`、`fb1c2bf3f1fcaa99f559ec3f1a21e1c70b0390ccc4bdd4908a345cf26f4f1c39`。这是空白表版本标识；填写后字节Hash改变是正常的，不能拿空白表Hash当签名回应Hash。不要修改已消费的签名原件或历史收据。

## 九组实际问题

以下ID与实际准备JSON一致。支持和反证来自候选 `review_groups`，后果和范围帮助审核者写明用途，均不是预填决定。

| 公司 / 组ID | 要判断的具体用途 | 支持与最强反证 | 拒绝或证据不足意味着什么 |
| --- | --- | --- | --- |
| 600519 / EARNINGS | 历史扣非TTM代理能否用于低置信条件研究，而非已识别正常化盈利 | 已绑定813.6706767744亿元及归母桥；正常化调整、金融尾部损失和维护投入上界未知 | 否定代理则重审逐年盈利/ROE；证据不足要列具体调整或现金/投入缺口，不能机械加回损失 |
| 600519 / DURATION | B十年持续、后五年全资本ROE衰减能否用于此15年路径 | 核心产品毛利及品牌渠道支持持续性研究；扣非/毛利走弱，十年不是可观测寿命 | 拒绝须重审期限或路径；缺证据须指出持续/衰减机制，不凭较高估值选择A/B/C |
| 600519 / DISTRIBUTION | 25%留存、75%分配仅作模型条件是否可接受 | 共享递推未重复加入现金；母公司现金、上划、认缴时点及维护/扩产未充分识别 | 资金限制重大则重审分配/留存或暂停用途；接受不等于保证可收到现金 |
| 600519 / COST_TERMINAL | 已绑定权益成本与终端条件能否用于该版本 | 国债、beta、ERP及中央成本约6.7572%；代理异步且端点不是完整风险区间 | 拒绝须重审成本/终端；证据不足不能将条件端点说成公司全部风险范围 |
| 600519 / EVENT_MODEL | 精确候选是否具备进入正式事件/模型审查的研究准备 | 实际共享输出和上下文可核验；未继承公告批准、完整扫描或G3 | 本组接受也不替代七公告逐项材料性；窗口与valid_from差异仍须合法处理，不能改日期制造有效 |
| 600887 / EARNINGS_IMPAIRMENT | 扣非代理与盈利恢复用途是否合理，减值如何保留经济损失 | 已核TTM/H1进入候选；H1扣非同比-20.25%，非现金减值仍可能损失资本 | 否定代理则暂停或重审路径；不自动加回商誉/存货损失，不承诺恢复 |
| 600887 / CASH_FINANCING | CFO恢复能否支持假定分配，集团/母公司和外部融资如何区分 | 已核CFO与权益桥；付款基数影响恢复，内部抵销不消灭外部银行债务 | 重审融资与分配约束；80%至90%条件分配不证明1.22元底线或持续现金能力 |
| 600887 / CAPITAL_DURATION | 暂用权益成本与有限优势期是否有足够公司依据 | 复用1+3和3+5方案及已核资本/股数；8%至10%成本仍暂定，未分开两个资本池 | 短方案也非正式公平价值；中方案须恢复机制，证据不足不按较高结果选方案 |
| 600887 / EVENT_MODEL | 新财务事实和精确版本是否支持正式模型审查 | FY/H1官方身份、Hash及实际消费可核验；33公告材料性、G3及价格未准入 | 仅确认研究准备范围，另审33公告；不生成订单或私人仓位 |

字段范围原样保留：茅台EARNINGS对应 `facts.operating_inputs/research_case.financial_summary`；DURATION对应 `facts.scenario_inputs/assumption_bindings`；DISTRIBUTION对应 `facts.scenario_inputs/source_contract.distribution_input_status`；COST_TERMINAL对应 `facts.scenario_inputs/facts.valuation_timing`；EVENT_MODEL对应 `model_validity_input/source_contract/dependencies.model_version`。

伊利EARNINGS_IMPAIRMENT对应 `research_case.financial_summary/facts.scenario_inputs`；CASH_FINANCING对应 `facts.scenario_inputs/source_contract.distribution_input_status`；CAPITAL_DURATION对应 `facts.operating_inputs/facts.scenario_inputs/assumption_bindings`；EVENT_MODEL对应 `source_contract/model_validity_input`。字段范围只说明受审对象，不表示该组通过后这些字段全部已获无限用途批准。

## 怎样填写而不扩大批准

每组填写 `response`、`response_reason`、`confirmed_scope`。允许 `VERIFIED`、`REJECTED`、`INSUFFICIENT`；尚未作判断可留null，但该组仍形成PENDING阻塞。任何非null回答都必须附非空理由和明确范围，包括拒绝/证据不足时指出哪项用途不接受或哪项事实还不能判断。

`VERIFIED`确认的是写在 `confirmed_scope` 的具体用途。例如只有审核者真正同意时，才可写“仅确认扣非TTM可作此精确v5低置信条件研究代理，未确认跨周期正常化盈利和十五年增长”。这是措辞示例，不是系统建议勾选或现存批准。接受披露事实不等于接受预测，也不等于整模型或买入批准。

`REJECTED`记录不接受的用途和需返工的假设；`INSUFFICIENT`记录可判定边界及具体缺证据。两者都会保留相应组阻塞。填写本身不自动修改盈利、留存、期限或折现率；任何改数应另建候选，不能修改旧候选来维持审核有效。

顶层 `reviewer_id` 必须是实际获授权人的身份；`reviewed_at` 是真实带时区时间，须不早于候选workbench生成时点、不晚于当前时点，且在授权有效期内。未取得真实身份与决定时保持null。Agent可以协助整理证据，不能充当审核者、代填决定、生成其私钥或冒签。

`whole_model_approval` 可以保持null；即使九组或单家公司各组全部VERIFIED，仍有 `whole_model_review_missing`。整模型需要独立的既有 `post-m1-human-research-approval-v1` 对象，精确绑定估值artifact、ResearchCase、Facts和AssumptionSet及真实审核者/时间；不能填一个true来替代。

当前回应链的整模型对象要求 `reviewer_type=human_research_lead`、身份/证券/profile/审核时间与回应一致，并需额外 `human_whole_model` 权限。已有整模型决定包括PENDING_HUMAN_REVIEW、REJECTED_NEEDS_REWORK、APPROVED_CONDITIONAL_LOW_CONFIDENCE、APPROVED_RESEARCH_ONLY、SUPERSEDED；不要把单组VERIFIED填进整模型decision。`price_assessment_eligible` 必须是真实布尔判断，亦不等于PriceBridge已获准入。只要有组PENDING、REJECTED或INSUFFICIENT，链拒绝同时提交获批整模型。

## 身份与签名前置条件

当前 [authorization-trust-roots-v1.json](D:/GPTProject/value-investment/config/authorization-trust-roots-v1.json) 的 `pinned_trust_root_sha256=[]`，没有已注册可信身份。可以准备或填写研究意见，当前不能合法消费正式签名回应；自带一个新公钥不能自我授权。本说明不修改registry，不注册身份，不生成或索取私钥，也不使用测试hook绕过限制。

合法签名前须由真实审核者通过既有显式、经审查的注册流程取得被固定指纹的trust root。其schema为 `research-review-transport-trust-root-v1`，字段严格为 `schema_version/reviewer_id/public_key/scopes/symbols/valid_from/valid_until`；`public_key` 是Ed25519公钥的hex，组审核须有 `human_group_research`，整模型还需 `human_whole_model`，symbols须含对应证券。trust root的规范化指纹要在固定registry中，不能用CLI参数替换registry。

签名文件严格是 `{"payload": 完整填写回应, "signature": Ed25519签名hex}`。签名对象是 `REVIEW_RESPONSE_PURPOSE + canonical_contract_payload(payload).encode('utf-8')`，其中purpose为Python字节字面量 `b'value-investment/pending-research-response/v1\x00'`，末尾是真实零字节。不能对随意缩进后的JSON文件字节签名。公钥、权限、有效期和真实审核时间均须验证；私钥由审核者本人控制。本CLI没有注册或签名flag，不应虚构一条自动签名命令。

## CLI：准备与消费

在显式PowerShell 7 `C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe` 中运行；UTF-8初始化和项目目录如下。已有两份editable response可直接使用，下面prepare命令仅用于确需新空白表时，输出路径必须未存在，不覆盖现有表。

```powershell
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
Set-Location D:/GPTProject/value-investment

python -B scripts/current/run_company_research.py --symbol 600519 --pending-review-candidate runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/pending-candidate/candidate.json --pending-review-candidate-sha256 56554578776ab8eb7c1269ef2424df58a9cb90673f05c9370f2f792d929c1db2 --prepare-review-response --output runtime/d2-human-review-inputs-20261011-v1/600519-editable-response-new.json

python -B scripts/current/run_company_research.py --symbol 600887 --pending-review-candidate runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/candidate.json --pending-review-candidate-sha256 410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299 --prepare-review-response --output runtime/d2-human-review-inputs-20261011-v1/600887-editable-response-new.json
```

prepare返回 `EDITABLE_RESPONSE_PREPARED_NOT_APPROVED`；不重跑估值，也不产生人类审核。prepare模式禁止带签名/trust/history参数。两种审核模式都不能混入 `--package`、行情、事件、普通 `--research-reviews`、schedule或既有manifest等研究运行参数。

下面是消费命令模板，**只有真实身份注册和签名完成后才执行**。`SIGNED_RESPONSE_PATH`、`PINNED_TRUST_ROOT_PATH`、`SIGNED_RESPONSE_SHA256`、`TRUST_ROOT_FILE_SHA256`和 `NEW_OUTPUT_DIRECTORY` 是需替换的占位符，不是已存在资产或已获批身份；两个SHA参数取实际文件字节Hash，registry内指纹则按trust root规范化内容计算。

```powershell
python -B scripts/current/run_company_research.py --symbol 600519 --pending-review-candidate runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/pending-candidate/candidate.json --pending-review-candidate-sha256 56554578776ab8eb7c1269ef2424df58a9cb90673f05c9370f2f792d929c1db2 --signed-review-response SIGNED_RESPONSE_PATH --signed-review-response-sha256 SIGNED_RESPONSE_SHA256 --review-trust-root PINNED_TRUST_ROOT_PATH --review-trust-root-sha256 TRUST_ROOT_FILE_SHA256 --output NEW_OUTPUT_DIRECTORY

python -B scripts/current/run_company_research.py --symbol 600887 --pending-review-candidate runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/candidate.json --pending-review-candidate-sha256 410dd4c4fa935bc4ea0b7c596fbdc2a006ab0da4498a11694a7c9868e3520299 --signed-review-response SIGNED_RESPONSE_PATH --signed-review-response-sha256 SIGNED_RESPONSE_SHA256 --review-trust-root PINNED_TRUST_ROOT_PATH --review-trust-root-sha256 TRUST_ROOT_FILE_SHA256 --output NEW_OUTPUT_DIRECTORY
```

消费不带 `--prepare-review-response`。所有文件留在项目root内，output必须是runtime下尚未存在的独立目录。首次回应 `supersedes_response_sha256=null`，不传previous参数。已有已认证消费的回应时，后续必须同时传 `--previous-review-response PREVIOUS_SIGNED_RESPONSE_PATH` 与 `--previous-review-response-sha256 PREVIOUS_SIGNED_RESPONSE_SHA256`，并在payload中填匹配的 `supersedes_response_sha256`；须同审核者、同候选、时间更晚且指向最新认证头。不能回放同一签名或冒称未认证文件为前驱。

## 消费后应检查什么

合法消费产生 `receipt.json` 和追加式认证历史；只有提供真实typed整模型对象时才另出 `human-approval.json` 与 `research-reviews.json`。检查收据中的身份、精确candidate binding、各组scope、blockers及whole_model_review_present，不能只看命令退出成功。重复键、未知字段、改组顺序/范围、Hash漂移、过期权限、未来审核时间、旧回应冲突和签名不符均会拒绝。

消费收据仍明确 `research_admitted=false/event_materiality_approved=false/price_admitted=false/position_guidance=null`，不改已登记当前case。它认证和记录审核输入，不自动将公司升级为有效研究、行情准入或交易建议。单组拒绝会进入收据阻塞；后续研究接线与重算由Root按既有合同完成，不将新收据当已改变当前产品状态。

公告材料性另需 `shared-research-review-inputs-v2` 的模型上下文绑定、精确完整EventScan和每ID原件决定。茅台仍保留候选valid_from=2026-10-11与scan validity_from=2026-07-01的差异；不能改日期、清空events或删阻塞绕过检查。两家公司新候选或重要假设变更后，旧回应不因同股票代码而继承，须重新核验并按新版本审阅。

本说明只新增使用文档，不填写上述九组、不制造签名/身份/批准，也不修改候选、Excel、registry或policy。
