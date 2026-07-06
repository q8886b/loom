from __future__ import annotations


def test_write_draft_rejects_each_per_card_check(loom, loom_helpers):
    llm_source, llm_topic, llm_l2 = loom_helpers.write_committed_l2("llm", "percard")
    _med_source, _med_topic, med_l2 = loom_helpers.write_committed_l2("med", "percard")

    def run_case(label: str, check_id: str, plan: dict, args: list[str], expected: int = 2):
        task = loom["task_id"](label)
        loom["write_plan"](task, **plan)
        expanded = [task if item == "$TASK" else item for item in args]
        loom["run"](expanded, expected=expected)
        assert check_id in loom_helpers.reject_check_ids(task)

    run_case(
        "bad_type",
        "type_valid",
        {"task": "Bad type", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:9a", "--layer=L3", "--type=比较",
            "--title=非法类型", f"--links={llm_l2}",
            "--content=这张卡故意使用不存在的比较类型，应该被 type 合法集校验拒绝。",
        ],
    )
    run_case(
        "bad_namespace",
        "namespace_format",
        {"task": "Bad namespace", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:percard:bad", "--layer=L3", "--type=判断",
            "--title=错误 namespace", f"--links={llm_l2}",
            "--content=这张 L3 卡故意使用 L2 形态的 namespace，应该被 namespace 格式校验拒绝。",
        ],
    )
    run_case(
        "bad_layer_type",
        "layer_type_matrix",
        {"task": "Bad L4 type", "layer": "L4", "skill": "THINK"},
        [
            "write-draft", "$TASK", "gen:9a", "--layer=L4", "--type=概念",
            "--title=L4 概念", f"--links={llm_l2},{med_l2}",
            "--content=[探索期] L4 不允许概念型卡片，因为元层必须表达模式、判断或反思。",
        ],
    )
    run_case(
        "too_short",
        "min_length",
        {"task": "Too short", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:9b", "--layer=L3", "--type=判断",
            "--title=太短", f"--links={llm_l2}", "--content=太短",
        ],
    )
    run_case(
        "missing_link",
        "links_exist",
        {"task": "Missing link", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:9c", "--layer=L3", "--type=判断",
            "--title=悬空链接", "--links=llm:missing:01a",
            "--content=这张卡故意链接不存在的目标，应该被显性 link 不允许悬空的校验拒绝。",
        ],
    )
    run_case(
        "l3_without_l2",
        "l3_links_lower",
        {"task": "L3 without L2", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:9d", "--layer=L3", "--type=判断",
            "--title=只链接 L1", f"--links={llm_source}",
            "--content=这张 L3 卡只链接原文 source，没有链接任何 L2 消化卡，应该被拒绝。",
        ],
    )
    run_case(
        "l4_single_domain",
        "l4_links_lower",
        {"task": "L4 single domain", "layer": "L4", "skill": "THINK"},
        [
            "write-draft", "$TASK", "gen:9b", "--layer=L4", "--type=模式",
            "--title=单领域模式", f"--links={llm_l2}",
            "--content=[探索期] 这张 L4 候选只锚定一个领域，因此应该留在 L3 而不是上升为元层模式。",
        ],
    )
    run_case(
        "reflection_without_anchor",
        "reflection_anchored",
        {"task": "Reflection without anchor", "layer": "L3", "skill": "THINK"},
        [
            "write-draft", "$TASK", "llm:9e", "--layer=L3", "--type=反思",
            "--title=未锚定判断模式", f"--links={llm_topic}",
            "--content=这张反思卡只链接主题卡，没有锚定判断或模式卡，应该被反思锚定校验拒绝。",
        ],
    )
    run_case(
        "bad_l4_index",
        "l4_index_format",
        {"task": "Bad L4 index", "layer": "L4", "skill": "THINK"},
        [
            "write-draft", "$TASK", "gen:9c", "--layer=L4", "--type=模式",
            "--title=缺成熟度", f"--links={llm_l2},{med_l2}",
            "--content=这张 L4 卡没有在第一段开头标注探索期或熟练期，应该被索引格式校验拒绝。",
        ],
    )
    run_case(
        "bad_source",
        "source_real",
        {
            "task": "Bad L2 source",
            "source": llm_source,
            "layer": "L2",
            "phase": "deep",
            "topic_card": llm_topic,
            "skill": "DIGEST",
        },
        [
            "write-draft", "$TASK", "llm:percard:01z", "--type=判断",
            "--title=错误 source", "--source=llm:percard:src:missing",
            f"--links={llm_topic}",
            "--content=这张 L2 卡故意把 source 指向不存在的 L1 source card，应该被 source 真实校验拒绝。",
        ],
    )
    run_case(
        "duplicate_id",
        "card_id_unique",
        {
            "task": "Duplicate id",
            "source": llm_source,
            "layer": "L2",
            "phase": "scout",
            "skill": "DIGEST",
        },
        [
            "write-draft", "$TASK", llm_topic, "--type=主题",
            "--title=重复 ID", f"--source={llm_source}",
            "--content=这张主题卡故意复用已经入库的主题卡 ID，应该被 card_id 唯一性校验拒绝。",
        ],
    )
    run_case(
        "l2_cross_domain",
        "l2_no_cross_domain",
        {
            "task": "L2 cross domain",
            "source": llm_source,
            "layer": "L2",
            "phase": "deep",
            "topic_card": llm_topic,
            "skill": "DIGEST",
        },
        [
            "write-draft", "$TASK", "llm:percard:01y", "--type=判断",
            "--title=跨域 L2 link", f"--source={llm_source}",
            f"--links={llm_topic},{med_l2}",
            "--content=这张 L2 卡故意链接另一个领域的卡，应该被 DIGEST 只允许本材料内 link 的校验拒绝。",
        ],
    )


def test_l2_light_task_writes_card_layer_as_l2(loom, loom_helpers):
    source_id = "llm:l2light:src:01"
    topic_id = "llm:l2light:01"
    loom_helpers.import_source(source_id, "sources/07-LLM/l2light/ch01.md")
    task = loom["task_id"]("l2_light")
    loom["write_plan"](
        task,
        task="L2 light scout",
        source=source_id,
        layer="L2_light",
        phase="scout",
        skill="DIGEST",
    )
    loom["run"]([
        "write-draft", task, topic_id, "--type=主题", "--title=L2 light 主题",
        f"--source={source_id}",
        "--content=轻量消化任务仍然写入 L2 card layer，只是任务目标层表达处理密度较轻。",
    ])
    loom_helpers.commit_semantic_ready(task)
    assert loom["store"].get_card(topic_id)["layer"] == "L2"
