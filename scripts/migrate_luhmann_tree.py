#!/usr/bin/env python3
"""Apply an explicit semantic Luhmann-ID plan to a database copy.

The script never infers semantic placement. It only enforces that a reviewed
plan accounts for every card in scope and produces a complete tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from array import array
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loom import store  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, nargs="+")
    parser.add_argument("--source-db", type=Path, default=store.DB_PATH)
    parser.add_argument("--output-db", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _letters(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("a") + remainder) + result
    return result


def _expand_tree_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if "outputs" in plan:
        return plan
    trees = plan.get("trees")
    if not isinstance(trees, list):
        return plan

    namespace = (plan.get("scope") or {}).get("namespace", "")
    outputs: list[dict[str, Any]] = []

    default_rationale = plan.get("default_rationale")

    def walk(node: dict[str, Any], target_id: str) -> None:
        sources = node.get("source_ids") or [node.get("source")]
        output = {
            "target_id": target_id,
            "source_ids": sources,
            "canonical_source_id": node.get("canonical") or sources[0],
            "rationale": node.get("rationale") or default_rationale,
        }
        for optional in ("title", "content_file"):
            if node.get(optional):
                output[optional] = node[optional]
        outputs.append(output)
        for child_index, child in enumerate(node.get("children", []), 1):
            suffix = str(child_index) if target_id[-1].isalpha() else _letters(child_index)
            walk(child, target_id + suffix)

    for root_index, tree in enumerate(trees, plan.get("root_start", 1)):
        walk(tree, f"{namespace}:{root_index}")
    return {**plan, "outputs": outputs}


def load_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    return _expand_tree_plan(plan)


def scope_rows(conn: sqlite3.Connection, scope: dict[str, str]) -> list[sqlite3.Row]:
    layer = scope["layer"]
    namespace = scope.get("source_id_prefix", scope["namespace"] + ":") + "%"
    return conn.execute(
        "SELECT * FROM cards WHERE layer=? AND id LIKE ? ORDER BY id",
        (layer, namespace),
    ).fetchall()


def source_ids_sha256(source_ids: set[str]) -> str:
    """Return a stable fingerprint for the exact migration input set."""
    return hashlib.sha256("\n".join(sorted(source_ids)).encode("utf-8")).hexdigest()


def validate_plan(
    plan: dict[str, Any], plan_path: Path, source_db: Path
) -> dict[str, Any]:
    errors: list[str] = []
    if plan.get("version") != 1:
        errors.append("plan.version must be 1")

    scope = plan.get("scope") or {}
    layer = scope.get("layer")
    namespace = scope.get("namespace")
    if layer not in {"L2", "L3", "L4"} or not namespace:
        errors.append("scope must contain layer=L2/L3/L4 and namespace")

    outputs = plan.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append("outputs must be a non-empty list")
        outputs = []

    with store.connect(source_db) as conn:
        source_rows = scope_rows(conn, scope) if layer and namespace else []
        source_cards = {row["id"]: dict(row) for row in source_rows}
        all_card_ids = {
            row["id"] for row in conn.execute("SELECT id FROM cards").fetchall()
        }

    source_ids = set(source_cards)
    source_fingerprint = source_ids_sha256(source_ids)
    expected_source_count = plan.get("expected_source_count")
    expected_source_fingerprint = plan.get("expected_source_ids_sha256")
    if plan.get("remaining_as_roots") and (
        expected_source_count is None or expected_source_fingerprint is None
    ):
        errors.append(
            "remaining_as_roots requires expected_source_count and "
            "expected_source_ids_sha256"
        )
    if expected_source_count is not None and expected_source_count != len(source_ids):
        errors.append(
            f"source count changed: expected {expected_source_count}, got {len(source_ids)}"
        )
    if (
        expected_source_fingerprint is not None
        and expected_source_fingerprint != source_fingerprint
    ):
        errors.append(
            "source ID set changed: expected sha256 "
            f"{expected_source_fingerprint}, got {source_fingerprint}"
        )

    if plan.get("remaining_as_roots"):
        planned = {
            source_id
            for output in outputs
            for source_id in output.get("source_ids", [])
        }
        namespace_prefix = scope["namespace"] + ":"
        root_numbers = [
            int(output["target_id"].removeprefix(namespace_prefix))
            for output in outputs
            if output.get("target_id", "").removeprefix(namespace_prefix).isdigit()
        ]
        next_root = max(root_numbers, default=0) + 1
        for source_id in sorted(set(source_cards) - planned):
            outputs.append(
                {
                    "target_id": f"{scope['namespace']}:{next_root}",
                    "source_ids": [source_id],
                    "canonical_source_id": source_id,
                    "rationale": "未确认存在强父子关系，保留为独立认知根；弱关联继续由 links 表达。",
                }
            )
            next_root += 1

    planned_sources: list[str] = []
    targets: list[str] = []
    for index, output in enumerate(outputs):
        label = f"outputs[{index}]"
        target = output.get("target_id")
        sources = output.get("source_ids")
        canonical = output.get("canonical_source_id")
        if not isinstance(target, str) or not target:
            errors.append(f"{label}.target_id is required")
            continue
        targets.append(target)
        if not store.card_id_matches_layer(target, layer or ""):
            errors.append(f"{target}: invalid {layer} card ID")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{target}: source_ids must contain an existing cognitive card")
            continue
        planned_sources.extend(sources)
        if canonical not in sources:
            errors.append(f"{target}: canonical_source_id must be in source_ids")
        if not output.get("rationale"):
            errors.append(f"{target}: semantic rationale is required")
        content_file = output.get("content_file")
        if content_file and not (plan_path.parent / content_file).is_file():
            errors.append(f"{target}: content_file does not exist: {content_file}")

    duplicate_sources = sorted(
        source for source, count in Counter(planned_sources).items() if count != 1
    )
    if duplicate_sources:
        errors.append(f"source cards must appear exactly once: {duplicate_sources}")

    planned_ids = set(planned_sources)
    if source_ids != planned_ids:
        missing = sorted(source_ids - planned_ids)
        unknown = sorted(planned_ids - source_ids)
        if missing:
            errors.append(f"unaccounted source cards: {missing}")
        if unknown:
            errors.append(f"source_ids outside scope: {unknown}")

    duplicate_targets = sorted(
        target for target, count in Counter(targets).items() if count != 1
    )
    if duplicate_targets:
        errors.append(f"target IDs must be unique: {duplicate_targets}")

    target_ids = set(targets)
    collisions = sorted((target_ids & all_card_ids) - source_ids)
    if collisions:
        errors.append(f"target IDs collide with cards outside scope: {collisions}")
    for target in targets:
        parent = store._parent_id(target)
        if parent is not None and parent not in target_ids:
            errors.append(f"{target}: missing output parent {parent}")

    return {
        "ok": not errors,
        "scope": scope,
        "source_count": len(source_ids),
        "source_ids_sha256": source_fingerprint,
        "target_count": len(target_ids),
        "merge_reduction": len(source_ids) - len(target_ids),
        "errors": errors,
        "source_cards": source_cards,
    }


def backup_database(source_db: Path, output_db: Path) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    with store.connect(source_db) as source, store.connect(output_db) as target:
        source.backup(target)


def merged_tags(cards: list[dict[str, Any]]) -> list[str]:
    tags: set[str] = set()
    for card in cards:
        tags.update(store.parse_tags_json(card.get("tags") or "[]"))
    return sorted(tags)


def merged_embedding(
    source_ids: list[str], embeddings: dict[str, bytes]
) -> bytes | None:
    blobs = [embeddings[source_id] for source_id in source_ids if source_id in embeddings]
    if not blobs:
        return None
    if len(blobs) == 1:
        return bytes(blobs[0])

    vectors: list[array[float]] = []
    for blob in blobs:
        vector = array("f")
        vector.frombytes(blob)
        vectors.append(vector)
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors[1:]):
        raise ValueError("cannot merge embeddings with different dimensions")

    averaged = array(
        "f",
        (
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(dimensions)
        ),
    )
    return averaged.tobytes()


def build_id_rewriter(mapping: dict[str, str]):
    alternatives = "|".join(re.escape(card_id) for card_id in sorted(mapping, key=len, reverse=True))
    pattern = re.compile(rf"(?<![a-z0-9:_-])(?:{alternatives})(?![a-z0-9_-])")

    def rewrite(text: str) -> str:
        return pattern.sub(lambda match: mapping[match.group(0)], text)

    return rewrite


def apply_plan(
    plan: dict[str, Any],
    plan_path: Path,
    source_db: Path,
    output_db: Path,
    *,
    prepared_copy: bool = False,
) -> dict[str, Any]:
    if not prepared_copy:
        backup_database(source_db, output_db)
    outputs = plan["outputs"]
    mapping = {
        source_id: output["target_id"]
        for output in outputs
        for source_id in output["source_ids"]
    }
    rewrite_ids = build_id_rewriter(mapping)
    source_ids = sorted(mapping)
    target_ids = sorted({output["target_id"] for output in outputs})
    retired_ids = sorted(set(source_ids) - set(target_ids))
    placeholders = ",".join("?" for _ in source_ids)
    timestamp = time.time()

    with store.connect(output_db) as conn:
        cards = {
            row["id"]: dict(row)
            for row in conn.execute(
                f"SELECT * FROM cards WHERE id IN ({placeholders})", source_ids
            ).fetchall()
        }
        old_links = [
            (row["source_id"], row["target_id"])
            for row in conn.execute("SELECT source_id, target_id FROM links").fetchall()
        ]
        embeddings = {
            row["card_id"]: row["embedding"]
            for row in conn.execute(
                f"SELECT card_id, embedding FROM cards_vec WHERE card_id IN ({placeholders})",
                source_ids,
            ).fetchall()
        }
        expected_vector_count = sum(
            any(source_id in embeddings for source_id in output["source_ids"])
            for output in outputs
        )
        content_rewrites = 0
        source_rewrites = 0
        for row in conn.execute(
            f"SELECT id,content,source FROM cards WHERE id NOT IN ({placeholders})",
            source_ids,
        ).fetchall():
            new_content = rewrite_ids(row["content"])
            new_source = mapping.get(row["source"], row["source"])
            if new_content != row["content"] or new_source != row["source"]:
                conn.execute(
                    "UPDATE cards SET content=?,source=?,updated_at=? WHERE id=?",
                    (new_content, new_source, timestamp, row["id"]),
                )
                content_rewrites += new_content != row["content"]
                source_rewrites += new_source != row["source"]

        conn.execute("DELETE FROM links")
        conn.execute(f"DELETE FROM cards_vec WHERE card_id IN ({placeholders})", source_ids)
        conn.execute(f"DELETE FROM card_tags WHERE card_id IN ({placeholders})", source_ids)
        conn.execute(f"DELETE FROM cards WHERE id IN ({placeholders})", source_ids)

        for output in outputs:
            target = output["target_id"]
            canonical = cards[output["canonical_source_id"]]
            merged = [cards[source_id] for source_id in output["source_ids"]]
            content = canonical["content"]
            if output.get("content_file"):
                content = (plan_path.parent / output["content_file"]).read_text(
                    encoding="utf-8"
                ).strip()
            content = rewrite_ids(content)
            title = output.get("title") or canonical["title"]
            origin = "human" if any(c.get("origin") == "human" for c in merged) else "ai"
            tags_json = store.tags_to_json(merged_tags(merged))
            created_at = min(card["created_at"] for card in merged)
            conn.execute(
                """INSERT INTO cards
                   (id,title,type,content,source,layer,origin,tags,use_count,
                    search_count,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,0,0,?,?)""",
                (
                    target,
                    title,
                    canonical["type"],
                    content,
                    mapping.get(canonical["source"], canonical["source"]),
                    canonical["layer"],
                    origin,
                    tags_json,
                    created_at,
                    timestamp,
                ),
            )
            for tag in merged_tags(merged):
                conn.execute(
                    "INSERT INTO card_tags(card_id,tag) VALUES (?,?)", (target, tag)
                )
            embedding = merged_embedding(output["source_ids"], embeddings)
            if embedding is not None:
                conn.execute(
                    "INSERT INTO cards_vec(card_id, embedding) VALUES (?,?)",
                    (target, embedding),
                )

        remapped_links = {
            (mapping.get(source, source), mapping.get(target, target))
            for source, target in old_links
            if mapping.get(source, source) != mapping.get(target, target)
        }
        conn.executemany(
            "INSERT INTO links(source_id,target_id) VALUES (?,?)",
            sorted(remapped_links),
        )

    with store.connect(output_db) as conn:
        actual_targets = {
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM cards WHERE id IN ({','.join('?' for _ in target_ids)})",
                target_ids,
            ).fetchall()
        }
        old_refs = 0
        if retired_ids:
            retired_placeholders = ",".join("?" for _ in retired_ids)
            old_refs = conn.execute(
                f"""SELECT COUNT(*) AS n FROM links
                    WHERE source_id IN ({retired_placeholders})
                       OR target_id IN ({retired_placeholders})""",
                retired_ids + retired_ids,
            ).fetchone()["n"]
        dangling_links = conn.execute(
            """SELECT COUNT(*) AS n FROM links l
               LEFT JOIN cards s ON s.id=l.source_id
               LEFT JOIN cards t ON t.id=l.target_id
               WHERE s.id IS NULL OR t.id IS NULL"""
        ).fetchone()["n"]
        counters = conn.execute(
            "SELECT SUM(use_count) AS uses, SUM(search_count) AS searches "
            f"FROM cards WHERE id IN ({','.join('?' for _ in target_ids)})",
            target_ids,
        ).fetchone()
        missing_parents = []
        for target in target_ids:
            parent = store._parent_id(target)
            if parent is not None and parent not in actual_targets:
                missing_parents.append({"id": target, "parent_id": parent})
        vector_count = conn.execute(
            "SELECT COUNT(*) AS n FROM cards_vec "
            f"WHERE card_id IN ({','.join('?' for _ in target_ids)})",
            target_ids,
        ).fetchone()["n"]
        stale_text_refs = 0
        if retired_ids:
            find_retired = build_id_rewriter({card_id: "" for card_id in retired_ids})
            for row in conn.execute("SELECT content FROM cards").fetchall():
                stale_text_refs += find_retired(row["content"]) != row["content"]

    checks = {
        "target_set_exact": actual_targets == set(target_ids),
        "missing_parents": missing_parents,
        "retired_link_references": old_refs,
        "dangling_links": dangling_links,
        "use_count_sum": counters["uses"] or 0,
        "search_count_sum": counters["searches"] or 0,
        "vectors_preserved": vector_count,
        "vectors_expected": expected_vector_count,
        "content_cards_rewritten": content_rewrites,
        "source_fields_rewritten": source_rewrites,
        "cards_with_stale_text_references": stale_text_refs,
    }
    checks["ok"] = (
        checks["target_set_exact"]
        and not missing_parents
        and old_refs == 0
        and dangling_links == 0
        and checks["use_count_sum"] == 0
        and checks["search_count_sum"] == 0
        and vector_count == expected_vector_count
        and stale_text_refs == 0
    )
    return {
        "status": "dry_run_applied",
        "source_db": str(source_db.resolve()),
        "output_db": str(output_db.resolve()),
        "source_count": len(source_ids),
        "target_count": len(target_ids),
        "merge_reduction": len(source_ids) - len(target_ids),
        "checks": checks,
    }


def main() -> int:
    args = parse_args()
    source_db = args.source_db.resolve()
    prepared: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for raw_plan_path in args.plan:
        plan_path = raw_plan_path.resolve()
        plan = load_plan(plan_path)
        validation = validate_plan(plan, plan_path, source_db)
        public_validation = {k: v for k, v in validation.items() if k != "source_cards"}
        prepared.append((plan_path, plan, public_validation))

    validations_ok = all(validation["ok"] for _, _, validation in prepared)
    if not validations_ok or args.validate_only:
        print(
            json.dumps(
                {"validations": [validation for _, _, validation in prepared]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if validations_ok else 1

    if args.output_db is None:
        raise SystemExit("--output-db is required unless --validate-only is used")
    output_db = args.output_db.resolve()
    if output_db == source_db:
        raise SystemExit("refusing to modify the source database; choose --output-db")

    backup_database(source_db, output_db)
    results = [
        apply_plan(
            plan,
            plan_path,
            source_db,
            output_db,
            prepared_copy=True,
        )
        for plan_path, plan, _ in prepared
    ]
    print(
        json.dumps(
            {
                "validations": [validation for _, _, validation in prepared],
                "migrations": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all(result["checks"]["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
