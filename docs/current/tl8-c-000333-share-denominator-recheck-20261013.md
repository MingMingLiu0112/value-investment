# TL8 工作包 C：000333 2026-06-30 股本分母官方核验（2026-10-13）

本轮对 000333 美的集团的 2026-06-30 普通股分母执行了一次**有界官方复查**：
在前次封存窗口（CNINFO 2026-08-30~09-29、HKEX 2026-09-01~09-29）之外，
查询 2026-09-30 之后的新披露窗口，并补齐此前未取过的 2026-07-01~08-07
HKEX 窗口。所有来源均留存原件、固定 SHA-256，并由共享适用性适配器
（`scripts/build_midea_valuation_applicability.py`，v5）重新校验后接入。

**结论：原 A 级阻塞“2026-06-30 普通股分母无法界定”已闭环。**
发行人向港交所呈报的月报表直接枚举了该日的股本：

| 项目（2026-06-30） | A 股 | H 股 | 合计 |
| --- | ---: | ---: | ---: |
| 已发行股份总数 | 6,962,590,407 | 650,848,500 | 7,613,438,907 |
| 库存股份 | 149,091,572 | 0 | 149,091,572 |
| 已发行（不含库存） | 6,813,498,835 | 650,848,500 | **7,464,347,335** |

估值基准分母取 **7,464,347,335 股（已发行、不含库存股，按类别）**；
母公司权益 212.861055bn（2026H1 报告）本身已扣除同一库存股，两者口径一致。
本轮不产生任何每股估值、不升级任何门禁，`action=no_order`。

## 1. 查询窗口与来源

### 1.1 HKEX 有界窗口（新采集工具）

新增薄工具 `scripts/cases/capture_hkex_issuer_disclosure_window.py`：
按发行人代码固定身份（prefix 查询要求恰好命中一条），按日期窗口取回
完整披露列表，fail-closed（分页溢出、他方发行人、窗口外记录、目录已存在
均拒绝），`--download` 时留存原件并逐个记录 SHA-256。

| 窗口 | 记录数 | 窗口索引 SHA-256 | 窗口回执 SHA-256 |
| --- | ---: | --- | --- |
| 2026-07-01 ~ 2026-08-07 | 35 | `e94a4cd4…8ae2679` | `32824f83…9a98443` |
| 2026-09-30 ~ 2026-10-13 | 6 | `7e087984…ec7a116` | `3c503289…8aa7a5` |

来源目录：
`runtime/company-research/midea-denominator-recheck-20261013/`
（`hkex-window-20260701-20260807/`、`hkex-window-20260930-20261013/`）。

### 1.2 CNINFO 有界窗口

沿用现有
`scripts/cases/scan_prospective_public_event_window.py`（未新增扫描逻辑）：

- 窗口 2026-09-30 ~ 2026-10-13，发行人 000333 共 5 条公告；
  索引 SHA-256 `e69aac04…022c462`，扫描回执 SHA-256 `27e526f0…952d60f`；
  原件下载清单 SHA-256 `79ae42b5…0f51d4e8`。

## 2. 关键来源（原件 + 哈希）

| 来源 | 官方链接 | 本地留存路径 | SHA-256 |
| --- | --- | --- | --- |
| 2026 年 6 月月报表（2026-07-07 呈交，枚举 6-30 结存） | [HKEX PDF](https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0707/2026070700419_c.pdf) | `…/hkex-window-20260701-20260807/originals/12235688-2026070700419_c.pdf` | `fab9be2f…b3ecfd` |
| 2026 年 7 月月报表（2026-08-06 呈交，上月底结存复核 6-30） | [HKEX PDF](https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0806/2026080601118_c.pdf) | `…/hkex-window-20260701-20260807/originals/12275468-2026080601118_c.pdf` | `2b44a2f0…7dbaba9` |
| 2026 年 9 月月报表（2026-10-07 呈交，9 月滚动闭环） | [HKEX PDF](https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1007/2026100700897_c.pdf) | `…/hkex-window-20260930-20261013/originals/12365201-2026100700897_c.pdf` | `c56a8370…f64f378e` |
| 回购进展公告（截至 2026-09-30，公告编号 2026-073） | [CNINFO PDF](https://static.cninfo.com.cn/finalpage/2026-10-09/1225596587.PDF) | `…/cninfo-originals/1225596587.PDF` | `ecf88af0…3532a7073` |
| 回购进展公告（截至 2026-08-31，公告编号 2026-065） | [CNINFO PDF](https://static.cninfo.com.cn/finalpage/2026-09-03/1225544342.PDF) | `runtime/company-research/midea-share-denominator-followup-20260930/1225544342.pdf` | `24900692…b3d7cc50b` |
| 2026 年 A 股持股计划非交易过户完成公告（公告编号 2026-066） | [CNINFO PDF](https://static.cninfo.com.cn/finalpage/2026-09-03/1225544482.PDF) | `runtime/company-research/midea-share-denominator-followup-20260930/1225544482.pdf` | `d93bfd07…7b4716365` |

2026H1 半年度报告沿用既有固定件
`runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf`
（`576dd80e…c10159179b8`，第 87-88、169 页）。

## 3. 交叉校验（全部通过）

1. **与 2026H1 报告一致**：月报表 6-30 已发行总数
   6,962,590,407 + 650,848,500 = 7,613,438,907，与 H1 报告“股份总数”
   完全一致（A 股 6,962,590,407 + H 股 650,848,500）。
2. **两个月报表互证**：7 月月报表的“上月底结存”行与 6 月月报表的
   “本月底结存”行逐字段相同（6,813,498,835 / 149,091,572 / 6,962,590,407）。
3. **9 月滚动闭环**（检验库存股口径 = 回购专用账户）：
   2026-09-30 公告累计回购 123,010,307 股 − 2026-08-31 公告累计
   99,797,967 股 = 当月回购 23,212,340 股；9 月 3 日持股计划非交易过户
   转出 15,772,385 股；23,212,340 − 15,772,385 = **+7,439,955**，
   与月报表库存股变动 187,650,463 − 180,210,508 = +7,439,955 完全相等。
   即：转出回购账户的持股计划股份按“不再库存”处理，留在回购账户内的
   股份（无论用于注销或激励）均为库存股。
4. **与公司自身分配口径一致**：2026H1 中期分红以“总股本扣除回购专户余额”
   为基数（披露日 7,448,597,984 = 7,628,798,092 − 180,200,108），
   与月报表库存股=回购专户的口径一致。
5. **库存股构成可对账**：6-30 库存 149,091,572 − 2026 年方案累计回购
   68,679,031（H1 第 88 页，金额 5,476,158,082 元，与附注(41)
   “尚未注销的回购股份 5,476,600 千元”一致）= 80,412,541 股，
   即以往年度回购、面向股份支付激励方案的库存股（与 2025 年度分红
   所扣除的回购股份数一致）。

## 4. 记录但未采用的备选分母

- “仅剔除注销用途库存股”的口径：7,464,347,335 + 80,412,541 =
  **7,544,759,876**。该口径把尚未过户到持股计划的库存股视为已流通。
  由于母公司权益已按全部库存股成本做减项，采用该分母会与权益口径不一致，
  因此**记录但不采用**；如需压力测试，仅作为敏感性说明，不作为基准。
- H1 加权平均基本/稀释 EPS 分母（7,470,497,000 / 7,540,304,000）是期间
  平均数，不是期末计数，任何情况下不得替代。
- 2026-09-29 已验证的 7,445,382,896 股为**不同日期**，不得回填 6-30。

## 5. 接入共享研究链（applicability v5）

`scripts/build_midea_valuation_applicability.py` 升级为
`midea-valuation-applicability-v5`（评估日 2026-10-13）：

- 新增 8 个证据引用（两期月报表、9 月月报表、两份回购进展公告、
  持股计划过户公告、两个有界窗口索引），全部路径 + SHA-256 固定；
- 进入构建前逐页复核枚举文本（6 月月报表第 1-2 页、7 月月报表第 2 页、
  9 月月报表第 2 页、两份回购公告、过户公告第 2 页、H1 第 88 页），
  并断言 A+H 对账、分母对账、库存拆分对账与 9 月滚动恒等式；
- `blocker_classification.A_BLOCKING_UNKNOWN` 由 1 降为 0，
  `blockers` 清空；`valuation_basis_2026_06_30_share_scope` =
  `VERIFIED_2026_06_30_ISSUED_EXCLUDING_TREASURY`，
  基准分母 7,464,347,335 进入负载；
- 残余输入仍为 6 项 B 类情景输入（Bear/Base/Bull ROE 路径、股本成本、
  留存/派息、终值），维持 `valuation_run_status =
  NOT_RUN_B_SCENARIO_INPUTS_NOT_REGISTERED`、
  `decision = AUTHORIZED_DENOMINATOR_VERIFIED_PENDING_B_SCENARIO_INPUTS`，
  `registered_valuation_inputs` 仍为空、无 `ValuationResult` 输出；
- 产物 `runtime/company-research/midea-valuation-applicability-20261013-v5/evidence.json`
  SHA-256 `b69e2fc9…f5ee5f541`；指针
  `runtime/company-research/midea-valuation-applicability-latest.json`
  SHA-256 `4695c562…63dabfb1`（旧 v4 目录保留，不覆盖）。

FCFF 不适用的结论与三项 D 类证据停止**不变**；本闭环只解除 6-30 分母缺口。

## 6. 工程配套

- 新增 `tests/test_hkex_issuer_window_capture.py`（4 例，全合成 fixture：
  身份固定、窗口标准化、行数上限 fail-closed、他方发行人/窗口外记录拒绝、
  目录不可覆盖），并加入 Core Research Gates 的 pytest 清单；
- 脚本清单 `docs/architecture/script-inventory-v1.json` 登记新工具；
  `config/architecture-growth-baseline-v1.json` 更新
  `build_midea_valuation_applicability.py` 行数上限（296 → 418）；
- 既有测试 `tests/test_midea_valuation_applicability.py` 同步更新为
  v5 语义（A=0、分母已验证、备选分母记录、证据引用集合）。

## 7. 复现命令

```powershell
python -X utf8 -B scripts/cases/capture_hkex_issuer_disclosure_window.py --code 00300 --start 2026-07-01 --end 2026-08-07 --output-dir runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260701-20260807 --expect-name 美的集團 --download
python -X utf8 -B scripts/cases/capture_hkex_issuer_disclosure_window.py --code 00300 --start 2026-09-30 --end 2026-10-13 --output-dir runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260930-20261013 --expect-name 美的集團 --download
python -X utf8 -B scripts/cases/scan_prospective_public_event_window.py --symbol 000333 --name 美的集团 --start 2026-09-30 --end 2026-10-13
python -X utf8 -B scripts/build_midea_valuation_applicability.py
python -X utf8 -B -m pytest tests/test_midea_valuation_applicability.py tests/test_hkex_issuer_window_capture.py -q
```

## 8. 边界与后续

- 披露获取时点与本地抓取时钟未经独立时间戳背书；本记录为有界官方来源
  对账，不构成严格同时点（strict contemporaneous）PIT 证明；
- 6-30 分母闭环不改变“好公司 ≠ 好股票”：在 B 类情景输入注册并完成
  模型运行之前，000333 维持 `PENDING_RESEARCH`，页面上不得出现任何
  BUY/ADD/目标仓位语义；
- 下一次自然复核：2026Q3 报告（约 2026-10 月底）与后续月报表进入
  常规披露窗口时，可用同一工具重跑并比较。

`action=no_order`
