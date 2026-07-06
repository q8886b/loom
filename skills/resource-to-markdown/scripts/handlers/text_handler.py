"""text_handler.py — markdown/txt 直接处理。

策略：标准化（去 BOM、统一换行、保留原结构）后复制。
"""
from __future__ import annotations

from pathlib import Path


def convert(file_path: Path, out_md: Path) -> dict:
    try:
        raw = file_path.read_bytes()
        # 去 BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8", errors="replace")
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        out_md.write_text(text, encoding="utf-8")
        return {
            "ok": True, "engine": "copy",
            "chars": len(text),
            "attempts": [{"ok": True, "engine": "copy", "chars": len(text)}],
            "warnings": [],
        }
    except Exception as e:
        return {
            "ok": False, "engine": "copy",
            "attempts": [], "warnings": [str(e)],
            "error": str(e),
        }
