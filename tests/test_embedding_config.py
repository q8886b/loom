from __future__ import annotations

import importlib

import pytest


def test_embedding_default_is_local_ollama(monkeypatch, tmp_path):
    monkeypatch.setenv("LOOM_HOME", str(tmp_path / "empty_loom"))
    for key in [
        "LOOM_EMBED_PROVIDER",
        "LOOM_EMBED_MODEL",
        "LOOM_EMBED_DIM",
        "LOOM_EMBED_BASE_URL",
        "LOOM_EMBED_API_KEY",
        "OPENAI_API_KEY",
        "ZHIPU_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    import loom.embed as embed

    embed = importlib.reload(embed)
    cfg = embed.get_config()
    assert cfg.provider == "ollama"
    assert cfg.model == "bge-m3"
    assert cfg.dim == 1024
    assert cfg.base_url == "http://127.0.0.1:11434"


def test_embedding_openai_compatible_config(monkeypatch):
    monkeypatch.setenv("LOOM_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("LOOM_EMBED_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LOOM_EMBED_API_KEY", "test-key")
    monkeypatch.setenv("LOOM_EMBED_MODEL", "my-embed")
    monkeypatch.setenv("LOOM_EMBED_DIM", "768")

    import loom.embed as embed

    embed = importlib.reload(embed)
    cfg = embed.get_config()
    assert cfg.provider == "openai"
    assert cfg.base_url == "https://example.test/v1"
    assert cfg.api_key == "test-key"
    assert cfg.model == "my-embed"
    assert cfg.dim == 768


def test_store_rejects_embedding_dimension_mismatch(loom):
    store = loom["store"]
    store.insert_card(
        card_id="llm:mismatch:01",
        title="维度测试主题",
        type_="主题",
        content="这张卡用于验证向量维度不一致时会明确拒绝，避免不同模型的向量混入同一张表。",
        layer="L2",
        source="llm:mismatch:src:01",
        embedding=[0.0] * store.EMBED_DIM,
    )

    with pytest.raises(ValueError, match="rebuild-embeddings"):
        store.insert_card(
            card_id="llm:mismatch:02",
            title="错误维度",
            type_="主题",
            content="这张卡故意使用错误维度，应该触发重建向量索引的提示。",
            layer="L2",
            source="llm:mismatch:src:01",
            embedding=[0.0] * (store.EMBED_DIM + 1),
        )


def test_rebuild_embeddings_uses_current_provider_dimension(loom, monkeypatch, capsys):
    store = loom["store"]
    cli = loom["cli"]
    store.insert_card(
        card_id="llm:rebuild:01",
        title="重建向量主题",
        type_="主题",
        content="这张卡用于验证 rebuild-embeddings 会按照当前 provider 维度重建 sqlite-vec 表。",
        layer="L2",
        source="llm:rebuild:src:01",
        embedding=[0.0] * store.EMBED_DIM,
    )

    monkeypatch.setenv("LOOM_EMBED_PROVIDER", "ollama")
    monkeypatch.setenv("LOOM_EMBED_MODEL", "tiny-local")
    monkeypatch.setenv("LOOM_EMBED_DIM", "3")
    monkeypatch.setattr(cli.embed, "get_config", lambda: cli.embed.EmbeddingConfig(
        provider="ollama",
        model="tiny-local",
        dim=3,
        base_url="http://127.0.0.1:11434",
    ))
    monkeypatch.setattr(cli.embed, "embed", lambda _text: [0.1, 0.2, 0.3])
    monkeypatch.setattr(cli.embed, "embed_batch", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])

    loom["run"](["rebuild-embeddings", "--batch-size=1"], admin=True)
    out = capsys.readouterr().out
    assert '"dim": 3' in out
    assert store.get_embedding_dim() == 3
