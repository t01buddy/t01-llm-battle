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


@router.get("/{run_id}/results")
async def get_run_results(run_id: str):
    """Aggregate final results for display."""

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, battle_id, status FROM run WHERE id = ?",
            (run_id,),
        )
        run_row = await cursor.fetchone()
        if not run_row:
            raise HTTPException(status_code=404, detail="Run not found")

    run_data = dict(run_row)

    # Load fighter_results joined with fighter and battle_source
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                fr.fighter_id,
                fr.source_id,
                fr.final_output,
                fr.total_cost_usd,
                fr.total_input_tokens,
                fr.total_output_tokens,
                fr.judge_score,
                f.name           AS fighter_name,
                bs.label         AS source_label
            FROM fighter_result fr
            JOIN fighter      f  ON f.id  = fr.fighter_id
            JOIN battle_source bs ON bs.id = fr.source_id
            WHERE fr.run_id = ?
            ORDER BY f.position, bs.position
            """,
            (run_id,),
        )
        fr_rows = [dict(r) for r in await cursor.fetchall()]

    # Per (fighter_id, source_id): aggregate step counts and token/cost sums
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                sr.fighter_id,
                sr.source_id,
                COUNT(*)                               AS step_count,
                SUM(COALESCE(sr.input_tokens, 0))      AS agg_input_tokens,
                SUM(COALESCE(sr.output_tokens, 0))     AS agg_output_tokens,
                SUM(COALESCE(sr.cost_usd, 0))          AS agg_cost_usd
            FROM step_result sr
            WHERE sr.run_id = ?
            GROUP BY sr.fighter_id, sr.source_id
            """,
            (run_id,),
        )
        sr_agg = {
            (r["fighter_id"], r["source_id"]): dict(r)
            for r in await cursor.fetchall()
        }

    # Fetch last step output per (fighter_id, source_id) ordered by step position
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT sr.fighter_id, sr.source_id, sr.output_text
            FROM step_result sr
            JOIN fighter_step fs ON fs.id = sr.step_id
            WHERE sr.run_id = ?
              AND fs.position = (
                  SELECT MAX(fs2.position)
                  FROM step_result sr2
                  JOIN fighter_step fs2 ON fs2.id = sr2.step_id
                  WHERE sr2.run_id     = sr.run_id
                    AND sr2.fighter_id = sr.fighter_id
                    AND sr2.source_id  = sr.source_id
              )
            """,
            (run_id,),
        )
        last_output = {
            (r["fighter_id"], r["source_id"]): r["output_text"]
            for r in await cursor.fetchall()
        }

    summary = []
    for fr in fr_rows:
        key = (fr["fighter_id"], fr["source_id"])
        agg = sr_agg.get(key)
        # Manual fighters have no step_results; fall back to fighter_result columns
        final_output = last_output.get(key) or fr["final_output"]
        summary.append(
            {
                "fighter_id": fr["fighter_id"],
                "fighter_name": fr["fighter_name"],
                "source_id": fr["source_id"],
                "source_label": fr["source_label"],
                "score": fr["judge_score"],
                "total_cost_usd": agg["agg_cost_usd"] if agg else fr["total_cost_usd"],
                "total_input_tokens": agg["agg_input_tokens"] if agg else fr["total_input_tokens"],
                "total_output_tokens": agg["agg_output_tokens"] if agg else fr["total_output_tokens"],
                "final_output": final_output,
                "step_count": agg["step_count"] if agg else 0,
            }
        )

    return {
        "run_id": run_id,
        "battle_id": run_data["battle_id"],
        "status": run_data["status"],
        "summary": summary,
    }
