"""Tests for DELETE /battles/{battle_id}/sources/{source_id}."""
import io
import uuid
from datetime import datetime, timezone

import pytest
from t01_llm_battle.db import get_db


async def _create_battle(db_path: str) -> str:
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Delete Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()
    return battle_id


@pytest.mark.asyncio
async def test_delete_source_returns_204(client, db_path):
    """Delete an existing source returns 204."""
    battle_id = await _create_battle(db_path)

    upload = await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert upload.status_code == 201
    source_id = upload.json()["sources"][0]["id"]

    resp = await client.delete(f"/battles/{battle_id}/sources/{source_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_source_removes_from_db(client, db_path):
    """After deletion, listing sources no longer returns the deleted item."""
    battle_id = await _create_battle(db_path)

    upload = await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("y.txt", io.BytesIO(b"bye"), "text/plain")},
    )
    source_id = upload.json()["sources"][0]["id"]

    await client.delete(f"/battles/{battle_id}/sources/{source_id}")

    list_resp = await client.get(f"/battles/{battle_id}/sources")
    ids = [s["id"] for s in list_resp.json()["sources"]]
    assert source_id not in ids


@pytest.mark.asyncio
async def test_delete_nonexistent_source_returns_404(client, db_path):
    """Deleting a source that doesn't exist returns 404."""
    battle_id = await _create_battle(db_path)
    resp = await client.delete(f"/battles/{battle_id}/sources/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_wrong_battle_returns_404(client, db_path):
    """Deleting a source that belongs to a different battle returns 404."""
    battle_a = await _create_battle(db_path)
    battle_b = await _create_battle(db_path)

    upload = await client.post(
        f"/battles/{battle_a}/sources",
        files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")},
    )
    source_id = upload.json()["sources"][0]["id"]

    resp = await client.delete(f"/battles/{battle_b}/sources/{source_id}")
    assert resp.status_code == 404
