# Loom

**Language:** English | [简体中文](README.zh-CN.md)

Loom is an external brain for AI agents — and a continuously evolving cognitive network.

Drop in a book, paper, or video — AI digests it into linked cards:
raw text → single-material digest → cross-material synthesis → cross-domain patterns.
Each card is typed by its cognitive role, and real associations are carried by
an explicit link network.

When you ask a question, make a decision, or review an experience, AI pulls the
relevant cards back into context and thinks through your digested network. New
insights from that thinking then feed back into the network, so it grows
denser with use. Over time, sub-networks from different domains or people can
connect and collide, producing new cross-domain patterns at their intersections.

## Highlights

- **Layered** // L1 source, L2 single-material digest, L3 cross-material synthesis, L4 cross-domain patterns
- **Real digestion, not excerpting** // Scout reads for theme cards, Deep reads for the rest; cards are in your own words, atomic, and self-contained
- **Links are the source of truth** // The explicit link network carries associations; embeddings are only a tool for discovering missing links
- **Double-gated entry** // Compute checks + semantic checks before anything enters the database
- **Builds up** // Asking, thinking, and practicing all feed new cognition back into the network
- **Cross-domain / cross-people connectable** // The network structure naturally supports collisions across domains and people
- **Local-first** // SQLite on disk, embedding model of your choice

## Quick Start

Need: Claude Code or Codex, Python 3.11, an embedding model.

```bash
git clone git@github.com:q8886b/loom.git
cd loom
./install.sh
loom on
```

Set up a local embedding model (recommended: Ollama), edit `~/.loom/.env`:

```bash
ollama pull bge-m3
```

```
LOOM_EMBED_PROVIDER=ollama
LOOM_EMBED_MODEL=bge-m3
LOOM_EMBED_DIM=1024
```

Try it — in Claude Code:

> Digest `~/.loom/sources/07-LLM/demo/ch01.md` into L2 with loom-digest

AI reads the source, drafts cards, runs checks, commits. Verify with
`loom search "..."`.

More in [docs/quickstart.md](docs/quickstart.md).

## Design

The design baseline lives in [004](docs/design/004-layered-redesign-purpose.md)
(purpose) and [005](docs/design/005-layered-redesign-harness.md) (harness).

## Development

```bash
python3.11 -m pip install -e ".[dev]"
python3.11 -m pytest
```
