import pytest
import aiosqlite
from t01_llm_battle.db import init_db, get_db


@pytest.mark.asyncio
async def test_init_db_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cursor.fetchall()}
    assert "battle" in tables
    assert "fighter" in tables
    assert "run" in tables


@pytest.mark.asyncio
async def test_foreign_keys_enforced(tmp_path):
    """PRAGMA foreign_keys = ON must be active — inserting a fighter with a bad battle_id must fail."""
    import uuid
    from datetime import datetime, timezone

    db_path = str(tmp_path / "fk_test.db")
    await init_db(db_path)
    raised = False
    async with get_db(db_path) as db:
        try:
            await db.execute(
                "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "nonexistent-battle-id", "TestFighter", 0, 1,
                 datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raised = True
    assert raised, "Expected IntegrityError for FK violation — foreign_keys pragma may be OFF"
