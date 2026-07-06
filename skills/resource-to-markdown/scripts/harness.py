"""harness.py — 质量校验 + 兜底决策。

校验项（输入 raw.md，输出 list[CheckResult]）：
  - exists：文件存在且非空
  - min_chars：字数 ≥ 预期（按页数/时长估算）
  - has_heading：至少 1 个 markdown 标题
  - garbage_ratio：连续 > 30 字非中英文数字字符占比 < 5%
  - structure：段落 + 标题层次合理

校验项（切分后单元）：
  - unit_min：每 chXX.md ≥ 500 字
  - unit_max：每 chXX.md ≤ 50000 字
  - coverage：Σ chXX.md 字数 / raw.md 字数 ≥ 0.6
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


GARBAGE_PATTERN = re.compile(
    r"[^一-鿿　-〿A-Za-z0-9\s\.,;:!?'\"()\[\]{}\-—–…·、，。；：！？「」『』《》（）【】\n\r#>*_\-+=/\\@$%^&|~`]{30,}"
)
HEADING_PATTERN = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
# 中文章节模式也认作"有结构"
CHAPTER_PATTERN = re.compile(
    r"^第[一二三四五六七八九十百零〇\d]+[部分章节篇回讲]|^Chapter\s+\d+",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    reason: str = ""


def check_raw_md(md_path: Path, expected_min_chars: int = 200) -> List[CheckResult]:
    """对原始 markdown 文件做质量校验。"""
    results: List[CheckResult] = []

    if not md_path.exists():
        results.append(CheckResult("exists", False, f"file not found: {md_path}"))
        return results
    text = md_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        results.append(CheckResult("exists", False, "empty file"))
        return results
    results.append(CheckResult("exists", True))

    chars = len(text)
    if chars < expected_min_chars:
        results.append(CheckResult(
            "min_chars", False,
            f"{chars} chars < expected {expected_min_chars}",
        ))
    else:
        results.append(CheckResult("min_chars", True))

    garbage_matches = GARBAGE_PATTERN.findall(text)
    garbage_chars = sum(len(m) for m in garbage_matches)
    ratio = garbage_chars / max(chars, 1)
    if ratio > 0.05:
        results.append(CheckResult(
            "garbage_ratio", False,
            f"{ratio:.1%} garbage (>5%), {len(garbage_matches)} segments",
        ))
    else:
        results.append(CheckResult("garbage_ratio", True))

    if not HEADING_PATTERN.search(text) and not CHAPTER_PATTERN.search(text):
        # 对纯文本提取（PDF/视频转写）放宽：只要内容足够长且无乱码，就视为可用
        # 章节切分可走 hard_split 兜底，后续 LLM 清洗会重新组织结构
        if chars >= expected_min_chars and ratio <= 0.05:
            results.append(CheckResult(
                "has_heading", True,
                "no heading but content substantial (will use hard_split)",
            ))
        else:
            results.append(CheckResult(
                "has_heading", False,
                "no markdown heading or chapter pattern, content also weak",
            ))
    else:
        results.append(CheckResult("has_heading", True))

    return results


def check_units(
    unit_paths: List[Path],
    raw_chars: int,
    min_unit_chars: int = 500,
    max_unit_chars: int = 50000,
    min_coverage: float = 0.6,
) -> List[CheckResult]:
    """对切分后的 chXX.md 做质量校验。"""
    results: List[CheckResult] = []

    if not unit_paths:
        results.append(CheckResult("units_exist", False, "no units produced"))
        return results
    results.append(CheckResult("units_exist", True))

    too_small = []
    too_large = []
    total = 0
    for p in unit_paths:
        n = len(p.read_text(encoding="utf-8", errors="replace"))
        total += n
        if n < min_unit_chars:
            too_small.append(f"{p.name}={n}")
        elif n > max_unit_chars:
            too_large.append(f"{p.name}={n}")

    if too_small:
        results.append(CheckResult(
            "unit_min", False,
            f"{len(too_small)} units < {min_unit_chars}: {';'.join(too_small[:5])}",
        ))
    else:
        results.append(CheckResult("unit_min", True))

    if too_large:
        results.append(CheckResult(
            "unit_max", False,
            f"{len(too_large)} units > {max_unit_chars}: {';'.join(too_large[:5])}",
        ))
    else:
        results.append(CheckResult("unit_max", True))

    coverage = total / max(raw_chars, 1)
    if coverage < min_coverage:
        results.append(CheckResult(
            "coverage", False,
            f"{coverage:.1%} < {min_coverage:.0%} (units={total}, raw={raw_chars})",
        ))
    else:
        results.append(CheckResult("coverage", True))

    return results


def summarize(results: List[CheckResult]) -> dict:
    failures = [r for r in results if not r.passed]
    return {
        "passed": not failures,
        "total": len(results),
        "passed_count": len(results) - len(failures),
        "failures": [{"check_id": r.check_id, "reason": r.reason} for r in failures],
    }
