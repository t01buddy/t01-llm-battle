"""Tests for FR-8 / #137: expanded keys API with display_name, base_url, ollama, llm-studio."""
import pytest
import t01_llm_battle.routers.keys as keys_module
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
import t01_llm_battle.db as db_module
from t01_llm_battle.db import init_db, get_db
from t01_llm_battle.server import create_app


@pytest.fixture
async def keys_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    @asynccontextmanager
    async def _get_db_override(path=None):
        async with get_db(db_path) as db:
            yield db

    monkeypatch.setattr(db_module, "DB_PATH", __import__("pathlib").Path(db_path))
    monkeypatch.setattr(keys_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_keys_includes_ollama_and_lmstudio(keys_client):
    resp = await keys_client.get("/keys")
    assert resp.status_code == 200
    providers = [p["provider"] for p in resp.json()]
    assert "ollama" in providers
    assert "llm-studio" in providers


@pytest.mark.asyncio
async def test_list_keys_has_display_name_and_base_url_fields(keys_client):
    resp = await keys_client.get("/keys")
    assert resp.status_code == 200
    for item in resp.json():
        assert "display_name" in item
        assert "base_url" in item


@pytest.mark.asyncio
async def test_ollama_has_default_base_url(keys_client):
    resp = await keys_client.get("/keys")
    assert resp.status_code == 200
    ollama = next(p for p in resp.json() if p["provider"] == "ollama")
    assert ollama["base_url"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_lmstudio_has_default_base_url(keys_client):
    resp = await keys_client.get("/keys")
    assert resp.status_code == 200
    lmstudio = next(p for p in resp.json() if p["provider"] == "llm-studio")
    assert lmstudio["base_url"] == "http://localhost:1234"


@pytest.mark.asyncio
async def test_put_key_accepts_display_name_and_base_url(keys_client):
    resp = await keys_client.put(
        "/keys/openai",
        json={"key": "sk-test-1234567890", "display_name": "My OpenAI", "base_url": None},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"


@pytest.mark.asyncio
async def test_put_ollama_base_url_persisted(keys_client):
    resp = await keys_client.put(
        "/keys/ollama",
        json={"base_url": "http://192.168.1.10:11434"},
    )
    assert resp.status_code == 200

    resp2 = await keys_client.get("/keys/ollama")
    assert resp2.status_code == 200
    assert resp2.json()["base_url"] == "http://192.168.1.10:11434"


@pytest.mark.asyncio
async def test_put_display_name_persisted(keys_client):
    resp = await keys_client.put(
        "/keys/anthropic",
        json={"display_name": "Anthropic (work)"},
    )
    assert resp.status_code == 200

    resp2 = await keys_client.get("/keys/anthropic")
    assert resp2.status_code == 200
    assert resp2.json()["display_name"] == "Anthropic (work)"


@pytest.mark.asyncio
async def test_existing_key_management_unchanged(keys_client, monkeypatch):
    """env wins logic: env var overrides db key."""
    import os
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-abc")

    resp = await keys_client.get("/keys/openai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["set"] is True
    assert data["source"] == "env"
    assert data["masked_key"] is not None


@pytest.mark.asyncio
async def test_unknown_provider_returns_404(keys_client):
    resp = await keys_client.get("/keys/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_ollama_returns_422(keys_client):
    """Ollama has no API key — delete should fail with 422."""
    resp = await keys_client.delete("/keys/ollama")
    assert resp.status_code == 422
