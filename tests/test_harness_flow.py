from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


def _load_loom(tmp_path, monkeypatch):
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
    return cli, store, loom_home


@pytest.fixture()
def loom(tmp_path, monkeypatch):
    cli, store, loom_home = _load_loom(tmp_path, monkeypatch)
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


def _source_file(home: Path, rel: str, text: str) -> Path:
    path = home / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_source(loom, source_id: str, rel_path: str, title: str):
    path = _source_file(
        loom["home"],
        rel_path,
        f"# {title}\n\n这是一段用于 harness 测试的原文材料。它有足够内容支撑主题卡、判断卡和后续生成卡。",
    )
    loom["run"](["import-source", source_id, "--title", title, "--path", str(path)])


def _commit_semantic_ready(loom, task_id: str):
    loom["run"](["mark-ready", task_id])
    loom["run"](["stop-check", task_id], admin=True, expected=2)
    assert (Path("/tmp/loom_task") / task_id / ".semantic_sample.json").exists()
    loom["run"](["commit-ready", task_id, "--semantic-passed"])


def _write_l2_pair(loom, domain: str, book: str, unit: str = "01") -> tuple[str, str, str]:
    source_id = f"{domain}:{book}:src:{unit}"
    topic_id = f"{domain}:{book}:{unit}"
    card_id = f"{domain}:{book}:{unit}a"
    rel = f"sources/07-LLM/{book}/ch{unit}.md" if domain == "llm" else f"sources/02-医学/{book}/ch{unit}.md"
    _import_source(loom, source_id, rel, f"{book} {unit}")

    scout = loom["task_id"](f"scout_{domain}_{book}")
    loom["write_plan"](
        scout,
        task=f"Scout {book}",
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
        f"--title={book} 主题",
        f"--source={source_id}",
        "--content=本章主题卡概括材料的整体论点、结构骨架和阅读入口，供 Deep 阶段带着全局视野继续精读。",
    ])
    _commit_semantic_ready(loom, scout)

    deep = loom["task_id"](f"deep_{domain}_{book}")
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
        "--type=判断",
        f"--title={book} 判断",
        f"--source={source_id}",
        f"--links={topic_id}",
        "--content=这张判断卡基于材料形成可复用结论，并说明为什么相信这个结论以及它在行动中的意义。",
    ])
    _commit_semantic_ready(loom, deep)
    return source_id, topic_id, card_id


def test_replayable_harness_from_empty_store(loom):
    _llm_source, _llm_topic, llm_l2 = _write_l2_pair(loom, "llm", "harness")
    _med_source, _med_topic, med_l2 = _write_l2_pair(loom, "med", "clinic")

    think = loom["task_id"]("think_llm")
    loom["write_plan"](
        think,
        task="Build L3 from committed L2 cards",
        layer="L3",
        skill="THINK",
    )
    loom["run"]([
        "write-draft",
        think,
        "llm:1",
        "--layer=L3",
        "--type=判断",
        "--title=Harness 生成判断",
        f"--links={llm_l2}",
        "--content=这张 L3 卡从已消化的 L2 判断出发，形成面向多材料思考的生成性结论，而不是脱离材料凭空发挥。",
    ])
    _commit_semantic_ready(loom, think)

    propose_task = loom["task_id"]("l4")
    loom["run"]([
        "propose-l4",
        propose_task,
        "gen:1",
        "--title=跨域锚定模式",
        "--type=模式",
        f"--related=llm:1,{med_l2}",
        "--content=[探索期] 当一个判断能同时锚定软件智能与医学实践两个领域时，它才可能从领域经验上升为元层模式。这个模式仍需持续补充反例和边界。",
    ])
    proposals = sorted((Path("/tmp/loom_task") / propose_task / "staging").glob("*.json"))
    assert len(proposals) == 1
    loom["run"]([
        "proposal-decision",
        str(proposals[0]),
        "--decision=approved",
        "--reason=pytest approval",
    ], admin=True)
    loom["run"](["commit-l4", str(proposals[0])], admin=True)

    assert loom["store"].get_card("gen:1")["layer"] == "L4"
    assert set(loom["store"].get_links("gen:1")) >= {"llm:1", med_l2}

    med_think = loom["task_id"]("think_med")
    loom["write_plan"](
        med_think,
        task="Build another L3 card used as an L4 boundary",
        layer="L3",
        skill="THINK",
    )
    loom["run"]([
        "write-draft",
        med_think,
        "med:1",
        "--layer=L3",
        "--type=判断",
        "--title=医学边界判断",
        f"--links={med_l2}",
        "--content=这张医学 L3 判断为元层模式补充边界材料，说明同一模式在临床实践中需要更严格的适用条件。",
    ])
    _commit_semantic_ready(loom, med_think)

    edit_task = loom["task_id"]("edit_l4")
    loom["run"]([
        "propose-card-edit",
        edit_task,
        "gen:1",
        "--type=补充",
        "--related=med:1",
        "--content=[探索期] 当一个判断能同时锚定软件智能与医学实践两个领域时，它才可能从领域经验上升为元层模式。新增医学边界判断后，这个模式的适用范围更清楚：跨域迁移必须保留领域约束，而不是只保留抽象相似性。",
    ])
    edit_proposals = sorted((Path("/tmp/loom_task") / edit_task / "staging").glob("*.json"))
    assert len(edit_proposals) == 1
    payload = json.loads(edit_proposals[0].read_text(encoding="utf-8"))
    assert payload["related_cards"] == ["med:1"]
    loom["run"]([
        "proposal-decision",
        str(edit_proposals[0]),
        "--decision=approved",
    ], admin=True)
    loom["run"](["apply-card-edit", str(edit_proposals[0])], admin=True)

    assert "med:1" in set(loom["store"].get_links("gen:1"))
    assert "新增医学边界判断" in loom["store"].get_card("gen:1")["content"]

    loom["run"](["search", "判断", "--mode=fts", "--top=5"])
    original_embed = loom["cli"].embed.embed
    loom["cli"].embed.embed = lambda _text: (_ for _ in ()).throw(RuntimeError("missing key"))
    try:
        loom["run"](["search", "判断", "--top=5"])
    finally:
        loom["cli"].embed.embed = original_embed


def test_loom_wrapper_ignores_unrelated_python_on_path(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3.11"
    fake_python.write_text("#!/usr/bin/env bash\necho wrong-python >&2\nexit 42\n", encoding="utf-8")
    fake_python.chmod(0o755)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["LOOM_HOME"] = str(tmp_path / "loom_home")

    result = subprocess.run(
        [str(repo_root / "bin" / "loom"), "--help"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "wrong-python" not in result.stderr



def test_invalid_l3_without_l2_link_is_rejected(loom):
    task = loom["task_id"]("bad_l3")
    loom["write_plan"](task, task="Bad L3", layer="L3", skill="THINK")
    loom["run"]([
        "write-draft",
        task,
        "llm:9a",
        "--layer=L3",
        "--type=判断",
        "--title=无锚点生成",
        "--content=这张卡故意不链接任何 L2 卡，应该被计算层拒绝，防止生成层脱离材料依据。",
    ], expected=2)


def test_deep_requires_committed_topic_card(loom):
    source_id = "llm:missingtopic:src:01"
    _import_source(loom, source_id, "sources/07-LLM/missingtopic/ch01.md", "missing topic")
    task = loom["task_id"]("deep_missing_topic")
    loom["write_plan"](
        task,
        task="Deep without committed topic",
        source=source_id,
        layer="L2",
        phase="deep",
        topic_card="llm:missingtopic:01",
        skill="DIGEST",
    )
    loom["run"]([
        "write-draft",
        task,
        "llm:missingtopic:01a",
        "--type=判断",
        f"--source={source_id}",
        "--links=llm:missingtopic:01",
        "--content=Deep 阶段必须先有 Scout 已经入库的主题卡，否则应该在 write-draft 前置拦截处失败。",
    ], expected=1)


def test_origin_and_human_maintained_tags(loom):
    source_id, topic_id, _card_id = _write_l2_pair(loom, "llm", "originbook")

    task = loom["task_id"]("human_origin")
    loom["write_plan"](
        task,
        task="Human-origin card",
        source=source_id,
        layer="L2",
        phase="deep",
        topic_card=topic_id,
        skill="DIGEST",
    )
    human_id = "llm:originbook:01b"
    loom["run"]([
        "write-draft",
        task,
        human_id,
        "--type=判断",
        "--origin=human",
        "--title=人工判断",
        f"--source={source_id}",
        f"--links={topic_id}",
        "--content=这张卡表达用户明确提出的人工判断，AI 只负责整理成 Loom 卡片格式并保持可追溯链接。",
    ])
    _commit_semantic_ready(loom, task)

    card = loom["store"].get_card(human_id)
    assert card["origin"] == "human"
    assert card["tags"] == "[]"

    loom["run"]([
        "tag-card",
        human_id,
        "--add=[\"安全边际\",\"项目/loom\"]",
    ], admin=True)
    tagged = loom["store"].get_card(human_id)
    assert loom["store"].parse_tags_json(tagged["tags"]) == ["安全边际", "项目/loom"]

    loom["run"]([
        "tag-card",
        human_id,
        "--remove=[\"不存在\",\"项目/loom\"]",
    ], admin=True)
    retagged = loom["store"].get_card(human_id)
    assert loom["store"].parse_tags_json(retagged["tags"]) == ["安全边际"]
    assert loom["store"].list_tags() == [{"tag": "安全边际", "count": 1}]

    loom["run"](["search", "人工判断", "--mode=fts", "--tag=安全边际", "--top=5"])
