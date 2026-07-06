# 006 — 实施验收规格

> 本文是 005 实施的可复制验收文档。监督人只需读 005（设计基准）+ 006（本文件）即可工作。
> 每个检查项都有：**检查什么 / 怎么检查 / 通过标准 / 自检结果**。监督人逐项核对，全勾 = 实现达标。

## 一、总目标

按 005 设计**完整实现 Loom 的 harness**，12 个模块全部完成，多领域大量数据下端到端跑通。每个模块有可量化验收标准，全链路可重复执行。

**设计基准**：`docs/design/005-layered-redesign-harness.md`
**老实现参照**：`_legacy/2026-06-20/`（不迁移数据，建新库）

## 二、验收环境

| 项 | 要求 |
|---|---|
| 项目根 | `~/loom/` |
| Python | python3.11 |
| 向量索引 | sqlite-vec（2048 维） |
| Embedding | 智谱 Embedding-3，API Key 从 `~/.loom/.env` 读取 |
| Claude Code / Codex | 默认 `./install.sh` 安装全局 hooks 到 Claude `~/.claude/settings.json` / Codex `$CODEX_HOME/hooks.json`；`./install.sh --no-hooks` 跳过 hooks；项目级 hooks 用 `./install.sh --project` 生成到 `.claude/settings.json` / `.codex/hooks.json` |

**监督人执行前检查**：

```bash
cd ~/loom
ls loom                           # CLI 入口存在
ls data/brain.db                    # 主库存在
python3.11 -c "import sqlite_vec"   # 向量扩展可用
cat ~/.loom/.env | grep ZHIPU  # API Key 存在
```

## 三、测试材料集

跨 3 个领域，共 3 份完整材料，覆盖不同形态（教材/叙事/论著）：

| 领域 | 材料 | 形态 | 路径 |
|---|---|---|---|
| 07-LLM | Harness Engineering 全书 | 教材（19 章） | `sources/07-LLM/01-深入理解Harness_Engineering/` |
| 01-金融（技术面） | Murphy《金融市场技术分析》 | 教材 | `sources/01-金融/17-Murphy-金融市场技术分析.pdf` |
| 01-金融（基本面） | Graham《聪明的投资者》 | 论著/叙事 | `sources/01-金融/10-Graham-聪明的投资者.pdf` |

**最小验收规模**：
- 3 份材料 × 多个 L1 单元
- 总 L1 单元 ≥ 10 个
- 总产出 L2 卡 ≥ 50 张

## 四、模块验收（12 个模块）

每个模块：检查项 → 检查方法 → 通过标准 → 自检结果。

---

### 模块 1：存储层

**检查项**：`data/brain.db` schema 完整。

**检查方法**：
```bash
sqlite3 data/brain.db ".schema"
```

**通过标准**（输出必须包含）：
- `cards` 表，字段：`id, title, type, content, source, layer, use_count, search_count`
- `links` 表，字段：`source_id, target_id`（双向图邻接边）
- `cards_fts` 虚拟表（FTS5，挂 cards 的 title/content）
- `cards_vec` 虚拟表（sqlite-vec，2048 维 embedding 列）
- `task_trace` 表（任务记录：task_id, start, end, status, drafts_count, retries）

**自检结果**：（实现完成后填写实际 `.schema` 输出摘要）

- [ ] 监督人勾选

---

### 模块 2：loom 基础命令

**检查项**：5 个基础命令可执行。

**检查方法**：
```bash
loom read-source --help
loom write-draft --help
loom read-cards --help
loom read-l4-index --help
loom search --help
```

**通过标准**：
- 5 个命令都返回 0 退出码，有 --help 输出
- `search` 支持 `--mode=hybrid|fts|vector`，默认 hybrid

**额外验证**（search 三种模式）：
```bash
# 先入库几张测试卡（手动或脚本）
loom search "测试" --mode=hybrid    # 返回 JSON 数组
loom search "测试" --mode=fts       # 返回 JSON 数组
loom search "测试" --mode=vector    # 返回 JSON 数组（需要 embedding 已生成）
```

**自检结果**：

- [ ] 监督人勾选

---

### 模块 3：loom 结构遍历

**检查项**：4 个结构遍历命令可执行。

**检查方法**：
```bash
loom browse fin
loom children fin:1a
loom siblings fin:1a
loom neighbors fin:1a --depth=2
```

**通过标准**：4 个命令都返回 JSON（即使某些查询结果为空数组，命令本身不报错）。

**自检结果**：

- [ ] 监督人勾选

---

### 模块 4：loom-admin 特权命令

**检查项**：特权命令只通过 `loom-admin` 暴露，普通 `loom` 不暴露。

**检查方法**：
```bash
ls bin/loom bin/loom-admin
loom commit-ready --help            # 普通入口存在
loom commit-l4 --help               # 普通入口不存在（应失败）
loom-admin commit-l4 --help         # 特权入口存在
loom-admin apply-card-edit --help   # 特权入口存在
loom-admin update-card --help       # 特权入口存在
loom-admin delete-card --help       # 特权入口存在
loom-admin rebuild-l4-index --help  # 特权入口存在
loom-admin stop-check --help        # 特权入口存在
loom-admin stop-check-pending --help # 特权入口存在
loom-admin commit --help            # 旧入口不存在（应失败）
loom-admin commit-ready --help      # 特权入口不存在（应失败）
```

**通过标准**：
- 普通 `loom` 只暴露工作 agent 命令，`commit-ready` 保留为语义自检后的窄门入库命令
- `loom-admin` 暴露 hook / 主 agent 人工审核后才用的特权命令
- 默认 Claude settings 使用 `permissions.ask = ["Bash(loom-admin *)"]` 支持人工一次性授权
- 文档（SKILL.md）明确说明这些命令只在 hook 或主 agent（用户审核后）调用，工作 agent 不使用

**自检结果**：

- [ ] 监督人勾选

---

### 模块 5：loom 提案命令

**检查项**：L4 提案机制工作。

**检查方法**：
```bash
# 模拟一个任务
TASK_ID=test001
mkdir -p /tmp/loom_task/$TASK_ID/staging
loom propose-l4 $TASK_ID --title="测试模式" --content-file=/tmp/test.md --related=fin:1a
ls /tmp/loom_task/$TASK_ID/staging/    # 应有提案文件
```

**通过标准**：
- `propose-l4` 写入 `staging/` 目录，不报错
- `propose-l4` 不阻断（exit 0，不是写完就退出任务）
- `propose-card-edit` 同样工作

**自检结果**：

- [ ] 监督人勾选

---

### 模块 6：write-draft 计算校验

**检查项**：11 条计算校验全部生效。

**检查方法**（逐条故意触发拒绝）：
```bash
# 1. type 合法：传 type=比较
loom write-draft test001 bad:1 --type=比较 --source=sources/x.md --content-file=/tmp/c.md
# 期望：exit ≠ 0，stderr 含 "type"

# 2. layer×type 矩阵：L4 任务传 type=案例
# （需要 plan.json 的 layer=L4）
loom write-draft test001 bad:2 --type=案例 ...
# 期望：exit ≠ 0，stderr 含 "layer" 或 "type"

# 3. 长度门禁：content < 30 字
echo "太短" > /tmp/short.md
loom write-draft test001 bad:3 --type=概念 --source=sources/x.md --content-file=/tmp/short.md
# 期望：exit ≠ 0，stderr 含 "30" 或 "目录"

# 4. L3 必须 link L2：layer=L3 任务，不传 links
# 5. 反思锚定：type=反思，links 目标不是判断/模式
# 6. L4 索引格式：layer=L4，content 第一段不含 [探索期/熟练期]
# 7. source 真实：source 指向不存在的文件
# 8. card_id 唯一：传一个库里已存在的 id
# 9. L4 跨域锚定：layer=L4，links 只指向同一领域的 L2/L3（应被拒，单领域应归 L3）
# 10. L2 不跨领域 link：layer=L2，links 含跨领域 namespace 的卡（应被拒）
# 11. namespace 格式：card_id 不符合 layer 对应格式
```

**通过标准**：11 条都能被触发拒绝，每条 exit ≠ 0 + stderr 有对应错误信息。

**自检结果**：（实现后填 11 条的实际触发输出）

- [ ] 监督人勾选

---

### 模块 7：整批校验（stop-check）

**检查项**：4 条整批校验生效。

**检查方法**：
```bash
# 故意漏主题卡：L2 任务的 drafts 里没有 type=主题 的卡
# 跑 stop hook 计算层
loom-admin stop-check test001 --mode=normal
# 期望：exit 2，错误 JSON 含 "主题卡"

# 故意让 L2 卡不 link 主题卡
# 期望：exit 2，错误 JSON 含 "主题卡" 或 "link"

# 故意让同 task drafts 内两张卡 id 撞库
# 期望：exit 2，错误 JSON 含 "id_unique"

# 故意让同 task drafts 内两张卡 difflib 相似度 > 0.7
# 期望：exit 2，错误 JSON 含 "no_duplication"
```

**通过标准**：4 条整批校验都能触发拒绝。

**自检结果**：

- [ ] 监督人勾选

---

### 模块 8：Claude / Codex hook 配置

**检查项**：Claude 与 Codex 的 hook 配置完整（全局或项目级均可）。

**检查方法**：
```bash
cat ~/.claude/settings.json          # 或 .claude/settings.json
cat "${CODEX_HOME:-$HOME/.codex}/hooks.json"  # 或 .codex/hooks.json

# 在 loom 项目执行 loom on，确认 hook-guard 放行；loom off 后应拒绝
loom on
loom hook-guard && echo "allowed"
loom off
loom hook-guard || echo "blocked"
```

**通过标准**：
- Claude 配置含 `SubagentStop` / `Stop` hook 配置
- Codex 配置含 `SubagentStop` / `Stop` hook 配置
- 每个 Loom hook 只有一个 `type: "command"`，command 指向 `loom-hook`（安装后可为绝对路径）
- 不存在拆开的 `loom hook-guard` + `loom-admin stop-check-pending` 两条 command；二者有因果依赖，必须由 `loom-hook` 串行封装
- **不再有 `type: "prompt"` 语义层 hook**（语义层改为 block-back 子 agent 自检）
- `loom on` 后 hook-guard exit 0；`loom off` 后 hook-guard exit 1

**自检结果**：

- [ ] 监督人勾选

---

### 模块 9：stop-check 计算层 + block-back

**检查项**：计算层脚本工作，block-back 机制跑通。

**检查方法**：
```bash
# 准备一份合规的 drafts（手动或脚本造）
loom mark-ready good001
loom-admin stop-check good001 --mode=normal
# 期望：exit 2（decision:block，要求语义自检），写 .computed_passed.json + .semantic_sample.json
cat /tmp/loom_task/good001/.computed_passed.json   # 应有 drafts mtimes
cat /tmp/loom_task/good001/.semantic_sample.json   # 应有 3 张抽样

# 模拟子 agent 语义自检通过后 commit
loom commit-ready good001 --semantic-passed
# 期望：exit 0，cards 表有新记录，task_trace status=done

# 准备一份不合规的 drafts
loom-admin stop-check bad001 --mode=normal
# 期望：exit 2，JSON 含具体错误（无 .computed_passed.json）

# 模拟 draft 被偷改（计算层通过后改 draft）
loom-admin stop-check cheat001 --mode=normal  # 假设通过
echo "modified" >> /tmp/loom_task/cheat001/drafts/some.md  # 改 draft
loom commit-ready cheat001 --semantic-passed
# 期望：exit ≠ 0，错误含 "mtime" 或 "changed after"
```

**通过标准**：
- 合规 drafts 走完 mark-ready → stop-check（block）→ commit-ready 整链 → `cards/` 目录有文件，`cards` 表有记录
- 不合规 drafts → stop-check exit 2 + 结构化错误 JSON，不写 .computed_passed.json
- draft 被偷改 → commit-ready 拒绝（mtime 防篡改）
- commit-ready 必须带 `--semantic-passed` flag，否则直接拒
- 入库后若含 L4 卡 → `l4_index.md` 不主动重建（pull 模式，下次 read-l4-index 按 mtime 触发）

**自检结果**：

- [ ] 监督人勾选

---

### 模块 10：语义层 block-back

**检查项**：语义层走 block-back（子 agent 自检），不再有独立 prompt/agent hook。

**检查方法**：
```bash
# 计算层通过后，hook 写 sample 并 block
loom-admin stop-check sem001 --mode=normal
ls /tmp/loom_task/sem001/.semantic_sample.json  # 应存在
# 子 agent 读 sample 自检后，通过 commit-ready 提交：
loom commit-ready sem001 --semantic-passed
```

**通过标准**：
- Claude / Codex 配置里**没有** `type: "prompt"` 或 `type: "agent"` 的语义层 hook（语义判断走 block-back）
- 计算层通过后 hook 写 `.semantic_sample.json`（含随机 3 张抽样）
- 子 agent 读 sample 按 4 项判据自判：`type_match`/`single_unit`/`genuine_digest`/`self_contained`
- 自检通过后调 `commit-ready --semantic-passed` 入库；失败则修 draft 重新 mark-ready

**自检结果**：

- [ ] 监督人勾选

---

### 模块 11：skill 文件

**检查项**：4 个模式 skill + 共同前置齐全且内容完整。

**检查方法**：
```bash
ls skills/
cat skills/_loom_core.md
cat skills/loom-digest/SKILL.md
cat skills/loom-think/SKILL.md
cat skills/loom-use/SKILL.md
cat skills/loom-pipeline/SKILL.md
```

**通过标准**：
- 5 个文件存在（_loom_core + 4 个模式 skill）
- `_loom_core.md` 含铁律 / 合约 / 工具集 / type 易错点（所有模式 skill 通过 markdown 链接强制 Read）
- `loom-digest/SKILL.md` 含两阶段流程：Scout 通读建主题卡 + Deep 每章并行精读；含 mark-ready → 语义自检 → commit-ready 收尾协议
- `loom-think/SKILL.md` 含反复查询-关联-思考循环（不预设 layer）；含 mark-ready → 语义自检 → commit-ready 收尾协议
- `loom-use/SKILL.md` 含问问题/决策/复盘流程；含 mark-ready → 语义自检 → commit-ready 收尾协议
- `loom-pipeline/SKILL.md` 含 5 阶段编排（INGEST/SCOUT/DEEP/PER-BOOK/CROSS）+ 子 agent 收尾协议
- 每个 SKILL.md 能被 Claude Code 识别为 skill（frontmatter 含 name + description）

**自检结果**：

- [ ] 监督人勾选

---

### 模块 12：AGENTS.md 更新

**检查项**：AGENTS.md 反映新实现。

**检查方法**：
```bash
cat AGENTS.md
```

**通过标准**：
- CLI 用法更新为 `loom`（不是老 `python3.11 tools.py`）
- 老的 store.py/tools.py 相关内容删除或移到 _legacy 说明
- 保留通用规则：python3.11、ZHIPU_API_KEY 位置、资源管理硬约束、反作弊规范
- 密度门禁章节标注"由 write-draft + Claude/Codex stop-check hook 强制执行"

**自检结果**：

- [ ] 监督人勾选

---

## 五、端到端验收

### 阶段 1：单领域单材料跑通

**场景**：手动喂 Harness Engineering 的 `00_preface.md` 给 DIGEST。

**检查方法**：
```bash
# 主 agent 按 DIGEST 流程：
# 1. 写 plan.json（layer=L2, skill=DIGEST）
# 2. 起子 agent（带 timeout）
# 3. 子 agent 产出 drafts
# 4. stop-check hook 校验 + 语义自检 + commit-ready 入库
```

**通过标准**：
- drafts 中有 ≥ 1 张主题卡 + 若干 L2 卡
- 全部通过计算层 + 语义层校验
- stop-check 计算层通过，agent 语义自检后 `commit-ready --semantic-passed` 入库，cards 表有记录
- 任务 trace 记录存在

- [ ] 监督人勾选

### 阶段 2：单领域多材料跑通

**场景**：消化 Harness Engineering 的前 5 章。

**通过标准**：
- ≥ 5 个 L1 单元被消化
- ≥ 20 张 L2 卡入库
- 跨章节检索有效：`search "反馈回路"` 能召回多章的卡

- [ ] 监督人勾选

### 阶段 3：跨领域跑通

**场景**：消化 Murphy《金融市场技术分析》前几章 + Graham《聪明的投资者》前几章。

**通过标准**：
- 总 L2 卡 ≥ 50 张（3 份材料合计）
- 跨领域检索有效：`search "风险"` 能同时召回金融和 LLM 领域的卡
- ≥ 1 个跨域 L4 提案出现在 staging/（如"反馈回路收敛"同时出现在 harness 和金融书）

- [ ] 监督人勾选

## 六、量化指标验收

实现完成后，跑一份统计报告，指标达以下阈值：

| 指标 | 阈值 | 检查方法 |
|---|---|---|
| **密度门禁拒绝率** | 10%-60%（拒绝率为 0 说明校验没用；>60% 说明校验过严或 agent 质量太差） | `SELECT reason, COUNT(*) FROM reject_log GROUP BY reason`（若有日志）或从 task_trace 统计 |
| **回炉率** | < 50%（回炉 = stop-check 拒绝后重试；过高说明校验或 prompt 有问题） | task_trace 里 retries > 0 的任务占比 |
| **强制结束 / 回炉上限触发** | 至少被验证一次（构造一个故意失败的案例，确认运行时不会无限回炉） | 手动构造 + 观察 |
| **use_count 分布** | ≥ 50 张卡里，use_count 不全是 0（证明自动维护生效） | `SELECT COUNT(*) FROM cards WHERE use_count > 0` ≥ 10 |
| **search_count 分布** | 同上 | `SELECT COUNT(*) FROM cards WHERE search_count > 0` ≥ 10 |
| **孤立卡率** | < 20%（孤立 = 0 in-link + 0 out-link；过高说明 link 建设不足） | `SELECT COUNT(*) FROM cards WHERE id NOT IN (SELECT source_id FROM links) AND id NOT IN (SELECT target_id FROM links)` 占比 |
| **跨材料检索召回** | 给定一个明确跨材料的关键词，结果里至少有 2 个不同 source 的卡 | `loom search "反馈" --mode=hybrid` 检查结果的 source 字段多样性 |
| **跨域 L4 涌现** | staging/ 里 ≥ 1 个提案，其 related_cards 跨领域 | `ls /tmp/loom_task/*/staging/` + 检查提案的 related_cards |
| **跨领域一致性** | 两个金融子领域（技术面/基本面）的拒绝率差异 < 20 个百分点 | 分别统计两本的拒绝率，对比 |

**自检结果**：（实现完成后跑统计报告，填实际数值）

- [ ] 监督人勾选

## 七、可重复性验收

**检查方法**：同一份材料再跑一次 DIGEST。

**通过标准**：
- 流程正常，不撞库（或撞库时有明确的"已存在"处理）
- 不报错
- 产出质量稳定（不是这次 5 张卡、下次 20 张卡的大幅波动）

- [ ] 监督人勾选

## 八、最终验收清单

监督人逐项打勾。**全勾 = 实现达标**。

### 模块（12 项）
- [ ] 1. 存储层 schema 完整
- [ ] 2. 5 个基础命令可执行
- [ ] 3. 4 个结构遍历命令可执行
- [ ] 4. 4 个特权命令存在且权限隔离
- [ ] 5. L4 提案机制工作
- [ ] 6. write-draft 11 条计算校验生效
- [ ] 7. stop-check 4 条整批校验生效
- [ ] 8. Claude / Codex hook 配置完整 + loom on/off 作用域
- [ ] 9. stop-check 计算层 + block-back 机制工作
- [ ] 10. 语义层 block-back（子 agent 自检 + commit-ready）
- [ ] 11. 4 个模式 skill + _loom_core 齐全
- [ ] 12. AGENTS.md 更新

### 端到端（3 阶段）
- [ ] 阶段 1：单材料跑通
- [ ] 阶段 2：单领域多材料跑通（≥20 张 L2 卡）
- [ ] 阶段 3：跨领域跑通（≥50 张 L2 卡 + 跨域检索 + 跨域 L4）

### 量化指标（9 项）
- [ ] 密度门禁拒绝率 10%-60%
- [ ] 回炉率 < 50%
- [ ] 强制结束 / 回炉上限被验证
- [ ] use_count 分布非空
- [ ] search_count 分布非空
- [ ] 孤立卡率 < 20%
- [ ] 跨材料检索召回有效
- [ ] 跨域 L4 涌现 ≥ 1
- [ ] 跨领域一致性（拒绝率差 < 20pp）

### 可重复性
- [ ] 同一材料再跑一次正常

**总计 25 项。全勾 = 实现达标。**

---

## 附录：监督人须知

1. **设计基准是 005**。如果实现和 005 描述不符，以 005 为准（除非 005 本身有问题，需讨论修正）。
2. **自检结果字段**由实现者（我）填写实际命令输出。监督人对比"通过标准"和"自检结果"判断。
3. **阈值是初定值**。如果某项指标第一次跑出来不达标，先分析原因（是校验太严、agent 质量差、还是设计有问题），不盲目调阈值。
4. **测试材料真实**。用 sources/ 里已有的材料，不合成数据。
5. **不迁移老数据**。老 brain.db 在 `_legacy/`，新库从零开始。
