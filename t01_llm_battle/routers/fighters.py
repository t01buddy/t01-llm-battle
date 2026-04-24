"""
Fighter + steps CRUD.

POST   /battles/{battle_id}/fighters                         — create fighter
GET    /battles/{battle_id}/fighters                         — list fighters for battle
GET    /battles/{battle_id}/fighters/{fighter_id}            — get fighter with steps
DELETE /battles/{battle_id}/fighters/{fighter_id}            — delete fighter + steps
POST   /battles/{battle_id}/fighters/{fighter_id}/steps      — add a step to a fighter
PATCH  /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}/move  — move step up or down
DELETE /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}  — delete step

GET    /providers                                             — list all providers with type, models/functions, pricing
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db, DB_PATH
from ..providers.registry import list_providers, get_provider
from ..providers.base import ProviderType
from ..pricing import get_llm_cost, load_llm_pricing, load_tool_pricing

_SYSTEM_PROVIDERS = {
    "openai", "anthropic", "google", "groq",
    "openrouter", "ollama", "serper", "tavily", "firecrawl",
}

router = APIRouter(prefix="/battles/{battle_id}/fighters", tags=["fighters"])

providers_router = APIRouter(prefix="/providers", tags=["providers"])


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


@router.put("/{fighter_id}/steps/{step_id}", response_model=StepOut)
async def update_step(battle_id: str, fighter_id: str, step_id: str, body: StepCreate):
    """Update a step."""
    async with get_db() as db:
        await _get_fighter_or_404(db, battle_id, fighter_id)
        cur = await db.execute(
            """UPDATE fighter_step SET position=?, system_prompt=?, provider=?, model_id=?, provider_config=?
               WHERE id=? AND fighter_id=?""",
            (body.position, body.system_prompt, body.provider, body.model_id, body.provider_config, step_id, fighter_id),
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Step not found")
        cur = await db.execute("SELECT * FROM fighter_step WHERE id = ?", (step_id,))
        row = await cur.fetchone()
    return _row_to_step_out(row)


@router.patch("/{fighter_id}/steps/{step_id}/move", response_model=list[StepOut])
async def move_step(battle_id: str, fighter_id: str, step_id: str, direction: str):
    """Move a step up or down within its fighter. direction must be 'up' or 'down'."""
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction must be 'up' or 'down'")
    async with get_db() as db:
        await _get_fighter_or_404(db, battle_id, fighter_id)
        cur = await db.execute(
            "SELECT * FROM fighter_step WHERE fighter_id = ? ORDER BY position ASC",
            (fighter_id,),
        )
        rows = await cur.fetchall()
        ids = [r["id"] for r in rows]
        if step_id not in ids:
            raise HTTPException(status_code=404, detail="Step not found")
        idx = ids.index(step_id)
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if swap_idx < 0 or swap_idx >= len(ids):
            return [_row_to_step_out(r) for r in rows]
        pos_a, pos_b = rows[idx]["position"], rows[swap_idx]["position"]
        await db.execute("UPDATE fighter_step SET position=? WHERE id=?", (pos_b, ids[idx]))
        await db.execute("UPDATE fighter_step SET position=? WHERE id=?", (pos_a, ids[swap_idx]))
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM fighter_step WHERE fighter_id = ? ORDER BY position ASC",
            (fighter_id,),
        )
        updated = await cur.fetchall()
    return [_row_to_step_out(r) for r in updated]


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


# ---------------------------------------------------------------------------
# Provider info endpoint (mounted separately at /providers)
# ---------------------------------------------------------------------------

class ProviderModelInfo(BaseModel):
    id: str
    pricing_label: str  # e.g. "$2.50 / $10.00 per 1M tokens" or "1 credit ($0.001)"


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    provider_type: str  # "llm" or "tool"
    models: list[ProviderModelInfo]
    native_tools: list[str]  # only for LLM providers; empty list for tool providers
    enabled: bool = True
    is_system: bool = True
    config: dict = {}


def _build_provider_info(name: str) -> ProviderInfo | None:
    try:
        p = get_provider(name)
    except KeyError:
        return None

    model_ids = p.models()
    models: list[ProviderModelInfo] = []

    if p.provider_type == ProviderType.LLM:
        llm_pricing = load_llm_pricing()
        provider_prices = llm_pricing.get(name, {})
        for mid in model_ids:
            entry = provider_prices.get(mid)
            if entry:
                inp = entry["input_per_million"]
                out = entry["output_per_million"]
                label = f"${inp:.2f} in / ${out:.2f} out per 1M tokens"
            else:
                label = "pricing unknown"
            models.append(ProviderModelInfo(id=mid, pricing_label=label))
        native_tools: list[str] = list(getattr(p, "native_tools", []))
    else:
        # TOOL provider — models() returns function names; get credit pricing from centralized module
        tool_pricing = load_tool_pricing().get(name, {})
        credits_per_call = tool_pricing.get("credits_per_call", 0.0)
        usd_per_credit = tool_pricing.get("usd_per_credit", 0.0)
        for fn in model_ids:
            if credits_per_call:
                usd = credits_per_call * usd_per_credit
                label = f"{credits_per_call:.0f} credit (${usd:.4f} per call)"
            else:
                label = "pricing unknown"
            models.append(ProviderModelInfo(id=fn, pricing_label=label))
        native_tools = []

    return ProviderInfo(
        name=name,
        display_name=getattr(p, "display_name", name),
        provider_type=p.provider_type.value,
        models=models,
        native_tools=native_tools,
    )


@providers_router.get("", response_model=list[ProviderInfo])
async def list_provider_info() -> list[ProviderInfo]:
    """Return all registered providers with type, models/functions, pricing, enabled state, and config."""
    names = list_providers()

    # Fetch all provider_config rows in one query
    provider_configs: dict[str, dict] = {}
    async with get_db(DB_PATH) as db:
        cur = await db.execute("SELECT provider, enabled, server_url FROM provider_config")
        rows = await cur.fetchall()
        for row in rows:
            provider_configs[row["provider"]] = {
                "enabled": bool(row["enabled"]),
                "server_url": row["server_url"],
            }

    result = []
    for name in names:
        info = _build_provider_info(name)
        if info:
            cfg = provider_configs.get(name, {"enabled": True, "server_url": None})
            info.enabled = cfg["enabled"]
            info.is_system = name in _SYSTEM_PROVIDERS
            info.config = {"server_url": cfg["server_url"]} if cfg["server_url"] else {}
            result.append(info)
    return result
