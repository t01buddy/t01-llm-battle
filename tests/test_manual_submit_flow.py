"""Integration tests for manual fighter submit flow.

Covers POST /runs/{run_id}/steps/{step_result_id}/submit:
- successful submission updates status to complete
- run marked complete when all results are done
- 404 for unknown step_result_id
- 400 when status is not awaiting_input
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from t01_llm_battle.db import get_db


async def _seed_manual_run(db_path: str) -> tuple[str, str, str]:
    """Seed battle + manual fighter + source + run + awaiting_input fighter_result.

    Returns (run_id, fighter_result_id, battle_id).
    """
    battle_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Manual Battle", "openai", "gpt-4o", "Be helpful.", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Human", 1, 1, now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "Q1", "What is 2+2?", 1),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "running", now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "awaiting_input", now),
        )
        await db.commit()

    return run_id, fr_id, battle_id


@pytest.mark.asyncio
async def test_submit_manual_step_returns_complete(client, db_path):
    """Submitting a valid manual answer returns status=complete."""
    run_id, fr_id, _ = await _seed_manual_run(db_path)

    with patch("t01_llm_battle.routers.runs.score_response", new_callable=AsyncMock) as mock_score, \
         patch("t01_llm_battle.routers.runs.generate_report", new_callable=AsyncMock):
        mock_score.return_value = (9.0, "Great answer.")
        resp = await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "4"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["step_result_id"] == fr_id


@pytest.mark.asyncio
async def test_submit_manual_step_updates_db(client, db_path):
    """After submit, fighter_result.final_output and status are updated in DB."""
    run_id, fr_id, _ = await _seed_manual_run(db_path)

    with patch("t01_llm_battle.routers.runs.score_response", new_callable=AsyncMock) as mock_score, \
         patch("t01_llm_battle.routers.runs.generate_report", new_callable=AsyncMock):
        mock_score.return_value = (8.0, "Good.")
        await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "The answer is 4"},
        )

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT status, final_output FROM fighter_result WHERE id = ?", (fr_id,)
        )
        row = await cursor.fetchone()

    assert row["status"] == "complete"
    assert row["final_output"] == "The answer is 4"


@pytest.mark.asyncio
async def test_submit_marks_run_complete_when_all_done(client, db_path):
    """When the last awaiting_input result is submitted, the run status becomes complete."""
    run_id, fr_id, _ = await _seed_manual_run(db_path)

    with patch("t01_llm_battle.routers.runs.score_response", new_callable=AsyncMock) as mock_score, \
         patch("t01_llm_battle.routers.runs.generate_report", new_callable=AsyncMock):
        mock_score.return_value = (7.0, "OK.")
        await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "4"},
        )

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT status FROM run WHERE id = ?", (run_id,))
        row = await cursor.fetchone()

    assert row["status"] == "complete"


@pytest.mark.asyncio
async def test_submit_unknown_step_result_returns_404(client, db_path):
    """Submitting to a nonexistent step_result_id returns 404."""
    run_id, _, _ = await _seed_manual_run(db_path)

    resp = await client.post(
        f"/runs/{run_id}/steps/{uuid.uuid4()}/submit",
        json={"content": "answer"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_wrong_status_returns_400(client, db_path):
    """Submitting to a step_result that is not awaiting_input returns 400."""
    run_id, fr_id, _ = await _seed_manual_run(db_path)

    # First submit moves it to complete
    with patch("t01_llm_battle.routers.runs.score_response", new_callable=AsyncMock) as mock_score, \
         patch("t01_llm_battle.routers.runs.generate_report", new_callable=AsyncMock):
        mock_score.return_value = (5.0, "Meh.")
        await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "first"},
        )

    # Second submit should fail with 400
    resp = await client.post(
        f"/runs/{run_id}/steps/{fr_id}/submit",
        json={"content": "second"},
    )
    assert resp.status_code == 400
