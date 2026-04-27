"""News Fighters router — promotion from battle fighters (FR-22, FR-33).

GET    /news-fighters                          — list all news fighters
POST   /news-fighters                          — create a news fighter
GET    /news-fighters/{id}                     — get one news fighter
PUT    /news-fighters/{id}                     — update name/priority/fallback
DELETE /news-fighters/{id}                     — delete (system fighters: 403)
POST   /news-fighters/from-battle/{fighter_id} — promote battle fighter
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from ..db import get_db

_UNSET = object()

router = APIRouter(prefix="/news-fighters", tags=["news-fighters"])


class NewsFighterCreate(BaseModel):
    fighter_id: str
    name: str
    fallback_fighter_id: str | None = None
    priority: int = 5


_SENTINEL = "__unset__"


class NewsFighterUpdate(BaseModel):
    name: str | None = None
    # Use sentinel string to distinguish "not provided" from explicit null
    fallback_fighter_id: str | None = _SENTINEL  # type: ignore[assignment]
    priority: int | None = None


class NewsFighterOut(BaseModel):
    id: str
    fighter_id: str
    name: str
    fallback_fighter_id: str | None
    priority: int
    is_system: bool
    created_at: str
    updated_at: str


def _row_to_out(row) -> NewsFighterOut:
    return NewsFighterOut(
        id=row["id"],
        fighter_id=row["fighter_id"],
        name=row["name"],
        fallback_fighter_id=row["fallback_fighter_id"],
        priority=row["priority"],
        is_system=bool(row["is_system"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_or_404(nf_id: str):
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM news_fighter WHERE id = ?", (nf_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="News fighter not found")
    return row


@router.get("", response_model=list[NewsFighterOut])
async def list_news_fighters():
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM news_fighter ORDER BY priority DESC, name ASC"
        )
        rows = await cur.fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=NewsFighterOut, status_code=201)
async def create_news_fighter(body: NewsFighterCreate):
    now = datetime.now(timezone.utc).isoformat()
    nf_id = str(uuid.uuid4())
    async with get_db() as db:
        # Verify fighter exists
        cur = await db.execute("SELECT id FROM fighter WHERE id = ?", (body.fighter_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Battle fighter not found")
        await db.execute(
            """INSERT INTO news_fighter (id, fighter_id, name, fallback_fighter_id, priority, is_system, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (nf_id, body.fighter_id, body.name, body.fallback_fighter_id, body.priority, now, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM news_fighter WHERE id = ?", (nf_id,))
        row = await cur.fetchone()
    return _row_to_out(row)


@router.get("/{nf_id}", response_model=NewsFighterOut)
async def get_news_fighter(nf_id: str):
    return _row_to_out(await _get_or_404(nf_id))


@router.put("/{nf_id}", response_model=NewsFighterOut)
async def update_news_fighter(nf_id: str, body: NewsFighterUpdate):
    row = await _get_or_404(nf_id)
    now = datetime.now(timezone.utc).isoformat()
    name = body.name if body.name is not None else row["name"]
    fallback = row["fallback_fighter_id"] if body.fallback_fighter_id == _SENTINEL else body.fallback_fighter_id
    priority = body.priority if body.priority is not None else row["priority"]
    async with get_db() as db:
        await db.execute(
            "UPDATE news_fighter SET name=?, fallback_fighter_id=?, priority=?, updated_at=? WHERE id=?",
            (name, fallback, priority, now, nf_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM news_fighter WHERE id = ?", (nf_id,))
        row = await cur.fetchone()
    return _row_to_out(row)


@router.delete("/{nf_id}", status_code=204, response_model=None)
async def delete_news_fighter(nf_id: str):
    row = await _get_or_404(nf_id)
    if row["is_system"]:
        raise HTTPException(status_code=403, detail="System fighters cannot be deleted.")
    async with get_db() as db:
        await db.execute("DELETE FROM news_fighter WHERE id = ?", (nf_id,))
        await db.commit()


@router.post("/from-battle/{fighter_id}", response_model=NewsFighterOut, status_code=201)
async def promote_from_battle(fighter_id: str):
    """Copy a battle fighter + its steps into a standalone news fighter."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM fighter WHERE id = ?", (fighter_id,))
        src = await cur.fetchone()
        if src is None:
            raise HTTPException(status_code=404, detail="Battle fighter not found")

        # Copy fighter row
        new_fighter_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_fighter_id, src["battle_id"], src["name"] + " (news)", src["is_manual"], src["position"], now),
        )

        # Copy steps
        cur = await db.execute(
            "SELECT * FROM fighter_step WHERE fighter_id = ? ORDER BY position ASC", (fighter_id,)
        )
        steps = await cur.fetchall()
        for step in steps:
            new_step_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_step_id, new_fighter_id, step["position"], step["system_prompt"],
                 step["provider"], step["model_id"], step["provider_config"], now),
            )

        # Create news_fighter record
        nf_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO news_fighter (id, fighter_id, name, fallback_fighter_id, priority, is_system, created_at, updated_at)
               VALUES (?, ?, ?, NULL, 5, 0, ?, ?)""",
            (nf_id, new_fighter_id, src["name"], now, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM news_fighter WHERE id = ?", (nf_id,))
        row = await cur.fetchone()
    return _row_to_out(row)
