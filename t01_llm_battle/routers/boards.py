"""Boards router — Board CRUD with nested topic management and items (FR-24, FR-25, FR-26, FR-31).

GET    /boards                              — list all boards
POST   /boards                             — create a board
GET    /boards/{id}                        — get one board (with topics)
PUT    /boards/{id}                        — update board fields
DELETE /boards/{id}                        — delete board (system: 403)
GET    /boards/{id}/topics                 — list topics
POST   /boards/{id}/topics                 — create topic
PUT    /boards/{id}/topics/{topic_id}      — update topic
DELETE /boards/{id}/topics/{topic_id}      — delete topic
GET    /boards/{id}/items                  — paginated items, filterable by topic/tags
GET    /boards/{id}/items/tags             — unique tags within a topic
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import get_db

router = APIRouter(prefix="/boards", tags=["boards"])


class BoardTopicOut(BaseModel):
    id: str
    board_id: str
    name: str
    description: str
    tag_filter: list[str]
    position: int
    created_at: str
    updated_at: str


class BoardOut(BaseModel):
    id: str
    name: str
    description: str
    source_filter: list[str]
    fighter_ids: list[str]
    normalizer_provider: str | None
    normalizer_model: str | None
    normalizer_instructions: str | None
    schedule_cron: str | None
    max_news_per_run: int
    max_history: int
    is_active: bool
    is_system: bool
    template_id: str | None
    publish_config: dict[str, Any]
    topics: list[BoardTopicOut]
    created_at: str
    updated_at: str


class BoardCreate(BaseModel):
    name: str
    description: str = ""
    source_filter: list[str] = []
    fighter_ids: list[str] = []
    normalizer_provider: str | None = None
    normalizer_model: str | None = None
    normalizer_instructions: str | None = None
    schedule_cron: str | None = None
    max_news_per_run: int = 20
    max_history: int = 100
    is_active: bool = True
    template_id: str | None = None
    publish_config: dict[str, Any] = {}


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_filter: list[str] | None = None
    fighter_ids: list[str] | None = None
    normalizer_provider: str | None = None
    normalizer_model: str | None = None
    normalizer_instructions: str | None = None
    schedule_cron: str | None = None
    max_news_per_run: int | None = None
    max_history: int | None = None
    is_active: bool | None = None
    publish_config: dict[str, Any] | None = None


class TopicCreate(BaseModel):
    name: str
    description: str = ""
    tag_filter: list[str] = []
    position: int = 0


class TopicUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tag_filter: list[str] | None = None
    position: int | None = None


import json as _json


def _row_to_topic(row) -> BoardTopicOut:
    return BoardTopicOut(
        id=row["id"],
        board_id=row["board_id"],
        name=row["name"],
        description=row["description"] or "",
        tag_filter=_json.loads(row["tag_filter"] or "[]"),
        position=row["position"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_topics(db, board_id: str) -> list[BoardTopicOut]:
    cur = await db.execute(
        "SELECT * FROM board_topic WHERE board_id = ? ORDER BY position ASC", (board_id,)
    )
    return [_row_to_topic(r) for r in await cur.fetchall()]


def _row_to_board(row, topics: list[BoardTopicOut]) -> BoardOut:
    return BoardOut(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        source_filter=_json.loads(row["source_filter"] or "[]"),
        fighter_ids=_json.loads(row["fighter_ids"] or "[]"),
        normalizer_provider=row["normalizer_provider"],
        normalizer_model=row["normalizer_model"],
        normalizer_instructions=row["normalizer_instructions"],
        schedule_cron=row["schedule_cron"],
        max_news_per_run=row["max_news_per_run"],
        max_history=row["max_history"],
        is_active=bool(row["is_active"]),
        is_system=bool(row["is_system"]),
        template_id=row["template_id"],
        publish_config=_json.loads(row["publish_config"] or "{}"),
        topics=topics,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_board_or_404(board_id: str):
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM board WHERE id = ?", (board_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Board not found")
        topics = await _get_topics(db, board_id)
    return row, topics


@router.get("", response_model=list[BoardOut])
async def list_boards():
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM board ORDER BY is_system DESC, name ASC")
        rows = await cur.fetchall()
        result = []
        for row in rows:
            topics = await _get_topics(db, row["id"])
            result.append(_row_to_board(row, topics))
    return result


@router.post("", response_model=BoardOut, status_code=201)
async def create_board(body: BoardCreate):
    now = datetime.now(timezone.utc).isoformat()
    board_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """INSERT INTO board (id, name, description, source_filter, fighter_ids,
               normalizer_provider, normalizer_model, normalizer_instructions,
               schedule_cron, max_news_per_run, max_history, is_active, is_system,
               template_id, publish_config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
            (board_id, body.name, body.description,
             _json.dumps(body.source_filter), _json.dumps(body.fighter_ids),
             body.normalizer_provider, body.normalizer_model, body.normalizer_instructions,
             body.schedule_cron, body.max_news_per_run, body.max_history,
             int(body.is_active), body.template_id, _json.dumps(body.publish_config), now, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM board WHERE id = ?", (board_id,))
        row = await cur.fetchone()
        topics = await _get_topics(db, board_id)
    return _row_to_board(row, topics)


@router.get("/{board_id}", response_model=BoardOut)
async def get_board(board_id: str):
    row, topics = await _get_board_or_404(board_id)
    return _row_to_board(row, topics)


@router.put("/{board_id}", response_model=BoardOut)
async def update_board(board_id: str, body: BoardUpdate):
    row, _ = await _get_board_or_404(board_id)
    if bool(row["is_system"]):
        raise HTTPException(status_code=403, detail="System boards cannot be modified")
    now = datetime.now(timezone.utc).isoformat()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM board WHERE id = ?", (board_id,))
            row = await cur.fetchone()
            topics = await _get_topics(db, board_id)
        return _row_to_board(row, topics)
    # Serialize list/dict fields
    for field in ("source_filter", "fighter_ids", "publish_config"):
        if field in updates:
            updates[field] = _json.dumps(updates[field])
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [now, board_id]
    async with get_db() as db:
        await db.execute(f"UPDATE board SET {set_clause}, updated_at = ? WHERE id = ?", values)
        await db.commit()
        cur = await db.execute("SELECT * FROM board WHERE id = ?", (board_id,))
        row = await cur.fetchone()
        topics = await _get_topics(db, board_id)
    # Notify scheduler if schedule-relevant fields changed
    if "is_active" in updates or "schedule_cron" in updates:
        from .. import scheduler as board_scheduler
        board_scheduler.sync_board(
            board_id,
            bool(row["is_active"]),
            row["schedule_cron"],
        )
    return _row_to_board(row, topics)


@router.delete("/{board_id}", status_code=204)
async def delete_board(board_id: str):
    row, _ = await _get_board_or_404(board_id)
    if bool(row["is_system"]):
        raise HTTPException(status_code=403, detail="System boards cannot be deleted")
    async with get_db() as db:
        await db.execute("DELETE FROM board_topic WHERE board_id = ?", (board_id,))
        await db.execute("DELETE FROM board WHERE id = ?", (board_id,))
        await db.commit()


# --- Topic sub-routes ---

@router.get("/{board_id}/topics", response_model=list[BoardTopicOut])
async def list_topics(board_id: str):
    await _get_board_or_404(board_id)
    async with get_db() as db:
        topics = await _get_topics(db, board_id)
    return topics


@router.post("/{board_id}/topics", response_model=BoardTopicOut, status_code=201)
async def create_topic(board_id: str, body: TopicCreate):
    await _get_board_or_404(board_id)
    now = datetime.now(timezone.utc).isoformat()
    topic_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """INSERT INTO board_topic (id, board_id, name, description, tag_filter, position, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic_id, board_id, body.name, body.description,
             _json.dumps(body.tag_filter), body.position, now, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM board_topic WHERE id = ?", (topic_id,))
        row = await cur.fetchone()
    return _row_to_topic(row)


@router.put("/{board_id}/topics/{topic_id}", response_model=BoardTopicOut)
async def update_topic(board_id: str, topic_id: str, body: TopicUpdate):
    await _get_board_or_404(board_id)
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM board_topic WHERE id = ? AND board_id = ?", (topic_id, board_id)
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        updates = body.model_dump(exclude_none=True)
        if not updates:
            return _row_to_topic(row)
        if "tag_filter" in updates:
            updates["tag_filter"] = _json.dumps(updates["tag_filter"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [now, topic_id]
        await db.execute(f"UPDATE board_topic SET {set_clause}, updated_at = ? WHERE id = ?", values)
        await db.commit()
        cur = await db.execute("SELECT * FROM board_topic WHERE id = ?", (topic_id,))
        row = await cur.fetchone()
    return _row_to_topic(row)


@router.delete("/{board_id}/topics/{topic_id}", status_code=204)
async def delete_topic(board_id: str, topic_id: str):
    await _get_board_or_404(board_id)
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id FROM board_topic WHERE id = ? AND board_id = ?", (topic_id, board_id)
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        await db.execute("DELETE FROM board_topic WHERE id = ?", (topic_id,))
        await db.commit()


# --- Board Runs ---

class BoardRunOut(BaseModel):
    id: str
    board_id: str
    status: str
    items_fetched: int
    items_processed: int
    cost_usd: float | None
    started_at: str
    finished_at: str | None


# --- Items sub-routes (FR-31) ---

class BoardNewsItemOut(BaseModel):
    id: str
    run_id: str
    board_id: str
    title: str
    summary: str
    source_url: str
    source_name: str
    fighter_name: str
    category: str
    tags: list[str]
    relevance_score: float
    published_at: str | None
    created_at: str


class BoardItemsPage(BaseModel):
    items: list[BoardNewsItemOut]
    total: int
    page: int
    page_size: int
    pages: int


ItemsPage = BoardItemsPage  # backwards-compat alias


def _row_to_run(row) -> BoardRunOut:
    return BoardRunOut(
        id=row["id"],
        board_id=row["board_id"],
        status=row["status"],
        items_fetched=row["items_fetched"],
        items_processed=row["items_processed"],
        cost_usd=row["cost_usd"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )



def _row_to_news_item(row) -> BoardNewsItemOut:
    return BoardNewsItemOut(
        id=row["id"],
        run_id=row["run_id"],
        board_id=row["board_id"],
        title=row["title"],
        summary=row["summary"],
        source_url=row["source_url"],
        source_name=row["source_name"],
        fighter_name=row["fighter_name"],
        category=row["category"],
        tags=_json.loads(row["tags"] or "[]"),
        relevance_score=row["relevance_score"],
        published_at=row["published_at"],
        created_at=row["created_at"],
    )


@router.post("/{board_id}/run", response_model=BoardRunOut, status_code=202)
async def trigger_board_run(board_id: str):
    """Manually trigger a board execution run."""
    import asyncio
    from ..board_engine import execute_board_run
    row, _ = await _get_board_or_404(board_id)
    # Fire and forget — run in background
    asyncio.create_task(execute_board_run(board_id))
    # Return a pending run record
    from ..db import get_db as _get_db
    async with _get_db() as db:
        cur = await db.execute(
            "SELECT * FROM board_run WHERE board_id = ? ORDER BY started_at DESC LIMIT 1",
            (board_id,),
        )
        run_row = await cur.fetchone()
    if run_row:
        return _row_to_run(run_row)
    # Run hasn't been created yet (race) — return minimal response
    return BoardRunOut(
        id="pending",
        board_id=board_id,
        status="pending",
        items_fetched=0,
        items_processed=0,
        cost_usd=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
    )


@router.post("/{board_id}/publish", status_code=200)
async def publish_board(board_id: str):
    """Manually trigger a publish for this board using its publish_config."""
    from ..publisher import publish_board as _publish_board
    row, _ = await _get_board_or_404(board_id)
    publish_config = _json.loads(row["publish_config"] or "{}")
    if not publish_config.get("target"):
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=422, detail="No publish target configured for this board")

    # Fetch latest items
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM board_news_item WHERE board_id = ? ORDER BY relevance_score DESC LIMIT 100",
            (board_id,),
        )
        rows = await db.fetchall() if False else await cur.fetchall()
    items = [dict(r) for r in rows]
    for item in items:
        item["tags"] = _json.loads(item.get("tags") or "[]")

    board_dict = dict(row)
    result = await _publish_board(board_dict, items, publish_config)
    return result


@router.get("/{board_id}/runs", response_model=list[BoardRunOut])
async def list_board_runs(board_id: str):
    await _get_board_or_404(board_id)
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM board_run WHERE board_id = ? ORDER BY started_at DESC LIMIT 20",
            (board_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_run(r) for r in rows]


@router.get("/{board_id}/runs/{run_id}", response_model=BoardRunOut)
async def get_board_run(board_id: str, run_id: str):
    await _get_board_or_404(board_id)
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM board_run WHERE id = ? AND board_id = ?", (run_id, board_id)
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
    return _row_to_run(row)


@router.get("/{board_id}/items/tags", response_model=list[str])
async def list_board_item_tags(board_id: str, topic_id: str | None = None):
    """Return unique tags across all items in this board, optionally filtered by topic."""
    await _get_board_or_404(board_id)
    topic_tag_filter: list[str] = []
    if topic_id:
        async with get_db() as db:
            cur = await db.execute(
                "SELECT tag_filter FROM board_topic WHERE id = ? AND board_id = ?",
                (topic_id, board_id),
            )
            row = await cur.fetchone()
        if row:
            topic_tag_filter = _json.loads(row["tag_filter"] or "[]")
    async with get_db() as db:
        cur = await db.execute(
            "SELECT tags FROM board_news_item WHERE board_id = ?", (board_id,)
        )
        rows = await cur.fetchall()
    seen: set[str] = set()
    for row in rows:
        item_tags = _json.loads(row["tags"] or "[]")
        if topic_tag_filter and not any(t in item_tags for t in topic_tag_filter):
            continue
        for tag in item_tags:
            seen.add(tag)
    return sorted(seen)


@router.get("/{board_id}/items", response_model=BoardItemsPage)
async def list_board_items(
    board_id: str,
    topic_id: str | None = None,
    tags: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List news items for a board, optionally filtered by topic or tags."""
    await _get_board_or_404(board_id)
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    async with get_db() as db:
        # Build WHERE clause
        wheres = ["board_id = ?"]
        params: list = [board_id]

        if topic_id:
            cur = await db.execute(
                "SELECT tag_filter FROM board_topic WHERE id = ? AND board_id = ?",
                (topic_id, board_id),
            )
            trow = await cur.fetchone()
            if trow:
                topic_tags = _json.loads(trow["tag_filter"] or "[]")
                if topic_tags:
                    tag_conditions = " OR ".join(["tags LIKE ?" for _ in topic_tags])
                    wheres.append(f"({tag_conditions})")
                    params.extend([f'%"{t}"%' for t in topic_tags])

        if tag_list:
            tag_conditions = " OR ".join(["tags LIKE ?" for _ in tag_list])
            wheres.append(f"({tag_conditions})")
            params.extend([f'%"{t}"%' for t in tag_list])

        where_sql = " AND ".join(wheres)

        # Count
        cur = await db.execute(f"SELECT COUNT(*) FROM board_news_item WHERE {where_sql}", params)
        total = (await cur.fetchone())[0]

        # Page
        offset = (page - 1) * page_size
        cur = await db.execute(
            f"SELECT * FROM board_news_item WHERE {where_sql} ORDER BY relevance_score DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        rows = await cur.fetchall()

    pages = max(1, (total + page_size - 1) // page_size)
    return BoardItemsPage(
        items=[_row_to_news_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
