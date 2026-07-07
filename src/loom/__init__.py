"""Loom harness implementation.

Package structure:
  loom.store    - SQLite storage layer (cards, links, FTS5, sqlite-vec)
  loom.embed    - Configurable embedding providers (Ollama/OpenAI/Zhipu)
  loom.cli      - CLI entry (bin/loom dispatches here)
  loom.checks   - Computational checks (write-draft inline + stop-check batch)
"""
