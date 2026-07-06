from __future__ import annotations

import importlib
import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def loom(tmp_path, monkeypatch):
    loom_home = tmp_path / "loom_home"
    monkeypatch.setenv("LOOM_HOME", str(loom_home))
    monkeypatch.setenv("LOOM_SESSION_ID", f"pytest-{uuid.uuid4().hex}")

    import loom.store as store
    import loom.checks as checks
    import loom.embed as embed
    import loom.cli as cli

    store = importlib.reload(store)
    checks = importlib.reload(checks)
    embed = importlib.reload(embed)
    cli = importlib.reload(cli)

    fake_vec = [0.0] * store.EMBED_DIM
    monkeypatch.setattr(cli.embed, "embed", lambda _text: fake_vec)
    monkeypatch.setattr(cli.embed, "embed_batch", lambda texts: [fake_vec for _ in texts])

    store.init_db()
    task_ids: list[str] = []

    def run(args, *, admin=False, expected=0):
        rc = cli.main(args, entrypoint="loom-admin" if admin else "loom")
        assert rc == expected
        return rc

    def task_id(prefix: str) -> str:
        tid = f"pytest_{prefix}_{uuid.uuid4().hex[:8]}"
        task_ids.append(tid)
        return tid

    def write_plan(tid: str, **plan):
        task_dir = Path("/tmp/loom_task") / tid
        task_dir.mkdir(parents=True, exist_ok=True)
        payload = {"task_id": tid, **plan}
        (task_dir / "plan.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    yield {
        "cli": cli,
        "store": store,
        "home": loom_home,
        "run": run,
        "task_id": task_id,
        "write_plan": write_plan,
    }

    for tid in task_ids:
        shutil.rmtree(Path("/tmp/loom_task") / tid, ignore_errors=True)


@pytest.fixture()
def loom_helpers(loom):
    def source_file(rel: str, text: str) -> Path:
        path = loom["home"] / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def import_source(
        source_id: str,
        rel_path: str | None = None,
        title: str = "测试材料",
        text: str | None = None,
    ) -> str:
        if rel_path is None:
            rel_path = f"sources/07-LLM/{source_id.replace(':', '_')}.md"
        path = source_file(
            rel_path,
            text or "# 测试材料\n\n这是一段用于 harness 测试的原文材料。它有足够内容支撑主题卡、判断卡和生成卡。",
        )
        loom["run"](["import-source", source_id, "--title", title, "--path", str(path)])
        return source_id

    def commit_semantic_ready(task_id: str):
        loom["run"](["mark-ready", task_id])
        loom["run"](["stop-check", task_id], admin=True, expected=2)
        task_dir = Path("/tmp/loom_task") / task_id
        assert (task_dir / ".computed_passed.json").exists()
        assert (task_dir / ".semantic_sample.json").exists()
        loom["run"](["commit-ready", task_id, "--semantic-passed"])

    def write_committed_topic(source_id: str, topic_id: str):
        scout = loom["task_id"]("scout_topic")
        loom["write_plan"](
            scout,
            task="Scout topic",
            source=source_id,
            layer="L2",
            phase="scout",
            skill="DIGEST",
        )
        loom["run"]([
            "write-draft",
            scout,
            topic_id,
            "--type=主题",
            "--title=章节主题",
            f"--source={source_id}",
            "--content=这张主题卡提供该测试章节的整体论点、结构骨架和 Deep 阶段继续精读所需的全局入口。",
        ])
        commit_semantic_ready(scout)
        return topic_id

    def write_committed_l2(
        domain: str = "llm",
        book: str = "contract",
        unit: str = "01",
        *,
        card_type: str = "判断",
        suffix: str = "a",
    ) -> tuple[str, str, str]:
        source_id = f"{domain}:{book}:src:{unit}"
        topic_id = f"{domain}:{book}:{unit}"
        card_id = f"{domain}:{book}:{unit}{suffix}"
        import_source(source_id, f"sources/07-LLM/{book}/ch{unit}.md")
        write_committed_topic(source_id, topic_id)

        deep = loom["task_id"](f"deep_{domain}_{book}_{unit}_{suffix}")
        loom["write_plan"](
            deep,
            task=f"Deep {book}",
            source=source_id,
            layer="L2",
            phase="deep",
            topic_card=topic_id,
            skill="DIGEST",
        )
        loom["run"]([
            "write-draft",
            deep,
            card_id,
            f"--type={card_type}",
            f"--title={book} {card_type}",
            f"--source={source_id}",
            f"--links={topic_id}",
            "--content=这张 L2 卡基于材料形成可复用认知单元，并说明为什么这个单元可以支撑后续生成层思考。",
        ])
        commit_semantic_ready(deep)
        return source_id, topic_id, card_id

    def rejected_payload(task_id: str) -> dict:
        path = Path("/tmp/loom_task") / task_id / ".rejected.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def reject_check_ids(task_id: str | None = None) -> list[str]:
        with loom["store"].connect() as conn:
            if task_id:
                rows = conn.execute(
                    "SELECT check_id FROM reject_log WHERE task_id=? ORDER BY id",
                    (task_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT check_id FROM reject_log ORDER BY id").fetchall()
        return [row["check_id"] for row in rows]

    return SimpleNamespace(
        source_file=source_file,
        import_source=import_source,
        commit_semantic_ready=commit_semantic_ready,
        write_committed_topic=write_committed_topic,
        write_committed_l2=write_committed_l2,
        rejected_payload=rejected_payload,
        reject_check_ids=reject_check_ids,
    )
