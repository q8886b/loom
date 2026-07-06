# 002 — Workbench 设计

> Loom 交互壳的完整重写：从单页可视化到双模式运作平台。
> 核心目标是让 AI 的写操作可审计、可回滚——人确认后才成为正式数据。

## 1. 问题

### 1.1 当前 viewer.html 的局限

| 维度 | 现状 | 问题 |
|---|---|---|
| 模式 | 纯浏览（图谱+详情） | 没有"使用"—消化/问答/治理/复盘都在 CLI 完成 |
| 编辑 | Web 无编辑入口 | 改卡只能 CLI，人无法在可视化上下文中编辑 |
| 审计 | 无状态区分 | AI 改了什么、人审了什么，全混在一起 |
| 版本 | SQLite 覆盖写 | 无历史，无法 diff，无法回滚 |
| 框架 | 单文件 HTML + D3 | 维护性差，不支持交互式任务窗口 |

### 1.2 核心痛点

AI 输出可能被污染，但当前没有机制区分"AI 写的"和"人审过的"数据。所有写操作都是原地覆盖，无法追踪、无法回滚。

## 2. 设计目标

1. **可审计**：所有 AI 写操作进入 pending 状态，人确认后才正式入库（confirmed）
2. **可 DIFF**：卡片内容放文件系统，pending 改动用 `.old.md` 保留原版，git 提供完整历史
3. **双模式**：浏览（图谱+树+详情）与使用（多任务 chat）在同一个壳中切换
4. **可运作**：使用模式通过 Claude Code CLI subagent 执行消化/问答/治理/复盘
5. **默认读最新**：pending 卡已生效（参与检索/链接/图谱），仅审计标签——避免"AI 写的卡自己检索不到"

## 3. 模式架构

```
┌─────────────────────────────────────────────────┐
│  Header [浏览 | 使用]  toggle                  │
├─────────────────────────────────────────────────┤
│                                                  │
│   浏览模式（路由 /browse, /browse/:id, /review）   │
│   ┌──────────┬──────────────┬──────────────┐    │
│   │ 卢曼树   │  焦点图谱     │  详情/编辑    │    │
│   │ (左240px)│  (中 flex)   │  (右360px)   │    │
│   └──────────┴──────────────┴──────────────┘    │
│                                                  │
│   使用模式（路由 /use, /use/:task_id）             │
│   ┌──────────┬──────────────┬──────────────┐    │
│   │ 任务列表  │  任务窗口     │  上下文面板   │    │
│   │ (左280px)│  (中 chat)   │  (右卡+trace) │    │
│   └──────────┴──────────────┴──────────────┘    │
│                                                  │
└─────────────────────────────────────────────────┘
```

- 双模式通过**顶部 toggle 切换**，路由同步更新
- 跨模式：使用 → 浏览（带参数跳转，如打开任务中引用的卡）；浏览 → 使用不可直接跳

## 4. 核心概念：pending/confirmed

### 4.1 原则：默认读最新

**pending 不是"未生效"，而是"已生效但状态未签字"。**

- 读操作（search/get/neighbors/browse/图谱/认知循环）默认读最新：有 `.old.md` 意味着当前 `.md` 是 pending 版本
- 读不到 pending 卡会引发矛盾——AI 在认知循环中检索不到自己刚写的卡

### 4.2 语义

| 状态 | 含义 | 谁写的 | 能否参与检索 |
|---|---|---|---|
| `confirmed` | 人工审过，质量有保证 | 用户 / 已确认的 AI 输出 | ✓ |
| `pending` | AI 写入，未审，当前生效 | AI（新建/修改） | ✓ |

pending 字段仅 3 个作用：
1. **可视化标记**（"这张卡是 AI 改的，未审"）
2. **回滚基线**（拒绝时回到 confirmed 版本）
3. **质量信号**（confirmed = 人工审过）

## 5. 数据层

### 5.1 文件系统（卡片内容 source of truth）

```
cards/
  .git/                      # git repo — 确认 = commit
  gen/
    01.md / 01.old.md
    01a.md
    01a1.md
  med/
    06.md
    06a.md
    06a1.md
  law/
    14.md
    14g.md / 14g.old.md    # .old.md 存在 = AI 改过该卡（status=pending）
  tasks/                     # 任务历史（JSON，非卡片文件）
    ...
```

#### 卡片文件格式

```markdown
---
id: law:14g
title: 违约责任的构成
type: 机制
links: [law:14, law:14h]
source: 民法典第577条
parent: law:14
status: confirmed
created_at: 2026-06-15T10:32:00
updated_at: 2026-06-15T10:32:00
confirmed_at: 2026-06-15T10:32:00
---

违约责任的构成要件包括四个方面：...

见 law:14（合同效力）。
```

- `links` 数组中的 ID 在写入时由 store.py 自动解析为双向 link（写入 SQLite card_links 表）
- content 中的 "见 X" 在解析时自动匹配 frontmatter links

#### `.old.md` 规则

| 场景 | `.md` | `.old.md` |
|---|---|---|
| AI 新建卡 | 写新文件 | 不创建 |
| AI 改 confirmed 卡 | 覆盖 | 创建（备份当前 `.md`，不交 git） |
| AI 改 pending 卡（再改） | 覆盖 | 不动（保留初版 baseline） |
| 用户改 confirmed 卡 | 覆盖 | 删 `.old.md`（如果有） |

### 5.2 SQLite（结构化索引）

brain.db 继续作为 SQLite 主库，但退化为索引角色：

**cards 表**（索引，不与文件系统双写内容）
```sql
CREATE TABLE cards (
    id TEXT PRIMARY KEY,           -- 如 "law:14g"
    ns TEXT NOT NULL,              -- 如 "law"
    luhmann_id TEXT NOT NULL,      -- 如 "14g"
    file_path TEXT NOT NULL,       -- 如 "cards/law/14g.md"
    old_path TEXT,                 -- .old.md 路径，NULL = 无 pending 改动
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- confirmed | pending
    content TEXT,                  -- 缓存，从 .md 加载
    parent_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT              -- NULL = pending
);
CREATE INDEX idx_cards_ns ON cards(ns);
CREATE INDEX idx_cards_status ON cards(status);
CREATE INDEX idx_cards_parent ON cards(parent_id);
```

**card_links 表**（不变）
```sql
CREATE TABLE card_links (
    card_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'related',
    PRIMARY KEY (card_id, target_id)
);
```

**card_vectors 表**（sqlite-vec，不变）

**card_fts 表**（FTS5，不变）

**tasks 表**
```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,           -- UUID
    type TEXT NOT NULL,            -- query | digest | govern | review
    model TEXT NOT NULL,           -- 前端选的 alias（如 "cc-zhipu52"）
    title TEXT NOT NULL,           -- 用户输入的任务标题
    status TEXT NOT NULL DEFAULT 'running',
    claude_session_id TEXT,        -- Claude Code session UUID（如果保留）
    pid INTEGER,                   -- 子进程 PID（用于 kill）
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);
```

**task_messages 表**
```sql
CREATE TABLE task_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    role TEXT NOT NULL,            -- user | assistant | system
    content TEXT,                  -- 消息正文
    tool_calls TEXT,               -- JSON: [{tool, input, output}]
    sequence INTEGER NOT NULL,     -- 消息序号
    created_at TEXT NOT NULL
);
CREATE INDEX idx_task_msgs ON task_messages(task_id, sequence);
```

**task_artifacts 表**
```sql
CREATE TABLE task_artifacts (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    card_id TEXT NOT NULL,
    action TEXT NOT NULL,          -- created | updated | deleted
    created_at TEXT NOT NULL,
    PRIMARY KEY (task_id, card_id, action)
);
```

## 6. 状态机

```
                    AI 新建
                      │
                      ▼
                 ┌─────────┐   用户确认    ┌───────────┐
                 │ pending │──────────────►│ confirmed │
                 └─────────┘               └───────────┘
                      │       AI 改 confirmed     ▲
                      │    ┌──────────────────────┘
                      │    │       用户确认 / 拒绝
                      │    ▼
                      │  pending（有 .old.md）
                      │    │
                      │    ├── 确认 → 删 .old.md, status=confirmed
                      │    │
                      │    └── 拒绝 → cp .old.md .md, 删 .old.md, status=confirmed
                      │
                      └── 拒绝（AI 新建） → 删 .md + 删 SQLite 记录
```

- AI 所有写操作默认 `status=pending`
- 用户 web 编辑直接 `status=confirmed`
- git diff：`git diff cards/law/14g.md` 当 `.old.md` 存在时（未确认）
- 确认时 `git commit`；拒绝时 `git checkout <path>`（有 `.old.md` 时）/ `git rm`（新建时）

## 7. 使用模式：任务系统

### 7.1 任务类型

| 类型 | icon | 描述 |
|---|---|---|
| `query` | ◐ | 问 Loom 一个问题（认知循环：检索 → 推理 → 修正） |
| `digest` | ⌘ | 消化材料（文献/教材），产出 pending 卡片 |
| `govern` | ✎ | 治理（抓 lint 错误 → 修复 → lint 再验证） |
| `review` | ⟳ | 复盘（经验提取 → 改进项） |

### 7.2 任务窗口

```
┌──────────────────────────┐
│  chat 消息流              │
│  ┌──────────────────────┐│
│  │ user 气泡             ││
│  └──────────────────────┘│
│  ┌──────────────────────┐│
│  │ assistant 气泡        ││
│  │ + 结构化卡（inline）   ││
│  └──────────────────────┘│
│         ...               │
│  ┌──────────────────────┐│
│  │ 输入框                ││
│  └──────────────────────┘│
└──────────────────────────┘
```

- assistant 消息中的**卡片引用**（如 "已建卡 law:14g"）渲染为可点击的卡片预览卡片
- trace 在右栏实时展示（子进程的 tool_use/tool_result）

### 7.3 子进程集成

```
启动：spawn("cc-zhipu52", ["-p", "--output-format", "stream-json",
       "--include-partial-messages", "--permission-mode", "bypassPermissions",
       prompt])
      ↓
实时流：stdout 逐行 JSON → SSE 推前端（事件类型: message/tool_use/tool_result/error/done）
      ↓
存档：每条消息写入 task_messages 表（sequence 递增）
      ↓
结束：进程退出 → task.status = 'completed'|'error' → 通知前端
      ↓
中断：浏览器关 → 进程继续（独立于 WS 连接）
      + 重新打开 → 从 task_messages 加载已有消息 + reconnect SSE
```

### 7.4 并发控制

- 全局最大 3 个并行子进程
- 超过 → `status=queued`，按 FIFO 拉起
- 每个进程 30min 全局超时 → SIGKILL

### 7.5 模型选择

```json
// config/models.json 或 SQLite config 表
{
  "models": [
    {"id": "cc-kimi", "label": "Kimi (便宜)", "command": "cc-kimi"},
    {"id": "cc-zhipu52", "label": "智谱 GLM-5.2", "command": "cc-zhipu52"},
    {"id": "cc-sonnet", "label": "Claude Sonnet 4.6", "command": "claude", "args": ["--model", "sonnet"]}
  ]
}
```

用户在发起任务时选模型，不同任务可选不同 alias。

## 8. 浏览模式：待审页

### 8.1 入口

顶部 status bar 显示 "待确认 (N)"——N = pending 卡总数。点击 → 路由到 `/review`。

### 8.2 布局

```
┌─────────────────────────────────────────────────────┐
│  待审页                                [全选] [确认所选] [拒绝所选]
│  筛选: [按任务▾] [按 ns▾] [按时间▾]                    │
├─────────────────────────────────────────────────────┤
│  ☑  law:14g  违约责任构成    机制    task: abc123     │
│     preview: "违约责任的构成要件包括四个方面..."         │
│     DIFF: [+] 红色 / [-] 绿色（如果 .old.md 存在）     │
│  ☐  law:14h  违约责任的排除    机制    task: abc123     │
│     preview: "以下情形不构成违约责任..."                │
│  ☐  med:50a  急性胰腺炎诊断    概念    task: def456     │
│     preview: "急性胰腺炎的诊断标准..."                  │
│ ...                                                   │
└─────────────────────────────────────────────────────┘
```

- 每行：checkbox + ID + 标题 + type + 来源任务 + 简短 preview
- 展开 → DIFF 视图（如果 `.old.md` 存在：+绿色 -红色 行级对比）
- 支持全选 / 按 task 过滤 / 批量确认 / 批量拒绝
- 单张卡可点击跳转到 `/browse/:card_id` 在浏览上下文查看

### 8.3 原位 review

在浏览模式详情区，pending 卡：
- 左边框黄色，标题后 `[待确认]` 标签
- DIFF 按钮（如有 `.old.md`）
- 确认 / 拒绝 按钮

## 9. 前端路由

| 路由 | 组件 | 描述 |
|---|---|---|
| `/` | `App.vue` | 重定向到 `/browse` |
| `/browse` | `BrowseMode.vue` | 浏览模式默认（无选中卡） |
| `/browse/:card_id` | `BrowseMode.vue` | 浏览模式 + 选中卡详情深链 |
| `/review` | `ReviewPanel.vue` | 待审页（批量确认/拒绝） |
| `/use` | `UseMode.vue` | 使用模式（任务列表 + 空白任务区） |
| `/use/:task_id` | `UseMode.vue` | 使用模式 + 指定任务深链 |

## 10. 后端 API

### 卡片
| 端点 | 描述 |
|---|---|
| `GET /api/cards` | 搜索（q/ns/type/status/top） |
| `GET /api/cards/:id` | 卡片详情（content+links+meta） |
| `POST /api/cards` | 建卡（按调用方身份定 status） |
| `PUT /api/cards/:id` | 改卡（按调用方身份定 status） |
| `DELETE /api/cards/:id` | 删卡 |
| `POST /api/cards/:id/confirm` | 确认 pending |
| `POST /api/cards/:id/reject` | 拒绝 pending |
| `GET /api/cards/:id/neighbors?depth=` | 邻居卡 |
| `GET /api/cards/:id/children` | 子卡列表 |
| `GET /api/cards/:id/diff` | diff（.old.md vs .md） |

### 待审
| 端点 | 描述 |
|---|---|
| `GET /api/pending?ns=&type=&task_id=` | 待审列表（分页） |
| `POST /api/pending/batch-confirm` | 批量确认 `{ids: [...]}` |
| `POST /api/pending/batch-reject` | 批量拒绝 `{ids: [...]}` |

### 卢曼树
| 端点 | 描述 |
|---|---|
| `GET /api/tree/:ns` | namespace 的卢曼树结构 |

### 任务
| 端点 | 描述 |
|---|---|
| `GET /api/tasks` | 任务列表（sidebar） |
| `POST /api/tasks` | 启动任务 `{type, model, prompt}` |
| `GET /api/tasks/:id` | 任务详情 |
| `GET /api/tasks/:id/messages?since=` | 消息历史（重连） |
| `GET /api/tasks/:id/stream` | SSE 实时流 |
| `POST /api/tasks/:id/cancel` | 取消任务（kill 进程） |
| `GET /api/tasks/:id/artifacts` | 任务产出的 pending 卡列表 |

### 配置
| 端点 | 描述 |
|---|---|
| `GET /api/config/models` | 可用模型列表 |
| `GET /api/stats` | 统计（卡片数/pending 数/任务数） |

## 11. 浏览图谱

- **焦点驱动**：选中一张卡 → 渲染它 + 父子 + 1-2 跳邻居
- 渲染：D3-force / v-network-graph / cytoscape（实施时定）
- 节点颜色按 type
- pending 卡节点为虚线边框
- 点击节点 → 路由到 `/browse/:card_id`

## 12. 迁移方案

### 12.1 步骤

1. 写 `scripts/migrate_v2.py` 脚本
2. 从 SQLite cards 表读所有 6735 张
3. 对每张卡：生成 `cards/<ns>/<luhmann_id>.md`（frontmatter + content）
4. SQLite 新增字段：`file_path`, `status`, `old_path`, `confirmed_at`
5. 所有现有卡设 `status=confirmed`
6. `cards/` 目录 `git init && git add -A && git commit -m "init: migrate all 6735 cards"`
7. 干跑（--dry-run）验证 → 实跑
8. 旧 content 字段保留为缓存（不从 SQLite 删）

### 12.2 风险控制

- 迁移前 `cp data/brain.db data/brain.db.bak`
- 迁移后验证：随机抽 100 张卡对比 `file.md` content 与 SQLite content 一致性
- 新 store.py 先双读（读文件 → 降级读 SQLite content cache）确保兼容

## 13. 技术栈

| 层级 | 选择 |
|---|---|
| 前端框架 | Vue 3 + Vite |
| 图谱渲染 | 待定（d3-force / v-network-graph / cytoscape） |
| 后端框架 | FastAPI + uvicorn |
| 数据库 | SQLite（WAL）+ sqlite-vec + FTS5 |
| 版本管理 | git（cards/ 子目录） |
| subagent | Claude Code CLI（-p --output-format stream-json） |
| 实时通信 | SSE（任务 trace 推送） |
| 目标平台 | 仅桌面浏览器（1280px+） |

## 14. 决策索引

| # | 决策 | 选项 |
|---|---|---|
| A1 | 双模式架构 | 顶部 toggle 切换浏览/使用 |
| A2 | 浏览模式布局 | 三栏（卢曼树 \| 焦点图谱 \| 详情） |
| A3 | 使用模式布局 | 三栏（sidebar \| 任务窗口 \| 上下文） |
| A4 | 跨模式方向 | 仅使用→浏览，单向 |
| B1 | 图谱模式 | 焦点驱动（选中卡为中心+父子+1-2跳） |
| B2 | 编辑模式 | 详情区原位切编辑 |
| B3 | pending 呈现 | 原位混合+视觉区分+专门待审页 |
| C1 | 任务类型 | 4种（问/消化/治理/复盘） |
| C2 | 任务窗口 | chat + 结构化卡片 |
| C3 | 右栏结构 | 卡列表 + trace 上下分栏 |
| C4 | sidebar 排序 | 时间倒序 + 搜索 + 置顶 |
| C5 | 任务持久化 | SQLite tasks + task_messages 两表 |
| C6 | 并发控制 | 全局 max=3，排队 |
| C7 | 任务中断 | 后台继续 + reconnect |
| C8 | 模型选择 | alias 可配置 + 前端选 |
| D1 | CC 集成 | CLI 子进程 + --output-format stream-json |
| D2 | subagent 权限 | bypassPermissions + prompt 约束 |
| D3 | 超时 | 全局 30min |
| E1 | 内容存储 | 文件系统 cards/<ns>/<id>.md 平铺 |
| E2 | pending 文件 | 原地改 + .old.md 备份 |
| E3 | status 字段 | SQLite confirmed/pending |
| E4 | 读取原则 | 默认读最新（pending 已生效） |
| E5 | git 化 | cards/ 是 git repo，确认=commit |
| E6 | 确认/拒绝 | 删/.old.md 还原 + status 变更 |
| E7 | task 血缘 | task_artifacts 表 |
| E8 | 批量操作 | 待审页多选 + 一键确认/拒绝 |
| E9 | 数据迁移 | 6735 张一次性全量迁移 |
| F1-F6 | 技术栈 | Vue3+Vite / FastAPI / 仅桌面 / 重写 / 多路由+深链 / 不分层 |
