"""Embedding via Zhipu Embedding-3 (2048-dim), OpenAI-compatible API.

Reads ZHIPU_API_KEY from ~/.loom/.env, then the ZHIPU_API_KEY environment variable.
"""
from __future__ import annotations

import os
import ssl
from pathlib import Path


def _loom_home() -> Path:
    return Path(os.environ.get("LOOM_HOME", Path.home() / ".loom"))


def _get_ssl_context() -> ssl.SSLContext:
    """Build an SSL context. Prefer certifi bundle (works on macOS where the
    system Python cert store may be empty)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _setup_urllib_ssl() -> None:
    """Make urllib.urlopen use our SSL context (certifi-backed)."""
    import urllib.request
    ctx = _get_ssl_context()
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https_handler)
    urllib.request.install_opener(opener)


_setup_urllib_ssl()

ENV_PATHS = [
    _loom_home() / ".env",
]

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "embedding-3"
DIM = 2048


def _load_api_key() -> str:
    for p in ENV_PATHS:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ZHIPU_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    # fallback to env
    val = os.environ.get("ZHIPU_API_KEY", "")
    if not val:
        raise RuntimeError(
            "ZHIPU_API_KEY not found. Looked in: "
            + ", ".join(str(p) for p in ENV_PATHS)
        )
    return val


def _http_post_json(url: str, payload: dict, timeout: int = 60, retries: int = 3):
    """HTTP POST with retry. Uses certifi SSL context."""
    import urllib.request
    import json as _json
    import time as _time
    api_key = _load_api_key()
    data = _json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                _time.sleep(1.5 * (attempt + 1))
    raise last_err


def embed(text: str) -> list[float]:
    """Embed a single string. Returns 2048-dim list. Retries on transient errors."""
    payload = {
        "model": MODEL,
        "input": text if len(text) <= 8000 else text[:8000],
        "dimensions": DIM,
    }
    data = _http_post_json(f"{API_BASE}/embeddings", payload)
    vec = data["data"][0]["embedding"]
    if len(vec) != DIM:
        raise RuntimeError(f"Embedding dim mismatch: got {len(vec)}, expected {DIM}")
    return vec


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in one call (cheaper). Retries on transient errors."""
    inputs = [t if len(t) <= 8000 else t[:8000] for t in texts]
    payload = {"model": MODEL, "input": inputs, "dimensions": DIM}
    data = _http_post_json(f"{API_BASE}/embeddings", payload, timeout=120)
    return [d["embedding"] for d in data["data"]]
