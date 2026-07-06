"""Console entry points for installed Loom packages."""
from __future__ import annotations

import os
import sys

from . import cli, store


def main() -> int:
    store.init_db()
    return cli.main(sys.argv[1:], entrypoint="loom")


def admin_main() -> int:
    store.init_db()
    return cli.main(sys.argv[1:], entrypoint="loom-admin")


if __name__ == "__main__":
    entrypoint = os.environ.get("LOOM_ENTRYPOINT", "loom")
    store.init_db()
    raise SystemExit(cli.main(sys.argv[1:], entrypoint=entrypoint))
