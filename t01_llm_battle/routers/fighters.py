"""
Fighter + steps CRUD.

POST   /battles/{battle_id}/fighters                         — create fighter
GET    /battles/{battle_id}/fighters                         — list fighters for battle
GET    /battles/{battle_id}/fighters/{fighter_id}            — get fighter with steps
DELETE /battles/{battle_id}/fighters/{fighter_id}            — delete fighter + steps
POST   /battles/{battle_id}/fighters/{fighter_id}/steps      — add a step to a fighter
DELETE /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}  — delete step
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db

router = APIRouter(prefix="/battles/{battle_id}/fighters", tags=["fighters"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FighterCreate(BaseModel):
    name: str
    is_manual: bool = False
    position: int = 0


class FighterOut(BaseModel):
    id: str
    battle_id: str
    name: str
    is_manual: bool
    position: int
    created_at: str


class FighterWithSteps(FighterOut):
    steps: list[StepOut] = []


class StepCreate(BaseModel):
    position: int
    system_prompt: str | None = None
    provider: str
    model_id: str
    provider_config: str = "{}"


class StepOut(BaseModel):
    id: str
    fighter_id: str
    position: int
    system_prompt: str | None
    provider: str
    model_id: str
    provider_config: str
    created_at: str


# Rebuild FighterWithSteps now that StepOut is defined
FighterWithSteps.model_rebuild()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_fighter_or_404(db: Any, battle_id: str, fighter_id: str) -> Any:
    cursor = await db.execute(
        "SELECT * FROM fighter WHERE id = ? AND battle_id = ?",
        (fighter_id, battle_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Fighter not found")
    return row


def _row_to_fighter_out(row: Any) -> FighterOut:
    return FighterOut(
        id=row["id"],
        battle_id=row["battle_id"],
        name=row["name"],
        is_manual=bool(row["is_manual"]),
        position=row["position"],
        created_at=row["created_at"],
    )


def _row_to_step_out(row: Any) -> StepOut:
    return StepOut(
        id=row["id"],
        fighter_id=row["fighter_id"],
        position=row["position"],
        system_prompt=row["system_prompt"],
        provider=row["provider"],
        model_id=row["model_id"],
        provider_config=row["provider_config"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=FighterOut, status_code=201)
async def create_fighter(battle_id: str, body: FighterCreate):
    """Create a fighter for a battle."""
    # Verify battle exists
    async with get_db() as db:
        cur = await db.execute("SELECT id FROM battle WHERE id = ?", (battle_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Battle not found")

        fighter_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, body.name, int(body.is_manual), body.position, now),
        )
        await db.commit()

        cur = await db.execute("SELECT * FROM fighter WHERE id = ?", (fighter_id,))
        row = await cur.fetchone()

    return _row_to_fighter_out(row)


@router.get("", response_model=list[FighterOut])
async def list_fighters(battle_id: str):
    """List all fighters for a battle."""
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM fighter WHERE battle_id = ? ORDER BY position ASC, created_at ASC",
            (battle_id,),
        )
        rows = await cur.fetchall()

    return [_row_to_fighter_out(r) for r in rows]


@router.get("/{fighter_id}", response_model=FighterWithSteps)
async def get_fighter(battle_id: str, fighter_id: str):
    """Get a fighter with its steps."""
    async with get_db() as db:
        fighter_row = await _get_fighter_or_404(db, battle_id, fighter_id)

        cur = await db.execute(
            "SELECT * FROM fighter_step WHERE fighter_id = ? ORDER BY position ASC",
            (fighter_id,),
        )
        step_rows = await cur.fetchall()

    fighter = _row_to_fighter_out(fighter_row)
    steps = [_row_to_step_out(r) for r in step_rows]

    return FighterWithSteps(**fighter.model_dump(), steps=steps)


@router.delete("/{fighter_id}", status_code=204, response_model=None)
async def delete_fighter(battle_id: str, fighter_id: str):
    """Delete a fighter and all its steps."""
    async with get_db() as db:
        await _get_fighter_or_404(db, battle_id, fighter_id)

        await db.execute("DELETE FROM fighter_step WHERE fighter_id = ?", (fighter_id,))
        await db.execute(
            "DELETE FROM fighter WHERE id = ? AND battle_id = ?",
            (fighter_id, battle_id),
        )
        await db.commit()


@router.post("/{fighter_id}/steps", response_model=StepOut, status_code=201)
async def add_step(battle_id: str, fighter_id: str, body: StepCreate):
    """Add a step to a fighter."""
    async with get_db() as db:
        await _get_fighter_or_404(db, battle_id, fighter_id)

        step_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO fighter_step
               (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                step_id,
                fighter_id,
                body.position,
                body.system_prompt,
                body.provider,
                body.model_id,
                body.provider_config,
                now,
            ),
        )
        await db.commit()

        cur = await db.execute("SELECT * FROM fighter_step WHERE id = ?", (step_id,))
        row = await cur.fetchone()

    return _row_to_step_out(row)


@router.delete("/{fighter_id}/steps/{step_id}", status_code=204, response_model=None)
async def delete_step(battle_id: str, fighter_id: str, step_id: str):
    """Delete a step from a fighter."""
    async with get_db() as db:
        await _get_fighter_or_404(db, battle_id, fighter_id)

        cur = await db.execute(
            "DELETE FROM fighter_step WHERE id = ? AND fighter_id = ?",
            (step_id, fighter_id),
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Step not found")
