"""Tests for battle-related DB operations and health check endpoint.

Note: There is no dedicated /battles REST router in the current server;
battles are created directly in the DB. These tests verify DB-level CRUD
and the /healthz endpoint that confirms the server is up.
"""
import uuid
from datetime import datetime, timezone

import pytest
from t01_llm_battle.db import get_db


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_battle_in_db(db_path):
    """Insert a battle row directly and verify it is retrievable."""
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Test Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT id, name FROM battle WHERE id = ?", (battle_id,))
        row = await cursor.fetchone()

    assert row is not None
    assert row["id"] == battle_id
    assert row["name"] == "Test Battle"


@pytest.mark.asyncio
async def test_list_battles_in_db(db_path):
    """Insert two battles and verify both are returned."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        for name in ("Alpha", "Beta"):
            await db.execute(
                "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), name, "openai", "gpt-4o", "", now),
            )
        await db.commit()

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT name FROM battle ORDER BY name")
        names = [row[0] for row in await cursor.fetchall()]

    assert "Alpha" in names
    assert "Beta" in names


@pytest.mark.asyncio
async def test_delete_battle_in_db(db_path):
    """Delete a battle row and verify it is gone."""
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "To Delete", "openai", "gpt-4o", "", now),
        )
        await db.commit()

    async with get_db(db_path) as db:
        await db.execute("DELETE FROM battle WHERE id = ?", (battle_id,))
        await db.commit()

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT id FROM battle WHERE id = ?", (battle_id,))
        row = await cursor.fetchone()

    assert row is None
