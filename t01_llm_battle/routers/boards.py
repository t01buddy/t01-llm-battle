"""Boards router — Board CRUD with nested topic management (FR-24, FR-25, FR-26).

GET    /boards                              — list all boards
POST   /boards                             — create a board
GET    /boards/{id}                        — get one board (with topics)
PUT    /boards/{id}                        — update board fields
DELETE /boards/{id}                        — delete board (system: 403)
GET    /boards/{id}/topics                 — list topics
POST   /boards/{id}/topics                 — create topic
PUT    /boards/{id}/topics/{topic_id}      — update topic
DELETE /boards/{id}/topics/{topic_id}      — delete topic
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
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
