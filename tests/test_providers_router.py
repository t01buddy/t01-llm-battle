"""Tests for provider management API: PATCH/PUT/DELETE /providers/{name}."""
import pytest
from httpx import AsyncClient, ASGITransport
from contextlib import asynccontextmanager
from pathlib import Path

import t01_llm_battle.db as db_module
import t01_llm_battle.routers.runs as runs_module
import t01_llm_battle.routers.sources as sources_module
import t01_llm_battle.routers.providers as providers_module
import t01_llm_battle.routers.fighters as fighters_module
from t01_llm_battle.db import init_db, get_db
from t01_llm_battle.server import create_app


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.fixture
async def client(db_path, monkeypatch):
    _db_path = db_path

    @asynccontextmanager
    async def _get_db_override(path=None):
        async with get_db(_db_path) as db:
            yield db

    monkeypatch.setattr(db_module, "DB_PATH", Path(_db_path))
    monkeypatch.setattr(runs_module, "get_db", _get_db_override)
    monkeypatch.setattr(sources_module, "get_db", _get_db_override)
    monkeypatch.setattr(providers_module, "get_db", _get_db_override)
    monkeypatch.setattr(fighters_module, "DB_PATH", Path(_db_path))

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_patch_provider_disable(client):
    """PATCH /providers/openai disables the provider."""
    r = await client.patch("/providers/openai", json={"enabled": False})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openai"
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_patch_provider_enable(client):
    """PATCH /providers/openai can re-enable after disabling."""
    await client.patch("/providers/openai", json={"enabled": False})
    r = await client.patch("/providers/openai", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True


@pytest.mark.asyncio
async def test_patch_unknown_provider_404(client):
    """PATCH /providers/unknown returns 404."""
    r = await client.patch("/providers/does-not-exist", json={"enabled": False})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_provider_config_server_url(client):
    """PUT /providers/ollama/config sets server_url."""
    r = await client.put("/providers/ollama/config", json={"server_url": "http://localhost:11434"})
    assert r.status_code == 200
    assert r.json()["server_url"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_put_provider_config_unknown_404(client):
    """PUT /providers/unknown/config returns 404."""
    r = await client.put("/providers/unknown/config", json={"server_url": "http://x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_system_provider_403(client):
    """DELETE /providers/openai returns 403 — system provider."""
    r = await client.delete("/providers/openai")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_unknown_provider_404(client):
    """DELETE /providers/unknown returns 404."""
    r = await client.delete("/providers/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_providers_includes_enabled_and_is_system(client):
    """GET /providers returns enabled and is_system fields."""
    r = await client.get("/providers")
    assert r.status_code == 200
    providers = r.json()
    assert len(providers) > 0
    openai = next((p for p in providers if p["name"] == "openai"), None)
    assert openai is not None
    assert "enabled" in openai
    assert "is_system" in openai
    assert "config" in openai
    assert openai["is_system"] is True
    assert openai["enabled"] is True  # default


@pytest.mark.asyncio
async def test_get_providers_reflects_disabled_state(client):
    """GET /providers reflects disabled state after PATCH."""
    await client.patch("/providers/openai", json={"enabled": False})
    r = await client.get("/providers")
    openai = next(p for p in r.json() if p["name"] == "openai")
    assert openai["enabled"] is False
