# M2-M7 人工复核交接清单：2026-09-24

更新：2026-09-24，M2 Checkpoint A 已由用户签收为 `HUMAN_PASS`。本文件汇总
后续用户本人仍需确认的事项；Checkpoint A 通过不代表 Checkpoint B-D 已签收。
所有机器产物固定 `action=no_order`，真实 IPS、持仓、现金和生产操作仍需要用户
单独提供或授权。

## 1. 本轮机器验收

以下审计均按当前仓库真实文件重新计算。运行时收据位于 `runtime/`，公开仓库不提交
私人数据。M2 Verification v1 已标记 `SEMANTICALLY_SUPERSEDED`，不得再引用旧的
“3 个 VERIFIED”结论。

| 审计 | 机器结果 | 仅剩人工项 | 收据 SHA-256 |
| --- | --- | --- | --- |
| M2 Verification v2 | `MACHINE_CHECKS_PASS`；`PIT=PASS`；v1 已语义替代 | 18 条 LEAD 的 0 / 13 / 5 resolution 语义复核 | report `310d56e408655c7c46ef510a4ce3aab44d99ab9aeb021c9ddd41f140a2fb1653` |
| M2 Verification v2 manifest | `CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION` | 已用户签收 `HUMAN_PASS` | `520d175d5a7696b970c091c88be9e8b5996a7627a58828594671f524e360aabe` |
| M3 决策卡 | m3c1-m3c6 `DONE`；m3c7 人工 | 三张负向卡理解与 Checkpoint B | `755c2ec01a21cf357de212014c9d3e11cf35f0595802814d24182c7a77069429` |
| M3 原工作簿候选 | owc1-owc6 `DONE`；owc7 人工 | 决策复核页阅读与 Checkpoint B 边界 | `9a083e943685cdb5c29802b430f414b5b11b15764314e7f230b09acdc421fef6` |
| M3 历史链叠加 | hoc1-hoc6 `DONE`；hoc7 人工 | 模拟历史边界与 Checkpoint B 边界 | `5e56c6e18668e9b5c345a839f85d22afc5e548c9a855ecce09f9ffcf1fee508c` |
| M6 运营预检 | 工程 `DONE`；运营 `NOT_STARTED` | 真实恢复演练、20 连续会话、1 真实事件、生产授权 | `cf079a92d93690ad60f717d4ef177237dfe5083507da86eb0b592515f87cc43f` |

## 2. M2 Checkpoint A：已完成人工复核

打开 WPS 云盘 `价投跟踪` 文件夹中的：

```text
A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx
```

候选 SHA-256：

```text
d423ef1ab0114f97e4a20d2f7f770b85e74b3764d6484b63d2fec03c9da82718
```

M2 Verification v2 对冻结的 18 条 LEAD 的真实结果：

```text
VERIFIED_FOR_DEEP_RESEARCH = 0
REJECTED_AFTER_VERIFICATION = 13
INSUFFICIENT_EVIDENCE = 5
UNSUPPORTED = 0
```

0 个 VERIFIED 是允许且诚实的结果，不代表运行失败，也不代表 A 股没有质量公司。
最少确认四件事：

1. 在 `01_全市场与数据健康` 能看懂官方 Universe、四通道覆盖和 Quality 覆盖不足。
2. 在 `02_候选与重点关注` 能区分 `LEAD`、`VERIFIED`、`REJECTED` 和
   `INSUFFICIENT`，不把候选数或旧 v1 结论当买入数。
3. 至少阅读一条 `REJECTED_AFTER_VERIFICATION` 和一条 `INSUFFICIENT_EVIDENCE`，
   能说明为什么低 PE、高股息或单期数据不足以进入深研队列。
4. 在 `09_审计与证据` 能抽查一条 Hash 或来源链接，并确认没有 BUY/ADD/仓位列。

用户已完成以上理解并正式记录：

```text
M2_CHECKPOINT_A = HUMAN_PASS
```

v3 是 Checkpoint A 签收时审阅的冻结版本。当前展示后继候选为 v4：

```text
A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.xlsx
SHA-256=569adf26fece3b45666138c050776b40cb077f0e0b9f498a0dd77445a83c2a59
```

v4 只把 M2 状态改为 `DONE / HUMAN_PASS` 并加入 M3/M5 新证据层，不覆盖 v3、
不改变 Checkpoint A 的审阅对象，也不签发 Checkpoint B-D 或 M7 交付。

机器重提包位于
`runtime/m2-checkpoint-a-human-resubmission-20260924-v2/checkpoint-a-packet.json`，
该历史人工里程碑收据位于同目录 `receipt.json`。新的 append-only 签收收据位于
`runtime/m2-checkpoint-a-human-acceptance-20260924-v3/receipt.json`，sequence=2
并绑定前序收据 Hash。M2 正式收口为 `DONE`；总 Goal 仍为 `PARTIAL`。

## 3. M3 Checkpoint B：用户要确认什么

本轮已生成版本化、只读、Hash 固定的复核包，见
[m3-checkpoint-b-review-packet-20260924.md](m3-checkpoint-b-review-packet-20260924.md)。
运行时可复核包位于 `runtime/m3-checkpoint-b-human-review-20260924-v1/`；它保持
`PENDING_HUMAN_REVIEW`，不会替用户签收。
只读逐卡明细位于
`runtime/m3-checkpoint-b-review-detail-20260924-v2/review-detail.md`。

三份候选都只需要看负向决策信息：

```text
A股价值投资_M3决策卡候选_20260924.xlsx
A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx
A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx
```

必须确认：

1. 格力、华域、伊利当前都是 `INSUFFICIENT_RESEARCH` 或等价研究不足状态。
2. 没有因为三家公司“看起来便宜”而生成买入、加仓、目标仓位或订单。
3. 历史链页面明确标注“模拟”，不是真实交易或真实收益证据。
4. 用户能复述至少三张卡各自的阻断、反证和重新打开研究的条件。

额外边界：当前 600519 / 2024-06-21 Historical Research Replay 的事实、公告和
行情满足 PIT，但 Median-PE 规则是 2026-09-12 注册的追溯扩展。仓库没有可验证的
当时规则登记证据，因此该案例不构成 strict contemporaneous-rule PIT；证据检索
见 [m3-historical-pit-evidence-20260924.md](m3-historical-pit-evidence-20260924.md)。

## 4. M4：用户需要提供的私有输入

在提供以下信息前，系统只能继续非个人化工程，不能给出个人仓位：

```text
IPS 与投资期限
当前资产、现金和持仓
单股上限、行业上限、周期暴露上限
流动性需求
股息收入目标
风险约束和授权账户范围
```

这些内容不能进入公开 GitHub，应使用用户确认的私有、加密存储。

## 5. M5：1225578520 已记录为 NOT_MATERIAL

人工材料性结论：

```text
symbol=600887
announcement_id=1225578520
human_decision=NOT_MATERIAL
PDF SHA-256=7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c
本地路径=runtime/m5-disclosure-review-20260923T213249Z/600887/announcements/2026-09-24/1225578520.pdf
```

该结论只表示这条员工持股计划购买完成公告不要求当前估值、模型有效性、股息可持续性
或价格吸引力立即重算。它不表示伊利是买入目标，也不表示 M5 持续事件监控已经通过。

600519 的独立真实披露窗口另有 9 条公告等待逐条人工判定。本轮已完成 Hash 对账并
生成空白回填表，详见
[m5-600519-disclosure-review-20260924.md](m5-600519-disclosure-review-20260924.md)。
空白回填表为：

```text
A股价值投资_M5真实披露人工复核回填_600519_20260924.xlsx
```

9 条公告全部为 `PENDING_HUMAN_REVIEW`，没有因 600519 无历史人工台账而结转旧结论。

## 6. M6 / M7：当前不签收

M6 只有在前序产品验收、真实恢复演练、20 个连续真实交易会话和至少 1 个真实
财务/资本事件完成后，并在用户对生产迁移、调度、通知、资源和回退方案单独授权
后，才能开始运营。M7 的最终交付签收必须在 M6 通过后由用户在常用设备实际操作确认。

## 7. 本轮不做什么

```text
不把 Checkpoint A 的 HUMAN_PASS 扩大为 Checkpoint B-D、BUY、M4 READY 或 M7 完成
不伪造 IPS、持仓、现金、Entry 或历史交易
不连接券商、不自动下单
不迁移生产数据库、不新增生产计划任务或通知
不修改服务器 PTA 项目
不把 18 个 LEAD、0 个 VERIFIED 或测试通过数当成真实研究/产品通过
```

M2 Checkpoint A 已记录交接。下一单步继续 M3 Decision Review / Checkpoint B，
同时推进依赖已满足的离线工程；在 M7 用户验收前，总目标保持 `PARTIAL`。
