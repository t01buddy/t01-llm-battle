import sqlite3
from unittest.mock import patch, AsyncMock

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
async def test_delete_battle_cascades(tmp_path):
    """Deleting a battle must cascade to fighter, battle_source, and run rows."""
    import uuid
    from datetime import datetime, timezone

    db_path = str(tmp_path / "cascade_test.db")
    await init_db(db_path)
    battle_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Cascade Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "F1", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "src", "hello", 1),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "pending", now),
        )
        await db.commit()

    async with get_db(db_path) as db:
        await db.execute("DELETE FROM battle WHERE id = ?", (battle_id,))
        await db.commit()

    async with get_db(db_path) as db:
        for table, col in [("fighter", "battle_id"), ("battle_source", "battle_id"), ("run", "battle_id")]:
            cursor = await db.execute(f"SELECT id FROM {table} WHERE {col} = ?", (battle_id,))
            rows = await cursor.fetchall()
            assert rows == [], f"{table} rows not cascaded after battle delete"


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


@pytest.mark.asyncio
async def test_init_db_migration_already_applied_is_swallowed(tmp_path):
    """'duplicate column name' / 'already exists' OperationalError is silently skipped (FR-15)."""
    import t01_llm_battle.db as db_module

    db_path = str(tmp_path / "test.db")
    # First call applies schema + migrations cleanly
    await init_db(db_path)
    # Second call: every migration hits 'already exists' — must not raise
    await init_db(db_path)


@pytest.mark.asyncio
async def test_init_db_unexpected_migration_error_is_raised(tmp_path):
    """Unexpected OperationalError (not 'already applied') propagates out of init_db (NFR Reliability)."""
    import t01_llm_battle.db as db_module

    db_path = str(tmp_path / "test.db")

    # Inject a migration that triggers a real unexpected error
    bad_sql = "SELECT * FROM nonexistent_table_xyz"
    original = db_module._MIGRATIONS_SQL
    try:
        db_module._MIGRATIONS_SQL = [bad_sql]
        with pytest.raises(sqlite3.OperationalError, match="nonexistent_table_xyz"):
            await init_db(db_path)
    finally:
        db_module._MIGRATIONS_SQL = original
