#!/usr/bin/env python3.11
"""批量消化脚本：对一批 L1 单元自动跑 DIGEST。

每个 L1 单元独立写 plan.json + drafts，跑 stop-check 入库。
不 spawn 真子 agent（避免 Claude API 调用），而是从 L1 内容自动
提取摘要作为 L2 卡 content——用于规模验收，不是真实消化。

Usage:
  python3.11 scripts/batch_digest.py <chapter_glob> [--prefix he] [--layer L2]

Example:
  python3.11 scripts/batch_digest.py 'sources/07-LLM/01-深入理解Harness_Engineering/ch0[1-5].md'
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Loom = ROOT / "bin" / "loom"


def _run_sb(*args, check=True):
    """Run bin/loom, return (exit_code, stdout, stderr)."""
    r = subprocess.run(
        ["python3.11", str(ROOT / "bin" / "loom.py"), *args],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if check and r.returncode != 0:
        sys.stderr.write(f"[loom error] args={args}\n{r.stderr}\n")
    return r.returncode, r.stdout, r.stderr


def _summarize(text: str, max_chars: int = 600) -> str:
    """Cheap 'digest': strip markdown noise, take first non-empty paragraphs."""
    t = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    out = []
    cur = 0
    for l in lines:
        if cur + len(l) > max_chars:
            break
        out.append(l)
        cur += len(l)
    return "\n".join(out) if out else text[:max_chars]


def _hash_id(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:6]


def digest_one(l1_path: str, prefix: str, layer: str, chapter_idx: int) -> dict:
    """Digest a single L1 file. Returns summary dict."""
    task_id = f"batch_{prefix}_{chapter_idx:03d}_{_hash_id(l1_path)}"
    task_dir = Path(f"/tmp/loom_task/{task_id}")
    drafts_dir = task_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # plan.json
    plan = {
        "task_id": task_id,
        "task": f"消化 {l1_path}",
        "source": l1_path,
        "layer": layer,
        "skill": "DIGEST",
    }
    (task_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    text = Path(l1_path).read_text(encoding="utf-8")
    title_match = re.search(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(l1_path).stem

    # Topic card
    topic_id = f"{prefix}:topic_ch{chapter_idx:02d}"
    topic_content = f"# {title}\n\n" + _summarize(text, 500)
    topic_file = task_dir / "topic.md"
    topic_file.write_text(topic_content, encoding="utf-8")

    code, out, err = _run_sb(
        "write-draft", task_id, topic_id,
        "--type=主题", f"--title={title}",
        f"--source={l1_path}",
        f"--content-file={topic_file}",
    )
    if code != 0:
        return {"l1": l1_path, "status": "topic_failed", "err": err}

    # 1-2 additional L2 cards (concept / judgment)
    extra_cards = []
    # try to find "核心命题" or first non-empty paragraph
    body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if paragraphs:
        # concept card from first substantive paragraph
        concept_id = f"{prefix}:concept_ch{chapter_idx:02d}"
        concept_content = f"**核心要点**\n\n" + _summarize(paragraphs[0], 400)
        concept_file = task_dir / "concept.md"
        concept_file.write_text(concept_content, encoding="utf-8")
        code2, _, err2 = _run_sb(
            "write-draft", task_id, concept_id,
            "--type=概念", f"--title={title} 核心要点",
            f"--source={l1_path}", f"--links={topic_id}",
            f"--content-file={concept_file}",
        )
        if code2 == 0:
            extra_cards.append(concept_id)

    if len(paragraphs) >= 2:
        judge_id = f"{prefix}:judge_ch{chapter_idx:02d}"
        judge_content = f"**判断**\n\n" + _summarize(paragraphs[1], 400)
        judge_file = task_dir / "judge.md"
        judge_file.write_text(judge_content, encoding="utf-8")
        code3, _, err3 = _run_sb(
            "write-draft", task_id, judge_id,
            "--type=判断", f"--title={title} 关键判断",
            f"--source={l1_path}", f"--links={topic_id}",
            f"--content-file={judge_file}",
        )
        if code3 == 0:
            extra_cards.append(judge_id)

    # stop-check
    code, out, err = _run_sb("stop-check", task_id, "--mode=normal", check=False)
    if code == 0:
        return {"l1": l1_path, "status": "committed",
                "topic": topic_id, "extras": extra_cards}
    return {"l1": l1_path, "status": "rejected", "err": err, "out": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help="glob pattern for L1 files")
    ap.add_argument("--prefix", default="he")
    ap.add_argument("--layer", default="L2")
    args = ap.parse_args()

    files = sorted(glob.glob(args.pattern))
    if not files:
        sys.exit(f"no files match: {args.pattern}")

    print(f"批量消化 {len(files)} 个 L1 单元 (prefix={args.prefix}, layer={args.layer})")
    results = []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f}")
        r = digest_one(f, args.prefix, args.layer, i)
        print(f"   → {r['status']}")
        results.append(r)

    committed = sum(1 for r in results if r["status"] == "committed")
    rejected = sum(1 for r in results if r["status"] == "rejected")
    print(f"\n汇总：committed={committed}, rejected={rejected}, total={len(files)}")
    # write report
    report_path = Path(f"/tmp/loom_task/batch_report_{args.prefix}_{int(time.time())}.json")
    report_path.write_text(
        json.dumps({"pattern": args.pattern, "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"详细报告：{report_path}")


if __name__ == "__main__":
    main()
