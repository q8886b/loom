# 003 — Harness 重设计（活文档）

## 元信息

- 创建：2026-06-20
- 状态：进行中（活文档，持续追加）
- 目的：从头重新设计 Loom 的 harness——确保规则在 prompt 层之外有 tool/hook/sub-agent 强制执行；让 Loom 真正成为"思考伙伴"而非"记忆系统"
- 与 001 的关系：001 解决"密度门禁下沉到工具层"，003 是更大的范围——从 digest/think/collide 三个循环到 tool/hook/sub-agent 三类组件的整体重设计。001 的三层架构（L1 Skill / L2 Tool / L3 Orchestration）是 003 的底层骨架

## 顶层设计哲学

（待后续讨论沉淀，暂记一些已隐含的原则）

- 规则不应只在 prompt 层（agent 仍会违反）；必须下沉到 tool/hook/sub-agent
- LLM 不能 API 调用——所有 LLM 语义判断都通过 Claude 会话中的子 agent 实现
- 工具/脚本只做事实性、确定性工作（搜索召回、统计、读取、聚类）
- 三个循环（digest / think / collide）全部手动触发，不需要后台进程

## 决策清单（索引）

| # | 决策 | 状态 | 日期 |
|---|---|---|---|
| 1 | digest 采用多 Pass 架构（Adler + 诠释学循环）| 已定 | 2026-06-20 |
| 2 | Pass 0 全局骨架由独立 scout agent 建立 | 已定 | 2026-06-20 |
| 3 | Pass 2 反刍是必须的（每本都做）| 已定 | 2026-06-20 |
| 4 | digest 用单 agent 顺序消化（不并发章节）| 已定 | 2026-06-20 |

## 决策详情

### 决策 1：digest 采用多 Pass 架构

**背景**：

当前 digest 流程是单遍线性——agent 拿第一章 → 精读 → 建卡 → 第二章 → ...

这导致三个结构性问题：

1. **章节 N 的 agent 不知道章节 N+1 的内容**——但很多书是螺旋递进的：概念在第 1 章引入，到第 5 章才完整展开
2. **章节 N+1 的案例可能需要第 7 章的方法论才能正确理解**——但第 7 章还没读
3. **第 1 章的判断可能在最后一章被作者自己修正**——但第 1 章的卡已经建好、type 已经定死

**单遍线性 → 局部最优但全局失真**。

实际后果：fin 23 本书平均页/卡 > 30（最严重 Bulkowski 86 页/卡），把书变成了缩写而非消化。这不只是密度问题，更是"没有全局视野导致漏识别独立单元"的问题。

**决策**：

采用 4 Pass 架构：

| Pass | 名称 | 任务 | 触发 | 理论根据 |
|---|---|---|---|---|
| 0 | 检视阅读 | 读目录/章节首尾/概念扫描，建 global_skeleton | 消化启动 | Adler 检视阅读 |
| 1 | 分析阅读 | 逐章精读建卡 | skeleton 建好 | Adler 分析阅读 |
| 2 | 反刍（诠释学回归）| 全书看完后回头修订 | Pass 1 完成 | 诠释学循环 part→whole→part |
| 3 | 跨章节模式抽象 | 抽象领域模式 / 补 gen link | Pass 2 完成 | Adler 主题阅读 + Loom 已有 Pass 3.5 |

**理论根据**：

- **Adler《如何阅读一本书》**——4 个层次：基础阅读（字面）/ 检视阅读（系统化略读抓结构）/ 分析阅读（深度精读）/ 主题阅读（跨书比较）
- **诠释学循环（Schleiermacher / Dilthey）**——整体通过部分理解，部分通过整体理解，循环往复
- **综合**：Adler 给分层骨架（Pass 0/1/3），诠释学循环给 Pass 2 的回归机制——这是单独读 Adler 没有的、而 Loom 必须的"回头修订"步

### 决策 2：Pass 0 全局骨架由独立 scout agent 建立

**背景**：

- 主 digest agent 的 context 是稀缺资源，不能让它同时承担"侦察 + 消化"
- scout 的工作是"快速侦察"——不是精读，是抓结构
- scout 不建卡，只产 skeleton；建卡是 digest agent 的工作

**决策**：

- spawn 独立的 scout agent（主 agent 的子 agent）
- scout 产出 `global_skeleton_<book>.md`（具体路径待定，可能放 `data/digest_workspace/<book_id>/skeleton.md`）
- digest agent 启动时读 skeleton，作为顺序消化时的全局视野

**skeleton 内容（必须包含）**：

- 全书论点（一句话）
- 章节结构（每章 1-2 句摘要）
- 核心概念清单（每个概念在哪些章节展开）
- 章节依赖图（哪章铺垫哪章）
- 预判：哪些章节密度高（独立认知单元多）
- 控制 2000-5000 字

**scout 的工作机制（重要）——不读全书，自适应探索结构**：

scout 模拟 Adler 检视阅读的"系统略读"——不读全书，只读一小部分关键内容。但**不同书的结构千差万别**（教材按章、法典按条文、案例集按 case、论文集按 paper、博客按 post、对话录按话轮），不能让脚本一刀切地"取每章首尾段"——这会把理解结构的工作错误地交给确定性脚本。

**核心分工原则**：
- 脚本只做"原始素材准备"（PDF→markdown、TOC 提取、stats 报告）
- "理解结构"必须交给 LLM（通过 scout agent）

三层流水线：

```
PDF / epub 文件
    ↓
[Step 1] 预处理脚本（L2 工具层，纯确定性，不做语义工作）
    工具：bin/book_to_text.py
    只做：
      - PDF/epub → markdown 全文（pdftotext / markitdown）
      - 提取 PDF 自带的 TOC（如果有）
      - stats：总字数、总段落、疑似标题的行（regex 候选）
    不做：
      - 章节切分（不假设书的结构）
      - 首尾段提取（不假设首尾段就是论点）
    产出：book_raw.md（全文）+ book_meta.json（TOC + stats）
    不调 LLM
    ↓
[Step 2] scout agent（LLM，主 agent 子 agent，多步工具调用）
    有 bash / read / grep / head / tail / wc 工具
    自适应探索书的结构：
      1. 看 book_meta.json 的 TOC（如果有）→ grep 验证 TOC 是否对得上正文
      2. TOC 不存在 → grep 章标题模式（"第X章" / "Chapter X" / 数字编号 / 其他规律）
      3. 浏览前言 / 后记
      4. 按识别出的章节结构，每章采样（首段、末段、或自己判断）
      5. grep 核心概念在全文的分布
    不假设书的结构——发现结构
    产出：global_skeleton_<book>.md（2000-5000 字）
    ↓
[Step 3] digest agent 启动时读 skeleton
```

**对不同结构的书都通用**：

| 书类型 | scout 怎么处理 |
|---|---|
| 教材（章节清晰）| 看 TOC → 每章采样首尾 |
| 法典（按条文）| 识别"第X条"模式 → 按编/章/节切分 → 抽样条文 |
| 案例集（按 case）| 识别"案例 N" / "Case N"模式 → 每个 case 摘要 |
| 论文集 | 识别每篇论文的 abstract / conclusion |
| 博客合集 | 识别 post 标题 / 日期分隔 |
| 对话录 | 识别话轮或主题 |
| 叙事书 | 章节标题 + 跨章主题扫描 |

**为什么是预处理 + scout 两层**：

| 层 | 职责 | 实现 | 为什么 |
|---|---|---|---|
| 预处理 | 转格式、提 TOC、报 stats | Python 脚本（确定性）| 纯原始素材准备，零 LLM 成本 |
| 探索结构 | 识别书的结构模式、采样关键段 | scout agent（多步工具调用）| 理解结构是 LLM 工作，不能交给脚本；scout 是真 agent，自适应不同书类型 |
| 综合 | 推断章节依赖、预判密度 | scout agent（同一调用内）| 上一阶段的延续 |

**scout 是真正的 agent，不是 LLM API 一次调用**：

它有 bash / read / grep 工具，多步操作到任务完成。工具调用次数不限，但每次调用记 trace（便于事后审计）。

**预处理脚本大幅简化**：

实际上预处理脚本只做：
1. `pdftotext` 或 `markitdown` 把 PDF/epub 转 markdown
2. 提取 PDF 自带的 TOC（如果有）
3. 报告 stats：总字数、总段落、疑似标题的行（regex 候选）

约 50 行 Python。不做任何"理解"。

**优势**：

1. 不同结构的书都用同一流程
2. scout 是 agent，有适应性——能处理法典/教材/案例集/论文集等不同结构
3. 预处理可重用——任何书同一脚本
4. 预处理产物可审计——book_raw.md + book_meta.json 是文件，人和 agent 都能查
5. 失败回退简单——skeleton 质量不好可以看 scout 的 trace 找原因

### 决策 3：Pass 2 反刍必须执行

**背景**：

- 诠释学循环的"部分 → 整体 → 部分"回归步不可省
- Pass 1 时 agent 只有局部视野——它建卡时不知道后面章节会修正/补充什么
- 省略 Pass 2 等于让"早期章节的卡"永远处于"未看到反例/补充"的状态
- 这正是 fin 失败消化的根因之一——很多卡建错了 type、漏了内容、漏了 link，但没人回头看

**决策**：

- 每本书 Pass 1 完成后强制 Pass 2
- 不按复杂度分级、不抽样触发
- 成本不是减项理由——质量是 Loom 的核心价值

**Pass 2 的任务清单**：

- 拿 skeleton + Pass 1 卡索引（不全量 content）
- 逐项检查：
  1. 早期卡是否被后期内容修正 / 补充？（→ update）
  2. type 是否需要调整？（原以为是概念，全书看完发现是判断）
  3. 是否漏了"回头看才发现"的独立单元？（→ 补建卡）
  4. forward link 占位是否可以补全？（→ 实际 link 或删占位）
  5. 全书级判断卡 / 反思卡此时建（Pass 1 只建了章节级）

**Pass 2 的执行者**：

- 不能复用 digest agent（Pass 1 结束时 context 已耗尽）
- spawn 独立的修订 agent（也是主 agent 的子 agent）
- 给它：skeleton + Pass 1 卡索引（id + title + type + 一句话摘要）

### 决策 4：单 agent 顺序消化（不并发章节）

**背景**：

- 多 agent 并行消化章节需要 skeleton 同步——一致性风险高
- 单 agent 顺序消化一致性最好，速度次之
- context 限制靠"skeleton + 当前章节文本"解决，不需要一次读全书

**决策**：

- digest agent 一个，按章节顺序处理整本书
- 不并发章节级 agent
- 章节 N 完成后，章节 N+1 可以引用章节 N 的卡（实际 link）
- 章节 N 内的卡如果要引用章节 N+M 的概念，用 forward link 占位（具体语法见开放问题 2），Pass 2 补全

**章节 context 策略**：

- 每次塞给 digest agent：skeleton + 当前章节文本 + 前一章产出卡的 id/title
- 不塞全书
- 章节 N 结束时输出"本章产出卡列表"，作为章节 N+1 的 context

## 当前架构示意

```
主 agent（Claude 会话里）
  │
  ├─ spawn scout agent
  │     └─ 产 global_skeleton_<book>.md
  │
  ├─ spawn digest agent（带 skeleton，按章顺序）
  │     ├─ 章节 1：建卡 + 可能 forward link 占位
  │     ├─ 章节 2：建卡 + 实际 link 到章节 1 卡
  │     ├─ ...
  │     └─ 产 Pass 1 卡全集 + 卡索引
  │
  └─ spawn 修订 agent（带 skeleton + Pass 1 卡索引）
        ├─ 全书级 type 复核
        ├─ 早期卡修订
        ├─ forward link 补全 / 清理
        ├─ 漏建卡补建
        └─ 产全书级判断卡 / 反思卡
```

## 待讨论的开放问题

1. **Pass 2 的 context 策略**：卡索引 vs lint 驱动？
   - 卡索引：全量列出所有 Pass 1 卡的 id+title+type+摘要，让修订 agent 看全
   - lint 驱动：先跑 lint 找出可疑卡（孤立、type 可疑、forward link 占位未补），修订 agent 只看这些
   - 倾向：厚书用 lint 驱动（卡索引可能爆 context），薄书用卡索引

2. **forward link 占位的具体语法**
   - 候选：`[(future:第5章 "概念X")]` / `[TODO:第5章 X]` / 普通 markdown 注释 `<!-- 见第5章 X -->`
   - 工具层需要能扫描这些标记，让 Pass 2 知道哪里要补

3. **scout 建错骨架怎么回退**
   - 主 agent 怎么判断 skeleton 质量不够？
   - 回退策略：让 scout 重做？主 agent 自己补？digest agent 边消化边修订？

4. **Pass 0 scout agent 的失败 / 质量检查机制**
   - skeleton 字数过少 → 失败？
   - 章节数与原书 TOC 不一致 → 失败？
   - 核心概念清单为空 → 失败？

5. **章节文本怎么从 PDF / epub 提取并分块**
   - 当前已有 OCR 处理扫描版 PDF
   - 但章节切分需要规则（按 TOC / 按长度 / 按标题级别）

6. **Pass 2 修订 agent 的 prompt 设计**
   - 任务边界、检查清单、输出格式

7. **跨书一致性**（同一主题多本书消化时的同步）
   - 暂不在本轮讨论范围

## 参考文档

- `docs/design/000-system-overview.md`（系统完整定义）
- `docs/design/001-harness-design.md`（三层架构，本文档的底层骨架）
- `docs/research/017-pattern-layer-implementation.md`（Pass 3.5 模式桥接的来源）
- `docs/research/018-cross-domain-pattern-reuse.md`（关系骨架翻译 + LLM 结构等同性判断）
