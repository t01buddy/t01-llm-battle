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


# --- POST /providers/pricing/refresh (FR-18) ---

@pytest.mark.asyncio
async def test_pricing_refresh_happy_path(client, monkeypatch, tmp_path):
    """POST /providers/pricing/refresh returns 200 with updated_at and models_updated."""
    import httpx as httpx_module
    import t01_llm_battle.routers.providers as providers_module

    raw_payload = {
        "openai/gpt-4o": {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.000005,
            "output_cost_per_token": 0.000015,
        },
        "anthropic/claude-3-opus": {
            "litellm_provider": "anthropic",
            "input_cost_per_token": 0.000015,
            "output_cost_per_token": 0.000075,
        },
    }

    class _MockResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return raw_payload

    class _MockClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): return _MockResponse()

    monkeypatch.setattr(httpx_module, "AsyncClient", lambda **kw: _MockClient())
    cache_file = tmp_path / "llm_pricing.json"
    monkeypatch.setattr(providers_module, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(providers_module, "_CACHE_FILE", cache_file)

    r = await client.post("/providers/pricing/refresh")
    assert r.status_code == 200
    data = r.json()
    assert "updated_at" in data
    assert data["models_updated"] == 2
    assert cache_file.exists()
    import json
    saved = json.loads(cache_file.read_text())
    assert "openai/gpt-4o" in saved
    assert saved["openai/gpt-4o"]["input_per_million"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_pricing_refresh_502_on_fetch_failure(client, monkeypatch):
    """POST /providers/pricing/refresh returns 502 when httpx raises."""
    import httpx as httpx_module
    import t01_llm_battle.routers.providers as providers_module

    class _FailingClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): raise httpx_module.ConnectError("timeout")

    monkeypatch.setattr(httpx_module, "AsyncClient", lambda **kw: _FailingClient())

    r = await client.post("/providers/pricing/refresh")
    assert r.status_code == 502
    assert "LiteLLM" in r.json()["detail"]


@pytest.mark.asyncio
async def test_pricing_refresh_skips_unknown_provider(client, monkeypatch, tmp_path):
    """Entries with no litellm_provider mapping are excluded from the cache."""
    import httpx as httpx_module
    import t01_llm_battle.routers.providers as providers_module

    raw_payload = {
        "unknown-provider/model-x": {
            "litellm_provider": "some_unknown_llm",
            "input_cost_per_token": 0.001,
            "output_cost_per_token": 0.002,
        },
        "openai/gpt-4o-mini": {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.00000015,
            "output_cost_per_token": 0.0000006,
        },
    }

    class _MockResponse:
        def raise_for_status(self): pass
        def json(self): return raw_payload

    class _MockClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): return _MockResponse()

    monkeypatch.setattr(httpx_module, "AsyncClient", lambda **kw: _MockClient())
    cache_file = tmp_path / "llm_pricing.json"
    monkeypatch.setattr(providers_module, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(providers_module, "_CACHE_FILE", cache_file)

    r = await client.post("/providers/pricing/refresh")
    assert r.status_code == 200
    assert r.json()["models_updated"] == 1
    import json
    saved = json.loads(cache_file.read_text())
    assert "openai/gpt-4o-mini" in saved
    assert not any("unknown" in k for k in saved)
