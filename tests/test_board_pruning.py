"""Tests for board run history pruning."""
from __future__ import annotations

import uuid

import pytest

from t01_llm_battle.board_engine import _prune_history
from t01_llm_battle.db import get_db


async def _insert_run(db, board_id: str, started_at: str) -> str:
    run_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO board_run (id, board_id, status, started_at) VALUES (?, ?, 'complete', ?)",
        (run_id, board_id, started_at),
    )
    await db.commit()
    return run_id


@pytest.mark.asyncio
async def test_prune_keeps_max_history(db_path):
    from t01_llm_battle.db import get_db as _get_db
    async with _get_db(db_path) as db:
        board_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO board (id, name, description, source_filter, fighter_ids,
               max_news_per_run, max_history, is_active, is_system,
               template_id, publish_config, created_at, updated_at)
               VALUES (?, 'Prune Test', '', '[]', '[]', 20, 3, 1, 0, NULL, '{}', '2024-01-01', '2024-01-01')""",
            (board_id,),
        )
        await db.commit()
        # Insert 5 runs
        run_ids = []
        for i in range(5):
            rid = await _insert_run(db, board_id, f"2024-01-0{i+1}T00:00:00")
            run_ids.append(rid)

    await _prune_history(board_id, max_history=3, db_path=db_path)

    async with _get_db(db_path) as db:
        cur = await db.execute(
            "SELECT id FROM board_run WHERE board_id = ? ORDER BY started_at DESC",
            (board_id,),
        )
        remaining = [r["id"] for r in await cur.fetchall()]

    assert len(remaining) == 3
    # Most recent 3 kept
    assert run_ids[-1] in remaining
    assert run_ids[-2] in remaining
    assert run_ids[-3] in remaining
    # Oldest 2 deleted
    assert run_ids[0] not in remaining
    assert run_ids[1] not in remaining


@pytest.mark.asyncio
async def test_prune_noop_when_within_limit(db_path):
    from t01_llm_battle.db import get_db as _get_db
    async with _get_db(db_path) as db:
        board_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO board (id, name, description, source_filter, fighter_ids,
               max_news_per_run, max_history, is_active, is_system,
               template_id, publish_config, created_at, updated_at)
               VALUES (?, 'Prune Noop', '', '[]', '[]', 20, 10, 1, 0, NULL, '{}', '2024-01-01', '2024-01-01')""",
            (board_id,),
        )
        await db.commit()
        run_ids = []
        for i in range(3):
            rid = await _insert_run(db, board_id, f"2024-01-0{i+1}T00:00:00")
            run_ids.append(rid)

    await _prune_history(board_id, max_history=10, db_path=db_path)

    async with _get_db(db_path) as db:
        cur = await db.execute(
            "SELECT id FROM board_run WHERE board_id = ?", (board_id,)
        )
        remaining = [r["id"] for r in await cur.fetchall()]

    assert len(remaining) == 3
