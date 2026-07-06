#!/usr/bin/env python3
"""最终 checklist 自检（对应 docs/design/006）。

脚本只做可自动验证的检查；端到端质量项依赖本机真实数据，未跑过数据时会显示不通过。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

LOOM = ROOT / "bin" / "loom"
LOOM_ADMIN = ROOT / "bin" / "loom-admin"
DB = ROOT / "data" / "brain.db"

results: list[tuple[str, str, str, str]] = []


def check(idx: str, name: str, ok: bool, evidence: str = "") -> None:
    mark = "✓" if ok else "✗"
    results.append((idx, name, mark, evidence))
    print(f"[{mark}] {idx}. {name}")
    if evidence:
        print(f"    evidence: {evidence}")


def run_cmd(*args: str, admin: bool = False) -> tuple[int, str, str]:
    exe = LOOM_ADMIN if admin else LOOM
    r = subprocess.run([str(exe), *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def sqlite_scalar(sql: str, default: Any = None) -> Any:
    if not DB.exists():
        return default
    try:
        with sqlite3.connect(str(DB)) as conn:
            row = conn.execute(sql).fetchone()
            return row[0] if row else default
    except sqlite3.Error:
        return default


def sqlite_list(sql: str) -> list[Any]:
    if not DB.exists():
        return []
    try:
        with sqlite3.connect(str(DB)) as conn:
            return [r[0] for r in conn.execute(sql).fetchall()]
    except sqlite3.Error:
        return []


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def hook_commands(cfg: dict[str, Any], event: str) -> list[str]:
    commands: list[str] = []
    for group in cfg.get("hooks", {}).get(event, []):
        for hook in group.get("hooks", []):
            if hook.get("type") == "command":
                commands.append(str(hook.get("command", "")))
    return commands


def has_prompt_or_agent_hook(cfg: dict[str, Any]) -> bool:
    for groups in cfg.get("hooks", {}).values():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") in {"prompt", "agent"}:
                    return True
    return False


def loom_hook_cfg_ok(path: Path) -> tuple[bool, str]:
    cfg = load_json(path)
    evidence: list[str] = []
    ok = True
    for event in ("SubagentStop", "Stop"):
        commands = hook_commands(cfg, event)
        loom_commands = [c for c in commands if "loom-hook" in c]
        split_commands = [
            c for c in commands
            if "hook-guard" in c or "stop-check-pending" in c
        ]
        event_ok = len(loom_commands) == 1 and not split_commands
        ok = ok and event_ok
        evidence.append(f"{event}: loom-hook={len(loom_commands)}, split={len(split_commands)}")
    ok = ok and not has_prompt_or_agent_hook(cfg)
    evidence.append(f"prompt_or_agent={has_prompt_or_agent_hook(cfg)}")
    return ok, "; ".join(evidence)


# ========== 模块 1-12 ==========
schema = subprocess.run(
    ["sqlite3", str(DB), ".schema"],
    capture_output=True,
    text=True,
).stdout if DB.exists() else ""
tables = subprocess.run(
    ["sqlite3", str(DB), ".tables"],
    capture_output=True,
    text=True,
).stdout if DB.exists() else ""
check(
    "1",
    "存储层 schema 完整",
    all(t in schema for t in ["cards", "links", "cards_fts", "task_trace", "reject_log"])
    and "cards_vec" in tables,
    "schema/tables inspected",
)

basic_ok = True
for cmd in ["read-source", "write-draft", "read-cards", "read-l4-index", "search"]:
    rc, _, _ = run_cmd(cmd, "--help")
    basic_ok = basic_ok and rc == 0
check("2", "5 个基础命令可执行", basic_ok)

struct_ok = True
for cmd in ["browse", "children", "siblings", "neighbors"]:
    rc, _, _ = run_cmd(cmd, "--help")
    struct_ok = struct_ok and rc == 0
check("3", "4 个结构遍历可执行", struct_ok)

ordinary_hidden_ok = True
for cmd in ["commit-l4", "apply-card-edit", "update-card", "delete-card", "rebuild-l4-index", "stop-check"]:
    rc, _, _ = run_cmd(cmd, "--help")
    ordinary_hidden_ok = ordinary_hidden_ok and rc != 0
admin_ok = True
for cmd in [
    "commit-l4",
    "apply-card-edit",
    "update-card",
    "delete-card",
    "rebuild-l4-index",
    "stop-check",
    "stop-check-pending",
]:
    rc, _, _ = run_cmd(cmd, "--help", admin=True)
    admin_ok = admin_ok and rc == 0
check("4", "特权命令只通过 loom-admin 暴露", ordinary_hidden_ok and admin_ok)

prop_ok = True
for cmd in ["propose-l4", "propose-card-edit"]:
    rc, _, _ = run_cmd(cmd, "--help")
    prop_ok = prop_ok and rc == 0
check("5", "2 个提案命令存在", prop_ok)

checks_py = (ROOT / "src" / "loom" / "checks.py").read_text(encoding="utf-8")
single_expected = {
    "type_valid",
    "namespace_format",
    "layer_type_matrix",
    "min_length",
    "l3_links_lower",
    "l4_links_lower",
    "reflection_anchored",
    "l4_index_format",
    "source_real",
    "card_id_unique",
    "l2_no_cross_domain",
}
check(
    "6",
    "write-draft 11 条计算校验已实现",
    all(f'"{check_id}"' in checks_py for check_id in single_expected),
    f"expected={len(single_expected)}",
)

batch_expected = {"l2_has_topic", "l2_links_topic", "id_unique", "no_duplication"}
check(
    "7",
    "stop-check 4 条整批校验已实现",
    all(f'"{check_id}"' in checks_py for check_id in batch_expected),
    f"expected={len(batch_expected)}",
)

claude_ok, claude_ev = loom_hook_cfg_ok(ROOT / "config" / "claude-settings.json.example")
codex_ok, codex_ev = loom_hook_cfg_ok(ROOT / "config" / "codex-hooks.json.example")
check(
    "8",
    "Claude / Codex hook 示例配置完整",
    claude_ok and codex_ok,
    f"claude=({claude_ev}); codex=({codex_ev})",
)

wrapper_text = (ROOT / "bin" / "loom-hook").read_text(encoding="utf-8")
check(
    "9",
    "loom-hook 串行封装 guard + stop-check",
    "hook-guard" in wrapper_text
    and "stop-check-pending" in wrapper_text
    and '"decision"' in wrapper_text
    and '"block"' in wrapper_text,
)

core_text = (ROOT / "skills" / "_loom_core.md").read_text(encoding="utf-8")
check(
    "10",
    "语义层 block-back 协议写入 skill",
    all(k in core_text for k in ["type_match", "single_unit", "genuine_digest", "self_contained"])
    and "commit-ready --semantic-passed" in core_text,
)

skill_paths = [
    ROOT / "skills" / "_loom_core.md",
    ROOT / "skills" / "loom-digest" / "SKILL.md",
    ROOT / "skills" / "loom-think" / "SKILL.md",
    ROOT / "skills" / "loom-use" / "SKILL.md",
    ROOT / "skills" / "loom-pipeline" / "SKILL.md",
]
check("11", "4 个模式 skill + _loom_core 齐全", all(p.exists() for p in skill_paths))

agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
check(
    "12",
    "AGENTS.md 反映当前 hook/CLI 实现",
    "loom-hook" in agents
    and "Claude Code / Codex" in agents
    and "write-draft" in agents
    and "stop-check" in agents,
)


# ========== 端到端与量化指标 ==========
rc, out, _ = run_cmd("stats")
try:
    stats = json.loads(out) if rc == 0 and out.strip() else {}
except json.JSONDecodeError:
    stats = {}

total_cards = int(stats.get("total_cards", sqlite_scalar("SELECT COUNT(*) FROM cards", 0)) or 0)
l2_cards = int(sqlite_scalar("SELECT COUNT(*) FROM cards WHERE layer IN ('L2', 'L2_light')", 0) or 0)
l4_cards = int(sqlite_scalar("SELECT COUNT(*) FROM cards WHERE layer='L4'", 0) or 0)

check("S1", "阶段1 单材料跑通（至少有 L2 卡入库）", l2_cards > 0, f"l2_cards={l2_cards}")
check("S2", "阶段2 ≥20 张 L2 卡", l2_cards >= 20, f"l2_cards={l2_cards}")
check(
    "S3",
    "阶段3 ≥50 张卡 + 跨域 L4",
    total_cards >= 50 and l4_cards >= 1,
    f"total_cards={total_cards}, l4_cards={l4_cards}",
)

reject_count = int(sqlite_scalar("SELECT COUNT(*) FROM reject_log", 0) or 0)
task_count = int(sqlite_scalar("SELECT COUNT(*) FROM task_trace", 0) or 0)
done_task_count = int(sqlite_scalar("SELECT COUNT(*) FROM task_trace WHERE status='done'", 0) or 0)
retry_task_count = int(sqlite_scalar("SELECT COUNT(*) FROM task_trace WHERE retries > 0", 0) or 0)
reject_rate_ok = task_count == 0 or 0.10 <= reject_count / max(task_count + reject_count, 1) <= 0.60
retry_rate_ok = task_count == 0 or retry_task_count / max(task_count, 1) < 0.50

check("Q1", "拒绝率 10-60%", reject_rate_ok, f"rejects={reject_count}, tasks={task_count}")
check("Q2", "回炉率 <50%", retry_rate_ok, f"retry_tasks={retry_task_count}, tasks={task_count}")
check("Q3", "stop-check 有过 done task 记录", done_task_count > 0, f"done_tasks={done_task_count}")

use_count = int(sqlite_scalar("SELECT COUNT(*) FROM cards WHERE use_count > 0", 0) or 0)
search_count = int(sqlite_scalar("SELECT COUNT(*) FROM cards WHERE search_count > 0", 0) or 0)
orphan_count = int(sqlite_scalar(
    "SELECT COUNT(*) FROM cards "
    "WHERE id NOT IN (SELECT source_id FROM links) "
    "AND id NOT IN (SELECT target_id FROM links)",
    0,
) or 0)
orphan_rate = orphan_count / max(total_cards, 1)

check("Q4", "use_count >0 ≥10", use_count >= 10, f"cards_with_use={use_count}")
check("Q5", "search_count >0 ≥10", search_count >= 10, f"cards_with_search={search_count}")
check("Q6", "孤立卡率 <20%", total_cards > 0 and orphan_rate < 0.20, f"orphan_rate={orphan_rate:.1%}")

rc, out, _ = run_cmd("search", "反馈", "--mode=fts", "--top=10")
search_ok = rc == 0 and out.strip().startswith("{")
check("Q7", "跨材料检索可执行", search_ok)
check("Q8", "跨域 L4 涌现 ≥1", l4_cards >= 1, f"l4_cards={l4_cards}")

namespaces = sqlite_list("SELECT DISTINCT substr(id, 1, instr(id || ':', ':') - 1) FROM cards")
check("Q9", "跨领域分布", len(set(namespaces)) >= 3, f"namespaces={sorted(set(namespaces))}")

rc, out, _ = run_cmd("search", "风险", "--mode=fts", "--top=3")
check("R1", "可重复性（search 不报错）", rc == 0 and out.strip().startswith("{"))


total = len(results)
passed = sum(1 for _, _, mark, _ in results if mark == "✓")
print(f"\n{'=' * 60}")
print(f"总计 {passed}/{total} 项通过")
print(f"{'=' * 60}")
if passed == total:
    print("✓ 全部通过，实现达标")
else:
    print("✗ 有未通过项")
    for idx, name, mark, _ in results:
        if mark == "✗":
            print(f"  - {idx}. {name}")

sys.exit(0 if passed == total else 1)
