"""Run execution engine — executes all fighters x sources for a given run."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime, timezone

from .db import DB_PATH, get_db, resolve_api_key, _PROVIDER_ENV_VARS
from .judge import score_response, generate_report
from .providers.base import ProviderRequest, ProviderResult
from .providers.registry import get_provider
from . import rate_limiter


async def _inject_api_key(provider_name: str, db_path) -> str | None:
    """If the env var for provider is not set, look up DB and set it temporarily.

    Returns the env var name that was set (so the caller can restore it), or None.
    """
    import os

    env_var = _PROVIDER_ENV_VARS.get(provider_name)
    if not env_var:
        return None
    if os.environ.get(env_var):
        return None  # env already set; nothing to do

    key = await resolve_api_key(provider_name, db_path)
    if key:
        os.environ[env_var] = key
        return env_var
    return None


async def _execute_pair(
    run_id: str,
    fighter: dict,
    steps: list[dict],
    source: dict,
    judge_provider: str | None,
    judge_model: str | None,
    judge_rubric: str | None,
    db_path,
) -> bool:
    """Execute one fighter x source pair. Returns True if successful (not errored)."""
    import os

    fighter_id = fighter["id"]
    is_manual = fighter["is_manual"]
    source_id = source["id"]
    source_content = source["content"]

    fr_id = str(uuid.uuid4())
    fr_now = datetime.now(timezone.utc).isoformat()

    if is_manual:
        async with get_db(db_path) as db:
            await db.execute(
                "INSERT INTO fighter_result "
                "(id, run_id, fighter_id, source_id, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fr_id, run_id, fighter_id, source_id, "awaiting_input", fr_now),
            )
            await db.commit()
        return True  # manual is not an error

    # Mark fighter_result as running
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "running", fr_now),
        )
        await db.commit()

    # Execute steps sequentially within this fighter
    step_input = source_content
    had_error = False
    total_cost: float = 0.0
    total_latency: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    final_output: str | None = None

    for step in steps:
        step_id = step["id"]
        sr_id = str(uuid.uuid4())
        sr_now = datetime.now(timezone.utc).isoformat()

        try:
            provider = get_provider(step["provider"])

            config = json.loads(step["provider_config"]) if step["provider_config"] else {}
            temperature = config.pop("temperature", 0.7)
            max_tokens = config.pop("max_tokens", 2048)
            extra = config

            request = ProviderRequest(
                model=step["model_id"],
                system_prompt=step["system_prompt"] or "",
                user_prompt=step_input,
                temperature=temperature,
                max_tokens=max_tokens,
                extra=extra,
            )

            await rate_limiter.acquire(step["provider"])
            injected_env_var = await _inject_api_key(step["provider"], db_path)
            t0 = time.monotonic()
            result: ProviderResult = await provider.run(request)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if injected_env_var:
                os.environ.pop(injected_env_var, None)

            async with get_db(db_path) as db:
                await db.execute(
                    "INSERT INTO step_result "
                    "(id, run_id, fighter_id, step_id, source_id, "
                    "input_text, output_text, input_tokens, output_tokens, "
                    "latency_ms, cost_usd, error, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sr_id, run_id, fighter_id, step_id, source_id,
                        step_input, result.content, result.input_tokens,
                        result.output_tokens, latency_ms, result.cost_usd,
                        result.error, sr_now,
                    ),
                )
                await db.commit()

            if result.error:
                had_error = True
                break

            total_cost += result.cost_usd or 0.0
            total_latency += latency_ms
            total_input_tokens += result.input_tokens or 0
            total_output_tokens += result.output_tokens or 0

            step_input = result.content
            final_output = result.content

        except Exception as exc:
            async with get_db(db_path) as db:
                await db.execute(
                    "INSERT INTO step_result "
                    "(id, run_id, fighter_id, step_id, source_id, "
                    "input_text, output_text, input_tokens, output_tokens, "
                    "latency_ms, cost_usd, error, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sr_id, run_id, fighter_id, step_id, source_id,
                        step_input, None, None, None, None, None,
                        str(exc), sr_now,
                    ),
                )
                await db.commit()
            had_error = True
            break

    # Update fighter_result
    fr_status = "error" if had_error else "complete"
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE fighter_result SET "
            "status = ?, final_output = ?, total_cost_usd = ?, "
            "total_latency_ms = ?, total_input_tokens = ?, total_output_tokens = ? "
            "WHERE id = ?",
            (
                fr_status, final_output, total_cost if total_cost else None,
                total_latency if total_latency else None,
                total_input_tokens if total_input_tokens else None,
                total_output_tokens if total_output_tokens else None,
                fr_id,
            ),
        )
        await db.commit()

    # Run judge scoring for completed results
    if not had_error and final_output and judge_provider and judge_model:
        injected_judge_env_var = await _inject_api_key(judge_provider, db_path)
        judge_score, judge_reasoning = await score_response(
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_rubric=judge_rubric or "",
            source_content=source_content,
            response_content=final_output,
        )
        if injected_judge_env_var:
            os.environ.pop(injected_judge_env_var, None)
        async with get_db(db_path) as db:
            await db.execute(
                "UPDATE fighter_result SET judge_score = ?, judge_reasoning = ? WHERE id = ?",
                (judge_score, judge_reasoning, fr_id),
            )
            await db.commit()

    return not had_error


async def execute_run(run_id: str, db_path=DB_PATH) -> None:
    """Execute a run: all fighter x source pairs in parallel; steps sequential within each pair."""

    # Mark run as running — preserve original started_at set at creation time (FR-10)
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE run SET status = ? WHERE id = ?",
            ("running", run_id),
        )
        await db.commit()

    # Load run to get battle_id
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT battle_id FROM run WHERE id = ?", (run_id,))
        run_row = await cursor.fetchone()
        if not run_row:
            return
        battle_id = run_row["battle_id"]

    # Load judge config from battle
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT judge_provider, judge_model, judge_rubric FROM battle WHERE id = ?",
            (battle_id,),
        )
        battle_row = await cursor.fetchone()
        judge_provider = battle_row["judge_provider"] if battle_row else None
        judge_model = battle_row["judge_model"] if battle_row else None
        judge_rubric = battle_row["judge_rubric"] if battle_row else None

    # Load fighters for this battle
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id, name, is_manual FROM fighter WHERE battle_id = ? ORDER BY position",
            (battle_id,),
        )
        fighters = [dict(r) for r in await cursor.fetchall()]

    # Load sources for this battle
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id, content FROM battle_source WHERE battle_id = ? ORDER BY position",
            (battle_id,),
        )
        sources = [dict(r) for r in await cursor.fetchall()]

    # Pre-load steps for each fighter
    fighter_steps: dict[str, list[dict]] = {}
    for fighter in fighters:
        async with get_db(db_path) as db:
            cursor = await db.execute(
                "SELECT id, position, system_prompt, provider, model_id, provider_config "
                "FROM fighter_step WHERE fighter_id = ? ORDER BY position",
                (fighter["id"],),
            )
            fighter_steps[fighter["id"]] = [dict(r) for r in await cursor.fetchall()]

    # Build all fighter x source tasks and run them in parallel
    tasks = [
        _execute_pair(
            run_id=run_id,
            fighter=fighter,
            steps=fighter_steps[fighter["id"]],
            source=source,
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_rubric=judge_rubric,
            db_path=db_path,
        )
        for fighter in fighters
        for source in sources
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # all_errored if every result was False or an exception
    all_errored = all(r is not True for r in results)

    # Mark run as complete (or error if ALL fighter_results errored)
    finished_at = datetime.now(timezone.utc).isoformat()
    run_status = "error" if all_errored else "complete"
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE run SET status = ?, finished_at = ? WHERE id = ?",
            (run_status, finished_at, run_id),
        )
        await db.commit()

    # Generate markdown report after all judging is complete
    if judge_provider and judge_model:
        import os
        injected_report_env_var = await _inject_api_key(judge_provider, db_path)
        await generate_report(run_id, judge_provider, judge_model, db_path)
        if injected_report_env_var:
            os.environ.pop(injected_report_env_var, None)


def start_run_background(run_id: str, db_path=DB_PATH) -> None:
    """Start run execution in a background thread."""

    def _run():
        asyncio.run(execute_run(run_id, db_path))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
