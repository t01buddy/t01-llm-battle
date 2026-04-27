"""Tests for /news-fighters CRUD router (FR-22, FR-33)."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import t01_llm_battle.db as db_module
import t01_llm_battle.routers.news_fighters as news_fighters_module
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
    monkeypatch.setattr(news_fighters_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# System fighters seeded on init
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_fighters_seeded_on_init(client):
    resp = await client.get("/news-fighters")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    names = {f["name"] for f in data}
    assert names == {"General Summarizer", "Tech Deep Dive", "YouTube Analyzer"}
    for f in data:
        assert f["is_system"] is True


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_news_fighter(client, db_path):
    # Create a battle + fighter first
    async with get_db(db_path) as db:
        battle_id = str(uuid.uuid4())
        fighter_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO battle (id, name, created_at) VALUES (?, ?, ?)",
            (battle_id, "Test Battle", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (fighter_id, battle_id, "My Fighter", now),
        )
        await db.commit()

    resp = await client.post("/news-fighters", json={
        "fighter_id": fighter_id,
        "name": "My News Fighter",
        "priority": 6,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My News Fighter"
    assert data["priority"] == 6
    assert data["is_system"] is False
    assert data["fighter_id"] == fighter_id


@pytest.mark.asyncio
async def test_get_news_fighter(client):
    resp = await client.get("/news-fighters")
    nf_id = resp.json()[0]["id"]
    resp2 = await client.get(f"/news-fighters/{nf_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == nf_id


@pytest.mark.asyncio
async def test_update_news_fighter_priority(client):
    resp = await client.get("/news-fighters")
    # Pick a system fighter to update priority
    nf = resp.json()[0]
    nf_id = nf["id"]
    old_priority = nf["priority"]
    new_priority = old_priority + 1

    resp2 = await client.put(f"/news-fighters/{nf_id}", json={"priority": new_priority})
    assert resp2.status_code == 200
    assert resp2.json()["priority"] == new_priority


@pytest.mark.asyncio
async def test_delete_system_fighter_forbidden(client):
    resp = await client.get("/news-fighters")
    sys_nf = next(f for f in resp.json() if f["is_system"])
    resp2 = await client.delete(f"/news-fighters/{sys_nf['id']}")
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_fighter(client, db_path):
    async with get_db(db_path) as db:
        battle_id = str(uuid.uuid4())
        fighter_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO battle (id, name, created_at) VALUES (?, ?, ?)",
            (battle_id, "Test Battle", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (fighter_id, battle_id, "Test Fighter", now),
        )
        await db.commit()

    resp = await client.post("/news-fighters", json={
        "fighter_id": fighter_id,
        "name": "Deletable Fighter",
        "priority": 3,
    })
    nf_id = resp.json()["id"]
    resp2 = await client.delete(f"/news-fighters/{nf_id}")
    assert resp2.status_code == 204

    resp3 = await client.get(f"/news-fighters/{nf_id}")
    assert resp3.status_code == 404


@pytest.mark.asyncio
async def test_promote_from_battle(client, db_path):
    async with get_db(db_path) as db:
        battle_id = str(uuid.uuid4())
        fighter_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO battle (id, name, created_at) VALUES (?, ?, ?)",
            (battle_id, "Promo Battle", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (fighter_id, battle_id, "Battle Fighter", now),
        )
        await db.execute(
            """INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at)
               VALUES (?, ?, 0, 'Summarize this.', 'openai', 'gpt-4o-mini', '{}', ?)""",
            (step_id, fighter_id, now),
        )
        await db.commit()

    resp = await client.post(f"/news-fighters/from-battle/{fighter_id}")
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Battle Fighter"
    assert data["is_system"] is False
    # Verify copied fighter has its own fighter_id (not the original)
    assert data["fighter_id"] != fighter_id


@pytest.mark.asyncio
async def test_fallback_chain_configurable(client, db_path):
    async with get_db(db_path) as db:
        battle_id = str(uuid.uuid4())
        fighter_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO battle (id, name, created_at) VALUES (?, ?, ?)",
            (battle_id, "Fallback Battle", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (fighter_id, battle_id, "Fallback Fighter", now),
        )
        await db.commit()

    # Create primary news fighter
    resp1 = await client.post("/news-fighters", json={
        "fighter_id": fighter_id, "name": "Primary", "priority": 5,
    })
    primary_id = resp1.json()["id"]

    # Create secondary with fallback pointing to primary
    resp2 = await client.post("/news-fighters", json={
        "fighter_id": fighter_id, "name": "Secondary",
        "priority": 3, "fallback_fighter_id": primary_id,
    })
    assert resp2.status_code == 201
    assert resp2.json()["fallback_fighter_id"] == primary_id

    # Update via PUT
    secondary_id = resp2.json()["id"]
    resp3 = await client.put(f"/news-fighters/{secondary_id}", json={"fallback_fighter_id": None})
    assert resp3.json()["fallback_fighter_id"] is None
