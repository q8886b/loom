"""Loom Workbench backend — single-file FastAPI.

5 endpoints, all read-only (writes go through bin/loom).
Built fresh on the new loom.store functional API.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"
for path in (str(_PROJECT_ROOT), str(_SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from loom import store  # noqa: E402

store.init_db()

app = FastAPI(title="Loom Workbench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ns(card_id: str) -> str:
    return card_id.split(":", 1)[0] if ":" in card_id else ""


def _tags(value: str | None) -> list[str]:
    try:
        return store.parse_tags_json(value or "[]")
    except ValueError:
        return []


def _brief(conn, card_row) -> dict[str, Any]:
    """统一图谱/搜索/详情的轻量字段。L1 节点不返回 full content（008 §18）。"""
    row = dict(card_row)
    layer = row["layer"]
    if layer == "L1":
        # 读取全文做摘要/统计，但不回传 content 字段
        content = ""
        try:
            content_row = conn.execute(
                "SELECT content FROM cards WHERE id=?", (row["id"],)
            ).fetchone()
            content = content_row["content"] if content_row else ""
        except Exception:
            content = ""
        return {
            "id": row["id"],
            "title": row["title"],
            "type": row["type"],
            "layer": row["layer"],
            "namespace": _ns(row["id"]),
            "source": row["source"] or "",
            "origin": row.get("origin") or "ai",
            "tags": _tags(row.get("tags")),
            "use_count": row["use_count"],
            "search_count": row["search_count"],
            "snippet": content[:200],
            "content_size": len(content),
            "has_full_content": True,
        }
    return {
        "id": row["id"],
        "title": row["title"],
        "type": row["type"],
        "layer": row["layer"],
        "namespace": _ns(row["id"]),
        "source": row["source"] or "",
        "origin": row.get("origin") or "ai",
        "tags": _tags(row.get("tags")),
        "use_count": row["use_count"],
        "search_count": row["search_count"],
    }


def _full_card(card_id: str) -> dict[str, Any] | None:
    """详情接口：显式返回 L1 全文（点击节点时按需调用）。"""
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
    d["namespace"] = _ns(card_id)
    d["links"] = store.get_links(card_id)
    d["origin"] = d.get("origin") or "ai"
    d["tags"] = _tags(d.get("tags"))
    return d


def _tag_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return store.normalize_tags([s.strip() for s in raw.split(",") if s.strip()])


def _prefix_bounds(ns: str) -> tuple[str, str]:
    prefix = f"{ns}:"
    return prefix, f"{ns};"


def _append_ns_filter(sql: str, params: list[Any], ns: str, alias: str = "c") -> tuple[str, list[Any]]:
    lower, upper = _prefix_bounds(ns)
    return sql + f" AND {alias}.id >= ? AND {alias}.id < ?", [*params, lower, upper]


def _append_tag_filter(sql: str, params: list[Any], tags: list[str], alias: str = "c") -> tuple[str, list[Any]]:
    tag_sql, tag_params = store._tag_filter_sql(tags, alias=alias)
    return sql + tag_sql, [*params, *tag_params]


def _dedup_edges(rows) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []
    for r in rows:
        s, t = r["source_id"], r["target_id"]
        key = (s, t) if s <= t else (t, s)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": s, "target": t})
    return edges


# --------------------------------------------------------------------------
# Tree (Luhmann-style, derived from the store's canonical ID parser)
# --------------------------------------------------------------------------

def _parent_of(card_id: str) -> str | None:
    """Return the canonical L2/L3/L4 parent; L1 is never part of the tree."""
    return store._parent_id(card_id)


def _luhmann_depth(card_id: str, valid_ids: set[str] | None = None) -> int:
    """Depth from top: top-level = 1, child = 2, grandchild = 3, ...

    If valid_ids is provided, stops walking when parent is not in the set
    (treats dangling parents as top). This handles cross-chapter abstractions
    like 'llm:1a' whose virtual parent 'llm:1' doesn't exist as a card.
    """
    depth = 1
    current = card_id
    seen: set[str] = set()
    while True:
        if current in seen:
            break
        seen.add(current)
        p = _parent_of(current)
        if not p:
            break
        if valid_ids is not None and p not in valid_ids:
            break
        depth += 1
        current = p
    return depth


@app.get("/api/tree")
def tree(ns: str | None = Query(None), tag: str | None = Query(None)) -> dict[str, Any]:
    tags = _tag_list(tag)
    sql = "SELECT id, title, type, layer, origin, tags FROM cards c WHERE 1=1"
    params: list[str] = []
    if ns:
        sql, params = _append_ns_filter(sql, params, ns, alias="c")
    sql, params = _append_tag_filter(sql, params, tags, alias="c")
    sql += " ORDER BY c.id"
    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    nodes_by_id = {r["id"]: r for r in rows}

    # Pass 1: build full children map
    children: dict[str, list[str]] = {}
    is_child: set[str] = set()
    for r in rows:
        pid = _parent_of(r["id"])
        if pid and pid in nodes_by_id:
            children.setdefault(pid, []).append(r["id"])
            is_child.add(r["id"])

    # Pass 2: roots = cards that are not anyone's child
    roots = [_tree_node(nodes_by_id[r["id"]], nodes_by_id, children)
             for r in rows if r["id"] not in is_child]
    return {"namespace": ns or "all", "roots": roots}


def _tree_node(row, by_id, children_map) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "type": row["type"],
        "layer": row["layer"],
        "namespace": _ns(row["id"]),
        "origin": row.get("origin") or "ai",
        "tags": _tags(row.get("tags")),
        "children": [
            _tree_node(by_id[cid], by_id, children_map)
            for cid in children_map.get(row["id"], [])
        ],
    }


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------
@app.get("/api/stats")
def stats(
    include_orphans: bool = Query(False),
    include_activity: bool = Query(False),
) -> dict[str, Any]:
    orphan_cards: int | None = None
    orphan_rate: float | None = None
    active_use: int | None = None
    active_search: int | None = None
    base: dict[str, Any] = {}
    ns_counts: dict[str, int] = {}
    with store.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        by_layer = {r[0]: r[1] for r in conn.execute("SELECT layer, COUNT(*) FROM cards GROUP BY layer")}
        by_type = {r[0]: r[1] for r in conn.execute("SELECT type, COUNT(*) FROM cards GROUP BY type")}
        by_origin = {r[0]: r[1] for r in conn.execute("SELECT origin, COUNT(*) FROM cards GROUP BY origin")}
        tag_count = conn.execute("SELECT COUNT(DISTINCT tag) FROM card_tags").fetchone()[0]
        links_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        if include_activity:
            active_use = conn.execute("SELECT COUNT(*) FROM cards WHERE use_count > 0").fetchone()[0]
            active_search = conn.execute("SELECT COUNT(*) FROM cards WHERE search_count > 0").fetchone()[0]
        if include_orphans:
            orphan_cards = conn.execute(
                """SELECT COUNT(*) FROM cards c WHERE
                   NOT EXISTS (SELECT 1 FROM links l WHERE l.source_id = c.id)
                   AND NOT EXISTS (SELECT 1 FROM links l WHERE l.target_id = c.id)"""
            ).fetchone()[0]
            orphan_rate = (orphan_cards / total) if total else 0.0
        rows = conn.execute(
            "SELECT substr(id, 1, instr(id, ':')-1) AS ns, COUNT(*) AS c "
            "FROM cards WHERE instr(id, ':') > 0 GROUP BY ns"
        ).fetchall()
        for r in rows:
            ns_counts[r["ns"]] = r["c"]
    base.update({
        "total_cards": total,
        "by_layer": by_layer,
        "by_type": by_type,
        "by_origin": by_origin,
        "tag_count": tag_count,
        "links_count": links_count,
        "orphan_cards": orphan_cards,
        "orphan_rate": orphan_rate,
        "cards_with_use_count": active_use,
        "cards_with_search_count": active_search,
        "namespaces": ns_counts,
    })
    return base


@app.get("/api/tags")
def tags() -> dict[str, Any]:
    items = store.list_tags()
    return {"count": len(items), "tags": items}


@app.get("/api/version")
def version() -> dict[str, Any]:
    with store.connect() as conn:
        row = conn.execute("SELECT MAX(updated_at) AS updated_at, COUNT(*) AS count FROM cards").fetchone()
        tag_row = conn.execute("SELECT COUNT(*) AS count FROM card_tags").fetchone()
    return {
        "cards_updated_at": row["updated_at"] or 0,
        "cards_count": row["count"],
        "tag_edges": tag_row["count"],
    }


@app.get("/api/cards/by_ns/{ns}")
def cards_by_ns(ns: str, tag: str | None = Query(None)) -> dict[str, Any]:
    tags = _tag_list(tag)
    with store.connect() as conn:
        sql = "SELECT id, title, type, layer, origin, tags FROM cards c WHERE 1=1"
        params: list[Any] = []
        sql, params = _append_ns_filter(sql, params, ns, alias="c")
        sql, params = _append_tag_filter(sql, params, tags, alias="c")
        sql += " ORDER BY c.id"
        rows = conn.execute(sql, params).fetchall()
    cards = [
        {
            "id": r["id"],
            "title": r["title"],
            "type": r["type"],
            "layer": r["layer"],
            "namespace": _ns(r["id"]),
            "origin": r["origin"] or "ai",
            "tags": _tags(r["tags"]),
        }
        for r in rows
    ]
    by_layer: dict[str, int] = {}
    for card in cards:
        by_layer[card["layer"]] = by_layer.get(card["layer"], 0) + 1
    return {"namespace": ns, "count": len(cards), "by_layer": by_layer, "cards": cards}


# --------------------------------------------------------------------------
# Card
# --------------------------------------------------------------------------
@app.get("/api/cards/{card_id}")
def get_card(card_id: str) -> dict[str, Any]:
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    card["namespace"] = _ns(card_id)
    card["links"] = store.get_links(card_id)
    card["origin"] = card.get("origin") or "ai"
    card["tags"] = _tags(card.get("tags"))
    return card


@app.get("/api/graph/expand/{card_id}")
def graph_expand(card_id: str) -> dict[str, Any]:
    """Return direct children (Luhmann) + link-neighbors of a card.

    Used for incremental expansion: single-click a card → frontend appends
    these nodes to the current graph without re-laying-out existing nodes.
    """
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")

    with store.connect() as conn:
        # Luhmann children: id LIKE 'parent%' with single extra segment
        all_rows = conn.execute(
            "SELECT id, title, type, layer, source, origin, tags, use_count, search_count FROM cards ORDER BY id"
        ).fetchall()
        all_cards = [_brief(conn, r) for r in all_rows]
        link_rows = conn.execute(
            "SELECT source_id, target_id FROM links"
        ).fetchall()

    all_ids = {c["id"] for c in all_cards}
    # Luhmann children (direct: parent + one segment)
    children = []
    for c in all_cards:
        if c["id"] == card_id:
            continue
        p = _parent_of(c["id"])
        if p == card_id:
            children.append(c)

    # Link neighbors (1-hop)
    link_neighbors = []
    for r in link_rows:
        a, b = r["source_id"], r["target_id"]
        if a == card_id and b in all_ids:
            link_neighbors.append(b)
        elif b == card_id and a in all_ids:
            link_neighbors.append(a)
    link_neighbor_ids = set(link_neighbors)

    # Combine: children + link_neighbors, deduped
    expand_ids = {card_id}
    for c in children:
        expand_ids.add(c["id"])
    for nid in link_neighbor_ids:
        expand_ids.add(nid)

    visible_cards = [c for c in all_cards if c["id"] in expand_ids]

    # Hierarchy edges within this subset
    hierarchy_pairs: set[tuple[str, str]] = set()
    for c in visible_cards:
        p = _parent_of(c["id"])
        if p and p in expand_ids:
            hierarchy_pairs.add((p, c["id"]))

    # Link edges within subset
    link_pairs: set[tuple[str, str]] = set()
    for r in link_rows:
        a, b = r["source_id"], r["target_id"]
        if a in expand_ids and b in expand_ids:
            key = (a, b) if a <= b else (b, a)
            if key not in hierarchy_pairs:
                link_pairs.add(key)

    return {
        "nodes": visible_cards,
        "hierarchy_edges": [{"source": a, "target": b} for a, b in hierarchy_pairs],
        "link_edges": [{"source": a, "target": b} for a, b in link_pairs],
    }


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
@app.get("/api/search")
def search(
    q: str,
    ns: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    top: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    query = q.strip()
    tags = _tag_list(tag)
    # FTS5 trigram tokenizer needs >= 3 chars; fall back to LIKE for short queries
    if len(query) < 3:
        results = _search_like(query, top=top, ns=ns, type_=type, tags=tags)
    else:
        results = store.search_fts(query, top=top, ns=ns, type_=type, tags=tags)
        # If FTS returns nothing, try LIKE fallback
        if not results:
            results = _search_like(query, top=top, ns=ns, type_=type, tags=tags)
    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id": r["id"],
                "title": r["title"],
                "type": r["type"],
                "layer": r["layer"],
                "namespace": _ns(r["id"]),
                "source": r.get("source") or "",
                "origin": r.get("origin") or "ai",
                "tags": _tags(r.get("tags")),
                "score": r.get("score"),
            }
            for r in results
        ],
    }


def _search_like(query: str, top: int = 20, ns: str | None = None,
                 type_: str | None = None,
                 tags: list[str] | None = None) -> list[dict[str, Any]]:
    """Fallback search using LIKE for short queries or when FTS fails."""
    with store.connect() as conn:
        sql = """SELECT id, title, type, layer, source, origin, tags FROM cards c
                 WHERE (title LIKE ? OR content LIKE ?)"""
        params: list[Any] = [f"%{query}%", f"%{query}%"]
        if ns:
            sql, params = _append_ns_filter(sql, params, ns, alias="c")
        if type_:
            sql += " AND c.type = ?"
            params.append(type_)
        sql, params = _append_tag_filter(sql, params, tags or [], alias="c")
        sql += " ORDER BY c.id LIMIT ?"
        params.append(top)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------
@app.get("/api/graph/overview")
def graph_overview(max_depth: int = Query(1, ge=0, le=10)) -> dict[str, Any]:
    """Global graph, density-controlled view.

    max_depth=0 → namespace clusters only (special: returns ns as virtual nodes)
    max_depth=1 → theme/structure cards (the trunk)
    max_depth=2 → trunk + up to 2 children per parent
    max_depth=3 → trunk + up to 3 children/parent over 2 extra levels
    """
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, type, layer, source, origin, tags, use_count, search_count FROM cards ORDER BY id"
        ).fetchall()
        all_cards = [_brief(conn, r) for r in rows]
        all_link_rows = conn.execute(
            "SELECT source_id, target_id FROM links"
        ).fetchall()

    # L0: namespace virtual nodes
    if max_depth == 0:
        ns_counts: dict[str, int] = {}
        ns_links: dict[tuple[str, str], int] = {}
        for c in all_cards:
            ns_counts[c["namespace"]] = ns_counts.get(c["namespace"], 0) + 1
        # ns-level edges: any link between cards of different ns
        for r in all_link_rows:
            a, b = r["source_id"], r["target_id"]
            na, nb = _ns(a), _ns(b)
            if na != nb:
                key = (na, nb) if na <= nb else (nb, na)
                ns_links[key] = ns_links.get(key, 0) + 1
        nodes = [
            {
                "id": ns,
                "title": f"{ns} ({count})",
                "type": "namespace",
                "layer": "L0",
                "namespace": ns,
                "source": "",
                "depth": 0,
            }
            for ns, count in ns_counts.items()
        ]
        return {
            "nodes": nodes,
            "hierarchy_edges": [],
            "link_edges": [{"source": a, "target": b, "weight": w} for (a, b), w in ns_links.items()],
        }

    # L1+: trunk = theme/structure cards, then expand Luhmann children
    # per parent with a cap so SVG rendering stays responsive.
    all_ids = {c["id"] for c in all_cards}
    parent_of = {c["id"]: _parent_of(c["id"]) for c in all_cards}
    trunk = [c for c in all_cards if c["type"] in ("主题", "结构")]
    trunk_ids = {c["id"] for c in trunk}

    if max_depth == 1:
        visible_ids = set(trunk_ids)
    else:
        # Expand depth-first-ish: each parent contributes at most `cap` children.
        # Caps chosen so L2/L3 stay well under 100 nodes for smooth SVG rendering.
        cap = {2: 2, 3: 3}.get(max_depth, 3)
        visible_ids = set(trunk_ids)
        current = set(trunk_ids)
        for _ in range(1, max_depth):
            nxt: set[str] = set()
            children_by_parent: dict[str, list[str]] = {}
            for c in all_cards:
                pid = parent_of[c["id"]]
                if pid and pid in current and c["id"] not in visible_ids:
                    children_by_parent.setdefault(pid, []).append(c["id"])
            for pid, child_ids in children_by_parent.items():
                # Keep stable ordering by Luhmann id
                for cid in sorted(child_ids)[:cap]:
                    nxt.add(cid)
            visible_ids.update(nxt)
            current = nxt

    visible = [c for c in all_cards if c["id"] in visible_ids]
    visible_ids = {c["id"] for c in visible}

    # Hierarchy edges: ID-based parent → child
    hierarchy_pairs: set[tuple[str, str]] = set()
    for c in visible:
        p = parent_of[c["id"]]
        if p and p in visible_ids:
            hierarchy_pairs.add((p, c["id"]))

    # Link edges: cards.links table, minus those that are also hierarchy
    link_pairs: set[tuple[str, str]] = set()
    for r in all_link_rows:
        a, b = r["source_id"], r["target_id"]
        if a in visible_ids and b in visible_ids:
            key = (a, b) if a <= b else (b, a)
            if key not in hierarchy_pairs:
                link_pairs.add(key)

    for c in visible:
        c["depth"] = _luhmann_depth(c["id"], all_ids)

    return {
        "nodes": visible,
        "hierarchy_edges": [{"source": a, "target": b} for a, b in hierarchy_pairs],
        "link_edges": [{"source": a, "target": b} for a, b in link_pairs],
    }


@app.get("/api/graph/by_ns/{ns}")
def graph_by_ns(
    ns: str,
    tag: str | None = Query(None),
    view: str = Query("all", pattern="^(all|summary)$"),
    layer: str | None = Query(None),
    include: str | None = Query(None),
    limit: int = Query(0, ge=0, le=1000),
) -> dict[str, Any]:
    """All cards in a namespace + their internal edges + cross-namespace links.

    cross_links: links where one end is in this ns and the other is outside.
    Each entry has source, target, external_id, external_ns, external_title.
    """
    tags = _tag_list(tag)
    include_ids = {s.strip() for s in (include or "").split(",") if s.strip()}
    with store.connect() as conn:
        sql = "SELECT id, title, type, layer, source, origin, tags, use_count, search_count FROM cards c WHERE 1=1"
        params: list[Any] = []
        sql, params = _append_ns_filter(sql, params, ns, alias="c")
        if layer:
            sql += " AND c.layer = ?"
            params.append(layer)
        elif view == "summary":
            sql += " AND c.layer IN ('L3', 'L4')"
        sql, params = _append_tag_filter(sql, params, tags, alias="c")
        sql += " ORDER BY c.id"
        if view == "summary" and limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        existing_ids = {r["id"] for r in rows}
        extra_ids = sorted(include_ids - existing_ids)
        if extra_ids:
            placeholders = ",".join("?" * len(extra_ids))
            extra_sql = f"SELECT id, title, type, layer, source, origin, tags, use_count, search_count FROM cards c WHERE c.id IN ({placeholders})"
            extra_params: list[Any] = list(extra_ids)
            tag_sql, tag_params = _append_tag_filter("", [], tags, alias="c")
            extra_sql += tag_sql
            extra_params.extend(tag_params)
            rows.extend(conn.execute(extra_sql, extra_params).fetchall())
        cards = [_brief(conn, r) for r in rows]
        ids = {c["id"] for c in cards}
        link_rows = []
        all_card_map: dict[str, dict[str, Any]] = {}
        if ids:
            lower, upper = _prefix_bounds(ns)
            link_rows = conn.execute(
                f"SELECT source_id, target_id FROM links "
                f"WHERE (source_id >= ? AND source_id < ?) "
                f"OR (target_id >= ? AND target_id < ?)",
                (lower, upper, lower, upper),
            ).fetchall()
            external_ids: set[str] = set()
            for r in link_rows:
                a, b = r["source_id"], r["target_id"]
                if a in ids and b not in ids:
                    external_ids.add(b)
                elif b in ids and a not in ids:
                    external_ids.add(a)
            if external_ids:
                ext_placeholders = ",".join("?" * len(external_ids))
                all_card_rows = conn.execute(
                    f"SELECT id, title, type, layer, origin, tags FROM cards "
                    f"WHERE id IN ({ext_placeholders})",
                    tuple(external_ids),
                ).fetchall()
                all_card_map = {r["id"]: dict(r) for r in all_card_rows}

    hierarchy_pairs: set[tuple[str, str]] = set()
    for c in cards:
        p = _parent_of(c["id"])
        if p and p in ids:
            hierarchy_pairs.add((p, c["id"]))

    link_pairs: set[tuple[str, str]] = set()
    cross_links_seen: set[tuple[str, str]] = set()
    cross_links: list[dict[str, Any]] = []
    for r in link_rows:
        a, b = r["source_id"], r["target_id"]
        a_in = a in ids
        b_in = b in ids
        if a_in and b_in:
            key = (a, b) if a <= b else (b, a)
            if key not in hierarchy_pairs:
                link_pairs.add(key)
        elif a_in and not b_in:
            key = (a, b) if a <= b else (b, a)
            if key not in cross_links_seen:
                cross_links_seen.add(key)
                ext = all_card_map.get(b)
                cross_links.append({
                    "source": a, "target": b,
                    "external_id": b,
                    "external_ns": _ns(b),
                    "external_title": ext["title"] if ext else b,
                    "external_type": ext["type"] if ext else "",
                    "external_layer": ext["layer"] if ext else "",
                    "external_origin": ext.get("origin", "ai") if ext else "ai",
                    "external_tags": _tags(ext.get("tags")) if ext else [],
                })
        elif b_in and not a_in:
            key = (a, b) if a <= b else (b, a)
            if key not in cross_links_seen:
                cross_links_seen.add(key)
                ext = all_card_map.get(a)
                cross_links.append({
                    "source": a, "target": b,
                    "external_id": a,
                    "external_ns": _ns(a),
                    "external_title": ext["title"] if ext else a,
                    "external_type": ext["type"] if ext else "",
                    "external_layer": ext["layer"] if ext else "",
                    "external_origin": ext.get("origin", "ai") if ext else "ai",
                    "external_tags": _tags(ext.get("tags")) if ext else [],
                })

    return {
        "nodes": cards,
        "hierarchy_edges": [{"source": a, "target": b} for a, b in hierarchy_pairs],
        "link_edges": [{"source": a, "target": b} for a, b in link_pairs],
        "cross_links": cross_links,
    }


@app.get("/api/graph/cluster/{card_id}")
def graph_cluster(
    card_id: str,
    depth: int = Query(2, ge=1, le=3),
) -> dict[str, Any]:
    center = store.get_card(card_id)
    if not center:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")

    neighbor_ids = store.get_neighbors(card_id, depth=depth)
    all_ids = [card_id, *neighbor_ids]
    with store.connect() as conn:
        placeholders = ",".join("?" * len(all_ids))
        rows = conn.execute(
            f"SELECT id, title, type, layer, source, origin, tags, use_count, search_count FROM cards WHERE id IN ({placeholders})",
            all_ids,
        ).fetchall()
        cards = [dict(r) for r in rows]
        link_rows = conn.execute(
            f"SELECT source_id, target_id FROM links "
            f"WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})",
            (*all_ids, *all_ids),
        ).fetchall()

    visible_ids = {c["id"] for c in cards}
    # Hierarchy edges
    hierarchy_pairs: set[tuple[str, str]] = set()
    for c in cards:
        p = _parent_of(c["id"])
        if p and p in visible_ids:
            hierarchy_pairs.add((p, c["id"]))
    # Link edges (excluding hierarchy)
    link_pairs: set[tuple[str, str]] = set()
    for r in link_rows:
        a, b = r["source_id"], r["target_id"]
        key = (a, b) if a <= b else (b, a)
        if key not in hierarchy_pairs:
            link_pairs.add(key)

    layer_order = {"L1": 0, "L2_light": 1, "L2": 2, "L3": 3, "L4": 4}
    cards_by_id = {c["id"]: c for c in cards}
    ordered = [cards_by_id[card_id]] + sorted(
        (cards_by_id[i] for i in neighbor_ids if i in cards_by_id),
        key=lambda c: (layer_order.get(c["layer"], 9), c["id"]),
    )
    nodes = [
        {
            "id": c["id"],
            "title": c["title"],
            "type": c["type"],
            "layer": c["layer"],
            "namespace": _ns(c["id"]),
            "source": c["source"] or "",
            "origin": c.get("origin") or "ai",
            "tags": _tags(c.get("tags")),
            "use_count": c.get("use_count", 0),
            "search_count": c.get("search_count", 0),
        }
        for c in ordered
    ]
    return {
        "center": nodes[0] if nodes else None,
        "nodes": nodes,
        "hierarchy_edges": [{"source": a, "target": b} for a, b in hierarchy_pairs],
        "link_edges": [{"source": a, "target": b} for a, b in link_pairs],
    }


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------
# Static SPA hosting (production only)
# --------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_INDEX = _STATIC_DIR / "index.html"
_STATIC_ASSETS = _STATIC_DIR / "assets"

if _STATIC_INDEX.exists():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_ASSETS)), name="assets")

    @app.get("/")
    def spa_root():
        return FileResponse(_STATIC_INDEX)

    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str):
        if full_path.startswith(("api/", "assets/")):
            raise HTTPException(status_code=404)
        return FileResponse(_STATIC_INDEX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
