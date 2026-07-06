"""bin/loom CLI entry point.

Usage:
  bin/loom <command> [args]

Commands are dispatched to functions in loom.cli. See loom/cli.py for implementations.
"""
import os
import sys

# Add repo/src to path so `loom` package resolves regardless of cwd.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from loom import store  # noqa: E402
from loom import cli  # noqa: E402

# 启动时跑 init_db：所有 CREATE TABLE IF NOT EXISTS + 一次性 schema 迁移都幂等。
# 首次连接的几毫秒开销换"schema 永远最新"的保证，无需独立的 migrate 命令。
store.init_db()

if __name__ == "__main__":
    entrypoint = os.environ.get("LOOM_ENTRYPOINT", "loom")
    sys.exit(cli.main(sys.argv[1:], entrypoint=entrypoint))
