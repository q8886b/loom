---
name: loom-digest
description: 消化新材料入网（L1→L2）。两阶段子 agent：Scout 通读整本书建立每章主题卡，Deep 每章并行精读产出 L2 精华卡。
---

# DIGEST 流程（L1 → L2，两阶段子 agent）

## 两阶段总览

L2 处理一份材料（一本书或一份长材料）分**两个独立子 agent 阶段**：

| 阶段 | 子 agent 数 | 输入 | 产出 |
|---|---|---|---|
| **主 agent 准备** | 0（主 agent 自己做） | 原始材料 | L1 markdown（按章切分）+ scout/deep plan.json |
| **Scout** | 1 个 | 整本书所有 ch*.md | 每章一张主题卡（chapter-level 全局视野）|
| **Deep** | N 个（每章一个，并行） | 该章 ch.md + 该章主题卡 | 该章其余 L2 卡（概念/结构/机制/案例/判断/反思）|

**为什么必须两阶段**：单 agent 一次读整本书 + 一次产出所有卡片不可控（30 章一本书一次输出 300 张卡片做不到）。Scout 产出少（每章 1 张），Deep 每章独立 context 产出可控。

---

## 第 0 步：L1 捕获（主 agent，起子 agent 之前）

把原始材料（PDF/epub/整本 markdown）切成可独立消化的章节 markdown，落盘到 `sources/<领域>/<编号>-<书名>/<单元标识>.md`。

判定标准（005 §2.3）：**单元内部主题连贯、可独立消化，不需要其他单元的上下文也能读懂**。书按章切，论文按篇切。

**已切分的材料跳过此步**——如 Harness Engineering 已有 ch01~ch19.md。

切分完成后，**用 `loom import-source` 把每个 markdown 注册为 L1 source card**（008 §24）：

```bash
loom import-source <领域>:<书>:src:<单元ID> \
  --title="<章节标题>" \
  --path=sources/<领域>/<编号>-<书名>/<单元ID>.md
```

- L1 source card id 规范（008 §15）：`<领域>:<书>:src:<单元ID>`，如 `llm:harness:src:08`
- L1 卡的 `content` 自动写入全文，`source` 保留 markdown 路径
- L1 卡可被 search / read-source / graph / suggest-links 覆盖，与 L2/L3/L4 共用同一交互模型

## 第 1 步：价值判断（Bacon 分级，主 agent）

读 L1（全文或检视），判断材料价值，决定 layer（task target）：

| layer | 含义 |
|---|---|
| L1 | 只注册 L1 source card，不消化 |
| L2_light | 轻量消化（核心几张卡，不穷尽）|
| L2 | 完整消化到 L2 |

**不强制档位**（Bacon "浅尝/吞下/嚼/消化" 只是参考），但**必须有这个判断动作**。结果写入 plan.json。

判断依据：信息密度、与现有网络的相关性。低价值材料也保留在 sources/——保存与消化独立。

如果 layer=L1，到此结束——材料已注册为 L1 source card，不再起子 agent。

## 第 2 步：写 plan.json（主 agent，区分 scout/deep）

```bash
# Scout 任务（1 个）
SCOUT_ID=scout_<book>_$(date +%s)
mkdir -p /tmp/loom_task/$SCOUT_ID/drafts
cat > /tmp/loom_task/$SCOUT_ID/plan.json <<EOF
{
  "task_id": "$SCOUT_ID",
  "phase": "scout",
  "task": "Scout《<书名》建立每章主题卡",
  "book": "sources/<领域>/<书目录>",
  "chapters": ["ch01.md", "...", "chN.md"],
  "layer": "L2",
  "skill": "DIGEST"
}
EOF

# Deep 任务（每章一份，N 个并行）
DEEP_ID=deep_<book>_<ch>_$(date +%s)
mkdir -p /tmp/loom_task/$DEEP_ID/drafts
cat > /tmp/loom_task/$DEEP_ID/plan.json <<EOF
{
  "task_id": "$DEEP_ID",
  "phase": "deep",
  "task": "Deep <ch> 精读产出 L2 卡",
  "chapter": "<ch>.md",
  "topic_card": "<ns>:<章节号>",
  "layer": "L2",
  "skill": "DIGEST"
}
EOF
```

---

# Scout 阶段（第一次子 agent，1 个，通读整本书建主题卡）

## Scout Step 1：分次读 L1 所有章节

按章节顺序逐个 read-source（L1 source card id 或 markdown 路径都行），**整本书读完才进入 Step 2**：

```bash
loom read-source <ns>:<book>:src:01
loom read-source <ns>:<book>:src:02
# ...
loom read-source <ns>:<book>:src:N
```

整本书读完后，子 agent 持有整本书的认知（每章讲了什么、章间关系、整体结构）。

## Scout Step 2：写每章主题卡（type=主题，最先建）

主题卡是 L2 的入口，提供全局视野——整体论点、结构骨架。模拟"第二遍读书"的状态。

**基于整本书的认知，回头逐章建立主题卡**（跨章语境是 Scout 的价值所在）：

- card_id 命名：`<ns>:<章节号>`（如 `he:01`、`he:12`）
- 先 `loom browse <ns>` 检查 id 冲突——**已存在的主题卡不覆盖**
- 每张主题卡内容：该章整体论点 + 结构骨架 + 该章在整本书的位置

```bash
cat > /tmp/topic_<ch>.md <<'EOF'
# <章节标题> 主题

<一段话讲清这章在整本书的什么位置、讲什么、核心论点、结构骨架。约 100-300 字。>
EOF

loom write-draft $SCOUT_ID <ns>:<ch> \
  --type=主题 --title="<章节标题>" \
  --source=<ns>:<book>:src:<ch> \
  --layer=L2 \
  --content-file=/tmp/topic_<ch>.md
```

## Scout Step 3：报告完成

输出每张主题卡 card_id + 一句话主题。**不直接 commit**——commit 必须在计算层 + 语义自检之后通过 `commit-ready` 触发。

**所有主题卡写完后，调 `loom mark-ready $SCOUT_ID` 标记完成**（关键！否则 stop-check 扫描不到，drafts 不会 commit）：

```bash
loom mark-ready $SCOUT_ID
```

收尾按运行时区分：

- Claude Code：子 agent 退出后，SubagentStop hook 扫描所有 `.ready` 但未 done 的 task → 跑计算层校验。计算通过后 block 回 Scout agent，Scout agent 对主题卡做语义自检（主题卡通常只有几张，逐张判断 type_match/single_unit/genuine_digest/self_contained）。
- Codex：安装并信任 hooks 后，同样由 SubagentStop/Stop hook 自动触发 `loom-hook`；只有 hooks 未安装或未触发时，才手动调 `loom-admin stop-check-pending` 兜底。随后读取 `/tmp/loom_task/$SCOUT_ID/.semantic_sample.json` 做同样语义自检。

语义通过后调：

```bash
loom commit-ready $SCOUT_ID --semantic-passed
```

计算或语义失败 → 按 block reason 修 draft，重新 `mark-ready`。

---

# 主 agent 中转检查

Scout 子 agent 退出后，主 agent 验证：
1. `scout` task_trace status=done，committed_count > 0
2. `loom browse <ns>` 看到 N 张主题卡已入库
3. 对每章起 Deep 子 agent（并行）

---

# Deep 阶段（第二次子 agent，每章一个，并行 N 个）

## Deep Step 1：读该章 L1 全文 + 主题卡

```bash
loom read-source <ns>:<book>:src:<ch>
loom read-cards <topic_card_id> --task-id $DEEP_ID
```

此时子 agent 状态 = "已读过一遍"（持有该章全文 + 主题卡全局视野）。

## Deep Step 2：产出其余 L2 卡

基于全局视野，按需精读细节，识别独立认知单元。每个单元一张卡：

| 信号 | type |
|---|---|
| "这是什么" | 概念 |
| "由什么组成/怎么排列" | 结构 |
| "如何发生/为什么变化" | 机制 |
| "具体发生过什么" | 案例 |
| "结论是什么/为什么相信/为什么这样做" | 判断 |
| "某判断的适用条件/例外/反例" | 反思（必须 link 判断/模式卡）|

**密度判据**（来自 AGENTS.md）：
- 1 张卡 = 能用一句问句概括
- 简单概念 30 字够，复杂机制 800 字才讲清，看单元本身
- 禁止：总结型（塞多个单元）、目录型（<30 字）、抄录型（不改写）、碎片型（切碎单元）

card_id 命名：`<ns>:<ch><suffix>`（如 he:12a、he:12b、he:12r），避免与现有卡冲突。主题卡 `<ns>:<ch>` 是本章卢曼树根，Deep 卡作为其子节点延伸。

每张 L2 卡必须 `--source=<对应 L1 source card id>` 且 `--links=<topic_card_id>[,本材料内其他 L2 卡]`（008 §1）：

```bash
loom write-draft $DEEP_ID <ns>:<ch>a \
  --type=<type> --title="<标题>" \
  --source=<ns>:<book>:src:<ch> \
  --layer=L2 \
  --links=<topic_card_id>[,<本材料内其他相关 L2 卡>] \
  --content-file=<content file>
```

**DIGEST 完全 L4-blind**：不调 read-l4-index、不调 read-cards(L4 卡)、不 link L4 卡。
专注消化材料，不被元层干扰。L4 连接是后续 THINK 阶段的事。

发现新模式涌现时（可迁移的稳定结构），先在任务报告中记录 L4 候选：核心命题、可能跨哪些领域、需要锚定哪些 L2/L3 卡。不要在当前 L2 drafts 未入库前调用 `propose-l4`；正式提案等相关 L2/L3 已 `commit-ready` 入库后再做。

## Deep Step 3：发现可迁移结构 → L3 模式卡（默认）或 L4 提案（罕见）

- **L3 模式卡**：跨**材料**的可迁移结构（同领域多份材料反复出现的模式）。挂领域 namespace 下，用 `write-draft --layer=L3` 写。**这是默认出口**。
- **L4 候选**：跨**领域**的元层原理（脱离任何具体领域都成立的思考方式）。Deep 阶段只记录候选；正式 `propose-l4` 必须等相关 L2/L3 已入库后执行，再写 staging 等主 agent + 用户审核。

**判据**：跨材料 ≠ 跨领域。具体领域（如 LLM agent 工程）内部的跨材料模式是 L3，不是 L4。L4 罕见——大多数可迁移结构只是 L3。

### L3 模式卡写法

L3 必须 link 至少一张 L2 卡（008 §20；L1 可补充但不满足门槛）。ID 应反映该模式在领域树中的位置——它是螺旋探索中已确认的关系的产物，不是写卡后再去挂靠。具体规则见 `_loom_core.md`。

```bash
loom write-draft $DEEP_ID <ns>:<lujiman_id> \
  --type=模式 --title="<模式名>" \
  --layer=L3 \
  --links=<本材料主题卡>,<其他相关 L2 卡> \
  --content-file=<content 文件>
```

### L4 候选记录（仅当真跨域）

在 Deep 结果里写清楚：候选标题、核心结构命题、为什么不是单领域 L3、预期锚定哪些已产出的 L2/L3 卡。相关 L2/L3 通过 `commit-ready` 入库后，再由主 agent 或 THINK agent 用 `propose-l4` 写 staging。**不直接写 L4 库**——L4 演进必须经过 proposal / human review：主 agent 汇报用户 → 用户批准 → 主 agent 将 proposal JSON 的 status 改为 `"approved"` → 调 `loom-admin commit-l4 <proposal.json>` 入库。

## Deep Step 4：报告完成

所有 drafts 写完后，**报告任务完成**（不直接 commit——commit 由你在语义自检通过后显式触发）：

> 任务 $DEEP_ID 完成。drafts 里有 N 张卡。

**所有 L2 卡写完后，调 `loom mark-ready $DEEP_ID` 标记完成**（关键！否则 stop-check 扫描不到，不会进入校验）：

```bash
loom mark-ready $DEEP_ID
```

收尾按运行时区分：

- Claude Code：子 agent 退出 → SubagentStop hook 扫描所有 `.ready` 但未 done 的 task → 跑**计算层校验**（12 条单卡 + 4 条整批）
- Codex：安装并信任 hooks 后，同样由 SubagentStop/Stop hook 自动触发 `loom-hook`；只有 hooks 未安装或未触发时，才手动调 `loom-admin stop-check-pending` 兜底

- 计算层失败 → hook 返回 `decision:block` + 错误清单，子 agent 不能退出，按清单修 draft 后重新 `mark-ready`
- 计算层通过 → 写 `.computed_passed.json` + `.semantic_sample.json`，要求 agent 做语义自检

## Deep Step 5：语义自检 + commit-ready

计算层通过后，agent 必须完成语义质检再提交：

```bash
loom read-cards $(cat /tmp/loom_task/$DEEP_ID/.semantic_sample.json | python3.11 -c "import json,sys;print(' '.join(c['card_id'] for c in json.load(sys.stdin)['cards']))") --task-id $DEEP_ID
```

对抽样的每张卡逐项判断（来自 004 type 系统 + 密度门禁）：

- `type_match`：内容是否在回答 type 该回答的核心问题
- `single_unit`：能否用一句问句概括
- `genuine_digest`：真消化还是抄录原文
- `self_contained`：不看 source 能否独立读懂

- 语义失败 → 修 draft，重新 `loom mark-ready $DEEP_ID`（会重跑计算层 + 重新抽样）
- 语义通过 → 调 `loom commit-ready $DEEP_ID --semantic-passed` 整批入库，然后退出

```bash
loom commit-ready $DEEP_ID --semantic-passed
```

---

## 超时保护

主 agent 起子 agent 时用 `timeout 600`（10 分钟）。超时走 salvage 模式（`loom-admin stop-check <task_id> --mode=salvage`，只跑计算层并 block，不绕过语义；子 agent 仍需 commit-ready）。

## 关键约束

- **Scout 先于 Deep**——Deep 启动时该章主题卡必须已 commit
- **主题卡由 Scout 建**，不由 Deep 建——Deep 见到的主题卡是 Scout 已建的（"已读过一遍"状态的前提）
- **Scout 只写主题卡**，**Deep 不写主题卡**——由 write-draft 强制拦截
- **Deep 每章一个独立子 agent**——并行，互不污染
- **子 agent 必须调 mark-ready**——否则 stop-check 扫描不到，不会校验
- **Codex 也应走 hook 自动触发**——若 hooks 未安装/未信任/未触发，再手动 `loom-admin stop-check-pending` 兜底
- **L2 可以 link 本域内其他卡（含主题卡），但不建跨领域 link**——跨域关联是 L3 THINK 阶段的事。反思卡仍要锚定 判断/模式 卡
- L4/L3 不在 DIGEST 时强制建（除非材料本身触发明显生成/模式）
- 不预测卡数——按材料认知结构自然产出
- **commit 由子 agent 在语义自检通过后调 commit-ready 触发**——子 agent 不调 commit/stop-check/commit-l4；hook 和主 agent 审核流需要的特权命令走 `loom-admin`


---

> **必读前置**：执行下文任何步骤前，**必须先用 Read 工具读取** [`skills/_loom_core.md`](../_loom_core.md)。
> 共同铁律（commit 权限 / 命名规范 / 密度门禁 / 整批校验）是本 skill 的硬前置条件——**不读不开工**。
