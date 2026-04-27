"""Tests for /news-sources CRUD router."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import t01_llm_battle.db as db_module
import t01_llm_battle.routers.news_sources as news_sources_module
from httpx import AsyncClient, ASGITransport
from t01_llm_battle.db import get_db, init_db
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

    monkeypatch.setattr(db_module, "DB_PATH", _db_path)
    monkeypatch.setattr(news_sources_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# System sources seeded on init
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_sources_seeded_on_init(client):
    resp = await client.get("/news-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    names = {s["name"] for s in data}
    assert names == {"HN Top", "TechCrunch RSS", "AI News (Serper)", "GitHub Trending"}
    for src in data:
        assert src["is_system"] is True


# ---------------------------------------------------------------------------
# CRUD for user sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_news_source(client):
    resp = await client.post("/news-sources", json={
        "name": "My Blog RSS",
        "source_type": "rss",
        "config": {"url": "https://example.com/feed"},
        "tags": ["blog", "personal"],
        "priority": 3,
        "max_items": 10,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Blog RSS"
    assert data["source_type"] == "rss"
    assert data["tags"] == ["blog", "personal"]
    assert data["priority"] == 3
    assert data["max_items"] == 10
    assert data["is_system"] is False
    assert data["status"] == "active"
    assert data["config"] == {"url": "https://example.com/feed"}


@pytest.mark.asyncio
async def test_get_news_source(client):
    create_resp = await client.post("/news-sources", json={
        "name": "Test Source",
        "source_type": "url",
    })
    src_id = create_resp.json()["id"]

    resp = await client.get(f"/news-sources/{src_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == src_id
    assert resp.json()["name"] == "Test Source"


@pytest.mark.asyncio
async def test_get_nonexistent_source_returns_404(client):
    resp = await client.get(f"/news-sources/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_news_source(client):
    create_resp = await client.post("/news-sources", json={
        "name": "Old Name",
        "source_type": "rss",
        "priority": 5,
        "max_items": 10,
        "tags": [],
    })
    src_id = create_resp.json()["id"]

    resp = await client.put(f"/news-sources/{src_id}", json={
        "name": "New Name",
        "priority": 9,
        "tags": ["updated"],
        "fighter_affinity": "fighter-abc",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["priority"] == 9
    assert data["tags"] == ["updated"]
    assert data["fighter_affinity"] == "fighter-abc"
    # unchanged fields preserved
    assert data["source_type"] == "rss"
    assert data["max_items"] == 10


@pytest.mark.asyncio
async def test_delete_user_source(client):
    create_resp = await client.post("/news-sources", json={
        "name": "To Delete",
        "source_type": "url",
    })
    src_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/news-sources/{src_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/news-sources/{src_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_system_source_returns_403(client):
    """System sources cannot be deleted."""
    list_resp = await client.get("/news-sources")
    system_src = next(s for s in list_resp.json() if s["is_system"])

    resp = await client.delete(f"/news-sources/{system_src['id']}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Configurable fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tags_priority_max_items_fighter_affinity_configurable(client):
    resp = await client.post("/news-sources", json={
        "name": "Configurable Source",
        "source_type": "api",
        "tags": ["ai", "ml"],
        "priority": 8,
        "max_items": 50,
        "fighter_affinity": "my-fighter",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["tags"] == ["ai", "ml"]
    assert data["priority"] == 8
    assert data["max_items"] == 50
    assert data["fighter_affinity"] == "my-fighter"


@pytest.mark.asyncio
async def test_update_status_to_disabled(client):
    """System sources can be disabled (not deleted)."""
    list_resp = await client.get("/news-sources")
    system_src = next(s for s in list_resp.json() if s["is_system"])

    resp = await client.put(f"/news-sources/{system_src['id']}", json={"status": "disabled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"
