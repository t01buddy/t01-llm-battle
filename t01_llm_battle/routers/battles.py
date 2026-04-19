"""Battle CRUD router — create, list, get, delete."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db

router = APIRouter(prefix="/battles", tags=["battles"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class BattleCreate(BaseModel):
    name: str
    judge_provider: str
    judge_model: str
    judge_rubric: str


class BattleSummary(BaseModel):
    id: str
    name: str
    created_at: str


class BattleDetail(BaseModel):
    id: str
    name: str
    judge_provider: str
    judge_model: str
    judge_rubric: str
    created_at: str


class BattleCreated(BaseModel):
    id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=BattleCreated, status_code=201)
async def create_battle(body: BattleCreate) -> BattleCreated:
    """Create a new battle and return its id."""
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Battle name must not be empty or whitespace.")
    battle_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (battle_id, body.name, body.judge_provider, body.judge_model, body.judge_rubric, created_at),
        )
        await db.commit()

    return BattleCreated(id=battle_id)


@router.get("", response_model=list[BattleSummary])
async def list_battles() -> list[BattleSummary]:
    """Return all battles ordered by creation date descending."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, created_at FROM battle ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

    return [BattleSummary(id=row["id"], name=row["name"], created_at=row["created_at"]) for row in rows if row["id"]]


@router.get("/{battle_id}", response_model=BattleDetail)
async def get_battle(battle_id: str) -> BattleDetail:
    """Return full details for a single battle."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, judge_provider, judge_model, judge_rubric, created_at FROM battle WHERE id = ?",
            (battle_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Battle not found")

    return BattleDetail(
        id=row["id"],
        name=row["name"],
        judge_provider=row["judge_provider"],
        judge_model=row["judge_model"],
        judge_rubric=row["judge_rubric"],
        created_at=row["created_at"],
    )


@router.delete("/{battle_id}", status_code=204, response_model=None)
async def delete_battle(battle_id: str) -> None:
    """Delete a battle and all related data via cascade."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM battle WHERE id = ?", (battle_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Battle not found")

        # Delete child records first (SQLite foreign keys may not be enforced by default)
        await db.execute(
            "DELETE FROM step_result WHERE run_id IN (SELECT id FROM run WHERE battle_id = ?)",
            (battle_id,),
        )
        await db.execute(
            "DELETE FROM fighter_result WHERE run_id IN (SELECT id FROM run WHERE battle_id = ?)",
            (battle_id,),
        )
        await db.execute("DELETE FROM run WHERE battle_id = ?", (battle_id,))
        await db.execute(
            "DELETE FROM fighter_step WHERE fighter_id IN (SELECT id FROM fighter WHERE battle_id = ?)",
            (battle_id,),
        )
        await db.execute("DELETE FROM fighter WHERE battle_id = ?", (battle_id,))
        await db.execute("DELETE FROM battle_source WHERE battle_id = ?", (battle_id,))
        await db.execute("DELETE FROM battle WHERE id = ?", (battle_id,))
        await db.commit()
