"""Board scheduler — APScheduler-backed cron scheduler for board execution (FR-27)."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .board_engine import execute_board_run
from .db import DB_PATH

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _run_board(board_id: str, db_path: str) -> None:
    try:
        run_id = await execute_board_run(board_id, db_path)
        log.info("scheduler: board %s run completed: %s", board_id, run_id)
    except Exception:
        log.exception("scheduler: board %s run failed", board_id)


def _job_id(board_id: str) -> str:
    return f"board-{board_id}"


def start(db_path: str = DB_PATH) -> AsyncIOScheduler:
    """Start the scheduler (call on FastAPI startup)."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    return scheduler


def stop() -> None:
    """Stop the scheduler gracefully (call on FastAPI shutdown)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


async def load_boards(db_path: str = DB_PATH) -> None:
    """Register cron jobs for all active boards with a schedule_cron."""
    from .db import get_db
    scheduler = get_scheduler()
    async with get_db(db_path) as db:
        cur = await db.execute(
            "SELECT id, schedule_cron FROM board WHERE is_active = 1 AND schedule_cron IS NOT NULL"
        )
        rows = await cur.fetchall()
    for row in rows:
        _register(row["id"], row["schedule_cron"], db_path)
    log.info("scheduler: loaded %d board job(s)", len(rows))


def _register(board_id: str, cron_expr: str, db_path: str = DB_PATH) -> None:
    scheduler = get_scheduler()
    job_id = _job_id(board_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            log.warning("scheduler: invalid cron '%s' for board %s — skipped", cron_expr, board_id)
            return
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
        )
        scheduler.add_job(
            _run_board,
            trigger=trigger,
            args=[board_id, db_path],
            id=job_id,
            replace_existing=True,
        )
        log.info("scheduler: registered board %s with cron '%s'", board_id, cron_expr)
    except Exception:
        log.exception("scheduler: failed to register board %s", board_id)


def _deregister(board_id: str) -> None:
    scheduler = get_scheduler()
    job_id = _job_id(board_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        log.info("scheduler: deregistered board %s", board_id)


def sync_board(board_id: str, is_active: bool, schedule_cron: str | None, db_path: str = DB_PATH) -> None:
    """Called by update_board to keep scheduler in sync with DB changes."""
    if is_active and schedule_cron:
        _register(board_id, schedule_cron, db_path)
    else:
        _deregister(board_id)
