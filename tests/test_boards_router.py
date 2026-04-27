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


# --- Items endpoint tests (FR-31) ---

async def _seed_items(db_path, board_id, items):
    """Insert board_run + board_news_item rows directly for testing."""
    import aiosqlite, uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, started_at) VALUES (?, ?, 'complete', ?)",
            (run_id, board_id, now),
        )
        for item in items:
            import json
            await db.execute(
                """INSERT INTO board_news_item
                   (id, run_id, board_id, title, summary, source_url, source_name, fighter_name,
                    category, tags, relevance_score, published_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), run_id, board_id, item["title"], item.get("summary", ""),
                 item.get("source_url", ""), item.get("source_name", ""), item.get("fighter_name", ""),
                 item.get("category", ""), json.dumps(item.get("tags", [])),
                 item.get("relevance_score", 5.0), item.get("published_at"), now),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_items_empty_board(client):
    resp = await client.post("/boards", json={"name": "Empty Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_items_sorted_by_relevance_score(client, db_path):
    resp = await client.post("/boards", json={"name": "Score Board"})
    board_id = resp.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "Low", "tags": ["tech"], "relevance_score": 2.0},
        {"title": "High", "tags": ["tech"], "relevance_score": 9.0},
        {"title": "Mid", "tags": ["tech"], "relevance_score": 5.0},
    ])
    resp = await client.get(f"/boards/{board_id}/items")
    assert resp.status_code == 200
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == ["High", "Mid", "Low"]


@pytest.mark.asyncio
async def test_items_pagination(client, db_path):
    resp = await client.post("/boards", json={"name": "Paged Board"})
    board_id = resp.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": f"Item {i}", "tags": ["tech"], "relevance_score": float(i)} for i in range(25)
    ])
    resp = await client.get(f"/boards/{board_id}/items?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 25
    assert data["pages"] == 3
    assert len(data["items"]) == 10

    resp2 = await client.get(f"/boards/{board_id}/items?page=3&page_size=10")
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 5


@pytest.mark.asyncio
async def test_items_topic_filter(client, db_path):
    resp = await client.post("/boards", json={"name": "Topic Filter Board"})
    board_id = resp.json()["id"]
    resp_t = await client.post(f"/boards/{board_id}/topics", json={
        "name": "AI Only", "tag_filter": ["ai"], "position": 0
    })
    topic_id = resp_t.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "AI Item", "tags": ["ai", "tech"], "relevance_score": 8.0},
        {"title": "Tech Only", "tags": ["tech"], "relevance_score": 7.0},
    ])
    resp = await client.get(f"/boards/{board_id}/items?topic_id={topic_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "AI Item"


@pytest.mark.asyncio
async def test_items_tag_chip_filter(client, db_path):
    resp = await client.post("/boards", json={"name": "Tag Filter Board"})
    board_id = resp.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "ML Item", "tags": ["ai", "ml"], "relevance_score": 9.0},
        {"title": "AI Only", "tags": ["ai"], "relevance_score": 8.0},
    ])
    resp = await client.get(f"/boards/{board_id}/items?tags=ml")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["title"] == "ML Item"


@pytest.mark.asyncio
async def test_items_all_topic_returns_all(client, db_path):
    resp = await client.post("/boards", json={"name": "All Topic Board"})
    board_id = resp.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "A", "tags": ["ai"], "relevance_score": 5.0},
        {"title": "B", "tags": ["tech"], "relevance_score": 3.0},
    ])
    # No topic_id means "All" — returns everything
    resp = await client.get(f"/boards/{board_id}/items")
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_tags_endpoint_returns_unique_tags(client, db_path):
    resp = await client.post("/boards", json={"name": "Tags Board"})
    board_id = resp.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "X", "tags": ["ai", "tech"], "relevance_score": 7.0},
        {"title": "Y", "tags": ["tech", "ml"], "relevance_score": 5.0},
    ])
    resp = await client.get(f"/boards/{board_id}/items/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert set(tags) == {"ai", "tech", "ml"}


@pytest.mark.asyncio
async def test_tags_endpoint_filtered_by_topic(client, db_path):
    resp = await client.post("/boards", json={"name": "Tags Topic Board"})
    board_id = resp.json()["id"]
    resp_t = await client.post(f"/boards/{board_id}/topics", json={
        "name": "AI Topic", "tag_filter": ["ai"], "position": 0
    })
    topic_id = resp_t.json()["id"]
    await _seed_items(db_path, board_id, [
        {"title": "AI+Tech", "tags": ["ai", "tech"], "relevance_score": 8.0},
        {"title": "Tech Only", "tags": ["tech", "vc"], "relevance_score": 5.0},
    ])
    resp = await client.get(f"/boards/{board_id}/items/tags?topic_id={topic_id}")
    assert resp.status_code == 200
    tags = set(resp.json())
    # Only item with "ai" tag qualifies; its tags are "ai" + "tech"
    assert "ai" in tags
    assert "tech" in tags
    assert "vc" not in tags
