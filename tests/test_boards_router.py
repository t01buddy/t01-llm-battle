"""Tests for /boards CRUD API and nested /boards/{id}/topics endpoints."""
from contextlib import asynccontextmanager

import pytest
import t01_llm_battle.db as db_module
import t01_llm_battle.routers.boards as boards_module
from httpx import ASGITransport, AsyncClient
from t01_llm_battle.db import get_db, init_db
from t01_llm_battle.server import create_app


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test_boards.db")
    await init_db(path)
    return path


@pytest.fixture
async def client(db_path, monkeypatch):
    _db_path = db_path

    @asynccontextmanager
    async def _get_db_override(path=None):
        async with get_db(_db_path) as db:
            yield db

    monkeypatch.setattr(db_module, "DB_PATH", __import__("pathlib").Path(_db_path))
    monkeypatch.setattr(boards_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_boards_includes_system_board(client):
    resp = await client.get("/boards")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    sys_board = next((b for b in data if b["is_system"]), None)
    assert sys_board is not None
    assert sys_board["name"] == "Tech News Daily"
    assert len(sys_board["topics"]) == 3


@pytest.mark.asyncio
async def test_create_and_get_board(client):
    payload = {
        "name": "My Board",
        "description": "Test board",
        "source_filter": ["tech"],
        "fighter_ids": [],
        "normalizer_provider": "openai",
        "normalizer_model": "gpt-4o-mini",
        "normalizer_instructions": "Summarize.",
        "schedule_cron": "0 9 * * *",
        "max_news_per_run": 10,
        "max_history": 50,
        "is_active": True,
        "publish_config": {},
    }
    resp = await client.post("/boards", json=payload)
    assert resp.status_code == 201
    board = resp.json()
    assert board["name"] == "My Board"
    assert board["normalizer_provider"] == "openai"
    assert board["is_system"] is False

    resp2 = await client.get(f"/boards/{board['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == board["id"]


@pytest.mark.asyncio
async def test_update_board(client):
    resp = await client.post("/boards", json={"name": "Update Me"})
    assert resp.status_code == 201
    board_id = resp.json()["id"]

    resp = await client.put(f"/boards/{board_id}", json={"name": "Updated", "is_active": False})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "Updated"
    assert updated["is_active"] is False


@pytest.mark.asyncio
async def test_delete_board(client):
    resp = await client.post("/boards", json={"name": "Delete Me"})
    assert resp.status_code == 201
    board_id = resp.json()["id"]

    resp = await client.delete(f"/boards/{board_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/boards/{board_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_system_board_cannot_be_deleted(client):
    resp = await client.get("/boards")
    sys_board = next(b for b in resp.json() if b["is_system"])
    resp = await client.delete(f"/boards/{sys_board['id']}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_system_board_cannot_be_updated(client):
    resp = await client.get("/boards")
    sys_board = next(b for b in resp.json() if b["is_system"])
    resp = await client.put(f"/boards/{sys_board['id']}", json={"name": "Hacked"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_board_not_found(client):
    resp = await client.get("/boards/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_topic_crud(client):
    resp = await client.post("/boards", json={"name": "Topic Board"})
    board_id = resp.json()["id"]

    # Create topic
    resp = await client.post(f"/boards/{board_id}/topics", json={
        "name": "AI News", "description": "All about AI", "tag_filter": ["ai"], "position": 0
    })
    assert resp.status_code == 201
    topic = resp.json()
    assert topic["name"] == "AI News"
    assert topic["tag_filter"] == ["ai"]
    topic_id = topic["id"]

    # List topics
    resp = await client.get(f"/boards/{board_id}/topics")
    assert resp.status_code == 200
    assert any(t["id"] == topic_id for t in resp.json())

    # Update topic
    resp = await client.put(f"/boards/{board_id}/topics/{topic_id}", json={"name": "ML News"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "ML News"

    # Delete topic
    resp = await client.delete(f"/boards/{board_id}/topics/{topic_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/boards/{board_id}/topics")
    assert all(t["id"] != topic_id for t in resp.json())


@pytest.mark.asyncio
async def test_system_board_has_3_default_topics(client):
    resp = await client.get("/boards")
    sys_board = next(b for b in resp.json() if b["is_system"])
    topic_names = [t["name"] for t in sys_board["topics"]]
    assert "AI & ML" in topic_names
    assert "Startups & VC" in topic_names
    assert "Open Source" in topic_names


@pytest.mark.asyncio
async def test_topic_not_found(client):
    resp = await client.post("/boards", json={"name": "Board X"})
    board_id = resp.json()["id"]
    resp = await client.delete(f"/boards/{board_id}/topics/nonexistent")
    assert resp.status_code == 404
