#!/usr/bin/env python3.11
"""Read-only card-ID format and Luhmann parent-integrity audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loom import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=store.DB_PATH)
    parser.add_argument("--all", action="store_true", help="print every violation")
    parser.add_argument("--limit", type=int, default=20, help="sample size without --all")
    args = parser.parse_args()

    result = store.audit_luhmann_tree(args.db)
    if not args.all:
        limit = max(0, args.limit)
        result = {
            **result,
            "invalid_ids": result["invalid_ids"][:limit],
            "missing_parents": result["missing_parents"][:limit],
            "missing_parent_ids": result["missing_parent_ids"][:limit],
            "sample_limit": limit,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
