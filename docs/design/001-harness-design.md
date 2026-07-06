# 001 — Harness 设计

> 把密度门禁从"prompt 层"下沉到"tool 层 + orchestration 层"。
> 解决"规则写得清楚但 agent 仍违反"的根因。

## 1. 问题

历史上观察到 agent 反复违反密度门禁，尽管 AGENTS.md 写得清楚：

| 失败 | 实测样本 |
|---|---|
| 总结型 | 民诉法解释 14 张 / 1102 行材料 = 每张 ~78 行原文，单张塞 5 个独立机制 |
| 漏 link | content 有"见 law:6a"但 link 表无记录（多张） |
| ID 撞车 | 多次：law:13、law:11、law:12 都被新批 agent 撞旧批 |
| 孤立卡 | law namespace 孤立率 14.7%（52/353） |
| 目录型 | 部分 content < 30 字 |

每次失败我们的反应是"改 AGENTS.md 加规则"——这正是 Anthropic 警告的反模式：

> If the agent makes the same mistake twice, do not add another paragraph to the prompt.
> Turn the mistake into a test, hook, skill, CI check, or repo instruction.

## 2. 三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  L3  Orchestration（编排层，事后）                              │
│    • Lint Runner：lint_card.py / lint_chunk.py                  │
│    • Agent-as-Judge：spawn 独立 agent 抽查语义质量（可选）      │
│    • Scheduler：主 agent 协调子 agent，按 lint 结果驱动修复     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L2  Tool 层（带 guardrails，机器强制）                          │
│    store.py + tools.py                                          │
│    • create_card / update_card：                                │
│      - 自动 grep "见 X" → 建 link                              │
│      - 列举型检测 → 拒绝                                       │
│      - 长度门禁 → 拒绝                                         │
│      - type 合法性 → 拒绝                                      │
│    • get_next_id：返回空闲顶层 ID                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  L1  Skill 层（指令，原则性，靠 agent 自觉）                     │
│    SKILL.md + AGENTS.md                                         │
│    认知循环、密度门禁、8 种 type 定义                            │
│    → 这层给原则，但**不靠它强制执行**                            │
└─────────────────────────────────────────────────────────────────┘
```

### 关键约束

**禁止直接 API 调用 LLM**（项目约束）。
- L2 guardrails：纯算法（正则 / SQL / 计数）✓
- L3 Lint：纯算法 ✓
- L3 Agent-as-Judge：必须通过 spawn 子 agent（Agent tool），不直接 API

## 3. 失败模式 × 对应组件

| 失败模式 | 解法 | 所在层 | 检测方法 |
|---|---|---|---|
| 总结型（列举特征） | create_card 拒绝 | L2 | `re.findall(r"第\d+条", content)` ≥ 3 且 type ∉ {结构, 比较} |
| 总结型（语义级，无列举） | Agent-as-Judge | L3 | LLM 评判"一句问句能问完吗" |
| 漏 link | create_card 自动建 | L2 | grep `见\s*(law\|med\|gen):[a-zA-Z0-9]+` → 自动 link |
| ID 撞车 | get_next_id 工具 | L2 | SQL 查已用顶层 ID |
| 孤立卡 | lint_chunk 报告 | L3 | SQL count links |
| 目录型 | create_card 拒绝 | L2 | `len(content) < 30` |
| type 非法 | create_card 拒绝 | L2 | 不在 8 种合法集 |
| 抄录型 | lint_card 警告 | L3 | 与 source 字符串相似度（可选） |

## 4. 工作流程

### 一个 agent 的完整生命周期

```
[1] Pre-flight
    │   agent 调 get_next_id("law")
    │   → 工具读 DB 返回空闲顶层 ID（如 law:24）
    │   agent 调 search 看现有相关卡，避免重复
    ▼
[2] In-flight（每次 create_card）
    │   L2 guardrails 实时检查：
    │    ✗ 列举型 → 返回 ERROR，agent 必须重新设计这张卡
    │    ✗ content < 30 字 → 返回 ERROR
    │    ✗ type 非法 → 返回 ERROR
    │    ✓ 通过 → 写卡 + 自动从 content 建 link
    │   agent 不需要记得"建 link"——工具替它建
    ▼
[3] agent 报告完成
    ▼
[4] Post-flight Lint
    │   跑 lint_chunk.py law:24
    │   输出：孤立率、type 分布、未建 link、跨区重复
    │
    ├─ 有 ERROR → SendMessage 给 agent 要求修复 → 回 [2]
    │
    ▼
[5] Agent-as-Judge（可选，抽样 10 张）
    │   spawn 独立 agent
    │   给它 10 张随机卡 + checklist
    │   返回：通过 / 不通过 + 问题卡列表
    │
    ├─ 不通过 → 加入回炉队列 → 回 [2]
    │
    ▼
[6] 通过 → 该 ID 区"出库"，进入向量化队列
```

### 主 agent 协调流程

```
spawn N 个 agent → 等通知 →
  for each completed agent:
    1. 跑 lint_chunk 该 agent 工作的 ID 区
    2. 若 ERROR > 0：
       - SendMessage 给该 agent（如果还活着）要求修复
       - 或 spawn 新 agent 重做
    3. 通过后，可选 spawn 1 个 judge agent 抽查
    4. 进入下一批
```

## 5. Guardrails 规则表（详细）

### create_card / update_card 输入校验

| 规则 | 检测 | 动作 | 阈值依据 |
|---|---|---|---|
| 长度下限 | `len(content) < 30` | 拒绝 | 目录型特征：只列名称不解释 |
| 列举型 | `len(re.findall(r"第\d+条", content)) >= 3` AND `type not in {"结构", "比较"}` | 拒绝 | 总结型特征：列举多条独立规则 |
| type 合法 | `type not in VALID_TYPES` | 拒绝 | 系统约束 |
| ID 格式 | `re.match(r"^[a-z]+:\d{1,2}([a-z]\d*)*$", id)` | 拒绝 | 卢曼 ID 规则 |

### create_card 自动行为

| 行为 | 触发 | 实现 |
|---|---|---|
| 自动建 link | content 含 `见\s*(law\|med\|gen):([a-zA-Z0-9]+)` | 提取目标 ID，调内部 link 函数 |
| 拒绝循环 link | link 目标 == 自身 | 跳过 |

### L3 Lint 规则

| 规则 | 严重度 | 触发 | 豁免 |
|---|---|---|---|
| 孤立卡 | WARN | 0 out-link AND 0 in-link AND content 不含"见 X" | 无 |
| 漏 link | ERROR | content 提"见 X" 但 links 表无 | 无 |
| 无意义 link | WARN | link 表有 X 但 content 不提 | 父子（target 是 parent）；中心卡（in_links ≥ 5） |
| 总结型嫌疑 | WARN | "第X条"≥3 次 | type ∈ {结构, 比较} |
| 长度异常 | WARN | < 50 字 OR > 1500 字 | 无 |
| type 不一致 | INFO | 启发式（如比较卡没有"A vs B"） | 无 |

## 6. 阈值依据（避免拍脑袋）

### 列举型阈值"≥ 3 次"的依据

跑 lint_card 测了公司法 86 张存量卡：
- 比较卡（type=比较）平均含 "第\d+条" 12 次 → 必须豁免
- 结构卡（type=结构）平均含 7 次 → 必须豁免
- 机制卡（type=机制）平均含 2-3 次 → 3 是合理阈值
- 实际 lint 公司法 86 张抓到 11 张机制卡的总结型嫌疑（13%），人工抽样核对：误报率 ~40% → 阈值仍可调到 4 或 5

**修订**：先按 ≥ 3 起步，跑完存量后统计误报率再调。

### 长度下限"30 字"的依据

```
30 字 ≈ "第1062条：夫妻共同财产范围包括 5 类"（17字）+ 一句话解释（13字）
```
低于 30 字几乎肯定没解释清楚。

### 中心卡豁免"in_links ≥ 5"的依据

公司法 law:14（总览）in_links = 86（所有子卡都连它）。
公司法 law:14g（注册资本）in_links = 6。
两者都合理有"无 content 提及"的子卡 link（父子关系）。
5 是分水岭：≥ 5 几乎肯定是中心枢纽卡。

## 7. 实施阶段

| Phase | 内容 | 预估 | 依赖 |
|---|---|---|---|
| 0 | 暂停扩张，等当前 agent 完成 | 5-15 min | - |
| 1 | 写本文档 | 15 min | - |
| 2 | L2 store.py guardrails + get_next_id | 30 min | Phase 0 完成 |
| 3 | L3 lint 完善误报 + lint_chunk | 30-45 min | Phase 2 |
| 4 | 存量回炉（lint 492 张） | 30-60 min | Phase 3 |
| 5 | Agent-as-Judge 抽查 | 5 min | Phase 4 |
| 6 | SKILL.md / AGENTS.md 同步 | 10 min | Phase 2 |
| 7 | 新批 agent 用新 harness | 同前 | Phase 6 |

总计：**~2-3 小时**完成 harness 建设。

## 8. 验收标准

harness 建好后，对新批 agent 必须满足：

- [ ] agent 调 `get_next_id` 自动获取 ID，不再撞车
- [ ] agent 不需要手动 `link`，create_card 自动建
- [ ] 列举型卡被工具直接拒绝（agent 收到 ERROR 必须重新设计）
- [ ] post-flight lint 报告孤立率 < 5%（vs 当前 14.7%）
- [ ] post-flight lint 报告"漏 link" = 0
- [ ] Agent-as-Judge 抽样 10 张，"能用一句问句问完"通过率 ≥ 90%

## 9. 与 SKILL.md / AGENTS.md 的关系

L1（Skill）和 L2（Tool）的关系：

- **L1 仍需要**：给 agent 原则、type 定义、认知循环。agent 知道"要建什么卡"靠 L1。
- **L2 是兜底**：agent 即使忘了/理解错，工具强制执行"不能建什么卡"。
- **L3 是审计**：抓 L2 抓不到的语义问题。

**修订后的 AGENTS.md 密度门禁章节作用**：
- 仍是 agent 学习的"原则指南"
- 但**不再是唯一防线**
- 添加备注："以下规则在 L2 工具层强制执行，违反会被拒绝写入"

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| guardrails 误拒合理卡 | Phase 2 前跑存量统计，调阈值；豁免规则覆盖比较/结构/中心 |
| 改 store.py 影响在跑 agent | Phase 0 必须完成（所有 agent 退出）才进 Phase 2 |
| lint 误报刷屏 | Phase 3 三类豁免（父子/比较/中心）|
| Agent-as-Judge 主观 | 用结构化 checklist，不让 judge 自由评判 |
| Phase 4 存量回炉工作量爆炸 | 优先 ERROR（必须修），WARN 抽样 10% |
| Phase 7 新批仍出错 | 量化对比：新批 vs 旧批的孤立率/总结型率，不通过则调 harness |

## 11. 后续演进

未来可加：
- 抄录型检测：用 source 字段比对 content 相似度（字符串距离）
- 跨 chunk 重复卡检测：embedding 相似度 > 阈值
- NOTES.md 协议：agent 写 `/tmp/loom_agents/<id>.md`，主 agent 读笔记而非查 DB
- pre-flight 自动 search：agent 启动时自动跑 search 关键词，避免重复

但 P0-P7 已经覆盖核心痛点，后续演进可按需添加。
