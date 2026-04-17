"""Tests for the /runs router."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from t01_llm_battle.db import get_db


@pytest.mark.asyncio
async def test_get_run_status_not_found(client):
    """GET /runs/<nonexistent>/status should return 404."""
    resp = await client.get(f"/runs/{uuid.uuid4()}/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_status_returns_data(client, db_path):
    """Insert a battle + run directly, then poll status via the API."""
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Status Battle", "openai", "gpt-4o", "", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "pending", now),
        )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "pending"
    assert isinstance(data["fighter_results"], list)


@pytest.mark.asyncio
async def test_create_run_battle_not_found(client):
    """POST /runs with a nonexistent battle_id should return 404."""
    with patch("t01_llm_battle.engine.start_run_background"):
        resp = await client.post("/runs", json={"battle_id": str(uuid.uuid4())})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_no_fighters(client, db_path):
    """POST /runs for a battle with no fighters should return 422."""
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Empty Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()

    with patch("t01_llm_battle.engine.start_run_background"):
        resp = await client.post("/runs", json={"battle_id": battle_id})
    assert resp.status_code == 422
