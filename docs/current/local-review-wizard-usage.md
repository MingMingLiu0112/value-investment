# 本地审核草稿向导

正常用户通过 Root 的统一 `use_trade_assistant.py review` 入口选择公司；候选由固定发布来源配置提供，向导不推断最新版本。

高级入口为 `scripts/current/review_research.py --symbol CODE --candidate PATH --candidate-sha256 SHA`。默认逐组显示问题、支持、反证和影响，填写 VERIFIED、REJECTED 或 INSUFFICIENT、理由和范围；skip 保留未回答。最终预览后输入 save 才保存未签名草稿。任何输入阶段使用 cancel，或中断输入，均不保存。

无需指定输出：草稿默认保存到 `runtime/research-review-drafts/<UTC时间>-<公司>.json`。`--preview` 为非交互中文只读预览，不写文件；`--advanced-preview` 额外显示完整 Hash 和绑定。`--output` 可显式指定新的项目内 runtime 路径。

组回答草稿不替代本人整模型 G3 对象，不提供审核身份、审核时间或整模型批准，更不替代公告材料性和价格准入。正式整模型 G3 必须由本人提供既有合同对象并由合法身份签名。

本人提供已签名文件后，可加 `--signed-review-response PATH --review-trust-root PATH`。未提供相应 SHA 时计算实际文件 SHA，再调用原有签名消费及固定 pinned registry 验证；文件 Hash 不构成身份授权。`--previous-review-response PATH` 用于显式后继回应，亦计算未提供的 Hash。可显式提供这些 SHA 作为外部预期绑定。消费结果默认使用独立 `runtime/research-review-consumptions/` 目录。

本向导不生成私钥、不代签、不登记真实身份。当前真实 registry 为空时，正式签名消费继续失败关闭。草稿、显示、保存或工程测试均不代表真实批准。

消费遭遇 IO 中断后保留原目录和已有字节；没有完成 receipt 的 packet 不可使用。恢复须保留相同候选和签名输入，显式指定 `--output 原消费目录 --resume-incomplete --incomplete-consumption-sha256 原目录中incomplete-consumption.json的SHA`。恢复不会覆盖已有文件，候选或输入漂移、当前回应链冲突、已完成消费重放均拒绝。manifest 不含重试时间戳。
