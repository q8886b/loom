#!/usr/bin/env python3.11
"""convert.py — resource-to-markdown skill 主入口。

用法：
  python3.11 convert.py <input> [--out-dir=<dir>] [--language=<zh|en|auto>]
                                [--no-split] [--min=<500>] [--max=<50000>]
                                [--timeout=<sec>]

按扩展名 + 内容路由到最佳 handler：
  .md/.txt        → text_handler（直接复制）
  .pdf            → pdf_handler（pymupdf 探测 → Docling/MarkItDown/pymupdf 三层兜底）
  .epub           → epub_handler（pandoc → MarkItDown）
  .docx/.pptx     → office_handler（MarkItDown → pandoc）
  .html/.htm      → html_handler（pandoc → MarkItDown）
  mp4/webm/mp3... → av_handler（ffmpeg + faster-whisper）

输出：
  <out-dir>/<stem>.raw.md      # 原始转换
  <out-dir>/<stem>.quality.json # 质量报告
  <out-dir>/ch01.md, ch02.md... # 按章节切分（除非 --no-split）
  <out-dir>/_meta.json         # 元数据

 Harness：
  - 输入校验：扩展名合法、文件存在
  - 过程超时：每个 handler 有硬超时
  - 出口校验：长度/结构/乱码/章节切分都达标
  - 失败回退：引擎间逐级降级
  - 全失败：报告 + 退出码 1（罕见情况标记）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from handlers import pdf_handler, epub_handler, html_handler, office_handler, av_handler, text_handler, djvu_handler
from harness import check_raw_md, check_units, summarize
from split_chapters import split_markdown


# 扩展名 → handler 映射
EXT_MAP = {
    ".md": text_handler,
    ".markdown": text_handler,
    ".txt": text_handler,
    ".pdf": pdf_handler,
    ".epub": epub_handler,
    ".azw": epub_handler,
    ".azw3": epub_handler,
    ".mobi": epub_handler,
    ".djvu": djvu_handler,
    ".djv": djvu_handler,
    ".docx": office_handler,
    ".pptx": office_handler,
    ".xlsx": office_handler,
    ".html": html_handler,
    ".htm": html_handler,
    ".mp4": av_handler,
    ".webm": av_handler,
    ".mov": av_handler,
    ".avi": av_handler,
    ".mkv": av_handler,
    ".m4v": av_handler,
    ".mp3": av_handler,
    ".m4a": av_handler,
    ".wav": av_handler,
    ".aac": av_handler,
    ".flac": av_handler,
}


def estimate_min_chars(input_path: Path, ext: str) -> int:
    """按格式估算最小期望字数（用于 harness 校验）。"""
    if ext in (".md", ".markdown", ".txt"):
        return max(100, input_path.stat().st_size // 4)
    if ext == ".pdf":
        try:
            import pymupdf
            doc = pymupdf.open(input_path)
            pages = doc.page_count
            return max(500, pages * 200)  # 平均每页 200 字
        except Exception:
            return 1000
    if ext in (".epub", ".azw", ".azw3", ".mobi"):
        return max(500, input_path.stat().st_size // 10)
    if ext in (".docx", ".pptx"):
        return 500
    if ext in (".djvu", ".djv"):
        return max(500, input_path.stat().st_size // 40)
    if ext in (".html", ".htm"):
        return max(200, input_path.stat().st_size // 20)
    # 音视频：faster-whisper 一般每分钟 150-250 字
    return 1000


def run(input_path: Path, out_dir: Path,
        language: str = None,
        no_split: bool = False,
        min_chars: int = 500,
        max_chars: int = 50000,
        ) -> dict:
    """主入口，返回完整结果 dict。"""
    started = time.time()
    result: dict = {
        "input": str(input_path),
        "out_dir": str(out_dir),
        "started_at": started,
    }

    # 输入校验
    if not input_path.exists():
        result["status"] = "failed"
        result["error"] = f"input not found: {input_path}"
        return result

    ext = input_path.suffix.lower()
    if ext not in EXT_MAP:
        result["status"] = "failed"
        result["error"] = f"unsupported extension: {ext}"
        result["supported"] = list(EXT_MAP.keys())
        return result

    handler = EXT_MAP[ext]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    raw_md = out_dir / f"{stem}.raw.md"

    # 调 handler（音视频传 language）
    if handler is av_handler:
        convert_result = handler.convert(input_path, raw_md, language=language)
    else:
        convert_result = handler.convert(input_path, raw_md)

    result["convert"] = convert_result

    if not convert_result.get("ok"):
        result["status"] = "convert_failed"
        result["error"] = convert_result.get("error", "unknown")
        result["duration_sec"] = time.time() - started
        _write_quality_report(out_dir, stem, result)
        return result

    # harness: 校验 raw.md
    expected_min = estimate_min_chars(input_path, ext)
    raw_checks = check_raw_md(raw_md, expected_min_chars=expected_min)
    result["raw_checks"] = [c.__dict__ for c in raw_checks]
    raw_summary = summarize(raw_checks)

    # 章节切分
    if no_split:
        units = []
        # 把 raw.md 复制为 ch01.md 保持一致接口
        ch01 = out_dir / "ch01.md"
        ch01.write_text(raw_md.read_text(encoding="utf-8"), encoding="utf-8")
        units = [ch01]
    else:
        text = raw_md.read_text(encoding="utf-8", errors="replace")
        units = split_markdown(text, out_dir / "chapters",
                               prefix="ch", min_chars=min_chars, max_chars=max_chars)
        # 把 chapters/ 内容上提到 out_dir（如果只有少量章节，避免嵌套）
        if units:
            moved = []
            for u in units:
                target = out_dir / u.name
                if target.exists():
                    target.unlink()
                u.rename(target)
                moved.append(target)
            units = moved
            # 清理空 chapters/
            (out_dir / "chapters").rmdir() if (out_dir / "chapters").exists() else None
            try:
                (out_dir / "chapters").rmdir()
            except Exception:
                pass

    raw_chars = len(raw_md.read_text(encoding="utf-8", errors="replace"))
    unit_checks = check_units(units, raw_chars)
    result["units"] = [str(p) for p in units]
    result["unit_checks"] = [c.__dict__ for c in unit_checks]
    unit_summary = summarize(unit_checks)

    result["raw_summary"] = raw_summary
    result["unit_summary"] = unit_summary
    result["duration_sec"] = time.time() - started

    # 最终状态
    if raw_summary["passed"] and unit_summary["passed"]:
        result["status"] = "ok"
    elif raw_summary["passed"] and not unit_summary["passed"]:
        result["status"] = "ok_with_warnings"  # raw 可用但切分有瑕疵
    else:
        result["status"] = "quality_failed"

    _write_quality_report(out_dir, stem, result)
    return result


def _write_quality_report(out_dir: Path, stem: str, result: dict) -> None:
    report_path = out_dir / f"{stem}.quality.json"
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="resource-to-markdown converter")
    p.add_argument("input", help="input file path")
    p.add_argument("--out-dir", required=True,
                   help="output directory (will be created)")
    p.add_argument("--language", default=None,
                   help="音视频语言提示 (zh/en/auto)，PDF/EPUB 不需要")
    p.add_argument("--no-split", action="store_true",
                   help="不切章节，只产出 raw.md（复制为 ch01.md）")
    p.add_argument("--min", type=int, default=500,
                   help="章节最小字数（默认 500）")
    p.add_argument("--max", type=int, default=50000,
                   help="章节最大字数（默认 50000）")
    args = p.parse_args(argv)

    input_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()

    result = run(input_path, out_dir,
                 language=args.language,
                 no_split=args.no_split,
                 min_chars=args.min, max_chars=args.max)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 退出码：ok=0, ok_with_warnings=0, 其他非 0
    if result["status"] in ("ok", "ok_with_warnings"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
