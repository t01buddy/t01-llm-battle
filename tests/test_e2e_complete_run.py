"""E2E test: upload source -> create run with manual fighter -> submit -> check status."""
import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from t01_llm_battle.db import get_db


async def _create_battle_and_fighter(db_path: str) -> tuple[str, str, str]:
    """Seed battle + source + manual fighter. Returns (battle_id, source_id, fighter_id)."""
    battle_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "E2E Battle", "openai", "gpt-4o", "Be helpful.", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "Q1", "What is AI?", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "HumanExpert", 1, 1, now),
        )
        await db.commit()

    return battle_id, source_id, fighter_id


@pytest.mark.asyncio
async def test_e2e_complete_flow_source_to_results(client, db_path):
    """E2E: upload source -> create run -> submit manual response -> check results."""
    # Setup: create battle and manual fighter
    battle_id, source_id, fighter_id = await _create_battle_and_fighter(db_path)

    # 1. Create run
    with patch("t01_llm_battle.engine.start_run_background"):
        run_resp = await client.post(
            "/runs",
            json={"battle_id": battle_id},
        )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    # 2. Manually insert fighter_result (since background execution is patched)
    fr_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "awaiting_input", now),
        )
        await db.commit()

    # 3. Check run status — should show awaiting_input for manual fighter
    status_resp = await client.get(f"/runs/{run_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] in ("pending", "running")
    fighter_results = status_data["fighter_results"]
    assert len(fighter_results) == 1
    assert fighter_results[0]["status"] == "awaiting_input"

    # 4. Submit manual answer (triggers scoring + report generation)
    with patch("t01_llm_battle.routers.runs.score_response", new_callable=AsyncMock) as mock_score, \
         patch("t01_llm_battle.routers.runs.generate_report", new_callable=AsyncMock) as mock_report:
        mock_score.return_value = (9.5, "Excellent explanation.")
        mock_report.return_value = None
        submit_resp = await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "AI is artificial intelligence — systems designed to perform tasks autonomously."},
        )

    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "complete"

    # 5. Verify DB: fighter_result now complete with score
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT status, judge_score, judge_reasoning, final_output FROM fighter_result WHERE id = ?",
            (fr_id,),
        )
        row = await cursor.fetchone()

    assert row["status"] == "complete"
    assert row["judge_score"] == 9.5
    assert row["judge_reasoning"] == "Excellent explanation."
    assert row["final_output"] == "AI is artificial intelligence — systems designed to perform tasks autonomously."

    # 6. Get final results via /results endpoint
    results_resp = await client.get(f"/runs/{run_id}/results")
    assert results_resp.status_code == 200
    results_data = results_resp.json()
    assert results_data["run_id"] == run_id
    assert results_data["status"] == "complete"
    summary = results_data["summary"]
    assert len(summary) == 1
    assert summary[0]["fighter_id"] == fighter_id
    assert summary[0]["score"] == 9.5
