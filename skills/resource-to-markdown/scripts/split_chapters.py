"""split_chapters.py — markdown 按章节切分。

策略：
  1. 检测 H1 边界，按 H1 切
  2. 单元 > max_chars 时按 H2 再切
  3. 识别中文章节模式（第X章/第X部分/Chapter X）作为 fallback 边界
  4. 单元 < min_chars 时与下一单元合并
  5. 无任何结构信号时按字数硬切（句子边界优先）

不依赖 LLM——切分基于 markdown 结构 + 中文章节模式，后续 LLM 清洗/重写
在 INGEST 子流程里做（那是另一个 skill 的事）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# 中文章节模式：第X章/第X部分/第X节/Chapter X
# 注意：放弃 "数字+空格+大写词" 模式——会误中英文 PDF 的页眉（页码+书名）。
# 英文 PDF 的精确章节识别留给后续 LLM 清洗阶段（hard_split 兜底保证单元大小合理）。
CHAPTER_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+[部分章节篇回讲]", re.MULTILINE),
    re.compile(r"^Chapter\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^[一二三四五六七八九十]+[、.]\s*\S", re.MULTILINE),
]


def split_by_h1(text: str) -> List[Tuple[str, str]]:
    """按 H1 切，返回 [(title, body), ...]。H1 之前的引子归到 'preface'。"""
    matches = list(H1_RE.finditer(text))
    if not matches:
        return []

    units: List[Tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if len(preface) > 200:
            units.append(("preface", preface))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        body = f"# {title}\n\n{body}"
        units.append((title, body))

    return units


def split_by_h2(text: str) -> List[Tuple[str, str]]:
    """按 H2 切（当 H1 单元太长时用）。"""
    matches = list(H2_RE.finditer(text))
    if not matches:
        return []

    units: List[Tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if len(preface) > 200:
            units.append(("preface", preface))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        body = f"## {title}\n\n{body}"
        units.append((title, body))

    return units


def split_by_chinese_chapter(text: str) -> List[Tuple[str, str]]:
    """识别中文章节模式（第X章/第X部分/Chapter X）作为切分边界。

    用于 EPUB/PDF 转换后没有 # 标题但内容有清晰章节结构的情况。
    """
    # 找到所有章节标记的行
    chapter_lines: List[Tuple[int, str]] = []
    for pattern in CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            # 取整行作为标题
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end].strip()
            chapter_lines.append((line_start, line))

    if len(chapter_lines) < 2:
        return []

    # 去重 + 按位置排序
    seen = set()
    unique = []
    for pos, line in chapter_lines:
        if line not in seen and len(line) < 100:  # 跳过异常长行
            seen.add(line)
            unique.append((pos, line))
    unique.sort()

    if len(unique) < 2:
        return []

    units: List[Tuple[str, str]] = []
    if unique[0][0] > 0:
        preface = text[: unique[0][0]].strip()
        if len(preface) > 200:
            units.append(("preface", preface))

    for i, (pos, title) in enumerate(unique):
        body_start = pos
        body_end = unique[i + 1][0] if i + 1 < len(unique) else len(text)
        body = text[body_start:body_end].strip()
        # 转成 H1 markdown 标题
        body = f"# {title}\n\n{body}"
        units.append((title, body))

    return units


def hard_split(text: str, max_chars: int) -> List[Tuple[str, str]]:
    """无标题时按字数硬切（优先在段落边界切）。

    当单个段落 > max_chars 时，按句子边界再切；句子也超长时按硬字数切。
    """
    if len(text) <= max_chars:
        return [("part01", text)]

    units: List[Tuple[str, str]] = []
    paragraphs = text.split("\n\n")
    current = ""
    idx = 1

    def flush():
        nonlocal current, idx
        if current.strip():
            units.append((f"part{idx:02d}", current.strip()))
            idx += 1
            current = ""

    for p in paragraphs:
        # 段落本身太长 → 按句号切
        if len(p) > max_chars:
            # 先 flush 当前缓冲
            flush()
            # 按中英文句号切
            import re as _re
            sentences = _re.split(r"(?<=[。！？!?\.])\s+", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) > max_chars and buf:
                    units.append((f"part{idx:02d}", buf.strip()))
                    idx += 1
                    buf = s
                else:
                    buf = buf + s if buf else s
                # 单句就超长 → 按字数硬切
                while len(buf) > max_chars:
                    chunk = buf[:max_chars]
                    units.append((f"part{idx:02d}", chunk.strip()))
                    idx += 1
                    buf = buf[max_chars:]
            if buf.strip():
                current = buf
            continue

        if len(current) + len(p) > max_chars and current:
            flush()
            current = p
        else:
            current = current + "\n\n" + p if current else p

    flush()
    return units


def merge_small(
    units: List[Tuple[str, str]],
    min_chars: int = 500,
) -> List[Tuple[str, str]]:
    """太短的单元合并到下一个。"""
    if not units:
        return units
    merged: List[Tuple[str, str]] = []
    buffer_title = None
    buffer_body = ""
    for title, body in units:
        if len(buffer_body) < min_chars:
            buffer_body = buffer_body + "\n\n" + body if buffer_body else body
            buffer_title = buffer_title or title
        else:
            if buffer_title:
                merged.append((buffer_title, buffer_body))
            buffer_title = title
            buffer_body = body
    if buffer_title:
        merged.append((buffer_title, buffer_body))
    return merged


def split_markdown(
    text: str,
    out_dir: Path,
    prefix: str = "ch",
    min_chars: int = 500,
    max_chars: int = 50000,
    name_hint: str = "",
) -> List[Path]:
    """主入口：把 text 切成多个 chXX.md 落到 out_dir。

    返回单元文件路径列表。
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    units = split_by_h1(text)
    if not units:
        units = split_by_h2(text)
    if not units:
        units = split_by_chinese_chapter(text)
    if not units:
        units = hard_split(text, max_chars=max_chars)

    # 太长的单元按 H2 再切
    refined: List[Tuple[str, str]] = []
    for title, body in units:
        if len(body) > max_chars:
            sub_units = split_by_h2(body)
            if sub_units:
                refined.extend(sub_units)
            else:
                refined.append((title, body))
        else:
            refined.append((title, body))

    refined = merge_small(refined, min_chars=min_chars)

    # 最终硬切：保证每单元 ≤ max_chars
    final: List[Tuple[str, str]] = []
    for title, body in refined:
        if len(body) > max_chars:
            sub = hard_split(body, max_chars)
            for i, (sub_title, sub_body) in enumerate(sub, 1):
                final.append((f"{title}（{i}）", sub_body))
        else:
            final.append((title, body))

    # 按单元 id 生成文件名（ch01.md, ch02.md, ...）
    unit_paths: List[Path] = []
    for idx, (title, body) in enumerate(final, 1):
        fname = f"{prefix}{idx:02d}.md"
        path = out_dir / fname
        # 如果 body 没有起手标题，补一个
        if not body.lstrip().startswith("#"):
            body = f"# {title}\n\n{body}"
        path.write_text(body, encoding="utf-8")
        unit_paths.append(path)

    return unit_paths


if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser()
    p.add_argument("input_md")
    p.add_argument("out_dir")
    p.add_argument("--prefix", default="ch")
    p.add_argument("--min", type=int, default=500)
    p.add_argument("--max", type=int, default=50000)
    args = p.parse_args()

    src = Path(args.input_md)
    out = Path(args.out_dir)
    text = src.read_text(encoding="utf-8", errors="replace")
    units = split_markdown(text, out, prefix=args.prefix,
                           min_chars=args.min, max_chars=args.max)
    print(f"split into {len(units)} units:")
    for u in units:
        print(f"  {u.name}: {u.stat().st_size} bytes")
