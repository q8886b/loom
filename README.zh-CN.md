# Loom

**语言：** [English](README.md) | 简体中文

Loom 是 AI 的外置大脑，也是一个持续演化的认知网络。

给它一本书、一篇论文、一段视频——AI 会把材料一层层消化成互相连接的卡片：
原文 → 单材料精华 → 跨材料综合 → 跨域模式。每张卡片用认知类型定性，
用显性的 link 网络承载真实关联。

下次你问问题、做决策、复盘经历时，AI 会先把相关卡片读回 context，
基于你消化过的认知网络来思考；思考过程中产生的新洞察又会沉淀回去，
让网络越用越厚。长期来看，不同领域、不同人的子网络还可以连接碰撞，
在交叉处涌现出新的跨域模式。

## 特性

- **分层消化** // L1 原文 / L2 单材料精华 / L3 跨材料综合 / L4 跨域模式
- **真消化，不是摘录** // Scout 通读建主题卡，Deep 精读产出其余卡片；
  卡片用自己的话写、原子化、自足可读
- **Link 是真相** // 显性 link 网络承载关联，embedding 只是辅助建 link 的工具
- **双门禁入库** // 计算校验 + 语义校验，确保质量后才进库
- **越用越厚** // 提问、思考、实践的过程本身会沉淀新认知
- **跨域/跨人可连接** // 网络结构天然支持不同领域、不同人之间的碰撞
- **本地优先** // SQLite 在本地，向量模型自选

## 怎么开始

需要：Claude Code 或 Codex、Python 3.11、一个向量模型。

```bash
git clone git@github.com:q8886b/loom.git
cd loom
./install.sh
loom on
```

配本地向量模型（推荐 Ollama），编辑 `~/.loom/.env`：

```bash
ollama pull bge-m3
```

```
LOOM_EMBED_PROVIDER=ollama
LOOM_EMBED_MODEL=bge-m3
LOOM_EMBED_DIM=1024
```

试一份材料——在 Claude Code 里直接说：

> 用 loom-digest 把 `~/.loom/sources/07-LLM/demo/ch01.md` 消化成 L2

AI 自己读原文、写卡片、跑校验、入库。`loom search "..."` 验证。

更多见 [docs/quickstart.md](docs/quickstart.md)。

## 设计

Loom 的设计基准在 [004](docs/design/004-layered-redesign-purpose.md)（目的）
和 [005](docs/design/005-layered-redesign-harness.md)（harness 落地）。

## 开发

```bash
python3.11 -m pip install -e ".[dev]"
python3.11 -m pytest
```
