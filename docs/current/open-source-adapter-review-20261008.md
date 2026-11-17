# 当前 Goal 开源适配 sidecar 有界审查（2026-10-08）

## 1. 裁决与边界

本轮完成五库的静态源码审查和 **D1 因子 / D5 热点的最小可关闭接口设计**，不是适配器实现、策略验证或阶段验收。当前优先级仍为 D2 单公司纵向闭环；D1 保持 `INTERFACE_ONLY_NOT_EXPANDED`，D5 仍受独立 sleeve、value gate、PIT、walk-forward/OOS、成本和真实 Shadow 门约束，`action=no_order`。

| 库（附录代号） | 可借鉴部分 | 本轮适配裁决 |
| --- | --- | --- |
| lonelydancer88/a-share-value-investing-system（V） | 因子拆分、行业内标准化、公告日过滤与重述测试 | D1 方法对照；许可证 UNKNOWN，暂不复制、导入或运行其代码；不继承总分、DCF、组合和交易建议 |
| Danson-dan/stockanalysis（S） | 广度、涨跌停、行情降级与 stale 标记 | D5 缺陷/字段对照；许可证 UNKNOWN，暂不复制、导入或运行；“全市场”降级后实际上是热门池 |
| QYQSDTC/Money-Come-Terminal（M） | 拆分的情绪分项函数 | MIT 代码可作为后续独立复核对象；不采用固定成交量分、中性填补、默认综合权重和直接建议 |
| wenyuanw/a-share-heatmap（H） | 板块加权涨跌、分层展示、数据回退测试 | D5 最接近的观察型候选；仅借鉴小函数/字段合同，不嵌入 Next/React 项目，不把视觉估算或静态回退当真实热点 |
| microsoft/qlib（Q） | 版本化特征表达式、PIT 算子、训练/推断与标签隔离 | MIT 方法/离线基准候选；不装全套、不接入训练/交易框架；实际数据 PIT 与收益有效性仍 UNKNOWN |

**五库均未获本项目正式数据、研究或投资准入。** 热力图/终端不等于热点策略，Qlib 的 ML 特征不等于价值判断，任何仓库的分数不等于本项目 ResearchGate、ModelValidity 或买点。

工作目录：`D:/GPTProject/value-investment`。审查开始 HEAD：`5ba570920f588f4660e91439dedb5ab6f32ff1fe`。工作树已有业务、测试及 D2/D5 文档改动，均按既有工作继承；它们不是本轮成果。唯一正式写入文件为本报告；新增公开下载仅进入 `.tmp/open-source-review-20261008`。未修改业务代码、Goal/阶段/状态文件、Excel 或 server，未启动服务、安装依赖、执行外部代码、运行外部测试或提交 Git。

依据已读本仓库 `AGENTS.md`、`docs/current-stage-goal.md`、`docs/execution-status.md`、`docs/data-and-evidence-policy.md`、架构分层文档及 `docs/current/d5-satellite-interface-freeze-20261007.md`；并只读核对现存 `domain/portfolio/sentiment_contracts.py`。该合同明确只接收 `SYNTHETIC_CONTRACT_ONLY`，本设计不能将真实外部观察偷偷转换成现有 `SentimentFeatureSnapshot` 或 `ENTRY_REVIEW`。

## 2. 采样、版本与证据强度

先复用指定缓存。原五份 `repo.json` 是 API 限流错误，`commit.html` 为空，不能证明提交时间或维护健康。版本从缓存 `repo.html` 的结构化 `currentOid` 提取；本轮再获取固定 commit 元数据、树索引和必要 raw 文件。原缓存文件只有按 Git blob SHA-1 与该固定树一致时才复用。

| 代号 | 固定 commit（不自动跟随 main/master） | commit 的 committer 日期（UTC） | 版本/维护可见事实 |
| --- | --- | --- | --- |
| V | `c86dd7e76e8a33382bcedd2876afcfa5a7468771` | 2026-09-11 16:01:06Z | 该提交记录 CI 红灯根因和 top1 第四次翻转；缓存侧栏 0 release |
| S | `66fc319482e33f29cfdc1999b6c36742738ab204` | 2026-05-26 07:19:25Z | 提交为 AIstock v2.0；frontend package 是 1.0.0；缓存侧栏 0 release |
| M | `fa96fca4fbc03f6e63fb0784c07ac61658d491d7` | 2026-03-13 15:07:56Z | package 2.0.0；缓存侧栏 9 releases；有多平台构建 workflow |
| H | `3bdb3cad4673c2e61576568cca4c4f910df896e1` | 2026-09-30 16:29:14Z | 提交为自动刷新股票池；package 0.1.0；有测试/类型/构建 CI |
| Q | `be725493eb1a6bbb42bf11b37aa7669f59610ff1` | 2026-09-16 06:56:07Z | 提交固定 Actions 完整 SHA；package 版本由 setuptools-scm 动态生成；缓存侧栏 23 releases |

提交可通过 `https://github.com/<owner>/<repo>/commit/<commit>` 定位；下文证据链接均固定 commit。上述日期是 **代码提交日期**，不是数据日期、当日最新 HEAD 保证或未来维护承诺。未审阅历史提交序列、issue 响应、安全公告或 Actions 实际结果：持续维护能力、最后绿灯、安全漏洞状态、release 标签与 commit 的对应均为 **UNKNOWN**。自动数据更新提交也不能证明算法有人维护。

本轮新下载 49 个 HTTP 响应，共 **2,034,645 bytes**：15 份 commit/树元数据、34 个源码/配置文件；另外复用 9 个已有文件。下载并发上限 4、单请求 20 秒、单响应 2 MiB，无重试；未 clone 或下载巨型压缩包、行情数据库、模型权重。树索引仅用于选入口及核查许可证/测试文件是否存在，未逐文件遍历 Qlib 或其他库源码。

43 个采样文件全部通过 Git blob SHA-1 比对，并计算完整 SHA-256（附录）。为消除按 commit 查询树时响应 SHA 与真实 tree ID 的歧义，另按 commit 元数据中的真实 root tree SHA 校对；五库 root tree SHA 均匹配，索引 path/blob 项一致，`truncated=false`。这证明采样字节与固定源码树相符，**不证明算法经济正确、源数据授权或历史可用性**。

## 3. V：a-share-value-investing-system

入口 `vi_system/cli.py` 的 `cmd_screen`（L100）及 `cmd_demo`（L52）分别走筛查和 synthetic 通道；另有 backtest/portfolio 命令，但不在本项目适配范围。

代表算法：[factors.py](https://github.com/lonelydancer88/a-share-value-investing-system/blob/c86dd7e76e8a33382bcedd2876afcfa5a7468771/vi_system/pipeline/factors.py#L25)。实际逻辑是组内 mean/std（ddof=0）z-score，clip 到默认 ±3；行业样本少于默认 5 时回退全局 z；每柱按配置指标求平均，再作默认 z>=0 AND 门和默认 0.4/0.4/0.2 加权。行业名称本身不证明是历史申万二级；该 Tushare fetcher 只读取 stock_basic 的 industry。

主要风险：

- `_zscore_within` L37 将 NaN 填 0；没有任何可用指标的支柱也是 0；默认 AND 门允许 0 通过。虽记录 `*_valid`，已审 score 函数没有依该计数实现注释所称的覆盖率降权。缺失可能成为中性可过门状态，不能继承。
- [metrics.py](https://github.com/lonelydancer88/a-share-value-investing-system/blob/c86dd7e76e8a33382bcedd2876afcfa5a7468771/vi_system/pipeline/metrics.py#L247) 将缺失/非正利息费用映射到覆盖倍数 99；部分 payout 项缺失填 0。L288 所谓 `profit_growth_5y` 实际是毛利/总资产 GPA 的几何变化率，且固定指数 0.2；不能当净利润增长或未经期距校验的五年 CAGR。
- [store.py](https://github.com/lonelydancer88/a-share-value-investing-system/blob/c86dd7e76e8a33382bcedd2876afcfa5a7468771/vi_system/data/store.py#L123) 的 `facts_asof` 确实先过滤 announce_date<=asof，再按 code/field/period 取最新公告版本。存在 PIT 查询机制，但只有日期，没有本项目要求的可用时刻、公告原件 hash/定位及逐事实输入链；保存同 key 同公告日会保留最后写入值。
- [fetcher.py](https://github.com/lonelydancer88/a-share-value-investing-system/blob/c86dd7e76e8a33382bcedd2876afcfa5a7468771/vi_system/data/fetcher.py#L148) 在抓取报表时 L174 按 end_date 去重，可能在进入 Store 前丢掉重述版本；L210 用质押期末+30 天构造 announce_date，属于推算，不能认作严格 PIT。L81 只抓当前上市 `list_status=L`，历史退市/行业变迁覆盖不足；L124 raw 缺失时用复权 close 代替，存在价格口径混淆风险。另一个 WeStock 实现未采样，其历史质量为 UNKNOWN，不由 README 代证。

测试：[correctness_test.py](https://github.com/lonelydancer88/a-share-value-investing-system/blob/c86dd7e76e8a33382bcedd2876afcfa5a7468771/tests/correctness_test.py#L87) 用原版100/重述999 fixture 检查公告前空、重述前后选择；L180 有因子测试；L507 真实锚点段落承认 top1 多次更改及快照过拟合。另读 `tests/test_layers.py` 和 CI；CI 调用 smoke/correctness 模块，不代表实际数据公告日、覆盖率或收益有效性获证。本轮未执行，运行结果 UNKNOWN。

依赖：requirements 仅下限锁定 pandas>=2.0、numpy>=1.24、pyarrow>=14.0、pyyaml>=6.0、tabulate>=0.9；Tushare 注释为可选，fetcher 实际需要 token 和安装。无 Python 全量锁文件的证据，环境可复现性不足。树中未发现 LICENSE/COPYING/NOTICE；**许可证和代码复用授权 UNKNOWN**，公开可读不等于获准复制/导入。裁决：仅方法对照，D1 更适合从本项目已核验事实计算少量命名因子，不引入其排名/阈值。

## 4. S：stockanalysis

主要入口 `backend/app/main.py` L220 创建 FastAPI，L334/L337 注册情绪与基本面路由，带生命周期、数据库和缓存耦合；不适合整体作为轻量 sidecar。

代表算法：[sentiment_service.py](https://github.com/Danson-dan/stockanalysis/blob/66fc319482e33f29cfdc1999b6c36742738ab204/backend/app/services/sentiment_service.py#L261)。从50起点叠加涨跌比（±20）、上涨占比（±15）、涨停占比（最高+10）、MA20以上比例（±15），截断0..100。传入的 `limit_ratio` 没被评分函数使用；量能统计也没有进入该总分。

关键反例是 L100：MA20 缺失时以当前 price 替代，price>=price 将其计入均线以上。源码在采样 `stock_api.py` 中未见 MA20 构造，不能把该“趋势”项视为已算真实历史均线。L312 直接生成仓位6-8成/半仓等 advice，没有个人 IPS 和预算证据；任何对照均必须拒绝该输出字段。

数据：[stock_api.py](https://github.com/Danson-dan/stockanalysis/blob/66fc319482e33f29cfdc1999b6c36742738ab204/backend/app/utils/stock_api.py#L1194) 首先读东方财富，成功条件为 >100 条；失败改用约500只热门池的腾讯批次（L1240），不等于完整官方 Universe。基本面 `screen` L42 用实时 PE/PB，股息率等缺失默认0，没有公告版本 cutoff。情绪主函数 L45 标记旧缓存 stale 是优点，但 L119 是本机计算时间，L222 小时内覆盖 Redis 历史点、TTL14天/最多200条，不能作为不可变 PIT 历史档案或历史完整性证明。

依赖：backend requirements 固定 FastAPI 0.115.6、SQLAlchemy 2.0.36、Redis5.2.1、Celery5.4.0、pandas2.2.3/numpy2.2.1 等，但 AKShare/OpenAI/PyYAML 仍下限开放；需 PostgreSQL/Redis/worker 的整体应用负担。frontend 为 Vue/Vite/Ant Design/ECharts，存在 package-lock（仅确认树中路径，未审锁内容）。固定完整树中未找到测试命名路径或 LICENSE/COPYING/NOTICE，frontend 无 test 脚本；CI/实际测试质量与代码复用授权 **UNKNOWN**。“backtest”业务模块不算测试。裁决：不采用代码/成品，仅把字段、降级覆盖和错误放行作为 D5 设计反例。

## 5. M：Money-Come-Terminal

入口 `src/main/index.ts` L41 注册 IPC、创建 Electron 窗口；具体 IPC handler 未扩展审查。代表算法：[sentimentEngine.ts](https://github.com/QYQSDTC/Money-Come-Terminal/blob/fa96fca4fbc03f6e63fb0784c07ac61658d491d7/src/renderer/analysis/sentimentEngine.ts#L102) 汇总涨跌广度25%、涨停15%、跌停15%、指数趋势20%、北向15%、量能10%，输出0..100及热/冷级别。

实际风险：L75 `scoreVolume` 恒为50，尚无历史量能计算；指数/北向缺失也给50，总广度为0时跌停分给100，缺失并不阻止输出综合情绪。没有收益或阈值依据，不能转成本项目热点准入。

数据：[marketData.ts](https://github.com/QYQSDTC/Money-Come-Terminal/blob/fa96fca4fbc03f6e63fb0784c07ac61658d491d7/src/main/market/marketData.ts#L70) 经 TushareClient 查询日行情/指数/北向/融资，token 权限、当前接口可用和数据使用权未验证。L70 通过本机小时和周末回退日期，未用交易所节假日日历/显式上海时区；部分历史窗口从 `new Date()` 而非请求的历史 endDate 倒推。L136 构造失败/无数据时的全0广度默认值；L163 仅300/688走19.5%，其余9.5%，不能涵盖 ST、北交所、新股无涨跌停等规则；L206 按数值大小猜北向单位，不能替代提供者字段合同。

LICENSE 原文 MIT、版权2026 YiQian Qian（完整 hash 附录）；复用实质代码需保留版权和许可。package2.0.0：Electron^28、React^18、axios、klinecharts；有 package-lock 路径但未审锁内容。scripts 没有 test；固定树无测试命名文件。build workflow 是四目标平台构建/打包，不是算法测试，甚至 DMG 校验失败分支可仅 echo；构建成功不能代替数据/策略验证，实际运行结果 UNKNOWN。裁决：仅后续参考小型纯函数与字段分离，避免引入 Electron；本轮不继承分数或默认权重。

## 6. H：a-share-heatmap

主要数据入口：[treemap/route.ts](https://github.com/wenyuanw/a-share-heatmap/blob/3bdb3cad4673c2e61576568cca4c4f910df896e1/src/app/api/heatmap/treemap/route.ts#L17)，校验 market/period/codes 并调用 `getTreemapData`；返回带短缓存/stale-while-revalidate 的观察读模型。

代表算法：[treemap.ts](https://github.com/wenyuanw/a-share-heatmap/blob/3bdb3cad4673c2e61576568cca4c4f910df896e1/src/components/heatmap/treemap.ts#L163) 的 `weightedAverageChange` 用 value 加权涨跌、null跳过、无有效值返回null；`binaryTreemap` L336 用权重排序和平衡分割铺矩形。**后者是显示布局，前者是观察统计，都不是热点预测或持仓规则。**

测试：[treemap.test.ts](https://github.com/wenyuanw/a-share-heatmap/blob/3bdb3cad4673c2e61576568cca4c4f910df896e1/src/components/heatmap/treemap.test.ts#L91) 验证100/300权重、2/4涨幅得到3.5、空值返回null、面积比例/无重叠；`scripts/lib/market-data-sources.test.mjs` 覆盖备用源、无效价格/时间/单位、低覆盖失败、旧日拒绝、90%有效时保留未返回股票旧值等。这些是明确的边界测试，但没有 PIT 历史收益、walk-forward/OOS 或成本测试的证据；未执行，PASS UNKNOWN。

数据风险来自已读 [market-heatmap.ts](https://github.com/wenyuanw/a-share-heatmap/blob/3bdb3cad4673c2e61576568cca4c4f910df896e1/src/lib/market-heatmap.ts#L490)：

- L495 面积权重优先流通市值，再总市值，再 price*1,000,000；L502 用市值和当日涨幅估计 fallback 成交额。UI降级值不能当真实资金/成交量特征。
- L508 构造 hs300/zza500 时使用市值前300/500；不是官方历史指数成分。zza50 有另读 `market-constituents.ts` 的远端/seed/stale 机制，也没有历史成员有效期证明。
- L733/L794/L892 在源行情时间缺失时可使用当前抓取时间。L1993 fallback 可令 changePct=0；L2309 首次请求即返回 bundled fallback；虽然 source 标记 direct/fallback/stale 是优点，不能仅取 updatedAt 或 API 200 判定真实新鲜。
- [market-data-sources.mjs](https://github.com/wenyuanw/a-share-heatmap/blob/3bdb3cad4673c2e61576568cca4c4f910df896e1/scripts/lib/market-data-sources.mjs#L110) 主源东财失败用腾讯；有效覆盖>=90%时保留旧股票/行业映射及缺失行情。存在校验，却可能新旧混合、错过新上市/退市；sidecar 必须按每个成员和每项字段记录日期/coverage，不拿整包最新时间提升旧成员。

LICENSE 原文 MIT（2026 A-Share Heatmap contributors）；package 的 private=true 是发布设置，不抵消许可。依赖 Next16.3.3、React19.2.4、AI SDK、Zod，pnpm11.27.1，树有 pnpm-lock；锁内容未采样。Vitest config 在 node 下覆盖 src test.ts 与 scripts test.mjs；CI 用 Node22、frozen-lockfile、lint/typecheck/test/build，实际绿灯 UNKNOWN。裁决：D5 最小观察字段/加权统计优先候选，必须使用本项目已核验输入；不引入 UI、AI 路径或实时采集大框架。

## 7. Q：Qlib

主要入口 `pyproject.toml` 的 qrun -> `qlib.cli.run:run`；`run.py` 接受 YAML 工作流、路径和模板，最终组织量化任务，不作为本项目通用启动器。

代表算法：[Alpha158DL loader.py](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/contrib/data/loader.py#L149)：ROC_d 实际是 `Ref(close,d)/close`，不是常见 `close/lag(close,d)-1`；MA/STD 分别是历史窗口均值/标准差除当期close，默认窗口5/10/20/30/60。名字相同不表示公式相同，移植必须显式记录方向、窗口、复权和零分母规则，不能把158个技术因子等同价值因子。

PIT：[pit.py](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/data/pit.py#L26) 的 P 算子逐观察日 collapse 报告期序列，未来窗口直接 ValueError；[LocalPITProvider](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/data/data.py#L744) 按 YYYYMMDD 搜索可见修订并读取各期值，代码注释明确非线程安全。机制有证据；日粒度不能证明公告当日开盘前可用，来源date/修订链是否合法仍取决于输入。本轮未下载其真实金融数据或扩大到 collector/二进制读函数，输入来源原件/hash、全历史退市与成员完整性 **UNKNOWN**。

[handler.py](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/contrib/data/handler.py#L89) 将 `Ref(close,-2)/Ref(close,-1)-1` 放在 LABEL0，属于训练目标而非实时特征；不能混入 sidecar 输出。fit_start/end 和 infer/learn 分离是可借鉴合同，仍需本项目验证训练区间不跨 cutoff，并登记窗口 purge/embargo，不能仅相信框架名称。

测试：[test_pit.py](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/tests/test_pit.py#L38) setup 下载样例 CN/PIT 数据、normalize/dump，然后对查询、缺失、Mean/Ref/PRef 等期望表断言；不是纯离线、零依赖 fixture。仅静态阅读，未执行。CI 有跨 Windows/Linux/macOS 与 Python3.8..3.12 的配置、依赖一致性检查及 SHA 固定 Actions，不代表本次运行通过。

LICENSE 原文 Microsoft MIT。依赖不是只装 numpy/pandas：pyproject 包括 mlflow<3.13、Redis/Mongo、LightGBM、gym、cvxpy、Jupyter/pyarrow 等，setup 编译 C++/Cython rolling/expanding；RL另带 Torch/Tianshou。许多运行依赖仍未精确锁定，dev/test与collector也有额外依赖；平台求解器/版本约束说明维护者处理过兼容问题，不是本环境已兼容的证据。裁决：以文献式公式/PIT反例为基准；未来有需求时隔离离线比对，不将完整 qlib 引入本项目依赖或服务。

## 8. 最小 sidecar 设计（仅合同草案）

### 8.1 输入、输出与开关

采用本项目 owned adapter 和本地数据交换，未来落位 `infrastructure/market_data`；Application 做核验/隔离；Domain 只消费已验证 typed 值，不 import 五库、不读取网络或 Excel。无需新常驻 server；首期只读取调用方明确传入的不可变原始快照。此处命名是设计名，不宣称模块已存在。

```text
OpenSourceObservationAdapter.read(request, pinned_inputs) -> ObservationResult
request = {
  contract_version: "open_source_observation/v1",
  channel: "D1_FACTOR" | "D5_HOTSPOT",
  as_of: ISO date, cutoff_at: timezone-aware instant,
  subjects: explicit security_ids or explicit sector membership snapshot,
  feature_ids: small registered allowlist, config_hash: SHA256
}
result = {
  status: DISABLED | LICENSE_UNKNOWN | SOURCE_UNAVAILABLE |
          INSUFFICIENT_EVIDENCE | STALE | QUARANTINED |
          OBSERVATION_ONLY,
  observations: [FeatureObservation], reasons: [reason_code],
  action: "no_order"
}
```

建议配置三个关闭点：总开关 `enabled=false`；分通道 `d1_factor_enabled=false / d5_hotspot_enabled=false`；每个 upstream binding 的 `enabled=false`。默认 `mode=offline_snapshot_only`，没有隐式联网降级、环境探测或自动安装。总/通道/绑定关闭时先返回 DISABLED、observations为空，不读输入、不动态 import、不启动 worker。未来用户启用某开关也仅启用观察，不改变阶段授权、许可证/PIT gate 或 signal 准入；回滚只关对应开关即可。

### 8.2 minimal source / version / date / hash

四类元信息是最小必需，但必须拆清代码与数据，不能只给一串 repo URL 和抓取日：

| 字段组 | 最小字段 | 语义/校验 |
| --- | --- | --- |
| source | upstream_repo、immutable_code_url、data_provider、raw_data_ref、input_fact_ids；subject 的 security_id 或 membership_ref | 仓库是代码出处，数据原件另有出处；交易所/发行人/巨潮才是正式财务事实依据 |
| version | upstream_commit、adapter_version、formula_version、parser_version、config_hash、输入schema/单位/口径；实质复用另有license_ref | 只接受固定提交和 allowlist；变更任何规则/解析/profile/成员即使 raw hash相同也使增量缓存失效 |
| date | reviewed_at、period_end或quote_session/as_of、source_published_at、source_available_at及依据、fetched_at、computed_at、cutoff_at | 时区显式 Asia/Shanghai；报告期、研究截止、抓取日互不替代；必要输入available_at均<=cutoff |
| hash | code_sha256、raw_sha256、membership_sha256（适用时）、canonical_input_hash、output_hash | 重算校验真实字节；output hash对不含自身的规范化载荷计算；sha256不是PIT或财务真实性证明 |

`FeatureObservation` 仅承载 `feature_id, subject, value: Decimal|null, unit, basis, window, coverage, missing_reason, provenance`。provenance包含上表四组；coverage记录 expected/observed/missing成员数与输入水位，不能把热门池或90%回退标成全市场。缺失用null及原因，真实0另有证据；非法NaN/Infinity、单位冲突、hash失配、公司串配直接 QUARANTINED。

真实 source_available_at 不明时，不得伪造秒级时刻。若仅知公告日，按本项目登记的保守可用上界处理并保留依据；无可靠依据则 INSUFFICIENT_EVIDENCE，历史重放不准入。今天下载的历史数据记录真实 fetched/computed_at，不能假称历史当天已有本系统观察。

许可证 UNKNOWN 的 V/S binding 返回 LICENSE_UNKNOWN，不能用 sidecar 进程隔离或外部 import 绕过复制许可；若未来仅参考公开数学定义独立实现，也须记录本项目公式出处/实现版本而非冒称使用获许可的上游代码。MIT 的 M/H/Q 若实际复用，保留版权、许可和所用文件清单；代码许可证与行情/报告的数据使用权分开核查，数据权利未获证记 UNKNOWN。

### 8.3 D1 最小因子接口

首批设计仅 `ep_ttm` 与 `gross_profit_to_assets` 两个命名观测，输入必须来自本项目 PIT 已验 Facts/行情快照。分别显式标记归母TTM盈利/同日总市值、毛利与期末总资产的期间和合并范围；未经 profile 注册适用性检查不计算，金融/银行不自动复用一般公司 GPA。跨期、币种、单位、复权、股本不一致时null，不借缺失利息覆盖99或行业中性0修复。

D1 输出因子值和缺失原因，最多支持现有 ResearchCandidate 的复核依据；不输出总分、Universe全市场排行榜、仓位、估值或BUY。行业 z-score 仅保留未来扩展点；需要官方/受权历史行业归属、足够有效样本、覆盖门和独立规则版本后再设计。不得为了上游因子包“好用”扩大 D1 或延后 D2。

### 8.4 D5 最小热点接口

首批设计只 `sector_weighted_change_pct`、`market_breadth_ratio` 与 `turnover_change_ratio` 三项观察：

- 板块加权涨跌：明确用流通/总市值何者作为权重、权重基准时间、成员有效期；缺失/估算权重不补price乘常数，覆盖不足时null。它是板块观测，不是主题识别或预测。
- 广度：同一会话、同一已固定 Universe 下，上涨/(上涨+下跌+平盘)；缺价/停牌/无报价另列，分母为0时null，不给50或100。涨跌停计数如将来增加，需要逐证券当日制度/状态，拒绝统一9.5/19.5代理。
- 成交额变化：当前已完成会话成交额/前置已完成窗口的可比均额-1；窗口及是否排除当日明确版本化，零/缺失分母为null，不能用估算成交额或恒定50。盘中比较需另登记同时间切片规则，不直接与昨日全天相比。

未知 theme_persistence/crowding/event_confirmation/market_regime 不由涨跌颜色推断；保留 UNKNOWN/null。fallback/stale/混合新旧时间的字段只能留审计，不作为正式特征。数据提供者的总包 updatedAt 不能替代每项来源可用时间。

现有 D5 Domain 合同 synthetic-only；真实观察只能留 sidecar 的 OBSERVATION_ONLY 载荷。本轮不改变该合同、不生成 SentimentSignal/SwingTradePlan、不产生真实热点/买卖建议。未来正式映射需单独版本准入并完成 value/身份/财务/流动性/事件门、PIT历史成员控制、预登记阈值、walk-forward/OOS、手续费/印花税/滑点/停牌涨跌停拒单模拟及独立重放/Shadow。TACTICAL_HOTSPOT 不改 CORE_VALUE 估值、股息可持续性、核心 thesis 或组合预算。

### 8.5 有界运行与将来验收

未来只接受显式有限 subject/feature 列表；建议单次<=20证券、<=3特征、<=5MiB原始输入、10秒超时，版本化登记预算，超预算拒绝而非自动扩扫。不得消费上游任意 YAML 工作流、训练模型或建议文本。输出每项证据与失效原因；依赖失败只影响该 sidecar，不提升/降级核心研究结果，不启动上游应用。

实现阶段最小必要测试（本轮没有创建或执行这些测试）：

1. 全关闭/单通道关闭/单binding关闭不发生IO或import；超预算失败，核心D2读模型不依赖sidecar。
2. 缺失不变0/中性分，ST/北交所/停牌及非交易日不走默认涨跌停规则；fallback/stale/热门池不能升级正式全市场。
3. 财务原版/重述按可用时间切换；未知可用日、晚于cutoff、成员变更或代码/hash篡改拒绝；抓取日不回填历史发布日。
4. 公式、parser、config、profile或membership改变时缓存失效；以手算小fixture复核权重3.5及null，并核对Qlib ROC方向。
5. 标签的负Ref不得进入推断特征；fit区间越过cutoff拒绝。非synthetic观察不能进入现有synthetic D5合同；所有路径仍no_order且不带仓位/内在价值字段。

## 9. 已完成核查与 UNKNOWN 清单

本轮验证是源码/配置/测试 **静态核查** 与字节绑定，不是外部算法执行。43文件hash对固定blob通过，五库root tree元数据绑定通过，许可证和测试是否存在依据完整树索引；没有把README特性当实现证据。

仍 UNKNOWN：V/S代码复用授权；各数据提供者的使用权、当前权限/可用性；五库实际测试结果/最新CI；未采样算法和collector的正确性；实际输入公告时点/原件哈希/历史退市及成分完整性；策略OOS收益/成本/容量/Shadow；持续维护和安全漏洞状态。没有取得这些证据就不标READY/PASS。

本次有界审查到此结案，不自动扩大源码下载或启动适配。重开触发器仅为：V/S获明确许可证；拟复用文件/固定commit变化；出现正式可用时间和数据权利证据；或D2通过后另行授权一个最小adapter实现包。D1/D5的完整建设与D2里程碑不能由本报告互相代替。

## 附录 A：采样文件完整 SHA-256

代号与第1节一致。以下路径相对各上游库；本地下载对应
`D:/GPTProject/value-investment/.tmp/open-source-review-20261008/<owner>__<repo>/pinned/<path>`，
已缓存且blob一致的9文件仍在 `files/<path>`（V requirements；M LICENSE/package；
H LICENSE/package/vitest；Q LICENSE/pyproject/setup）。
远端定位统一为 `https://github.com/<owner>/<repo>/blob/<第2节固定commit>/<path>`。
每项都校对了固定树中的Git blob，不仅是计算本地hash。

| 库 | 上游路径 | SHA-256 |
| --- | --- | --- |
| V | `vi_system/cli.py` | `359701a85117a36a63c20bcb4b1618972ebe501fa2dc293f1005566667dd9fa0` |
| V | `vi_system/pipeline/factors.py` | `40d1bb06c2793e1aabf421db454441a12ece34d69645908116f09d4de54b2cd1` |
| V | `vi_system/pipeline/metrics.py` | `71650b3df7b96926a8e1305d3f2654c569183f912a17c9a7f4446d41e5a21535` |
| V | `vi_system/data/store.py` | `daaab5904c91f4b6b7faa12b8d5061f470faac2b2ac4e4ec2f3846733e25d85f` |
| V | `vi_system/data/fetcher.py` | `eaa6569cf5a03536b85683c58ec7a78d55c9a19baeb44f559452202ab5e65382` |
| V | `tests/correctness_test.py` | `0a7563827be5aa11f207ebd73595552dfc828ba22b3e81ebf98a42de2fa5f1e0` |
| V | `tests/test_layers.py` | `87ce38097b4a82e7ed7799f681adfda60487ec4a393e5bdad3df6ef2030580d9` |
| V | `.github/workflows/ci.yml` | `63f1ff51ea3e9f515be6a46e6b17a81484e69981c65d8194f3c61cb5465727f2` |
| V | `requirements.txt` | `59d980c1795155d83df9ddc10af038a79a045380c9fcb759f03b0f97f8593caf` |
| S | `backend/app/main.py` | `569fa8fc689881efc7f7a009523a3752bf36c2d8936a606839a1913cef8af314` |
| S | `backend/app/services/sentiment_service.py` | `817c4bff3bed27b40d5b0cf7a2f9d171ce06f3bba6e00b6ccb3a70ce3a88ad5e` |
| S | `backend/app/services/fundamental_service.py` | `3bb60bf551c2d7aaf89addfd11e38cb4594d82dbb9a37b9034e2c971605645e6` |
| S | `backend/app/services/market_provider.py` | `687bacc89bd48b877c50098de80c976f9511174dcd0363b2d89da1e786965225` |
| S | `backend/requirements.txt` | `b1c5edc20c46627d83dc180be12000569ac8d655da84354b0a4ecf9d4ef15740` |
| S | `frontend/package.json` | `a95f5d0c131243841edd9a611e490a6b4c0f7eda5367b4aac9061e607929871e` |
| S | `backend/app/utils/stock_api.py` | `8933ac7c82da336be6240b9a16e3fb93a6acff22374bb6f9db17b4bacb3a78c2` |
| M | `LICENSE` | `5338f464808b594ac7781b2624fe545e141d580308c13fdc2008fcdcfe900ba7` |
| M | `package.json` | `4e053e994d988b23db5dd95401f75848d7a37aac70d61fe181f48d05cba7ab49` |
| M | `src/main/index.ts` | `eae47f52893ae2bd9a5ba876c3b1cd42f65cca5c12d4d493c3bf3b54038ae29f` |
| M | `src/main/market/marketData.ts` | `7551c585057a557fdaaa6e0cbc6596d137a9704535fb6fdc244143edc7cf55dd` |
| M | `src/renderer/analysis/sentimentEngine.ts` | `5e03e9c699f9917443185cb6645173e070e73aca345455f6736e85d9f7bcddfc` |
| M | `.github/workflows/build.yml` | `bc2b8352a96d9f4f77e9636618ae901b0c8f7bd4fddf8399c5f2e16acd8c4434` |
| H | `LICENSE` | `14787f31327057aae02b515ad9ed98a8c75443e0b710f093ff83a2394be49c06` |
| H | `package.json` | `2bff47919f55371148402e5da3e0aea776831fc0e316d6f7a98be89d43352d58` |
| H | `src/app/api/heatmap/treemap/route.ts` | `60c76cbf138aa1bbe32647368396617116869530339c91ab5ea3f6294adffdbb` |
| H | `src/lib/market-heatmap.ts` | `da33b16db7771b166a9a651e672b7e05ba5681fed0cdf4e391a9553b23174d2e` |
| H | `src/lib/market-constituents.ts` | `c197e042d55eb183208991ab3cccea7772e0cb44f67274c9fe3b51162d56ecc4` |
| H | `src/components/heatmap/treemap.ts` | `f12f845159fb8a841c6216aa42fcfeb2cc95119fb3279762633df1f0460b5bb6` |
| H | `src/components/heatmap/treemap.test.ts` | `e7af97aebb8e76a0a5e37c904c1ca4d32959011f27150f6fde19782708030019` |
| H | `scripts/lib/market-data-sources.mjs` | `db3364a7bd3163a63c3175c4088f09fb0bc12ac7012a45080c39d9b5c07af0f6` |
| H | `scripts/lib/market-data-sources.test.mjs` | `e13c56da9b0e79f429de542ccd7b394043b8055e018e6d5b82c2e38505d789b8` |
| H | `.github/workflows/ci.yml` | `28782ca980ac7653199d6dcb8b75946ecd5248646a5491cad9806dfa4b081986` |
| H | `vitest.config.ts` | `68fd881dddb6f8e987fe71f021b94834e9923c5410bb880af4035d86d04efc9c` |
| Q | `LICENSE` | `c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383` |
| Q | `pyproject.toml` | `c47849f143278fef2c114513ca123c6100f007947cdf051928e734985f35a4e9` |
| Q | `setup.py` | `d4c91c0c581513eb23832e0491a3fd78be635bfa94bd690f4d47ed9b5eafc1b2` |
| Q | `qlib/cli/run.py` | `101e1c11b518b943b8d7cab1b7bf6d5fb7d62e060581ce76601204a9b5d8a569` |
| Q | `qlib/contrib/data/loader.py` | `814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb` |
| Q | `qlib/data/pit.py` | `1a1c3cea3655c38d27b3b3d3d373d915b3e3e08fff99ba2a7eb2fbc0da61894b` |
| Q | `tests/test_pit.py` | `c7aab7b717b9f0b6c8278d019046ea5c3d0674553c6590f6654b81f7f6ac87e3` |
| Q | `.github/workflows/test_qlib_from_source.yml` | `1cbdd17d49cb5840179b96acf91e47607087ee132ec3bf61c351c24838a8b467` |
| Q | `qlib/contrib/data/handler.py` | `b621481c6009c39066c67c71390fd2bea635f56daf9f2c4e38817eff268e3232` |
| Q | `qlib/data/data.py` | `9156bfef585b9e2d22d4d1ba5831efdb63b419d24846ee738eee237090ff6a24` |
