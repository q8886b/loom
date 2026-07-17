from __future__ import annotations

import json

import pytest


def _insert_l3(store, card_id: str) -> None:
    store.insert_card(
        card_id=card_id,
        title=card_id,
        type_="判断",
        content="这是一张用于验证卢曼树格式解析、父子关系和兄弟关系的测试卡片。",
        layer="L3",
    )


def test_luhmann_id_grammar_requires_a_complete_match(loom):
    store = loom["store"]
    valid = ["fin:3", "fin:3a", "fin:3a1", "fin:3ab", "fin:3ab12c"]
    invalid = ["fin:c01", "fin:3c_v2", "fin:3-a", "fin:3A", "fin:3a_2"]

    assert all(store.card_id_matches_layer(card_id, "L3") for card_id in valid)
    assert not any(store.card_id_matches_layer(card_id, "L3") for card_id in invalid)
    assert store._luhmann_segments("3c_v2") == []
    assert store._parent_id("fin:3c_v2") is None

    with pytest.raises(ValueError):
        _insert_l3(store, "fin:3c_v2")

    assert store.card_id_matches_layer("fin:grimes:src:11_2", "L1")


def test_audit_checks_l1_format_without_treating_l1_as_a_tree(loom):
    store = loom["store"]
    ts = store.now()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO cards
               (id,title,type,content,source,layer,origin,tags,
                use_count,search_count,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,0,0,?,?)""",
            (
                "fin:grimes:src:11.v2",
                "非法 L1 ID",
                "source",
                "这张原文卡用于验证全层格式审计，同时 L1 不参与卢曼父子关系。",
                "sources/01-金融/grimes/11_2.md",
                "L1",
                "ai",
                "[]",
                ts,
                ts,
            ),
        )

    result = store.audit_luhmann_tree()
    assert result["ok"] is False
    assert {item["id"] for item in result["invalid_ids"]} == {
        "fin:grimes:src:11.v2"
    }
    assert result["missing_parents"] == []


def test_children_and_siblings_follow_complete_segments(loom):
    store = loom["store"]
    for card_id in ["fin:3", "fin:3a", "fin:3ab", "fin:3a1", "fin:30", "fin:30a"]:
        _insert_l3(store, card_id)

    assert store.get_children("fin:3") == ["fin:3a", "fin:3ab"]
    assert store.get_children("fin:3a") == ["fin:3a1"]
    assert store.get_siblings("fin:3a") == ["fin:3ab"]
    assert store.get_siblings("fin:3") == ["fin:30"]


def test_store_boundary_requires_parent_and_accepts_atomic_parent_batch(loom):
    store = loom["store"]
    with pytest.raises(ValueError, match="requires missing parent 'fin:9'"):
        _insert_l3(store, "fin:9a")

    cards = [
        {
            "id": card_id,
            "title": card_id,
            "type": "判断",
            "content": "这是一张用于验证同一原子批次可以同时写入父卡和子卡的测试卡片。",
            "layer": "L3",
        }
        for card_id in ["fin:9", "fin:9a"]
    ]
    assert store.insert_cards_batch(cards, [None, None]) == {
        "status": "committed",
        "committed": ["fin:9", "fin:9a"],
    }


def test_delete_rejects_a_card_with_children(loom):
    store = loom["store"]
    _insert_l3(store, "fin:3")
    _insert_l3(store, "fin:3a")

    with pytest.raises(ValueError, match="has children"):
        store.delete_card("fin:3")

    assert store.get_card("fin:3") is not None
    assert store.get_card("fin:3a") is not None


def test_browse_tree_uses_structural_ancestry_not_text_prefix(loom, capsys):
    store = loom["store"]
    for card_id, type_ in [
        ("fin:book:1", "主题"),
        ("fin:book:1a", "概念"),
        ("fin:book:10", "主题"),
        ("fin:book:10a", "概念"),
    ]:
        store.insert_card(
            card_id=card_id,
            title=card_id,
            type_=type_,
            content="这张测试卡用于验证主题树按照完整卢曼段识别后代，而不是比较字符串前缀。",
            layer="L2",
        )

    loom["run"](["browse-tree", "fin:book"])
    payload = json.loads(capsys.readouterr().out)
    themes = {item["theme"]["id"]: item for item in payload["themes"]}
    assert [card["id"] for card in themes["fin:book:1"]["children"]] == [
        "fin:book:1a"
    ]
    assert [card["id"] for card in themes["fin:book:10"]["children"]] == [
        "fin:book:10a"
    ]


def test_remaining_as_roots_requires_an_exact_source_fingerprint(loom, tmp_path):
    from scripts import migrate_luhmann_tree as migration

    store = loom["store"]
    _insert_l3(store, "fin:1")
    _insert_l3(store, "fin:2")
    plan_path = tmp_path / "plan.json"
    plan = {
        "version": 1,
        "scope": {"layer": "L3", "namespace": "fin"},
        "remaining_as_roots": True,
        "outputs": [
            {
                "target_id": "fin:1",
                "source_ids": ["fin:1"],
                "canonical_source_id": "fin:1",
                "rationale": "保留第一张根卡。",
            }
        ],
    }

    invalid = migration.validate_plan(plan, plan_path, store.DB_PATH)
    assert invalid["ok"] is False
    assert any("remaining_as_roots requires" in error for error in invalid["errors"])

    source_ids = {"fin:1", "fin:2"}
    pinned_plan = {
        **plan,
        "outputs": [plan["outputs"][0]],
        "expected_source_count": 2,
        "expected_source_ids_sha256": migration.source_ids_sha256(source_ids),
    }
    valid = migration.validate_plan(pinned_plan, plan_path, store.DB_PATH)
    assert valid["ok"] is True


def test_migration_fails_when_an_expected_vector_is_not_preserved(
    loom, tmp_path, monkeypatch
):
    from scripts import migrate_luhmann_tree as migration

    store = loom["store"]
    store.insert_card(
        card_id="fin:1",
        title="源卡",
        type_="判断",
        content="这张源卡带有向量，用于验证迁移不能在向量丢失时仍然报告成功。",
        layer="L3",
        embedding=[0.0] * store.EMBED_DIM,
    )
    plan = {
        "outputs": [
            {
                "target_id": "fin:2",
                "source_ids": ["fin:1"],
                "canonical_source_id": "fin:1",
                "rationale": "把源卡迁移到新的根 ID。",
            }
        ]
    }
    monkeypatch.setattr(migration, "merged_embedding", lambda *_args: None)

    result = migration.apply_plan(
        plan,
        tmp_path / "plan.json",
        store.DB_PATH,
        tmp_path / "migrated.db",
    )
    assert result["checks"]["vectors_expected"] == 1
    assert result["checks"]["vectors_preserved"] == 0
    assert result["checks"]["ok"] is False


def test_tree_audit_reports_invalid_ids_and_missing_parents(loom):
    store = loom["store"]
    _insert_l3(store, "fin:3")
    _insert_l3(store, "fin:3a")

    ts = store.now()
    with store.connect() as conn:
        conn.executemany(
            """INSERT INTO cards
               (id, title, type, content, source, layer, origin, tags,
                use_count, search_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,0,0,?,?)""",
            [
                (
                    card_id,
                    title,
                    "判断",
                    content,
                    None,
                    "L3",
                    "ai",
                    "[]",
                    ts,
                    ts,
                )
                for card_id, title, content in [
                    (
                        "fin:3c_v2",
                        "非法历史卡",
                        "这张卡模拟绕过正常写入边界后遗留在存量数据库中的非法 ID。",
                    ),
                    (
                        "fin:9a",
                        "缺失父级历史卡",
                        "这张卡模拟绕过正常写入边界后遗留在存量数据库中的悬空子节点。",
                    ),
                ]
            ],
        )

    result = store.audit_luhmann_tree()
    assert result["ok"] is False
    assert result["summary"]["invalid_ids"] == 1
    assert result["summary"]["cards_with_missing_parent"] == 1
    assert result["invalid_ids"] == [{"id": "fin:3c_v2", "layer": "L3"}]
    assert result["missing_parents"] == [
        {"id": "fin:9a", "layer": "L3", "parent_id": "fin:9"}
    ]


def test_write_draft_requires_parent_but_accepts_parent_in_same_task(loom, loom_helpers):
    _source, _topic, l2_card = loom_helpers.write_committed_l2("llm", "tree")

    missing_task = loom["task_id"]("missing_parent")
    loom["write_plan"](
        missing_task,
        task="Missing Luhmann parent",
        layer="L3",
        skill="THINK",
    )
    loom["run"]([
        "write-draft",
        missing_task,
        "llm:90a",
        "--layer=L3",
        "--type=判断",
        "--title=缺失父级",
        f"--links={l2_card}",
        "--content=这张卡的格式合法，但父级并不存在，因此必须由卢曼父级完整性门禁拒绝。",
    ], expected=2)
    assert "luhmann_parent_exists" in loom_helpers.reject_check_ids(missing_task)

    same_task = loom["task_id"]("same_task_parent")
    loom["write_plan"](
        same_task,
        task="Parent and child in one task",
        layer="L3",
        skill="THINK",
    )
    for card_id, title in [("llm:90", "同批父卡"), ("llm:90a", "同批子卡")]:
        loom["run"]([
            "write-draft",
            same_task,
            card_id,
            "--layer=L3",
            "--type=判断",
            f"--title={title}",
            f"--links={l2_card}",
            "--content=这张卡用于验证父卡已在同一任务草稿中时，格式合法的子节点可以继续写入。",
        ])
