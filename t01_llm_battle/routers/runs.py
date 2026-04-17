"""Runs router — create and poll run execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..engine import start_run_background

router = APIRouter(prefix="/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    battle_id: str


class ManualSubmitRequest(BaseModel):
    content: str


class ManualSubmitResponse(BaseModel):
    step_result_id: str
    status: str


@router.post("")
async def create_run(body: CreateRunRequest):
    """Create a new run for a battle and kick off background execution."""

    # Verify battle exists
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM battle WHERE id = ?", (body.battle_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Battle not found")

    # Verify battle has at least one fighter
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM fighter WHERE battle_id = ?", (body.battle_id,)
        )
        row = await cursor.fetchone()
        if row[0] == 0:
            raise HTTPException(
                status_code=422, detail="Battle has no fighters"
            )

    # Verify battle has at least one source
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM battle_source WHERE battle_id = ?",
            (body.battle_id,),
        )
        row = await cursor.fetchone()
        if row[0] == 0:
            raise HTTPException(
                status_code=422, detail="Battle has no sources"
            )

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) "
            "VALUES (?, ?, ?, ?)",
            (run_id, body.battle_id, "pending", now),
        )
        await db.commit()

    # Kick off background execution
    start_run_background(run_id)

    return {"run_id": run_id, "status": "running"}


@router.get("/{run_id}/status")
async def get_run_status(run_id: str):
    """Poll run status including per-fighter, per-source step details."""

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, battle_id, status, started_at, finished_at "
            "FROM run WHERE id = ?",
            (run_id,),
        )
        run_row = await cursor.fetchone()
        if not run_row:
            raise HTTPException(status_code=404, detail="Run not found")

    run_data = dict(run_row)

    # Load fighter_results
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, fighter_id, source_id, status, final_output, "
            "total_cost_usd, total_latency_ms, total_input_tokens, "
            "total_output_tokens, judge_score, judge_reasoning "
            "FROM fighter_result WHERE run_id = ?",
            (run_id,),
        )
        fr_rows = [dict(r) for r in await cursor.fetchall()]

    # Load step_results for this run
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, fighter_id, step_id, source_id, "
            "output_text, input_tokens, output_tokens, latency_ms, "
            "cost_usd, error, created_at "
            "FROM step_result WHERE run_id = ?",
            (run_id,),
        )
        sr_rows = [dict(r) for r in await cursor.fetchall()]

    # Index step_results by (fighter_id, source_id)
    sr_index: dict[tuple[str, str], list[dict]] = {}
    for sr in sr_rows:
        key = (sr["fighter_id"], sr["source_id"])
        sr_index.setdefault(key, []).append(
            {
                "step_id": sr["step_id"],
                "status": "error" if sr["error"] else "complete",
                "error": sr["error"],
                "output_text": sr["output_text"],
                "input_tokens": sr["input_tokens"],
                "output_tokens": sr["output_tokens"],
                "latency_ms": sr["latency_ms"],
                "cost_usd": sr["cost_usd"],
            }
        )

    fighter_results = []
    for fr in fr_rows:
        key = (fr["fighter_id"], fr["source_id"])
        steps = sr_index.get(key, [])
        fighter_results.append(
            {
                "fighter_id": fr["fighter_id"],
                "source_id": fr["source_id"],
                "status": fr["status"],
                "final_output": fr["final_output"],
                "total_cost_usd": fr["total_cost_usd"],
                "total_latency_ms": fr["total_latency_ms"],
                "total_input_tokens": fr["total_input_tokens"],
                "total_output_tokens": fr["total_output_tokens"],
                "judge_score": fr["judge_score"],
                "judge_reasoning": fr["judge_reasoning"],
                "steps": steps,
            }
        )

    return {
        "run_id": run_data["id"],
        "status": run_data["status"],
        "started_at": run_data["started_at"],
        "finished_at": run_data["finished_at"],
        "fighter_results": fighter_results,
    }


@router.post(
    "/{run_id}/steps/{step_result_id}/submit",
    response_model=ManualSubmitResponse,
)
async def submit_manual_step(
    run_id: str,
    step_result_id: str,
    body: ManualSubmitRequest,
) -> ManualSubmitResponse:
    """Submit a human response for a manual fighter awaiting input.

    ``step_result_id`` identifies a ``fighter_result`` row whose status is
    ``awaiting_input``.  After updating it to ``complete`` the endpoint checks
    whether all fighter_results in the run are done and, if so, marks the run
    as ``complete``.
    """
    async with get_db() as db:
        # 1. Look up the fighter_result by id
        cursor = await db.execute(
            "SELECT id, run_id, status FROM fighter_result WHERE id = ?",
            (step_result_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Step result not found")

        # 2. Verify it belongs to the given run_id
        if row["run_id"] != run_id:
            raise HTTPException(
                status_code=404,
                detail="Step result does not belong to this run",
            )

        # 3. Verify status is awaiting_input
        if row["status"] != "awaiting_input":
            raise HTTPException(
                status_code=400,
                detail=f"Step result status is '{row['status']}', expected 'awaiting_input'",
            )

        # 4. Update fighter_result: final_output = content, status = complete,
        #    tokens/cost = 0 (manual — no LLM call)
        await db.execute(
            """
            UPDATE fighter_result
               SET final_output = ?,
                   status = 'complete',
                   total_cost_usd = 0,
                   total_input_tokens = 0,
                   total_output_tokens = 0
             WHERE id = ?
            """,
            (body.content, step_result_id),
        )
        await db.commit()

        # 5. Check whether all fighter_results for this run are now complete
        cursor = await db.execute(
            "SELECT status FROM fighter_result WHERE run_id = ?",
            (run_id,),
        )
        all_results = await cursor.fetchall()

    # 6. If all fighter_results are done, mark run as complete
    all_done = all(r["status"] in ("complete", "error") for r in all_results)

    if all_done:
        finished_at = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            await db.execute(
                "UPDATE run SET status = 'complete', finished_at = ? WHERE id = ?",
                (finished_at, run_id),
            )
            await db.commit()

    return ManualSubmitResponse(step_result_id=step_result_id, status="complete")
