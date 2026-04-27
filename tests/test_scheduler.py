"""Tests for board scheduler (FR-27)."""
from __future__ import annotations

import pytest

from t01_llm_battle.scheduler import (
    _deregister,
    _job_id,
    _register,
    get_scheduler,
    load_boards,
    start,
    stop,
    sync_board,
)


@pytest.fixture(autouse=True)
async def reset_scheduler():
    """Ensure a fresh scheduler for each test (async so event loop is running)."""
    import t01_llm_battle.scheduler as sched_mod
    sched_mod._scheduler = None
    yield
    stop()
    sched_mod._scheduler = None


@pytest.mark.asyncio
async def test_start_creates_running_scheduler():
    s = start()
    assert s.running
    stop()


@pytest.mark.asyncio
async def test_stop_shuts_down_scheduler():
    start()
    stop()
    import t01_llm_battle.scheduler as sched_mod
    assert sched_mod._scheduler is None


@pytest.mark.asyncio
async def test_register_adds_job():
    start()
    _register("board-abc", "0 * * * *")
    assert get_scheduler().get_job(_job_id("board-abc")) is not None


@pytest.mark.asyncio
async def test_register_invalid_cron_skipped():
    start()
    _register("board-bad", "not-a-cron")
    assert get_scheduler().get_job(_job_id("board-bad")) is None


@pytest.mark.asyncio
async def test_deregister_removes_job():
    start()
    _register("board-xyz", "30 6 * * *")
    _deregister("board-xyz")
    assert get_scheduler().get_job(_job_id("board-xyz")) is None


@pytest.mark.asyncio
async def test_sync_board_active_with_cron_registers():
    start()
    sync_board("board-s1", is_active=True, schedule_cron="0 8 * * *")
    assert get_scheduler().get_job(_job_id("board-s1")) is not None


@pytest.mark.asyncio
async def test_sync_board_inactive_deregisters():
    start()
    _register("board-s2", "0 8 * * *")
    sync_board("board-s2", is_active=False, schedule_cron="0 8 * * *")
    assert get_scheduler().get_job(_job_id("board-s2")) is None


@pytest.mark.asyncio
async def test_sync_board_no_cron_deregisters():
    start()
    _register("board-s3", "0 8 * * *")
    sync_board("board-s3", is_active=True, schedule_cron=None)
    assert get_scheduler().get_job(_job_id("board-s3")) is None


@pytest.mark.asyncio
async def test_register_replaces_existing_job():
    start()
    _register("board-rep", "0 6 * * *")
    _register("board-rep", "0 9 * * *")
    # Still only one job
    jobs = [j for j in get_scheduler().get_jobs() if j.id == _job_id("board-rep")]
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_load_boards_registers_active_boards(db_path):
    """load_boards registers active boards with schedule_cron from DB."""
    from t01_llm_battle.db import get_db
    board_id = "test-load-board-1"
    async with get_db(db_path) as db:
        await db.execute(
            """INSERT INTO board (id, name, description, source_filter, fighter_ids,
               schedule_cron, max_news_per_run, max_history, is_active, is_system,
               template_id, publish_config, created_at, updated_at)
               VALUES (?, 'Test', '', '[]', '[]', '0 6 * * *', 20, 10, 1, 0, NULL, '{}', '2024-01-01T00:00:00', '2024-01-01T00:00:00')""",
            (board_id,),
        )
        await db.commit()
    start()
    await load_boards(db_path)
    assert get_scheduler().get_job(_job_id(board_id)) is not None


@pytest.mark.asyncio
async def test_load_boards_skips_inactive(db_path):
    """load_boards does not register inactive boards."""
    from t01_llm_battle.db import get_db
    board_id = "test-load-board-inactive"
    async with get_db(db_path) as db:
        await db.execute(
            """INSERT INTO board (id, name, description, source_filter, fighter_ids,
               schedule_cron, max_news_per_run, max_history, is_active, is_system,
               template_id, publish_config, created_at, updated_at)
               VALUES (?, 'Inactive', '', '[]', '[]', '0 6 * * *', 20, 10, 0, 0, NULL, '{}', '2024-01-01T00:00:00', '2024-01-01T00:00:00')""",
            (board_id,),
        )
        await db.commit()
    start()
    await load_boards(db_path)
    assert get_scheduler().get_job(_job_id(board_id)) is None
