"""djvu_handler.py — DjVu 转 markdown。

策略：
  1. djvutxt 直接提取文本层（有隐藏文本层的 DjVu，最快）
  2. ddjvu → PDF → pdf_handler（纯扫描型 DjVu，走 OCR）
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MIN_TEXT_CHARS = 500  # Below this, assume no text layer → fall back to OCR


def convert(input_path: Path, out_md: Path) -> dict:
    errors = []

    # ── Strategy 1: djvutxt (text layer extraction) ──
    djvutxt = shutil.which("djvutxt")
    if djvutxt:
        try:
            result = subprocess.run(
                [djvutxt, str(input_path), str(out_md)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and out_md.exists():
                text = out_md.read_text(encoding="utf-8", errors="replace")
                if len(text) >= MIN_TEXT_CHARS:
                    return {"ok": True, "engine": "djvutxt",
                            "chars": len(text), "attempts": [],
                            "warnings": []}
                else:
                    errors.append(f"djvutxt produced only {len(text)} chars (threshold: {MIN_TEXT_CHARS})")
        except subprocess.TimeoutExpired:
            errors.append("djvutxt timeout 120s")
        except Exception as e:
            errors.append(f"djvutxt error: {e}")
    else:
        errors.append("djvutxt not found")

    # ── Strategy 2: ddjvu → PDF → OCR ──
    ddjvu = shutil.which("ddjvu")
    if not ddjvu:
        return {"ok": False, "engine": "djvu",
                "error": "djvulibre tools not installed; brew install djvulibre",
                "warnings": errors}

    tmpdir = Path(tempfile.mkdtemp(prefix="loom_djvu_"))
    try:
        pdf_path = tmpdir / "converted.pdf"
        result = subprocess.run(
            [ddjvu, "-format=pdf", "-quality=90",
             str(input_path), str(pdf_path)],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
            errors.append(f"ddjvu failed: {result.stderr[:200]}")
            return {"ok": False, "engine": "djvu",
                    "error": f"all strategies failed. Errors: {'; '.join(errors)}",
                    "warnings": errors}

        from handlers import pdf_handler
        pdf_result = pdf_handler.convert(pdf_path, out_md)
        pdf_result["engine"] = f"djvu→pdf→{pdf_result.get('engine', '?')}"
        pdf_result.setdefault("warnings", [])
        pdf_result["warnings"].insert(0, f"djvutxt failed ({errors[0][:80]}) → ddjvu → PDF")
        return pdf_result

    except subprocess.TimeoutExpired:
        errors.append("ddjvu timeout 600s")
        return {"ok": False, "engine": "djvu",
                "error": f"all strategies failed. Errors: {'; '.join(errors)}",
                "warnings": errors}
    except Exception as e:
        errors.append(str(e))
        return {"ok": False, "engine": "djvu",
                "error": f"all strategies failed. Errors: {'; '.join(errors)}",
                "warnings": errors}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    import argparse, json, sys
    p = argparse.ArgumentParser()
    p.add_argument("djvu")
    p.add_argument("out_md")
    args = p.parse_args()
    r = convert(Path(args.djvu), Path(args.out_md))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["ok"] else 1)
