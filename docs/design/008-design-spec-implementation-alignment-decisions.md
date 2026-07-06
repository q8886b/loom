# 008 — 004/005/实现差异对齐决策记录

> 本文记录 004 设计文档、005 harness 规格文档与当前实现之间的差异对齐结论。它不是新的系统设计入口；004 仍承载设计目的，005 仍承载规格落地。本文用于统一后续一次性修改文档与实现。

## 已确认决策

### 1. L2/DIGEST 阶段 link 规则

**决策**：L2/DIGEST 阶段必须 link 本 L1 单元的主题卡；允许 link 本书 / 本次材料内的其他 L2 卡；不 link 跨书、跨材料、跨领域、L4。

**口径**：
- 必选：非主题 L2 卡必须 link 对应主题卡。
- 可选：可以 link 本书 / 本次材料内其他 L2 卡，用于表达材料内部结构。
- 反思卡仍必须锚定判断/模式卡；锚点原则上应属于本书 / 本次材料内。
- 跨材料、跨领域、L4 连接放到 L3 THINK 阶段。

**实现改动**：
- 调整 `check_l2_no_cross_domain_links`，从“只禁跨领域/L4”升级为“允许主题卡 + 同书/同材料内 L2 + 反思锚点”。
- 更新 `skills/loom-digest/SKILL.md`，明确本材料内 link 可选，跨材料 link 禁止。
- 更新 004/005 中“L2 不建跨卡 link”的旧表述。

### 2. salvage 模式

**决策**：以 005 设计为准，salvage 不绕过语义层。

**口径**：
- `loom-admin stop-check <task_id> --mode=salvage` 计算层通过后，也应写 `.computed_passed.json` 与 `.semantic_sample.json`。
- salvage 也应 block 回 agent 做语义自检。
- 语义通过后仍由 `loom commit-ready <task_id> --semantic-passed` 入库。

**实现改动**：
- 修改 `cmd_stop_check(mode="salvage")`，使其复用 normal 的 computed/sample/block-back 流程。
- block reason 标明 salvage 语境。

### 3. 语义层判据的权威位置

**决策**：不引入 prompt hook；保留 command hook + skill 协议。

**口径**：
- 语义判据的权威位置是 `skills/_loom_core.md` 与各模式 skill 的收尾协议。
- `cmd_stop_check` 的 block reason 只负责提示当前需要按四判据检查 `.semantic_sample.json`。
- hook 配置保持 command-only。

**文档改动**：
- 修改 005 §7.3，删除“判据写在 `type:"prompt"` hook prompt 字段”的旧说法。

### 4. Hook 输出边界

**决策**：不改实现，改 005 的 Hook 铁律表述。

**口径**：
- Hook 禁止输出具体修复方案、替 agent 改内容、触发工具调用。
- Hook 可以输出状态机协议提示，例如“计算层已通过，请做语义自检；通过后走 commit-ready 协议”。

**文档改动**：
- 修改 005 §6.4，去掉“绝不包含执行指令”的绝对表述，改为区分“修复指令”和“协议提示”。

### 5. 旧 `loom-admin commit` 入口

**决策**：删除 / 不暴露旧 `loom-admin commit` 入口。

**理由**：该入口绕过 `.computed_passed.json`、语义自检和 `--semantic-passed`，与当前最小权限入库链路冲突。

**实现改动**：
- 从 admin parser 移除 `commit` 子命令。
- 删除或废弃 `cmd_commit`。
- 从 `skills/_loom_core.md` 特权命令列表删除 `loom-admin commit`。

### 6. DIGEST plan 的 `phase`

**决策**：保留实现中对 L2/L2_light 任务的 `phase=scout|deep` 强制要求，补 005 文档。

**口径**：
- 通用 plan 有基础字段。
- DIGEST-L2 专用 plan 必须有：
  - scout：`phase=scout`；
  - deep：`phase=deep` 且必须有 `topic_card`。

**文档改动**：
- 修改 005 §4.1，区分通用 plan 字段与 DIGEST 两阶段强制字段。

### 7. 卡片镜像路径示例

**决策**：只修 005 文档，不改实现。

**口径**：
- L2：`cards/fin/tianwei/03.md`
- L3：`cards/fin/3a.md`
- L4：`cards/gen/1a.md`

**文档改动**：
- 修改 005 §2.4 的 `cards/fin/3a.md # L2/L3` 示例。

### 8. `write-draft` 校验数量注释

**决策**：只修注释，不改逻辑。

**实现改动**：
- `cmd_write_draft` docstring / 注释从“8 条 per-card checks”改为“10 条 per-card checks”。

### 9. 诊断工具补进 005 工具清单

**决策**：补 005，不改实现。

**工具**：
- `loom silent-cards [--min-age-days=N]`
- `loom l4-upgrade-candidates [--use-count=N] [--reflections=N] [--domains=N]`

**口径**：
- 只提示，不自动删除沉默卡。
- 只列候选，不自动升级 L4。

### 10. L1 统一卡片化

**决策**：L1 是统一 card，不是卡片体系之外的文件旁路。

**口径**：
- L1 card：`layer=L1`，`type=source`。
- L1 有 card identity、数据库记录、use_count、search_count、links。
- L1 可以被 search、read-cards、作为 link 目标。
- UI 上 L1 source card 可点击。
- 点击详情时显示全文 markdown。
- 文件系统中的 markdown 是 L1 card 的全文内容来源或镜像，不是交互身份本身。

**UI/API 约束**：
- 图谱接口应纳入 L1 source card 节点。
- 图谱接口只返回 L1 的轻量 metadata / snippet / size，不一次性返回全文 content。
- L1 全文只在详情接口按需读取。

**文档改动**：
- 修改 004/005 中“L1 不是卡、无 type/links”的旧表述。
- 005 明确 L1 进入统一 card 模型。

**实现改动**：
- 增加 `layer=L1,type=source` 的 card 支持。
- L3 “必须 link L1/L2”中的 L1 改为 L1 source card，不接受裸 `.md` 路径作为等价替代。
- 后续收敛 `l1_files` 旁路表 / `search_l1_files` 旁路机制到统一 card 交互模型。

### 11. 005 成熟设计回补 004

**决策**：回补 004，但只补设计原则，不塞 005 的实现细节。

**回补内容**：
- L4 血肉 = L4 本体 + link 网络。
- L4 激活不能强制，只能主动 orient + 记录 + WARN + 长期反馈。
- 跨材料 ≠ 跨领域；单领域多材料抽象默认 L3，跨领域成立才进 L4。
- embedding 是辅助，link 是显性真相。
- 四项语义判据：`type_match` / `single_unit` / `genuine_digest` / `self_contained`。

### 12. `L1_only` 命名

**决策**：`L1_only` 改成 `L1`。

**口径**：
- task target layer：`L1 / L2_light / L2 / L3 / L4`。
- card layer：`L1 / L2 / L3 / L4`。
- `L1` 任务目标表示只建立 L1 source card，不继续 L2 消化。
- `L2_light` 是任务目标，不是 card layer；轻量消化产出的卡仍为 `layer=L2`。

**实现改动**：
- 移除 `L1_only` 作为 card layer。
- plan/task target 合法集改用 `L1`。
- 如需区分 card layer 与 task target layer，应拆分常量。

### 13. `source` type 的归属

**决策**：采用方案 B。

**口径**：
- 认知 type 仍是 8 种：概念、结构、机制、案例、判断、反思、模式、主题。
- card type = 8 种认知 type + `source`。
- `source` 不是认知 type，是 L1 原文卡的 card type。
- `source` 只能用于 `layer=L1`。

**实现改动**：
- 增加 `VALID_COGNITIVE_TYPES` 与 `VALID_CARD_TYPES`，避免把 `source` 混入 004 的 8 种认知 type。
- `type_valid` 使用 card type 合法集。
- `layer_type_matrix` 规定 `L1: {source}`。

### 14. `read-source` 与 `read-cards` 的边界

**决策**：保留 `read-source`，但语义改成“显式读取 L1 source card 全文”。

**口径**：
- `read-cards <id>` 可读取 L1/L2/L3/L4，但对 L1 默认只返回轻量信息，不返回全文。
- `read-source <path-or-source-card-id>` 专门读取 L1 source card 的全文 content。
- `read-source` 可接受 L1 card id 或 markdown path；返回结果应是 source card 形态。

**实现改动**：
- `cmd_read_cards` 对 `layer=L1` 做轻量返回。
- `cmd_read_source` 支持 L1 card id，并返回全文。

### 15. L1 source card id 规范

**决策**：L1 source card id 使用 `<领域>:<书>:src:<单元ID>`。

**示例**：
- `sources/07-LLM/24-HarnessEngineering/ch08.md` → `llm:harness:src:08`
- `sources/01-金融/02-Bernstein-与天为敌/03-伯努利与期望值.md` → `fin:tianwei:src:03`

**相邻层级**：
- L1 source card：`fin:tianwei:src:03`
- L2 主题卡：`fin:tianwei:03`
- L2 深卡：`fin:tianwei:03a`
- L3：`fin:3a`
- L4：`gen:1a`

### 16. L1 content 存储方式

**决策**：采用方案 C。

**口径**：
- L1 source card 的全文 markdown 存入 `cards.content`。
- `sources/...md` 仍保留，作为 source mirror / 人类可读原文文件。
- search 可命中 L1 全文。
- `read-cards`、graph API、orient、browse 等默认不返回 L1 全文。
- `read-source` / 详情接口显式返回 L1 全文。

**实现改动**：
- L1 入 `cards` 表时 `content` 保存全文。
- 所有轻量读取接口对 L1 做截断 / 摘要处理。

### 17. `source` 字段语义

**决策**：`source` 只在 L1/L2 有强语义；L3/L4 的依据靠 links。

**口径**：
- L1：`source` 保留原始文件路径 / URL / imported_from；当前先用原始 markdown 文件路径。
- L2：`source` 必须指向唯一的 L1 source card id。
- L3：不强制 `source`；依据必须通过 links 表达。
- L4：不强制 `source`；依据必须通过 links / proposal 表达。

**实现改动**：
- `check_source_real` 按 layer 区分。
- L2 校验 `source` 必须存在且 `layer=L1,type=source`。
- L3/L4 不再要求 `source` 真实存在。

### 18. 图谱 API / UI 对 L1 的轻量返回边界

**决策**：L1 source card 纳入图谱，但图谱接口不返回全文。

**口径**：
- 图谱节点返回统一基础字段：`id/title/type/layer/source/snippet/content_size/has_full_content/links`。
- L1 节点不返回 full `content`。
- 点击 L1 节点后，通过详情接口或 `read-source` 获取全文。

**实现改动**：
- 检查 `workbench/backend/main.py` 的 graph API；若返回 full content，改成轻量字段。
- 确保详情接口可返回 L1 full content。

### 19. L4 跨域锚定是否计入 L1

**决策**：L4 可以 link L1，但跨域锚定门槛只统计 L2/L3，不统计 L1。

**口径**：
- L4 links 可包含 L1/L2/L3/L4。
- L1 source card 可作为血肉补充。
- L4 合格门槛仍是至少 link 到 2 个不同领域的 L2/L3 卡。
- L1 不可用于凑跨域锚定门槛。

**实现改动**：
- `check_l4_links_lower` 保持统计 L2/L3。
- 错误文案说明 L1 可 link 但不计门槛。

### 20. L3 最低锚定门槛

**决策**：L3 必须至少 link 一张 L2；L1 可补充但不满足最低门槛。

**口径**：
- L3 links 可包含 L1/L2/L3/L4。
- 合格门槛：至少一张 L2。
- L1 source card 只是原文证据补充，不能替代 L2。

**实现改动**：
- `check_l3_links_lower` 改为要求至少一个 link 目标 `layer=L2`。
- 不再接受裸 `.md` 路径作为 L3 门槛。

### 21. L2 的 `source`

**决策**：L2 的 `source` 固定指向唯一的 L1 source card id。

**口径**：
- L2 主题卡和 L2 深卡都必须有 `source=<L1 source card id>`。
- `source` 表达 L2 消化自哪份 L1 原文。
- L3/L4 不强制 `source`。

**实现改动**：
- L2 write-draft 校验 source 是否为存在的 L1 source card。
- skill 示例从 source path 改为 source card id。

### 22. L1 的 `source`

**决策**：L1.source 保留原始文件路径。

**口径**：
- `L1.id` 是卡片身份。
- `L1.content` 存全文。
- `L1.source` 存原始 markdown 路径。

### 23. `read-cards` 读取 L1 的默认返回

**决策**：`read-cards <L1_ID>` 默认只返回轻量信息，不返回全文。

**口径**：
- 返回：`id/title/layer/type/source/snippet/content_size/use_count/search_count/links`。
- 不返回全文 `content`。
- 全文通过 `read-source <L1_ID>` 或详情接口获取。

**实现改动**：
- `cmd_read_cards` 对 L1 做特殊轻量输出。
- 如后续需要，可增加显式参数读取全文，但默认必须轻量。

### 24. L1 source card 创建入口

**决策**：新增 `loom import-source`，并在处理管线中补 L1 source card 注册步骤。

**口径**：
- `import-source` 是写操作，负责把 markdown 注册成 L1 source card。
- `read-source` 是读操作，只读取已注册 source card / path 的全文，不负责创建。
- DIGEST / PIPELINE 的第 0 步先 `import-source`，再进入 Scout/Deep。

**实现改动**：
- 新增 `loom import-source <source_id> --title=<title> --path=<markdown_path>`。
- 创建 `layer=L1,type=source` 的 card。
- `content` 写入 markdown 全文，`source` 写入原始 markdown 路径。
- 同步 FTS / embedding / card mirror。

### 25. `L2_light` 的边界

**决策**：`L2_light` 只存在于 plan / task 目标中，不是 card layer。

**口径**：
- card layer 只有 `L1 / L2 / L3 / L4`。
- task target layer 是 `L1 / L2_light / L2 / L3 / L4`。
- `L2_light` 表示轻量消化任务：产出的卡仍全部是 `layer=L2`。
- 实现与文档中任何把 `L2_light` 当作 card layer 的地方都应清理。

**实现改动**：
- 从 `LAYER_TYPE_MATRIX` 的 card layer 中移除 `L2_light`。
- 需要拆分 card layer 合法集与 task target 合法集。
- `write-draft` 的 `layer` 参数应写真实 card layer；plan 的目标可以是 `L2_light`。
- L2_light 任务下写出的 draft layer 应为 `L2`。

### 26. 004 / 005 修改边界

**决策**：004 只补设计原则和认知模型，005 补规格、接口、命令、校验、路径与实现约束。

**004 应补**：
- L1 也是卡，`type=source`。
- L4 血肉 = 本体 + link 网络。
- L4 激活不强制，只能主动 orient + 记录 + WARN + 长期反馈。
- 跨材料 ≠ 跨领域。
- embedding 是辅助，link 是显性真相。
- 四项语义判据。
- L1/L2/L3/L4 的认知关系澄清。

**005 应补**：
- `import-source`。
- `read-source` / `read-cards` 边界。
- L1 source card id 规范。
- L1 全文存储与轻量返回边界。
- `source` 字段按 layer 的语义。
- 图谱/API 轻量返回。
- 诊断工具、hook、plan、校验、命令细节。
- `L1_only -> L1`。
- `source` card type 方案 B。
- `L2_light` 只作 task 目标，不进 card layer。

## 尚待确认的差异点

暂无。下一步可按本文统一修改 004、005、skill、CLI、checks、store 与 workbench API。
