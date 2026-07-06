# Contributing to Loom

Thanks for considering a contribution. Loom is intentionally local-first and
data-private, so the most important rule is: contribute code and public design
docs, not personal knowledge bases.

## Development Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

For the optional Workbench UI:

```bash
python -m pip install -e ".[workbench]"
cd workbench/frontend
npm install
npm run build
```

## Contribution Rules

- Keep personal data out of Git: `data/`, `cards/`, `sources/`, `.loom-local/`,
  and `docs/research/` are intentionally ignored.
- Do not commit copyrighted source material, exam questions, private notes,
  API keys, local SQLite databases, screenshots, generated frontend bundles, or
  agent runtime settings.
- Preserve the local-first contract: by default, Loom reads and writes under
  `~/.loom` or `LOOM_HOME`; tests should isolate this with a temporary
  directory.
- Hooks that modify Claude Code or Codex settings must stay documented,
  guarded by `loom on`, and skippable with `--no-hooks`.
- Prefer small, focused changes with tests for CLI state-machine behavior.

## Internationalization

User-facing project docs should exist in English and Simplified Chinese when
they explain installation, concepts, or maintenance. The English README is the
default entry point; `README.zh-CN.md` is the Simplified Chinese counterpart.

## Before Opening a Pull Request

```bash
pytest
git status --short
git ls-files docs/research data cards sources .loom-local
```

The final command should print nothing for a public contribution.
