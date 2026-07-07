# Loom

**Language:** English | [简体中文](README.zh-CN.md)

Loom is a local-first cognitive harness for AI agents.

It is not a note app, and it is not a chatbot memory cache. Loom gives an
agent a disciplined way to read source material, digest it into cards, connect
those cards across materials, and grow reusable thinking patterns without
writing directly into the database.

The core design lives in:

- [004 - Layered Redesign Purpose](docs/design/004-layered-redesign-purpose.md)
- [005 - Layered Redesign Harness](docs/design/005-layered-redesign-harness.md)

## The Shape

Loom has four layers:

| Layer | Role | Output |
|---|---|---|
| `L1` | Faithful source capture | Markdown source cards |
| `L2` | Understanding one material | Concepts, structures, mechanisms, cases, judgments |
| `L3` | Thinking across materials | Synthesis, comparison, practical judgment |
| `L4` | Thinking about thinking | Patterns, judgments, reflections |

L1/L2 are about reading well. L3/L4 are about thinking with what has been read.

The important constraint: agents do not write straight into the card database.
They write drafts, Loom runs checks, then the agent performs a semantic review
before commit.

```text
write-draft -> mark-ready -> stop-check -> semantic review -> commit-ready
```

This is the harness: prompts explain the rules, tools enforce the state
transitions, hooks catch unfinished work, and the database keeps the graph
traceable.

## Search And Links

Vector search is a core capability. Without it, Loom loses much of its ability
to discover hidden relationships across materials.

But embeddings are not the source of truth. In Loom:

```text
embedding helps discover relationships
links record relationships
```

The embedding provider is configurable:

- Local Ollama embeddings, recommended for local-first use
- OpenAI-compatible embedding APIs
- Zhipu, kept as a compatibility preset

One database uses one embedding dimension. If you change embedding models, run:

```bash
loom-admin rebuild-embeddings
```

## Quick Start

```bash
git clone git@github.com:q8886b/loom.git
cd loom
./install.sh
```

Then follow [docs/quickstart.md](docs/quickstart.md) for embedding setup,
source import, search, hooks, and the optional Workbench.

## Private Data Boundary

The repository contains code, skills, tests, and design documents. It does not
contain your Loom data.

Runtime data lives outside Git:

```text
~/.loom/data/       SQLite database and derived indexes
~/.loom/cards/      Markdown card mirrors
~/.loom/sources/    Local source material
/tmp/loom_task/     Draft task workspaces
```

## Repository Map

```text
bin/                CLI wrappers
src/loom/           Python implementation
skills/             Agent skills for digest / think / use
docs/design/        Design baseline
workbench/          Optional local graph browser
tests/              Harness regression tests
```

## Development

```bash
python3.11 -m pip install -e ".[dev]"
python3.11 -m pytest
```
