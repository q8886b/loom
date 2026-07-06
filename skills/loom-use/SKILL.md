---
name: loom-use
description: 用卡片网络回答具体问题、做决策、做复盘。默认只回答；必要时提示沉淀机会，显式进入独立沉淀步骤后才产出 L3 实践卡或反思卡。
---

# USE 流程（用网络回答问题）

## 何时触发

- 用户问问题（"X 是什么？X 在 Y 场景下怎么用？"）
- 用户做决策（"我该选 A 还是 B？基于 Loom 我的知识"）
- 用户做复盘（"这次失败的根本原因是什么？"）

## 联网边界

USE 默认只用 Loom 本地卡片网络回答，不联网；除非用户当轮明确要求联网查询或外部验证。

## 卡片依据呈现

回答需要把关键卡片内容呈现出来，不只给结论：列出支撑卡片的 `id` / title，并摘出或转述卡片里直接支撑结论的内容。适当时再沿卡片 `source` 读取 L1 原文；若只用卡片，明确说明依据层级是卡片。

## 第 1 步：写 plan.json

```bash
TASK_ID=$(...)
mkdir -p /tmp/loom_task/$TASK_ID/drafts
cat > /tmp/loom_task/$TASK_ID/plan.json <<EOF
{
  "task_id": "$TASK_ID",
  "task": "<问题/决策/复盘描述>",
  "source": null,
  "layer": "L3",
  "skill": "USE"
}
EOF
```

`layer=L3` 只表示"如果本次明确进入沉淀，draft 的目标层是 L3"；不表示 USE 必须产出卡片。

## 第 2 步：启动时定位

```bash
loom orient
```

读立体目录（namespace 全貌 + L4 全量含命题摘要）。这是"思考-激活"的入口——看到 Loom 沉淀的思考方向，回答问题时主动用上相关 L4 模式。

## 第 3 步：反复检索 + 思考（过程显式化，前置呈现）

**核心要求**：思考过程必须对外显式化，并且**在产出答案之前**呈现给用户——不是事后总结，是让用户跟着你走完整条认知路径，看到每个假设如何被验证、修正、推翻或扩展。

**每轮检索都要讲清楚**：
- 你现在的假设 / 想验证什么
- 你调了什么工具、看了什么卡
- 你具体发现了什么（与预期对比）
- 这如何改变了你的想法（确认 / 推翻 / 扩展），暴露了什么新方向，下一步查什么、为什么

**格式由你决定**——段落、清单、对比表、嵌套结构，哪种能讲清就用哪种。不要把这一步变成填表，填表式的 narrate 不算思考。

**效果要求**：广度和深度都到位。

- 广度：与问题相关的视角要覆盖到——跨 namespace、跨层级、包括表面无关但结构等同的联系
- 深度：不停在标题层——相关的卡要深入到 content 的具体内容、实例、边界
- 深入一张卡可能暴露新方向（深度推动广度），新方向可能需要深入（广度推动深度）
- 循环到新的深度不再激发新的广度方向时 = 信息饱和

如果准备用某个 L4/L3 模式作为框架——先 `read-cards <id> --task-id $TASK_ID` 读完整 content，再 `neighbors` 看关联卡（反思/反例），确认该模式在此场景成立。标题对上 ≠ 模式适用。

**工具按需组合，没有正确顺序**：

```bash
loom search "<问题关键词>" --mode=hybrid --top=10   # 关键词 + 语义
loom browse-tree <namespace>                         # 领域骨架全貌
loom children <主题卡>                               # 展开结构
loom neighbors <相关卡> --depth=1                    # link 图
loom skim <id>                                       # 快速判断相关性
loom read-cards <id1> <id2> <id3> --task-id $TASK_ID # 批量深读 + 记录 read trace / L4 refs
loom wander <相关卡>                                 # 随机偏航
```

**饱和自检（不再 narrate 新轮次前问自己）**：
- 我只用了 search 一种入口，还是也看过领域骨架、走过随机方向？
- 有没有一整块相关视角我完全没覆盖？
- 用到的模式卡，我读过完整 content 和它的反思/反例卡吗？
- 连续检索返回的信息已经和之前重复了吗？（= 饱和信号）

## 第 4 步：回答

**先直接回答用户**——前面的螺旋 narrate 已经展示了思考过程，这里给出经过验证的完整答案。

默认到这里结束，不写卡。

只有出现新的、可复用、可支撑的判断 / 反思 / 实践模式时，才提示一次沉淀机会：候选标题、type、价值、支撑卡。临时查询、复述已有卡、支撑不足、凑流程的候选，不提示。

## 第 5 步：独立沉淀（仅在明确触发时）

仅当用户确认，或原始请求明确要求"形成卡片 / 入库 / 沉淀"时，才写 drafts。

写前检查：一句话可概括、自足、非复述、满足 layer/type/link 规则。通过后再写：

```bash
# L3 实践卡（具体问题的解法、决策依据；必须 link 至少一张 L2）
loom write-draft $TASK_ID <ns>:<id> \
  --type=判断 --title="<决策/结论>" \
  --links=<支撑的 L2 卡>,<相关的 L4 卡> \
  --content-file=<content>

# 反思卡（复盘某判断的适用条件）
loom write-draft $TASK_ID <ns>:<id> \
  --type=反思 --title="<反思标题>" \
  --links=<被反思的判断或模式卡> \
  --content-file=<content>
```

已存在卡需要补 link 时，只提示；用户确认后再维护。找候选近邻用 `loom suggest-links <id>`。

## 第 6 步：mark-ready → 语义自检 → commit-ready（仅当有 drafts）

没写 drafts 就直接结束。

如果产出了 drafts：

```bash
loom mark-ready $TASK_ID
```

收尾按 hook 状态区分：

- Claude Code：SubagentStop hook 扫 `.ready` 跑计算层校验，计算通过后 block 回来要求语义自检。
- Codex：安装并信任 hooks 后，同样由 SubagentStop/Stop hook 自动触发 `loom-hook`。只有 hooks 未安装或未触发时，才手动调 `loom-admin stop-check-pending` 兜底。

计算通过后读 `/tmp/loom_task/$TASK_ID/.semantic_sample.json`，判断 type_match / single_unit / genuine_digest / self_contained，通过后：

```bash
loom commit-ready $TASK_ID --semantic-passed
```

失败则修 draft，重新 `mark-ready`。

## 关键约束

- USE 主产出是回答 / 决策 / 复盘；沉淀是独立后续动作
- 不要每次 USE 都提议建卡；只有新的、可复用、可支撑的认知单元才提示一次
- 未经明确触发，不写 draft、不 mark-ready、不 commit-ready
- L3 卡必须 link 至少一张 L2 卡（008 §20；L1 可补充但不满足门槛）
- L3/L4 的 `source` 字段不强制（008 §17）
- 反思卡必须锚定判断/模式卡
- 沉淀宁缺毋滥，只保存值得复用的新增认知


---

> **必读前置**：执行下文任何步骤前，**必须先用 Read 工具读取** [`skills/_loom_core.md`](../_loom_core.md)。
> 共同铁律（commit 权限 / 命名规范 / 密度门禁 / 整批校验）是本 skill 的硬前置条件——**不读不开工**。
