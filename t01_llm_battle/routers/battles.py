"""Battle CRUD router — create, list, get, delete."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..db import get_db

router = APIRouter(prefix="/battles", tags=["battles"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StepBatch(BaseModel):
    position: int = 0
    system_prompt: str | None = None
    provider: str
    model_id: str
    provider_config: str = "{}"


class FighterBatch(BaseModel):
    name: str
    is_manual: bool = False
    position: int = 0
    steps: list[StepBatch] = []


class BattleCreate(BaseModel):
    name: str = Field(min_length=1)
    judge_provider: Optional[str] = None
    judge_model: Optional[str] = None
    judge_rubric: Optional[str] = None
    fighters: list[FighterBatch] = []

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Battle name cannot be blank")
        return v.strip()


class BattleSummary(BaseModel):
    id: str
    name: str
    created_at: str
    has_sources: bool = False


class BattleDetail(BaseModel):
    id: str
    name: str
    judge_provider: Optional[str] = None
    judge_model: Optional[str] = None
    judge_rubric: Optional[str] = None
    created_at: str


_UNSET = object()


class BattleUpdate(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: Optional[str] = None
    judge_provider: Optional[str] = None
    judge_model: Optional[str] = None
    judge_rubric: Optional[str] = None
    # When True, clear judge fields to NULL (disable judge)
    judge_enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Battle name cannot be blank")
        return v.strip() if v is not None else v


class BattleCreated(BaseModel):
    id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=BattleCreated, status_code=201)
async def create_battle(body: BattleCreate) -> BattleCreated:
    """Create a new battle (with optional nested fighters/steps) and return its id."""
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
        for fighter in body.fighters:
            fighter_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (fighter_id, battle_id, fighter.name, int(fighter.is_manual), fighter.position, created_at),
            )
            for step in fighter.steps:
                step_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO fighter_step
                       (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (step_id, fighter_id, step.position, step.system_prompt,
                     step.provider, step.model_id, step.provider_config, created_at),
                )
        await db.commit()

    return BattleCreated(id=battle_id)


@router.get("", response_model=list[BattleSummary])
async def list_battles() -> list[BattleSummary]:
    """Return all battles ordered by creation date descending."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT b.id, b.name, b.created_at,
                      COUNT(s.id) > 0 AS has_sources
               FROM battle b
               LEFT JOIN battle_source s ON s.battle_id = b.id
               GROUP BY b.id
               ORDER BY b.created_at DESC"""
        )
        rows = await cursor.fetchall()

    return [
        BattleSummary(id=row["id"], name=row["name"], created_at=row["created_at"], has_sources=bool(row["has_sources"]))
        for row in rows if row["id"]
    ]


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


@router.put("/{battle_id}", response_model=BattleDetail)
async def update_battle(battle_id: str, body: BattleUpdate) -> BattleDetail:
    """Update name and/or judge config for a battle."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, judge_provider, judge_model, judge_rubric, created_at FROM battle WHERE id = ?",
            (battle_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Battle not found")

        new_name = body.name if body.name is not None else row["name"]
        if body.judge_enabled is False:
            new_provider = None
            new_model = None
            new_rubric = None
        else:
            new_provider = body.judge_provider if body.judge_provider is not None else row["judge_provider"]
            new_model = body.judge_model if body.judge_model is not None else row["judge_model"]
            new_rubric = body.judge_rubric if body.judge_rubric is not None else row["judge_rubric"]

        await db.execute(
            "UPDATE battle SET name = ?, judge_provider = ?, judge_model = ?, judge_rubric = ? WHERE id = ?",
            (new_name, new_provider, new_model, new_rubric, battle_id),
        )
        await db.commit()

    return BattleDetail(
        id=battle_id,
        name=new_name,
        judge_provider=new_provider,
        judge_model=new_model,
        judge_rubric=new_rubric,
        created_at=row["created_at"],
    )


class RunSummary(BaseModel):
    id: str
    status: str
    started_at: str
    finished_at: str | None


@router.get("/{battle_id}/runs", response_model=list[RunSummary])
async def list_battle_runs(battle_id: str) -> list[RunSummary]:
    """Return all runs for a battle ordered by started_at descending."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM battle WHERE id = ?", (battle_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Battle not found")

        cursor = await db.execute(
            "SELECT id, status, started_at, finished_at FROM run "
            "WHERE battle_id = ? ORDER BY started_at DESC",
            (battle_id,),
        )
        rows = await cursor.fetchall()

    return [
        RunSummary(
            id=row["id"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
        for row in rows
    ]


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
