---
name: loom-pipeline
description: 多资源并行全链路编排——把 N 个任意格式资源一路跑到 L3/L4。当用户给一批资源（多本书/PDF/视频）要"端到端消化"、"批量处理"、"全链路跑通"时加载。所有阶段统一并发 ≤ 8。
---

# PIPELINE — 多资源并行全链路

## 何时用

- 用户给 N 个任意格式资源（PDF/EPUB/视频等），要端到端消化到 Loom 网络
- "批量处理 sources/01-金融 这批 PDF"
- "把这几本书跑通全流程"
- 单本消化走 DIGEST.md / THINK.md 即可，不需要本流程

## 核心承诺

- **不写新代码**：所有能力已就绪（resource-to-markdown skill / loom / DIGEST.md / THINK.md）
- **不调外部 LLM API**：主 agent 用当前运行时可用的子 agent/并行能力批量执行，子 agent 加载现有 skill
- **所有阶段并发 ≤ 8**：不触发 API 限速

## 全流程：5 阶段编排

```
阶段 1  INGEST         N 本 → markdown        sub agent × N（分批 ≤ 8）
阶段 2  SCOUT          每本建主题卡            sub agent × N（分批 ≤ 8）
阶段 3  DEEP           每章产 L2 卡            sub agent × N×M（分批 ≤ 8）
阶段 4  PER-BOOK THINK 每本接入已有网络        sub agent × N（分批 ≤ 8）
阶段 5  CROSS THINK    跨材料综合 + L4 抽象    sub agent × 1
```

## 子 agent 收尾协议（所有阶段通用）

每个产 drafts 的子 agent，退出前必须完成：

1. `loom mark-ready $TASK_ID` —— 写 `.ready`
2. 跑计算层校验（12 单卡 + 4 整批）：
   - Claude Code：SubagentStop hook 自动跑，计算通过后会 block 回来
   - Codex：安装并信任 hooks 后，SubagentStop/Stop hook 自动跑 `loom-hook`；hooks 未安装/未触发时手动 `loom-admin stop-check-pending` 兜底
3. agent 读 `/tmp/loom_task/$TASK_ID/.semantic_sample.json`，对抽样的卡做语义自检（type_match / single_unit / genuine_digest / self_contained）
4. 语义通过 → `loom commit-ready $TASK_ID --semantic-passed` 整批入库
5. 任一层失败 → 修 draft，重新 `mark-ready`（重跑计算 + 重新抽样）

**不再有"hook 自动 commit"**——commit 由子 agent 在语义自检通过后显式触发。主 agent 验收时查 `task_trace.status=done` 即可。

**两阶段 THINK 的理由**：
- 4 每本一个：单本深度足、context 不爆、趁热接入网络
- 5 单个跨所有：需要全局视野才能找跨书共性 / 抽象 L4

---

## 阶段 1: INGEST（任意格式 → markdown）

**主 agent 操作**：

每本书起一个 INGEST sub agent。N ≤ 8 全开，> 8 分批。

**为每本书准备**：
```bash
# 无需 task 目录——INGEST 产出是文件不是卡片，不入库
# 只需指定输出目录
BOOK_DIR="sources/<领域>/<编号>-<书名>"
```

**起 sub agent**（用当前运行时可用的并行能力；Claude Code 可一条消息发多个 Task tool call）：

```
你是 Loom 的 INGEST 子 agent。

加载 skill：skills/resource-to-markdown/SKILL.md

输入：<file>
输出目录：<BOOK_DIR>/

按 skill 指引调 convert.py 工具转换，看 quality.json 决定接受/重试/放弃。
产出 ch01.md, ch02.md, ... 落到 <BOOK_DIR>/。

报告：引擎 / 字数 / 章节数 / 质量判定（accept/warning/failed）。
```

**等所有 INGEST 完成**：失败的标 L1 跳过后续阶段。

---

## 阶段 2: SCOUT（每本建主题卡）

**前提**：阶段 1 全 done（每本有 chXX.md）。

**主 agent 操作**：每本书起一个 Scout sub agent。

```bash
for book in <book_list>; do
  SCOUT_ID=scout_${book}_$(date +%s)
  mkdir -p /tmp/loom_task/$SCOUT_ID/drafts
  cat > /tmp/loom_task/$SCOUT_ID/plan.json <<EOF
{
  "task_id": "$SCOUT_ID",
  "phase": "scout",
  "task": "Scout《<书名》建主题卡",
  "book": "sources/<领域>/<book_dir>",
  "chapters": ["ch01.md", "..."],
  "layer": "L2",
  "skill": "DIGEST"
}
EOF
done
```

**起 sub agent**（每本一个）：

```
你是 Loom 的 Scout 子 agent。

加载 skill：skills/loom/DIGEST.md，按 §Scout 流程执行。

任务 ID：$SCOUT_ID
书目录：sources/<领域>/<book_dir>/
namespace：<ns>（如 fin:kahneman）

按 DIGEST.md §Scout：
1. 分次 read-source 所有 chXX.md
2. 写每章主题卡（type=主题，layer=L2）
3. 调 `loom mark-ready $SCOUT_ID`

退出前不要直接 commit；按本文件“子 agent 收尾协议”完成计算层和语义层后再 `commit-ready`。
```

**等所有 Scout 完成**：
```bash
loom stats                                  # task_trace 看 scout_* 全 done
loom browse <ns>                            # 每本 namespace 有 N 张主题卡
sqlite3 ~/.loom/data/brain.db "SELECT task_id, status FROM task_trace WHERE task_id LIKE 'scout_%'"
```

---

## 阶段 3: DEEP（每章产 L2 卡）

**前提**：阶段 2 全 done（所有主题卡已 commit）。

**主 agent 操作**：

收集所有 (book, chapter) 对，按 8 一批切。

```bash
# 为每章准备 task
for book in <book_list>; do
  for ch in $(ls sources/<领域>/${book}/ch*.md | xargs -n1 basename); do
    DEEP_ID=deep_${book}_${ch%.md}_$(date +%s)
    mkdir -p /tmp/loom_task/$DEEP_ID/drafts
    cat > /tmp/loom_task/$DEEP_ID/plan.json <<EOF
{
  "task_id": "$DEEP_ID",
  "phase": "deep",
  "task": "Deep ${book} ${ch} 产 L2 卡",
  "chapter": "${ch}",
  "topic_card": "<ns>:<章节号>",
  "layer": "L2",
  "skill": "DIGEST"
}
EOF
  done
done
```

**起 sub agent**（分批 ≤ 8）：

```
你是 Loom 的 Deep 子 agent。

加载 skill：skills/loom/DIGEST.md，按 §Deep 流程执行。

任务 ID：$DEEP_ID
章节：sources/<领域>/${book_dir}/${ch}
主题卡 <ns>:<章节号> 已 commit，只读不建

按 DIGEST.md §Deep：
1. read-source 章节全文 + read-cards 主题卡
2. 产出 L2 卡（概念/结构/机制/案例/判断/反思）
3. 调 `loom mark-ready $DEEP_ID`
```

**分批策略**：
- 第 1 批 8 个 → 等全 done
- 第 2 批 8 个 → 等全 done
- ...

**等所有 Deep 完成**：
```bash
loom browse <ns>           # 每本 namespace 有 N+M 张卡（主题 + L2）
loom stats
```

---

## 阶段 4: PER-BOOK THINK（每本接入已有网络）

**前提**：阶段 3 全 done（所有 L2 卡已 commit）。

**为什么每本一个**：单本深度足、context 不爆、趁热做关联。

**主 agent 操作**：每本书起一个 THINK sub agent。

```bash
THINK_ID=think_${book}_connect_$(date +%s)
mkdir -p /tmp/loom_task/$THINK_ID/drafts
cat > /tmp/loom_task/$THINK_ID/plan.json <<EOF
{
  "task_id": "$THINK_ID",
  "task": "${book} 接入已有网络",
  "source": null,
  "layer": "L3",
  "skill": "THINK"
}
EOF
```

**起 sub agent**（每本一个，分批 ≤ 8）：

```
你是 Loom 的 THINK 子 agent。

加载 skill：skills/loom/THINK.md

任务 ID：$THINK_ID
目标：把《<书名>》的 L2 卡接入 Loom 已有网络

namespace：<ns>
这本书核心论点：<主 agent 用一句话概括给起点>

按 THINK.md：
1. orient 看 Loom 已有思考方向和领域全貌
2. 广度×深度互相推动：search 跨领域、browse-tree 看骨架、read-cards 深读相关卡
3. 产出 L3 卡：跨领域关联 / 对比 / 综合
4. 发现可迁移模式 → propose-l4
5. 调 `loom mark-ready $THINK_ID`
```

**等所有 4 完成**后进阶段 5。

---

## 阶段 5: CROSS-BOOK THINK（跨材料综合）

**前提**：阶段 4 全 done（所有书接入网络）。

**主 agent 操作**：起 1 个 THINK sub agent，全局视野。

```bash
THINK_ID=think_<topic>_cross_$(date +%s)
mkdir -p /tmp/loom_task/$THINK_ID/drafts
cat > /tmp/loom_task/$THINK_ID/plan.json <<EOF
{
  "task_id": "$THINK_ID",
  "task": "跨材料综合：<研究方向>",
  "source": null,
  "layer": "L3",
  "skill": "THINK"
}
EOF
```

**起 sub agent**（1 个）：

```
你是 Loom 的 THINK 子 agent。

加载 skill：skills/loom/THINK.md

任务 ID：$THINK_ID
研究方向：<主 agent 概括的跨材料主题，例如：
  "金融判断偏差的跨流派共性——Kahneman 偏误 / Douglas 交易心理 / Bernstein 风险史
   三本共同指向什么 L4 模式？相互有什么对比/补充？">

已消化的 namespace 列表：
- fin:kahneman
- fin:douglas
- fin:bernstein

按 THINK.md：
1. orient 看已有 L4 模式和领域全貌
2. 广度×深度互相推动：search 跨 namespace、browse-tree 各书骨架、read-cards 深读
3. 找跨书模式：共性 / 对比 / 综合
4. 产出 L3 综合卡（必须 link ≥ 2 个不同 namespace 的 L2）
5. 涌现新 L4 → propose-l4（关键产出）
6. 调 `loom mark-ready $THINK_ID`
```

**等 done**：
```bash
loom browse fin
loom orient
ls /tmp/loom_task/$THINK_ID/staging/   # L4 提案
```

**L4 / 卡片更新提案回流**：主 agent 扫描 `staging/` 后，必须把每份提案完整讲给用户审核；用户批准后，只有主 agent 调 `loom-admin commit-l4 <proposal.json>` 或 `loom-admin apply-card-edit <proposal.json>` 入库，pipeline 子 agent 不调用 `loom-admin`。

---

## 并发控制（所有阶段统一）

**每批 ≤ 8**（不触发 API 限速，留余量给主 agent + hook）：

| 阶段 | 总任务 | 并行模式 |
|---|---|---|
| 1 INGEST | N | N ≤ 8 全开；> 8 分 ⌈N/8⌉ 批 |
| 2 Scout | N | 同上 |
| 3 Deep | N×M | 分批 ≤ 8（每批 8 章） |
| 4 PER-BOOK | N | N ≤ 8 全开；> 8 分批 |
| 5 CROSS | 1 | 单跑 |

**运行时实现**：Claude Code 可一条消息里发多个 Task tool call → 并行执行；Codex 使用可用的子 agent/并行工具。两者都通过 hooks 收尾；Codex hooks 未触发时，主 agent 分批后手动 `loom-admin stop-check-pending` 兜底。

**硬约束**：
- 不跨阶段并行（Scout 和 Deep 不能同时跑，Deep 依赖 Scout 的主题卡）
- 不 3a + 3b 同时跑（3b 需 3a 全部接入完）

---

## 状态检查 Cheat Sheet

```bash
# 总览
loom stats
loom namespaces

# 单 namespace 看卡结构
loom browse <ns>
loom children <ns>:01

# 任务 trace（哪些 done、哪些 reject）
sqlite3 ~/.loom/data/brain.db "SELECT task_id, status, drafts_count, committed_count FROM task_trace ORDER BY started_at DESC LIMIT 30"

# L4 索引
loom orient

# 看 L4 提案
ls /tmp/loom_task/<think_task_id>/staging/
```

## 失败处理

| 阶段 | 失败 | 处理 |
|---|---|---|
| 1 INGEST | quality.json status≠ok | INGEST sub agent 自主决策；失败的标 L1 跳过后续阶段 |
| 2 Scout | task_trace.status=failed | 看 reject_log，重起该本 Scout |
| 3 Deep | 同上 | 单章失败不影响其他章，重起该章 Deep |
| 4 PER-BOOK | 同上 | 单本失败不影响其他本；该本跳过 |
| 5 CROSS | 同上 | 通常不 reject（产出开放），重起即可 |

## 例子：处理 5 本金融 PDF

```
输入：sources/01-金融/{12-Kahneman.pdf, 05-Douglas.pdf, 13-Kindleberger.pdf, 02-Bernstein.pdf, 01-金融怪杰.epub}

阶段 1（5 并行，一条消息发 5 Task）：
  → 5 个 sources/01-金融/<book>/ch*.md 就绪

阶段 2（5 并行）：
  → fin:kahneman:01..05, fin:douglas:01..04, ... 共 ~25 张主题卡

阶段 3（按 8 切批，假设共 30 章）：
  批 1: 8 个 Deep
  批 2: 8 个 Deep
  批 3: 8 个 Deep
  批 4: 6 个 Deep
  → ~150 张 L2 卡入库

阶段 4（5 并行）：
  → 5 × ~3 张 L3 关联卡 = 15 张 L3

阶段 5（1 个）：
  → 3-5 张跨书综合 L3 + 1-2 个 L4 模式提案
```

## 不在本文档范围

- 卡片密度校验（AGENTS.md + checks.py）
- L4 提案审核流程（DIGEST.md §Step 3）
- USE 流程（用户问问题时用，不在端到端流水线里）
- resource-to-markdown skill 内部实现（skills/resource-to-markdown/SKILL.md）


---

> **必读前置**：执行下文任何步骤前，**必须先用 Read 工具读取** [`skills/_loom_core.md`](../_loom_core.md)。
> 共同铁律（commit 权限 / 命名规范 / 密度门禁 / 整批校验）是本 skill 的硬前置条件——**不读不开工**。
