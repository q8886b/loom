# Loom

**语言：** [English](README.md) | 简体中文

Loom 是一个本地优先的 AI agent 认知 harness。

它不是笔记软件，也不是聊天机器人的记忆缓存。Loom 给 agent 一套受约束的方式：读取原始材料，消化成卡片，跨材料建立关联，并在不直接写数据库的前提下沉淀可复用的思考模式。

核心设计看这两份：

- [004 - 分层重设计：目的与思想](docs/design/004-layered-redesign-purpose.md)
- [005 - 分层重设计的 Harness 落地](docs/design/005-layered-redesign-harness.md)

## 结构

Loom 有四层：

| Layer | 作用 | 产物 |
|---|---|---|
| `L1` | 忠实捕获原文 | Markdown 原文卡 |
| `L2` | 理解单份材料 | 概念、结构、机制、案例、判断 |
| `L3` | 跨材料思考 | 综合、比较、实践判断 |
| `L4` | 对思考方式的沉淀 | 模式、判断、反思 |

L1/L2 是把材料读好。L3/L4 是用读过的材料继续思考。

关键约束：agent 不直接写卡片数据库。它先写 draft，Loom 跑检查，然后 agent 做语义复检，最后才能入库。

```text
write-draft -> mark-ready -> stop-check -> semantic review -> commit-ready
```

这就是 harness：prompt 说明规则，工具强制状态机，hook 捕获未完成工作，数据库保留可追溯的图结构。

## 向量与链接

向量化是核心能力。没有语义召回，Loom 发现跨材料隐性关联的能力会明显变弱。

但 embedding 不是事实来源。在 Loom 里：

```text
embedding 用来发现关系
link 用来记录关系
```

embedding provider 可配置：

- 本地 Ollama embedding，推荐的本地优先路径
- OpenAI-compatible embedding API
- Zhipu，作为兼容 preset 保留

一个数据库固定一个 embedding 维度。换模型后运行：

```bash
loom-admin rebuild-embeddings
```

## 快速开始

```bash
git clone git@github.com:q8886b/loom.git
cd loom
./install.sh
```

然后看 [docs/quickstart.md](docs/quickstart.md)，里面有 embedding 配置、原文导入、搜索、hooks 和可选 Workbench。

## 私有数据边界

仓库只包含代码、skills、测试和设计文档，不包含你的 Loom 数据。

运行时数据在 Git 之外：

```text
~/.loom/data/       SQLite 数据库和派生索引
~/.loom/cards/      Markdown 卡片镜像
~/.loom/sources/    本地源材料
/tmp/loom_task/     draft 任务工作区
```

## 仓库结构

```text
bin/                CLI wrapper
src/loom/           Python 实现
skills/             digest / think / use agent skills
docs/design/        设计基准
workbench/          可选本地图谱浏览器
tests/              harness 回归测试
```

## 开发

```bash
python3.11 -m pip install -e ".[dev]"
python3.11 -m pytest
```
