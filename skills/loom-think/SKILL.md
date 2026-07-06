---
name: loom-think
description: 深入思考、反刍、跨域研究。基于已有 L1L2 产出 L3 生成卡、可能的 L4 新模式、或更新已有卡。不预设产出 layer。
---

# THINK 流程（深入思考）

## 何时触发

- 刚消化完一本书，把新卡接入已有网络（关联、对比、综合、反例）
- 用户提出研究方向（"研究安全边际的跨流派应用"）
- 反思某个已有判断
- 跨域类比（"金融的反身性和 AI 的反馈回路有什么共同结构"）

## 不预设 layer

产出可能是：
- L3 生成卡（跨材料综合判断、跨域类比、反例、实践沉淀）
- L4 新模式提案（从多个 L2L3 抽象出可迁移结构）
- 更新已有 L2/L3/L4 卡（深化、补反例、修正）
- 探索性思考——结论是"这条路不通"也算有效产出

## 第 1 步：写 plan.json

```bash
TASK_ID=$(...)
mkdir -p /tmp/loom_task/$TASK_ID/drafts
cat > /tmp/loom_task/$TASK_ID/plan.json <<EOF
{
  "task_id": "$TASK_ID",
  "task": "<研究方向>",
  "source": null,   # THINK 通常不绑定单一 L1
  "layer": "L3",    # 主目标 L3，过程中可能涌现 L4
  "skill": "THINK"
}
EOF
```

## 第 2 步：启动时定位

```bash
loom orient
```

读立体目录（namespace 全貌 + L4 全量含命题摘要）。这是 Loom 的"思考-激活"机制——主动拉取思考方向，不是被动检索。

## 第 3 步：反复过程（查询 → 关联 → 思考 → 再查询，过程显式化前置呈现）

**核心要求**：思考过程必须对外显式化，并且**在产出 drafts 之前**呈现给用户——不是事后总结，是让用户跟着你走完整条认知路径，看到每个研究方向如何被检索验证、修正、推翻或扩展。

**每轮检索都要讲清楚**：
- 你现在的假设 / 研究方向 / 想验证什么
- 你调了什么工具、看了什么卡
- 你具体发现了什么（与预期对比）
- 这如何改变了你的想法（确认 / 推翻 / 扩展），暴露了什么新方向，下一步查什么、为什么

**格式由你决定**——段落、清单、对比表、嵌套结构，哪种能讲清就用哪种。不要把这一步变成填表，填表式的 narrate 不算思考。

**效果要求**：广度和深度都到位。

- 广度：研究方向涉及的视角要覆盖到——跨 namespace、跨层级、包括表面无关但结构等同的联系
- 深度：不停在标题层——相关的卡要深入到 content 的具体内容、实例、边界
- 深入一张卡可能暴露新方向（深度推动广度），新方向可能需要深入（广度推动深度）
- 循环到新的深度不再激发新的广度方向时 = 信息饱和

如果准备用某个 L4/L3 模式作为框架——先 `read-cards <id> --task-id $TASK_ID` 读完整 content，再 `neighbors` 看关联卡（反思/反例），确认该模式在此场景成立。标题对上 ≠ 模式适用。

**工具按需组合，没有正确顺序**：

```bash
loom search "<查询>" --mode=hybrid --top=10          # 关键词 + 语义
loom browse-tree <namespace>                          # 领域骨架全貌
loom children <主题卡ID>                              # 展开结构
loom siblings <卡ID>                                  # 兄弟卡
loom neighbors <卡ID> --depth=1                       # link 图
loom skim <id>                                        # 快速判断相关性
loom read-cards <id1> <id2> --task-id $TASK_ID        # 批量深读 + 记录 read trace / L4 refs
loom wander <卡ID>                                    # 随机偏航
# L4 模式的结构等同性判断（认知操作，不是工具）
# 面对新问题时自己判断：这个问题的结构是否等同某 L4 模式？
```

**饱和自检（不再 narrate 新轮次前问自己）**：
- 我只用了 search 一种入口，还是也看过领域骨架、走过随机方向？
- 有没有一整块相关视角我完全没覆盖？
- 用到的模式卡，我读过完整 content 和它的反思/反例卡吗？
- 连续检索返回的信息已经和之前重复了吗？（= 饱和信号）
- 不同 namespace 的卡之间有没有隐藏的结构等同？

## 第 4 步：产出 drafts

前面的螺旋 narrate 已经展示了思考路径，现在把识别出的新认知单元写到 drafts/：

```bash
# L3 生成卡（必须 link 至少一张 L2；L1 可补充但不满足门槛，008 §20）
loom write-draft $TASK_ID <ns>:<id> \
  --type=<type> --title="<标题>" \
  --links=<至少一张 L2>[,其他 L1L3] \
  --content-file=<content>

# 反思卡（必须锚定 判断/模式 卡）
loom write-draft $TASK_ID <ns>:<id> \
  --type=反思 --title="<标题>" \
  --links=<一张判断或模式卡> \
  --content-file=<content>

# 发现新模式 → 提案（L4 演进必须 proposal/human review，不自动入库）
# card_id 是 gen:<卢曼ID>，按卢曼树形：新顶级模式用 gen:Na，已有模式 gen:Xa 的深化用 gen:XaY
loom propose-l4 $TASK_ID gen:<卢曼ID> --title="<模式名>" \
  --content-file=<content with [探索期]> \
  --related=<相关卡ID>
# 提案写到 staging/，主 agent 汇报用户→用户决策→proposal-decision→commit-l4 入库
# 若 L4 提案 ID 与已有/待审提案冲突：不要只拒绝导致内容丢失；先保留更早提案，再为有价值的后发内容选择未占用 gen:<卢曼ID> 重新 propose-l4，并在汇报中说明旧提案→新提案映射。
```

长思考中按需或阶段性重读 L4 索引（轻量版，仅标题列表），用于刷新思考方向；不要为了合规在每张卡后机械调用：
```bash
loom read-l4-index
```

思考发现某张已有卡需要补 link（语义近但未连），用：
```bash
loom suggest-links <id>   # 找未 link 的语义近邻
```

## 第 5 步：更新已有卡（可选）

思考发现某张卡需要修正（L2/L3/L4 通用）——通过提案机制走 staging 闭环：

```bash
# 1. 读原卡获取当前内容
loom read-cards <card_id> --task-id $TASK_ID

# 2. 编辑成完整新版后提案（全量替换语义）
loom propose-card-edit $TASK_ID <card_id> \
  --type=修正 \
  --content-file=<完整新版content>
```

主 agent 用户审核后通过 `loom-admin apply-card-edit` 入库。内容修正（修漏、修错、补前提）用 `--type=修正`；发现有反例/边界否定了原有命题，应建反思卡锚定而非改原卡（§4）。

## 第 6 步：mark-ready → 语义自检 → commit-ready

```bash
loom mark-ready $TASK_ID
```

收尾按 hook 状态区分：

- Claude Code：SubagentStop hook 扫 `.ready` 跑计算层校验。计算通过后会 block 回来，要求你读 `.semantic_sample.json` 做语义自检（type_match / single_unit / genuine_digest / self_contained）。
- Codex：安装并信任 hooks 后，同样由 SubagentStop/Stop hook 自动触发 `loom-hook`。只有 hooks 未安装或未触发时，才手动调 `loom-admin stop-check-pending` 兜底。

通过后：

```bash
loom commit-ready $TASK_ID --semantic-passed
```

失败则修 draft，重新 `mark-ready`。

## 关键约束

- L3 卡必须 link 至少一张 L2 卡（008 §20；L1 可补充但不满足门槛）
- L3/L4 的 `source` 字段不强制（008 §17）；依据靠 links 表达
- 反思卡必须 link 一张判断/模式卡
- L4 涌现走提案通道，不自动入库
- THINK 不预设卡数——思考深度决定产出密度


---

> **必读前置**：执行下文任何步骤前，**必须先用 Read 工具读取** [`skills/_loom_core.md`](../_loom_core.md)。
> 共同铁律（commit 权限 / 命名规范 / 密度门禁 / 整批校验）是本 skill 的硬前置条件——**不读不开工**。
