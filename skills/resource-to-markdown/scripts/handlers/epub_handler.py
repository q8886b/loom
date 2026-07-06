"""epub_handler.py — EPUB / AZW / MOBI 转 markdown。

策略：
  1. DRM 检测：有加密/混淆特征 → 立即报告，不浪费时间兜底
  2. AZW/MOBI 先用 kindleunpack 解包为 EPUB
  3. 首选 markitdown（实测对中文 EPUB 输出最好，保留章节层级）
  4. 失败回退 pandoc（--from epub）
  5. 仍失败 → 解包 + 编码检测修复（GBK/GB2312 → UTF-8）+ pandoc 逐文件转换
  6. 全失败 → convert_failed
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

# ── DRM 检测 ──────────────────────────────────────────────────────────────

_DRM_SIGNATURES = [
    "zhangyue", "drm", "encryption", "rights.xml", "adept",
    "marlin", "fairplay", "suncom",
]


def _byte_entropy(raw: bytes, sample: int = 256) -> float:
    """Estimate byte entropy (0–1). High entropy (>0.85) with no valid encoding → encrypted."""
    if len(raw) == 0:
        return 0.0
    s = raw[:sample]
    counts = {}
    for b in s:
        counts[b] = counts.get(b, 0) + 1
    n = len(s)
    import math
    h = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return h / math.log2(min(n, 256))


def _is_drm_protected(epub_path: Path) -> tuple[bool, str]:
    """Check if EPUB appears to be DRM-encrypted.

    Returns (is_drm, reason).
    """
    try:
        with zipfile.ZipFile(epub_path) as zf:
            names = [n.lower() for n in zf.namelist()]

            # 1. Known DRM signatures in META-INF
            for sig in _DRM_SIGNATURES:
                for name in names:
                    if sig in name:
                        return True, f"META-INF 含 DRM 签名: {name}"

            # 2. Content files encrypted (high entropy, no valid XML/HTML header)
            content_files = [n for n in zf.namelist()
                           if n.endswith(('.xhtml', '.html', '.xml', '.htm'))
                           and 'META-INF' not in n]
            if not content_files:
                return False, ""

            encrypted = 0
            for name in content_files[:3]:  # Sample first 3
                raw = zf.read(name)
                if len(raw) == 0:
                    continue
                # Try all common encodings
                decodable = False
                for enc in ['utf-8', 'gb18030', 'gbk', 'shift_jis', 'latin-1']:
                    try:
                        decoded = raw.decode(enc)
                        if '<' in decoded[:200] or '?' in decoded[:200]:
                            decodable = True
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                if not decodable:
                    ent = _byte_entropy(raw)
                    if ent > 0.85:
                        encrypted += 1

            if encrypted >= 2:
                return True, f"内容文件疑似加密（{encrypted}/{min(3, len(content_files))} 个文件高熵且无法解码）"

            return False, ""
    except Exception:
        return False, ""


# ── 编码检测与修复 ─────────────────────────────────────────────────────────

def _detect_and_decode(raw: bytes) -> tuple[str, str]:
    """Detect encoding and decode bytes to string.

    Returns (text, encoding_used).
    """
    # 1. UTF-8 with BOM
    if raw[:3] == b'\xef\xbb\xbf':
        return raw[3:].decode('utf-8'), 'utf-8-bom'

    # 2. UTF-16 BOM
    if raw[:2] == b'\xfe\xff':
        return raw[2:].decode('utf-16-be'), 'utf-16-be'
    if raw[:2] == b'\xff\xfe':
        return raw[2:].decode('utf-16-le'), 'utf-16-le'

    # 3. Plain UTF-8
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        pass

    # 4. XML/HTML declared encoding (<?xml encoding="..."?>, <meta charset="...">)
    head = raw[:1024]
    import re
    m = re.search(rb'encoding\s*=\s*["\']([^"\']+)["\']', head)
    if m:
        declared = m.group(1).decode('ascii', errors='replace').lower()
        try:
            return raw.decode(declared), declared
        except (UnicodeDecodeError, LookupError):
            pass

    # 5. chardet
    try:
        import chardet
        detected = chardet.detect(raw)
        enc = detected.get('encoding')
        conf = detected.get('confidence', 0)
        if enc and conf > 0.7:
            try:
                return raw.decode(enc), f'chardet:{enc}'
            except (UnicodeDecodeError, UnicodeError):
                pass
    except ImportError:
        pass

    # 6. Brute-force CJK encodings
    for enc in ['gb18030', 'gbk', 'gb2312', 'big5', 'shift_jis', 'euc-jp', 'euc-kr']:
        try:
            decoded = raw.decode(enc)
            # Sanity: should look like HTML/XML
            if '<' in decoded[:500]:
                return decoded, enc
        except (UnicodeDecodeError, UnicodeError):
            continue

    # 7. Last resort: UTF-8 with replacement chars
    return raw.decode('utf-8', errors='replace'), 'utf-8-replace'


# ── 解包 + 编码修复兜底 ────────────────────────────────────────────────────

def _extract_fallback(epub_path: Path, out_md: Path) -> dict:
    """Extract EPUB, detect encoding per-file, convert with pandoc individually.

    Used when markitdown and pandoc both fail on a malformed/non-UTF-8 EPUB.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="loom_epub_fix_"))
    try:
        # 1. Extract EPUB
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(tmpdir)

        # 2. Find HTML/XHTML content files, sorted by filename (roughly chapter order)
        html_files = sorted(
            [f for f in tmpdir.rglob("*")
             if f.suffix.lower() in ('.html', '.xhtml', '.htm')],
            key=lambda p: p.name
        )

        if not html_files:
            return {"ok": False, "engine": "extract_fallback",
                    "error": "EPUB 内无 HTML/XHTML 文件"}

        # 3. Convert each file
        parts = []
        total_chars = 0
        encoding_used = None
        for hf in html_files:
            raw = hf.read_bytes()
            text, enc = _detect_and_decode(raw)
            if encoding_used is None and enc != 'utf-8':
                encoding_used = enc
            # Write fixed UTF-8 temp file for pandoc
            fixed = hf.parent / (hf.stem + "_fixed.html")
            fixed.write_text(text, encoding='utf-8')
            try:
                result = subprocess.run(
                    ["pandoc", "--wrap=none", "--markdown-headings=atx",
                     "-f", "html", "-t", "markdown_strict",
                     str(fixed)],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts.append(result.stdout)
                    total_chars += len(result.stdout)
            except (subprocess.TimeoutExpired, Exception):
                continue
            finally:
                fixed.unlink(missing_ok=True)

        if not parts:
            return {"ok": False, "engine": "extract_fallback",
                    "error": "pandoc 逐文件转换全部失败"}

        out_md.write_text("\n\n".join(parts), encoding='utf-8')
        warnings = []
        if encoding_used and encoding_used not in ('utf-8', 'utf-8-bom'):
            warnings.append(f"检测到 {encoding_used} 编码，已转为 UTF-8")
        return {"ok": True, "engine": f"extract+{encoding_used or 'utf-8'}+pandoc",
                "chars": total_chars, "warnings": warnings}

    except Exception as e:
        return {"ok": False, "engine": "extract_fallback", "error": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── AZW/MOBI 解包 ─────────────────────────────────────────────────────────

def _unpack_azw_mobi(input_path: Path) -> Path:
    """KindleUnpack 解包 AZW/MOBI → EPUB，返回 EPUB 路径。"""
    try:
        from mobi.kindleunpack import unpackBook
        import sys
    except ImportError:
        raise RuntimeError("mobi (kindleunpack) not installed; pip install mobi")

    tmpdir = tempfile.mkdtemp(prefix="loom_epub_")
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = open(tmpdir + "/_log.txt", "w")
        sys.stderr = sys.stdout
        unpackBook(str(input_path), tmpdir)
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        (Path(tmpdir) / "_log.txt").unlink(missing_ok=True)

    extracted = Path(tmpdir)
    for sub in ["mobi8", "mobi7"]:
        epub_files = list(extracted.glob(f"{sub}/*.epub"))
        if epub_files:
            return epub_files[0]

    # 回退：无内嵌 EPUB 时，找 HTML 用 pandoc 合成 EPUB
    for sub in ["mobi8", "mobi7"]:
        html_files = list(extracted.glob(f"{sub}/*.html")) + list(extracted.glob(f"{sub}/*.xhtml"))
        if html_files:
            html_path = html_files[0]
            epub_out = extracted / f"{sub}.epub"
            try:
                subprocess.run(
                    ["pandoc", "-f", "html", "-t", "epub", "-o", str(epub_out), str(html_path)],
                    capture_output=True, text=True, timeout=120, check=True,
                )
                return epub_out
            except Exception as e:
                raise RuntimeError(
                    f"kindleunpack produced HTML but pandoc EPUB synthesis failed: {e}"
                )

    raise RuntimeError(f"kindleunpack did not produce EPUB or HTML in {tmpdir}")


# ── 单引擎转换 ─────────────────────────────────────────────────────────────

def convert_with_markitdown(epub_path: Path, out_md: Path) -> dict:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(epub_path))
        text = result.text_content
        out_md.write_text(text, encoding="utf-8")
        return {"ok": True, "engine": "markitdown", "chars": len(text)}
    except Exception as e:
        return {"ok": False, "engine": "markitdown", "error": str(e)}


def convert_with_pandoc(epub_path: Path, out_md: Path) -> dict:
    """pandoc 兜底。"""
    if not shutil.which("pandoc"):
        return {"ok": False, "engine": "pandoc", "error": "pandoc not installed"}
    try:
        result = subprocess.run(
            [
                "pandoc", "--wrap=none",
                "--markdown-headings=atx",
                "-f", "epub",
                "-t", "markdown_strict",
                "-o", str(out_md),
                str(epub_path),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"ok": False, "engine": "pandoc",
                    "error": result.stderr[:200]}
        text = out_md.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "engine": "pandoc", "chars": len(text)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "engine": "pandoc", "error": "timeout 120s"}
    except Exception as e:
        return {"ok": False, "engine": "pandoc", "error": str(e)}


# ── 多级兜底编排 ───────────────────────────────────────────────────────────

def _convert_epub_inner(epub_path: Path, out_md: Path) -> dict:
    """EPUB 转换主流程：markitdown → pandoc → 解包+编码修复 → 失败。"""

    # 0. DRM 检测（前置）
    is_drm, drm_reason = _is_drm_protected(epub_path)
    if is_drm:
        return {
            "ok": False, "engine": "none",
            "attempts": [],
            "warnings": [f"DRM 保护: {drm_reason}"],
            "error": f"EPUB 受 DRM 保护，无法自动转换 ({drm_reason})",
        }

    # 1. markitdown
    r1 = convert_with_markitdown(epub_path, out_md)
    if r1["ok"]:
        return {**r1, "attempts": [r1], "warnings": []}

    # 2. pandoc
    r2 = convert_with_pandoc(epub_path, out_md)
    if r2["ok"]:
        return {**r2, "attempts": [r1, r2],
                "warnings": [f"markitdown 失败，回退 pandoc：{r1.get('error', '?')[:100]}"]}

    # 3. 解包 + 编码修复兜底
    r3 = _extract_fallback(epub_path, out_md)
    if r3["ok"]:
        return {
            **r3, "attempts": [r1, r2, r3],
            "warnings": (
                [f"markitdown/pandoc 失败，解包编码修复后成功（{r3.get('warnings', [''])[0]}）"]
                + r3.get("warnings", [])
            ),
        }

    # 4. 全失败
    return {
        "ok": False, "engine": "none",
        "attempts": [r1, r2, r3],
        "warnings": ["all engines + extract fallback failed"],
        "error": "epub conversion failed after all strategies",
    }


# ── 入口 ───────────────────────────────────────────────────────────────────

def convert(epub_path: Path, out_md: Path) -> dict:
    """入口：自动检测 AZW/MOBI 并先解包为 EPUB。"""
    ext = epub_path.suffix.lower()
    is_azw_mobi = ext in (".azw", ".azw3", ".mobi")

    if is_azw_mobi:
        try:
            real_epub = _unpack_azw_mobi(epub_path)
        except Exception as e:
            return {
                "ok": False, "engine": "none",
                "attempts": [],
                "warnings": [f"kindleunpack failed: {e}"],
                "error": f"azw/mobi unpack failed: {e}",
            }
        result = _convert_epub_inner(real_epub, out_md)
        result.setdefault("warnings", [])
        result["warnings"].insert(0, f"unpacked {ext} → EPUB via kindleunpack")
        tmpdir = real_epub.parent.parent
        shutil.rmtree(tmpdir, ignore_errors=True)
        return result

    return _convert_epub_inner(epub_path, out_md)


if __name__ == "__main__":
    import argparse, json, sys
    p = argparse.ArgumentParser()
    p.add_argument("epub")
    p.add_argument("out_md")
    args = p.parse_args()
    r = convert(Path(args.epub), Path(args.out_md))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["ok"] else 1)
