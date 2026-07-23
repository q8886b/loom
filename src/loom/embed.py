"""Embedding providers for Loom.

Loom treats embedding as a core capability, but the provider is configurable.
The default is a local Ollama model so open source users can keep source
material on their own machine. Zhipu is kept as a compatibility preset.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import ssl
from pathlib import Path
from typing import Any


def _loom_home() -> Path:
    return Path(os.environ.get("LOOM_HOME", Path.home() / ".loom"))


ENV_PATHS = [
    _loom_home() / ".env",
]


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dim: int
    base_url: str
    api_key: str = ""
    send_dimensions: bool = False


def _read_env_files() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    return _read_env_files().get(name, default)


def _positive_int(value: str, *, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be positive, got {parsed}")
    return parsed


def get_config() -> EmbeddingConfig:
    provider = _env("LOOM_EMBED_PROVIDER").strip().lower()
    if not provider:
        if _env("ZHIPU_API_KEY"):
            provider = "zhipu"
        elif _env("LOOM_EMBED_API_KEY") or _env("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "ollama"

    if provider == "none":
        raise RuntimeError(
            "embedding disabled by LOOM_EMBED_PROVIDER=none; use --mode=fts "
            "or configure an embedding provider"
        )

    if provider == "ollama":
        model = _env("LOOM_EMBED_MODEL", "bge-m3")
        dim = _positive_int(_env("LOOM_EMBED_DIM", "1024"), name="LOOM_EMBED_DIM")
        base_url = _env("LOOM_EMBED_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        return EmbeddingConfig(provider="ollama", model=model, dim=dim, base_url=base_url)

    if provider == "zhipu":
        model = _env("LOOM_EMBED_MODEL", "embedding-3")
        dim = _positive_int(_env("LOOM_EMBED_DIM", "2048"), name="LOOM_EMBED_DIM")
        base_url = _env("LOOM_EMBED_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        api_key = _env("LOOM_EMBED_API_KEY") or _env("ZHIPU_API_KEY")
        return EmbeddingConfig(
            provider="zhipu",
            model=model,
            dim=dim,
            base_url=base_url,
            api_key=api_key,
            send_dimensions=True,
        )

    if provider in {"openai", "openai-compatible"}:
        model = _env("LOOM_EMBED_MODEL", "text-embedding-3-small")
        dim = _positive_int(_env("LOOM_EMBED_DIM", "1536"), name="LOOM_EMBED_DIM")
        base_url = _env("LOOM_EMBED_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        api_key = _env("LOOM_EMBED_API_KEY") or _env("OPENAI_API_KEY")
        send_dimensions = _env("LOOM_EMBED_SEND_DIMENSIONS", "").lower() in {"1", "true", "yes"}
        return EmbeddingConfig(
            provider="openai",
            model=model,
            dim=dim,
            base_url=base_url,
            api_key=api_key,
            send_dimensions=send_dimensions,
        )

    raise RuntimeError(
        "unsupported LOOM_EMBED_PROVIDER: "
        f"{provider!r}; expected ollama, openai, zhipu, or none"
    )


def embedding_dim() -> int:
    # `none` is a supported operational mode for FTS-only imports/searches.
    # Store initialization still needs a stable DB vector dimension even though
    # individual embedding calls will intentionally be skipped by callers.
    if _env("LOOM_EMBED_PROVIDER").strip().lower() == "none":
        return _positive_int(_env("LOOM_EMBED_DIM", "2048"), name="LOOM_EMBED_DIM")
    return get_config().dim


def _get_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    retries: int = 3,
) -> dict[str, Any]:
    import time
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=_get_ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                break
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
        except Exception as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    assert last_err is not None
    raise last_err


def _trim(text: str, cfg: EmbeddingConfig) -> str:
    """Keep requests within the provider's practical input limit.

    Zhipu's embedding-3 rejects long CJK strings before returning a vector, so
    that provider is trimmed to 2000 characters; everyone else keeps the prior
    8000-character ceiling. The limit retains a representative opening of a
    Loom card or source unit.
    """
    limit = 2000 if cfg.provider == "zhipu" else 8000
    return text if len(text) <= limit else text[:limit]


def _validate(vec: list[float], cfg: EmbeddingConfig) -> list[float]:
    if len(vec) != cfg.dim:
        raise RuntimeError(
            f"embedding dim mismatch for provider={cfg.provider}, model={cfg.model}: "
            f"got {len(vec)}, expected {cfg.dim}. Set LOOM_EMBED_DIM and run "
            "`loom-admin rebuild-embeddings` if you changed models."
        )
    return vec


def _embed_batch_ollama(cfg: EmbeddingConfig, texts: list[str]) -> list[list[float]]:
    import urllib.error

    payload = {"model": cfg.model, "input": [_trim(t, cfg) for t in texts]}
    try:
        data = _http_post_json(f"{cfg.base_url}/api/embed", payload, timeout=120)
        vectors = data.get("embeddings")
        if not isinstance(vectors, list):
            raise RuntimeError("Ollama embedding response missing 'embeddings'")
        return [_validate(list(v), cfg) for v in vectors]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    vectors = []
    for text in texts:
        data = _http_post_json(
            f"{cfg.base_url}/api/embeddings",
            {"model": cfg.model, "prompt": _trim(text, cfg)},
            timeout=120,
        )
        vec = data.get("embedding")
        if not isinstance(vec, list):
            raise RuntimeError("Ollama embedding response missing 'embedding'")
        vectors.append(_validate(list(vec), cfg))
    return vectors


def _embed_batch_openai(cfg: EmbeddingConfig, texts: list[str]) -> list[list[float]]:
    if not cfg.api_key:
        raise RuntimeError("LOOM_EMBED_API_KEY or OPENAI_API_KEY is required for openai embeddings")
    payload: dict[str, Any] = {"model": cfg.model, "input": [_trim(t, cfg) for t in texts]}
    if cfg.send_dimensions:
        payload["dimensions"] = cfg.dim
    data = _http_post_json(
        f"{cfg.base_url}/embeddings",
        payload,
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        timeout=120,
    )
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError("embedding response missing 'data'")
    return [_validate(list(item["embedding"]), cfg) for item in items]


def _embed_batch_zhipu(cfg: EmbeddingConfig, texts: list[str]) -> list[list[float]]:
    if not cfg.api_key:
        raise RuntimeError("ZHIPU_API_KEY or LOOM_EMBED_API_KEY is required for zhipu embeddings")
    payload = {
        "model": cfg.model,
        "input": [_trim(t, cfg) for t in texts],
        "dimensions": cfg.dim,
    }
    data = _http_post_json(
        f"{cfg.base_url}/embeddings",
        payload,
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        timeout=120,
    )
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError("embedding response missing 'data'")
    return [_validate(list(item["embedding"]), cfg) for item in items]


def embed(text: str) -> list[float]:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    cfg = get_config()
    if cfg.provider == "ollama":
        return _embed_batch_ollama(cfg, texts)
    if cfg.provider == "zhipu":
        return _embed_batch_zhipu(cfg, texts)
    return _embed_batch_openai(cfg, texts)
