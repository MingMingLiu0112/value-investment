# TL10-RC: 版本身份、原子公开快照与失败关闭（2026-10-13）

本轮把「每日公开决策数据包」从"每次即时重算"收敛为"发布一次、校验读取"。

## 1. 问题（修复前）

- `publication_id` 只覆盖正式发布链绑定 + 行情登记指针 SHA；
  但数据包内容还取决于：公司研究登记文件、登记证据文件哈希、动态行情有效性、
  自然日/最近已完成交易日与新鲜度、计算引擎规则版本。
  → 同一个 `publication_id` 可以对应两份不同内容。
- CLI 只凭 `publication_id` 相同就返回 `UNCHANGED`，不比较本次计算结果，
  输入变化时可能静默沿用旧包。

## 2. 修复

### 2.1 身份输入（identity v4，引擎 v2）

`publication_id = "pub-" + sha256(canonical(identity_inputs))[:20]`，输入固定为：

1. 计算引擎版本（`ENGINE_VERSION`，规则变更即新身份）；
2. 正式发布链绑定（receipt / wps receipt / sources / handoff / read model / daily state）；
3. 行情登记指针的**观测** SHA-256；
4. 已归档行情包（每个标的的 bundle 观测 SHA-256）；
5. 公司研究登记文件的观测 SHA-256；
6. 登记证据文件的观测 SHA-256（逐条）；
7. read model 绑定的决策解释文件（`additional_evidence_bindings`）的观测 SHA-256（逐条）：
   文件内容变化会改变公司状态（降级为 `VALUE_EXPLANATION_BINDING_UNAVAILABLE`），
   因此同样是版本输入；v4 之前该输入缺失，只能依赖 exit 4 冲突守卫兜底，同一天内会拒绝发布；
8. 业务时钟：自然日 + 最近已完成交易日 —— 它们决定交易日、新鲜度与准入状态，
   因此必须显式成为版本输入，而不是靠"今天恰好是几号"隐式变化。

`generated_at` / `generated_at_china` 只是记时，不进入身份，也不进入内容摘要。

在 v4 覆盖全部内容输入后，exit 4 只用于防御"已落盘记录与本次重算不一致"
（人工改写落盘文件或引擎缺陷），正常输入漂移一律形成新版本。

### 2.2 内容摘要

`content_sha256 = sha256(packet 去掉 volatile 字段)`；
volatile 字段 = `generated_at`、`generated_at_china`、`content_sha256`、`excel_sync`。
`excel_sync` 是只读对照视图（发布时才比较），不属于决策内容。

### 2.3 CLI 协议（scripts/current/build_daily_public_packet.py）

| 情况 | 行为 | 退出码 |
| --- | --- | --- |
| 新内容 | 写版本目录 `runtime/daily-public-packet/daily-public-packet-<id>.json`，写快照回执，原子更新当前快照引用 | 0 `WRITTEN` |
| 完全相同（同身份 + 同内容摘要） | 不写新字节，复核快照引用；报告已存记录 | 0 `UNCHANGED` |
| 同身份 + 不同内容 | 失败关闭：写 `daily-public-packet-conflict-<id>-<stamp>.json`，不覆盖、不发布 | 4 `REFUSED_IDENTITY_CONFLICT` |
| 同身份记录不可读 | 失败关闭，不覆盖 | 3 `REFUSED_EXISTING_UNREADABLE` |
| 发布链不可用 | 不发布新快照，当前指针不动 | 2 `BLOCKED_CHAIN_UNAVAILABLE` |

## 3. 原子公开快照（application/product/public_snapshot.py）

- 指针：`config/current-daily-public-snapshot.json`（schema `current-daily-public-snapshot-v1`，`status=VERIFIED`），
  记录 `publication_id`、`packet_path`、`packet_sha256`、`content_sha256`、引擎/研究版本、发布时间、回执路径。
- 回执（不可变）：`runtime/daily-public-packet/receipts/daily-public-packet-<id>.receipt.json`，
  含身份输入与两层摘要；`write_new_json` 拒绝覆盖。
- 指针写入：同目录临时文件 + `os.replace`，读者只会看到旧版或新版，不会看到半发布状态。
- Web 读取：`GET /api/v1/daily-public-packet` 读取指针 → 校验文件 SHA → 校验内容摘要 →
  校验身份一致 → 原样返回该字节；任一失败 fail-closed：
  - 有指针但文件/哈希/摘要异常 → `snapshot_status` 明确报错；
  - 尚无任何快照（全新检出/测试夹具）→ 回退实时组合，并标注
    `snapshot_status="NO_VERIFIED_SNAPSHOT"` 与 blocker `PUBLIC_SNAPSHOT_UNAVAILABLE`，
    不伪装成"冻结版本"。
- 版本元数据：`GET /api/v1/daily-public-snapshot` 返回指针状态、两层 SHA、发布/生成时间、
  回执路径，以及 `excel_live` 只读对照。

## 4. 计数口径（TL10 §4）

- `formal_admission_count`：按证券去重计数（同一标的可以同时出现在公司快照、
  机会列表与研究队列中，只算一次准入）。
- `incomplete_research_count`：按证券去重。
- 来源完整性（`source_bindings_verified`）与投资准入（`formal_admission_count`、G3）
  是两个独立结论，任何界面都不得表述为"来源通过 = 可以投资"。

## 5. Excel 对照（只读）

`excel_sync` / `excel_live` 状态：

| 状态 | 含义 |
| --- | --- |
| `MATCHED` | 磁盘正式工作簿 SHA-256 与发布指针登记一致 |
| `DIFFERENT` | 不一致（可能一侧已更新）；不自动同步，转人工 |
| `NOT_VERIFIED` | 路径不可读或指针没有登记哈希：不允许声明"已同步" |
| `NOT_RESOLVED` | 未解析到正式工作簿路径 |

任何路径都不会写正式工作簿；TL10 不执行 Excel 发布。

## 6. 每日入口退出码（scripts/current/run_daily_workbench.ps1）

先出数据更新结果，再出 Web 结果，最后给整体结果；Web 启动成功不掩盖研究更新失败：

- `0` 更新 SUCCESS（Web 已启动/被跳过）；
- `2` 更新 BLOCKED（发布链不可用 / 身份冲突 / 刷新失败）；
- `3` 更新 PARTIAL（成功但有记录在案的提醒）；
- `4` 更新成功但 Web 启动失败。

SAFE_REFRESH 的能力边界：只刷新公开行情并重建快照；重跑研究、事件材料性复核与
G3 估值门仍是人工/工程步骤，入口只把它们列为待办，不代签。
