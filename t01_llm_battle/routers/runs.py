"""Runs router — create and poll run execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import DB_PATH, get_db, resolve_api_key, _PROVIDER_ENV_VARS
from ..engine import start_run_background
from ..judge import score_response, generate_report

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

    # Load fighter_results with fighter name via join
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT fr.id, fr.fighter_id, f.name AS fighter_name, "
            "fr.source_id, bs.label AS source_label, fr.status, fr.final_output, "
            "fr.total_cost_usd, fr.total_latency_ms, fr.total_input_tokens, "
            "fr.total_output_tokens, fr.judge_score, fr.judge_reasoning "
            "FROM fighter_result fr "
            "JOIN fighter f ON f.id = fr.fighter_id "
            "JOIN battle_source bs ON bs.id = fr.source_id "
            "WHERE fr.run_id = ?",
            (run_id,),
        )
        fr_rows = [dict(r) for r in await cursor.fetchall()]

    # Load step_results with order_index via join on fighter_step
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT sr.id, sr.fighter_id, sr.step_id, sr.source_id, "
            "COALESCE(fs.position, 0) AS order_index, "
            "sr.output_text, sr.input_tokens, sr.output_tokens, sr.latency_ms, "
            "sr.cost_usd, sr.error, sr.created_at "
            "FROM step_result sr "
            "LEFT JOIN fighter_step fs ON fs.id = sr.step_id "
            "WHERE sr.run_id = ?",
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
                "order_index": sr["order_index"],
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
        steps = sorted(sr_index.get(key, []), key=lambda s: s["order_index"])
        fighter_results.append(
            {
                "fighter_result_id": fr["id"],
                "fighter_id": fr["fighter_id"],
                "fighter_name": fr["fighter_name"],
                "source_id": fr["source_id"],
                "source_label": fr["source_label"],
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

    # 6. Score the just-submitted manual result
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT r.battle_id, b.judge_provider, b.judge_model, b.judge_rubric, "
            "bs.content AS source_content "
            "FROM fighter_result fr "
            "JOIN run r ON r.id = fr.run_id "
            "JOIN battle b ON b.id = r.battle_id "
            "JOIN battle_source bs ON bs.id = fr.source_id "
            "WHERE fr.id = ?",
            (step_result_id,),
        )
        ctx = await cursor.fetchone()

    if ctx and ctx["judge_provider"] and ctx["judge_model"] and body.content:
        import os
        env_var = _PROVIDER_ENV_VARS.get(ctx["judge_provider"])
        injected = False
        if env_var and not os.environ.get(env_var):
            key = await resolve_api_key(ctx["judge_provider"])
            if key:
                os.environ[env_var] = key
                injected = True
        judge_score, judge_reasoning = await score_response(
            judge_provider=ctx["judge_provider"],
            judge_model=ctx["judge_model"],
            judge_rubric=ctx["judge_rubric"] or "",
            source_content=ctx["source_content"],
            response_content=body.content,
        )
        if injected:
            os.environ.pop(env_var, None)
        async with get_db() as db:
            await db.execute(
                "UPDATE fighter_result SET judge_score = ?, judge_reasoning = ? WHERE id = ?",
                (judge_score, judge_reasoning, step_result_id),
            )
            await db.commit()

    # 7. If all fighter_results are done, mark run as complete and generate report
    all_done = all(r["status"] in ("complete", "error") for r in all_results)

    if all_done:
        finished_at = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            await db.execute(
                "UPDATE run SET status = 'complete', finished_at = ? WHERE id = ?",
                (finished_at, run_id),
            )
            await db.commit()
        if ctx and ctx["judge_provider"] and ctx["judge_model"]:
            import os
            env_var = _PROVIDER_ENV_VARS.get(ctx["judge_provider"])
            injected = False
            if env_var and not os.environ.get(env_var):
                key = await resolve_api_key(ctx["judge_provider"])
                if key:
                    os.environ[env_var] = key
                    injected = True
            await generate_report(run_id, ctx["judge_provider"], ctx["judge_model"])
            if injected:
                os.environ.pop(env_var, None)

    return ManualSubmitResponse(step_result_id=step_result_id, status="complete")



@router.get("/{run_id}/results")
async def get_run_results(run_id: str):
    """Aggregate final results for display."""

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, battle_id, status, report_markdown FROM run WHERE id = ?",
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
                fr.total_latency_ms,
                fr.total_input_tokens,
                fr.total_output_tokens,
                fr.judge_score,
                fr.status,
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
                SUM(COALESCE(sr.cost_usd, 0))          AS agg_cost_usd,
                SUM(COALESCE(sr.latency_ms, 0))        AS agg_latency_ms
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
                "total_latency_ms": agg["agg_latency_ms"] if agg else fr["total_latency_ms"],
                "total_input_tokens": agg["agg_input_tokens"] if agg else fr["total_input_tokens"],
                "total_output_tokens": agg["agg_output_tokens"] if agg else fr["total_output_tokens"],
                "final_output": final_output,
                "step_count": agg["step_count"] if agg else 0,
                "status": fr["status"],
            }
        )

    return {
        "run_id": run_id,
        "battle_id": run_data["battle_id"],
        "status": run_data["status"],
        "report_markdown": run_data.get("report_markdown"),
        "summary": summary,
    }
