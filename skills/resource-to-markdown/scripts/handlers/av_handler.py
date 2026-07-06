"""av_handler.py — 视频/音频转 markdown（带时间戳）。

策略（按可用性路由）：
  1. 首选 faster-whisper（如果模型已下载到本地缓存）
  2. 回退系统 whisper CLI（/opt/homebrew/bin/whisper，已装）
  3. 都失败 → 报错

输出按时间段切块，每 5 分钟左右一个 H2 段，便于后续切分。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def extract_audio(video_path: Path, out_audio: Path, timeout: int = 600) -> dict:
    """ffmpeg 提取/转换音轨到 16kHz mono wav。"""
    if not shutil.which("ffmpeg"):
        return {"ok": False, "error": "ffmpeg not installed"}
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vn", "-ac", "1", "-ar", "16000",
             "-f", "wav", str(out_audio)],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr[:200]}
        return {"ok": True, "audio_path": str(out_audio)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def transcribe_with_faster_whisper(audio_path: Path, out_md: Path,
                                    language: str = None,
                                    timeout: int = 1800) -> dict:
    """faster-whisper（首选，速度快、内存省）。

    模型选择策略：环境变量 WHISPER_MODEL > large-v3 > medium > base
    优先用本地缓存已有的模型，避免下载。
    """
    try:
        from faster_whisper import WhisperModel
        # 按优先级试模型
        candidates = []
        env_model = os.environ.get("WHISPER_MODEL")
        if env_model:
            candidates.append(env_model)
        candidates.extend(["large-v3", "medium", "base", "tiny"])

        model = None
        model_name = None
        last_err = None
        for name in candidates:
            try:
                model = WhisperModel(name, device="cpu", compute_type="int8")
                model_name = name
                break
            except Exception as e:
                last_err = e
                continue

        if model is None:
            return {"ok": False, "error": f"all models failed: {last_err}"}

        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
        )

        lines = [f"<!-- language: {info.language}, duration: {info.duration:.0f}s -->",
                 "", "# 转写", ""]

        last_h2_time = -10000
        seg_count = 0
        for seg in segments:
            seg_count += 1
            start = seg.start
            mm_s, ss_s = divmod(int(start), 60)
            text = seg.text.strip()
            if not text:
                continue
            if seg_count == 1 or start - last_h2_time > 300:
                lines.append("")
                lines.append(f"## [{mm_s:02d}:{ss_s:02d}]")
                lines.append("")
                last_h2_time = start
            lines.append(text)

        md_text = "\n".join(lines)
        out_md.write_text(md_text, encoding="utf-8")
        return {
            "ok": True,
            "engine": f"faster-whisper-{model_name}",
            "chars": len(md_text),
            "language": info.language,
            "duration_sec": info.duration,
        }
    except Exception as e:
        return {"ok": False, "error": f"faster-whisper: {e}"}


def transcribe_with_whisper_cli(audio_path: Path, out_md: Path,
                                  language: str = None,
                                  timeout: int = 3600) -> dict:
    """whisper CLI（系统装的 openai-whisper）兜底。

    用 base 模型（本地缓存已有 ~/.cache/whisper/base.pt）避免下载。
    """
    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        return {"ok": False, "error": "whisper CLI not installed"}

    tmpdir = tempfile.mkdtemp(prefix="whisper_out_")
    try:
        cmd = [
            whisper_bin,
            str(audio_path),
            "--model", "base",
            "--output_format", "json",
            "--output_dir", tmpdir,
            "--verbose", "False",
        ]
        if language:
            cmd.extend(["--language", language])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"whisper CLI: {result.stderr[:200]}"}

        json_files = list(Path(tmpdir).glob("*.json"))
        if not json_files:
            return {"ok": False, "error": "no whisper output"}
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        lines = [
            f"<!-- language: {data.get('language', '?')} -->",
            "", "# 转写", "",
        ]
        last_h2_time = -10000
        for seg in data.get("segments", []):
            start = seg.get("start", 0)
            mm_s, ss_s = divmod(int(start), 60)
            text = seg.get("text", "").strip()
            if not text:
                continue
            if start - last_h2_time > 300:
                lines.append("")
                lines.append(f"## [{mm_s:02d}:{ss_s:02d}]")
                lines.append("")
                last_h2_time = start
            lines.append(text)

        md_text = "\n".join(lines)
        out_md.write_text(md_text, encoding="utf-8")
        return {
            "ok": True,
            "engine": "whisper-cli-base",
            "chars": len(md_text),
            "language": data.get("language"),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"whisper CLI timeout {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": f"whisper CLI: {e}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def convert(media_path: Path, out_md: Path, language: str = None) -> dict:
    """主入口：视频/音频 → markdown。

    优先 whisper CLI（本地缓存命中秒开），faster-whisper 作为可选高质量路径。
    """
    warnings = []
    suffix = media_path.suffix.lower()
    needs_ffmpeg = suffix in (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v")

    audio_to_transcribe = media_path
    tmp_audio = None

    if needs_ffmpeg:
        tmp_audio = media_path.with_suffix(".tmp.wav")
        r_extract = extract_audio(media_path, tmp_audio)
        if not r_extract["ok"]:
            return {
                "ok": False, "engine": "none",
                "attempts": [], "warnings": [r_extract["error"]],
                "error": "ffmpeg extraction failed",
            }
        audio_to_transcribe = tmp_audio
        warnings.append("已用 ffmpeg 提取音轨")

    # 首选 whisper CLI（本地缓存命中），可选 faster-whisper（更高质量但需下载）
    prefer_faster = os.environ.get("PREFER_FASTER_WHISPER", "0") == "1"
    attempts = []

    if prefer_faster:
        r1 = transcribe_by_attempt(audio_to_transcribe, out_md,
                                    transcribe_with_faster_whisper, language, "faster-whisper")
        attempts.append(r1)
        if r1["ok"]:
            if tmp_audio and tmp_audio.exists():
                tmp_audio.unlink()
            return {**r1, "engine": "faster-whisper", "attempts": attempts, "warnings": warnings}
        warnings.append(f"faster-whisper 失败：{r1.get('error', '?')[:100]}")

    r2 = transcribe_by_attempt(audio_to_transcribe, out_md,
                                transcribe_with_whisper_cli, language, "whisper-cli")
    attempts.append(r2)
    if tmp_audio and tmp_audio.exists():
        tmp_audio.unlink()
    if r2["ok"]:
        return {**r2, "engine": "whisper-cli", "attempts": attempts, "warnings": warnings}

    # 如果 whisper CLI 失败且没用过 faster-whisper，最后试一下
    if not prefer_faster:
        r3 = transcribe_by_attempt(audio_to_transcribe, out_md,
                                    transcribe_with_faster_whisper, language, "faster-whisper")
        attempts.append(r3)
        if r3["ok"]:
            return {**r3, "engine": "faster-whisper", "attempts": attempts, "warnings": warnings}
        warnings.append(f"faster-whisper 失败：{r3.get('error', '?')[:100]}")

    return {
        "ok": False, "engine": "none",
        "attempts": attempts, "warnings": warnings,
        "error": "all engines failed",
    }


def transcribe_by_attempt(audio_path: Path, out_md: Path,
                           fn, language: str, name: str) -> dict:
    """统一异常包装。"""
    try:
        return fn(audio_path, out_md, language=language)
    except Exception as e:
        return {"ok": False, "error": f"{name}: {e}"}
