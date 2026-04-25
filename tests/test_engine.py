"""Tests for t01_llm_battle.engine — execute_run step sequencing and error handling."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from t01_llm_battle.db import get_db, init_db
from t01_llm_battle.engine import execute_run
from t01_llm_battle.providers.base import ProviderResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(content: str) -> ProviderResult:
    return ProviderResult(
        content=content,
        input_tokens=5,
        output_tokens=10,
        credits_used=None,
        cost_usd=0.001,
        model="gpt-4o-mini",
        provider="openai",
    )


async def _seed_battle(db_path: str) -> tuple[str, str]:
    """Insert a battle + single source. Returns (battle_id, source_id)."""
    battle_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Test Battle", "openai", "gpt-4o", "", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "source.txt", "hello world", 1),
        )
        await db.commit()

    return battle_id, source_id


async def _seed_fighter(db_path: str, battle_id: str, is_manual: bool = False) -> str:
    fighter_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Fighter A", int(is_manual), 1, now),
        )
        await db.commit()
    return fighter_id


async def _seed_step(db_path: str, fighter_id: str, position: int = 1) -> str:
    step_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO fighter_step "
            "(id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id, fighter_id, position, None, "openai", "gpt-4o-mini", "{}", now),
        )
        await db.commit()
    return step_id


async def _seed_run(db_path: str, battle_id: str) -> str:
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "pending", now),
        )
        await db.commit()
    return run_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_steps_output_chaining(tmp_path):
    """Step 2 receives step 1's output as its input."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    battle_id, source_id = await _seed_battle(db_path)
    fighter_id = await _seed_fighter(db_path, battle_id)
    step1_id = await _seed_step(db_path, fighter_id, position=1)
    step2_id = await _seed_step(db_path, fighter_id, position=2)
    run_id = await _seed_run(db_path, battle_id)

    call_inputs: list[str] = []

    async def fake_run(request):
        call_inputs.append(request.user_prompt)
        return _make_result(f"output-of-{request.user_prompt[:6]}")

    mock_provider = MagicMock()
    mock_provider.run = fake_run

    with (
        patch("t01_llm_battle.engine.get_provider", return_value=mock_provider),
        patch("t01_llm_battle.engine.rate_limiter.acquire", new=AsyncMock()),
        patch("t01_llm_battle.engine.score_response", new=AsyncMock(return_value=(8.0, "good"))),
        patch("t01_llm_battle.engine.generate_report", new=AsyncMock(return_value="report")),
        patch("t01_llm_battle.engine._resolve_api_key", new=AsyncMock(return_value=None)),
    ):
        await execute_run(run_id, db_path)

    # Step 1 receives source content; step 2 receives step 1's output
    assert call_inputs[0] == "hello world"
    assert call_inputs[1].startswith("output-of-hello")


@pytest.mark.asyncio
async def test_step_error_stops_subsequent_steps(tmp_path):
    """If step 1 raises, step 2 is skipped and fighter_result is 'error'."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    battle_id, source_id = await _seed_battle(db_path)
    fighter_id = await _seed_fighter(db_path, battle_id)
    await _seed_step(db_path, fighter_id, position=1)
    await _seed_step(db_path, fighter_id, position=2)
    run_id = await _seed_run(db_path, battle_id)

    call_count = 0

    async def fail_on_first(request):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("provider failed")

    mock_provider = MagicMock()
    mock_provider.run = fail_on_first

    with (
        patch("t01_llm_battle.engine.get_provider", return_value=mock_provider),
        patch("t01_llm_battle.engine.rate_limiter.acquire", new=AsyncMock()),
        patch("t01_llm_battle.engine.score_response", new=AsyncMock(return_value=(None, "err"))),
        patch("t01_llm_battle.engine.generate_report", new=AsyncMock(return_value="report")),
        patch("t01_llm_battle.engine._resolve_api_key", new=AsyncMock(return_value=None)),
    ):
        await execute_run(run_id, db_path)

    # Only step 1 was attempted (step 2 was skipped)
    assert call_count == 1

    # fighter_result should be 'error'
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT status FROM fighter_result WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
    assert row["status"] == "error"


@pytest.mark.asyncio
async def test_manual_fighter_awaiting_input(tmp_path):
    """Manual fighters create a fighter_result with status='awaiting_input'."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    battle_id, source_id = await _seed_battle(db_path)
    await _seed_fighter(db_path, battle_id, is_manual=True)
    run_id = await _seed_run(db_path, battle_id)

    with (
        patch("t01_llm_battle.engine.get_provider"),
        patch("t01_llm_battle.engine.rate_limiter.acquire", new=AsyncMock()),
        patch("t01_llm_battle.engine.score_response", new=AsyncMock(return_value=(None, ""))),
        patch("t01_llm_battle.engine.generate_report", new=AsyncMock(return_value="")),
        patch("t01_llm_battle.engine._resolve_api_key", new=AsyncMock(return_value=None)),
    ):
        await execute_run(run_id, db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT status FROM fighter_result WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()

    assert row["status"] == "awaiting_input"
