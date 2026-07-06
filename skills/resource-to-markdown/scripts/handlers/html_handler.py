"""html_handler.py — HTML 转 markdown。

策略：
  1. 首选 pandoc（结构保留最好）
  2. 失败回退 MarkItDown
  3. 检测 SPA 动态网页：div 标签多但正文少 → 标记 unsupported（需要 headless browser）
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


SPA_HINT_PATTERN = re.compile(r"<div[^>]*preset-id=|<div[^>]*elem-id=|<div id=\"app\"|<div id=\"root\"|window\.__INITIAL_STATE__")
DIV_PATTERN = re.compile(r"<div\b", re.IGNORECASE)


def detect_spa(html_text: str) -> dict:
    """检测是否为 SPA 动态网页（正文不在 HTML 里）。"""
    div_count = len(DIV_PATTERN.findall(html_text))
    text_chars = len(re.sub(r"<[^>]+>", "", html_text).strip())
    spa_hints = len(SPA_HINT_PATTERN.findall(html_text))

    is_spa = (
        spa_hints >= 1 and div_count > 20 and text_chars < 2000
    ) or (
        div_count > 100 and text_chars < 1000
    )

    return {
        "is_spa": is_spa,
        "div_count": div_count,
        "text_chars": text_chars,
        "spa_hints": spa_hints,
    }


def convert_with_pandoc(html_path: Path, out_md: Path) -> dict:
    if not shutil.which("pandoc"):
        return {"ok": False, "engine": "pandoc", "error": "not installed"}
    try:
        result = subprocess.run(
            [
                "pandoc", "--wrap=none",
                "--markdown-headings=atx",
                "-f", "html",
                "-t", "gfm",
                "-o", str(out_md),
                str(html_path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"ok": False, "engine": "pandoc",
                    "error": result.stderr[:200]}
        text = out_md.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "engine": "pandoc", "chars": len(text)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "engine": "pandoc", "error": "timeout 60s"}
    except Exception as e:
        return {"ok": False, "engine": "pandoc", "error": str(e)}


def convert_with_markitdown(html_path: Path, out_md: Path) -> dict:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(html_path))
        text = result.text_content
        out_md.write_text(text, encoding="utf-8")
        return {"ok": True, "engine": "markitdown", "chars": len(text)}
    except Exception as e:
        return {"ok": False, "engine": "markitdown", "error": str(e)}


def convert(html_path: Path, out_md: Path) -> dict:
    # SPA 预检
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="replace")
        spa = detect_spa(html_text)
    except Exception as e:
        spa = {"is_spa": False, "error": str(e)}

    if spa.get("is_spa"):
        return {
            "ok": False, "engine": "none",
            "attempts": [],
            "warnings": [
                f"SPA 动态网页（div={spa['div_count']}, text={spa['text_chars']}），"
                f"正文不在 HTML 里，需要 headless browser 渲染（skill 不支持）"
            ],
            "error": "unsupported: SPA content",
            "spa_detected": spa,
        }

    r1 = convert_with_pandoc(html_path, out_md)
    if r1["ok"]:
        return {**r1, "attempts": [r1], "warnings": [],
                "spa_detected": spa}
    r2 = convert_with_markitdown(html_path, out_md)
    if r2["ok"]:
        return {**r2, "attempts": [r1, r2],
                "warnings": [f"pandoc 失败，回退：{r1.get('error', '?')[:100]}"],
                "spa_detected": spa}
    return {
        "ok": False, "engine": "none",
        "attempts": [r1, r2], "warnings": ["all failed"],
        "error": "html conversion failed",
        "spa_detected": spa,
    }
