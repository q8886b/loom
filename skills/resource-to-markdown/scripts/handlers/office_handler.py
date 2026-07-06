"""office_handler.py — docx/pptx/xlsx 转 markdown。

MarkItDown 是这条路径的主力（微软原生支持 Office 格式）。
"""
from __future__ import annotations

from pathlib import Path


def convert_with_markitdown(file_path: Path, out_md: Path) -> dict:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(file_path))
        text = result.text_content
        out_md.write_text(text, encoding="utf-8")
        return {"ok": True, "engine": "markitdown", "chars": len(text)}
    except Exception as e:
        return {"ok": False, "engine": "markitdown", "error": str(e)}


def convert_with_pandoc(file_path: Path, out_md: Path) -> dict:
    """docx 可走 pandoc 兜底。"""
    import shutil, subprocess
    if not shutil.which("pandoc"):
        return {"ok": False, "engine": "pandoc", "error": "not installed"}
    try:
        result = subprocess.run(
            ["pandoc", "--wrap=none", "--markdown-headings=atx",
             "-f", "docx", "-t", "gfm",
             "-o", str(out_md), str(file_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"ok": False, "engine": "pandoc",
                    "error": result.stderr[:200]}
        text = out_md.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "engine": "pandoc", "chars": len(text)}
    except Exception as e:
        return {"ok": False, "engine": "pandoc", "error": str(e)}


def convert(file_path: Path, out_md: Path) -> dict:
    r1 = convert_with_markitdown(file_path, out_md)
    if r1["ok"]:
        return {**r1, "attempts": [r1], "warnings": []}

    # docx 可走 pandoc 兜底
    if file_path.suffix.lower() == ".docx":
        r2 = convert_with_pandoc(file_path, out_md)
        if r2["ok"]:
            return {**r2, "attempts": [r1, r2],
                    "warnings": [f"markitdown 失败，回退 pandoc：{r1.get('error', '?')[:100]}"]}

    return {
        "ok": False, "engine": "none",
        "attempts": [r1], "warnings": ["all failed"],
        "error": f"office conversion failed for {file_path.suffix}",
    }
