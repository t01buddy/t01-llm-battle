"""News Sources router — global source pool for news boards (FR-21, FR-30).

GET    /news-sources               — list all sources
POST   /news-sources               — create a source
GET    /news-sources/{id}          — get one source
PUT    /news-sources/{id}          — update a source
DELETE /news-sources/{id}          — delete (system sources: 404)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db

router = APIRouter(prefix="/news-sources", tags=["news-sources"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NewsSourceCreate(BaseModel):
    name: str
    source_type: str
    config: dict[str, Any] = {}
    tags: list[str] = []
    priority: int = 5
    max_items: int = 20
    fighter_affinity: str | None = None


class NewsSourceUpdate(BaseModel):
    name: str | None = None
    source_type: str | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None
    priority: int | None = None
    max_items: int | None = None
    fighter_affinity: str | None = None
    status: str | None = None


class NewsSourceOut(BaseModel):
    id: str
    name: str
    source_type: str
    config: dict[str, Any]
    tags: list[str]
    priority: int
    max_items: int
    fighter_affinity: str | None
    is_system: bool
    status: str
    last_error: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_out(row) -> NewsSourceOut:
    return NewsSourceOut(
        id=row["id"],
        name=row["name"],
        source_type=row["source_type"],
        config=json.loads(row["config"] or "{}"),
        tags=json.loads(row["tags"] or "[]"),
        priority=row["priority"],
        max_items=row["max_items"],
        fighter_affinity=row["fighter_affinity"],
        is_system=bool(row["is_system"]),
        status=row["status"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_or_404(source_id: str):
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM news_source WHERE id = ?", (source_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="News source not found")
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[NewsSourceOut])
async def list_news_sources():
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM news_source ORDER BY priority DESC, name ASC"
        )
        rows = await cur.fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=NewsSourceOut, status_code=201)
async def create_news_source(body: NewsSourceCreate):
    now = datetime.now(timezone.utc).isoformat()
    src_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """INSERT INTO news_source
               (id, name, source_type, config, tags, priority, max_items,
                fighter_affinity, is_system, status, last_error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', NULL, ?, ?)""",
            (src_id, body.name, body.source_type,
             json.dumps(body.config), json.dumps(body.tags),
             body.priority, body.max_items, body.fighter_affinity, now, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM news_source WHERE id = ?", (src_id,))
        row = await cur.fetchone()
    return _row_to_out(row)


@router.get("/{source_id}", response_model=NewsSourceOut)
async def get_news_source(source_id: str):
    row = await _get_or_404(source_id)
    return _row_to_out(row)


@router.put("/{source_id}", response_model=NewsSourceOut)
async def update_news_source(source_id: str, body: NewsSourceUpdate):
    row = await _get_or_404(source_id)
    now = datetime.now(timezone.utc).isoformat()

    name = body.name if body.name is not None else row["name"]
    source_type = body.source_type if body.source_type is not None else row["source_type"]
    config = json.dumps(body.config) if body.config is not None else row["config"]
    tags = json.dumps(body.tags) if body.tags is not None else row["tags"]
    priority = body.priority if body.priority is not None else row["priority"]
    max_items = body.max_items if body.max_items is not None else row["max_items"]
    fighter_affinity = body.fighter_affinity if body.fighter_affinity is not None else row["fighter_affinity"]
    status = body.status if body.status is not None else row["status"]

    async with get_db() as db:
        await db.execute(
            """UPDATE news_source SET name=?, source_type=?, config=?, tags=?,
               priority=?, max_items=?, fighter_affinity=?, status=?, updated_at=?
               WHERE id=?""",
            (name, source_type, config, tags, priority, max_items,
             fighter_affinity, status, now, source_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM news_source WHERE id = ?", (source_id,))
        row = await cur.fetchone()
    return _row_to_out(row)


@router.delete("/{source_id}", status_code=204, response_model=None)
async def delete_news_source(source_id: str):
    row = await _get_or_404(source_id)
    if row["is_system"]:
        raise HTTPException(
            status_code=403,
            detail="System sources cannot be deleted. Set status='disabled' to deactivate.",
        )
    async with get_db() as db:
        await db.execute("DELETE FROM news_source WHERE id = ?", (source_id,))
        await db.commit()
