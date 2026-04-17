import pytest
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
