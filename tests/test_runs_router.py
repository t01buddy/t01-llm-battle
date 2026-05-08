"""Tests for the /runs router."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from t01_llm_battle.db import get_db


@pytest.mark.asyncio
async def test_get_run_status_not_found(client):
    """GET /runs/<nonexistent>/status should return 404."""
    resp = await client.get(f"/runs/{uuid.uuid4()}/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_status_returns_data(client, db_path):
    """Insert a battle + run directly, then poll status via the API."""
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Status Battle", "openai", "gpt-4o", "", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "pending", now),
        )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "pending"
    assert isinstance(data["fighter_results"], list)


@pytest.mark.asyncio
async def test_create_run_battle_not_found(client):
    """POST /runs with a nonexistent battle_id should return 404."""
    with patch("t01_llm_battle.engine.start_run_background"):
        resp = await client.post("/runs", json={"battle_id": str(uuid.uuid4())})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_no_fighters(client, db_path):
    """POST /runs for a battle with no fighters should return 422."""
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Empty Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()

    with patch("t01_llm_battle.engine.start_run_background"):
        resp = await client.post("/runs", json={"battle_id": battle_id})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_manual_submit_completes_run(client, db_path):
    """Manual submit marks fighter_result complete and, when sole result, marks run complete."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Manual Battle", "", "", "", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "q1", "What is 2+2?", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Human", 1, 1, now),
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

    with patch("t01_llm_battle.routers.runs.score_response", return_value=(None, None)), \
         patch("t01_llm_battle.routers.runs.generate_report", return_value="report"):
        resp = await client.post(
            f"/runs/{run_id}/steps/{fr_id}/submit",
            json={"content": "The answer is 4."},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["step_result_id"] == fr_id
    assert data["status"] == "complete"

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT status FROM fighter_result WHERE id = ?", (fr_id,))
        row = await cursor.fetchone()
        assert row["status"] == "complete"

        cursor = await db.execute("SELECT status FROM run WHERE id = ?", (run_id,))
        run_row = await cursor.fetchone()
        assert run_row["status"] == "complete"


@pytest.mark.asyncio
async def test_manual_submit_wrong_run_returns_404(client, db_path):
    """Submit with a run_id that doesn't match the fighter_result returns 404."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    other_run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "B", "", "", "", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "s", "q", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "H", 1, 1, now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "running", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (other_run_id, battle_id, "running", now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "awaiting_input", now),
        )
        await db.commit()

    resp = await client.post(
        f"/runs/{other_run_id}/steps/{fr_id}/submit",
        json={"content": "answer"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_submit_non_awaiting_input_returns_400(client, db_path):
    """Submit to a fighter_result not in awaiting_input status returns 400."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "B2", "", "", "", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "s", "q", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "H", 1, 1, now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "running", now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "complete", now),
        )
        await db.commit()

    resp = await client.post(
        f"/runs/{run_id}/steps/{fr_id}/submit",
        json={"content": "too late"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cancel_run_not_found(client):
    """POST /runs/<nonexistent>/cancel should return 404."""
    resp = await client.post(f"/runs/{uuid.uuid4()}/cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_pending(client, db_path):
    """Cancel a pending run → status becomes 'cancelled'."""
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Cancel Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "pending", now),
        )
        await db.commit()

    resp = await client.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_run_already_complete(client, db_path):
    """Cancel a completed run → 400."""
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Done Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        await db.commit()

    resp = await client.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_run_results_not_found(client):
    """GET /runs/<nonexistent>/results should return 404."""
    resp = await client.get(f"/runs/{uuid.uuid4()}/results")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_results_leaderboard_aggregates(client, db_path):
    """Returns fighter leaderboard aggregates (avg score, cost, latency) for a complete run."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())
    sr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Results Battle", "openai", "gpt-4o", "", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "src1", "question text", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Fighter A", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id, fighter_id, 0, None, "openai", "gpt-4o", "{}", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        await db.execute(
            "INSERT INTO fighter_result (id, run_id, fighter_id, source_id, status, judge_score, judge_reasoning, total_cost_usd, total_latency_ms, total_input_tokens, total_output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "complete", 8.5, "good answer", 0.002, 1200, 50, 30, now),
        )
        await db.execute(
            "INSERT INTO step_result (id, run_id, fighter_id, step_id, source_id, input_text, output_text, input_tokens, output_tokens, latency_ms, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sr_id, run_id, fighter_id, step_id, source_id, "q", "The answer", 50, 30, 1200, 0.002, now),
        )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "complete"
    assert len(data["summary"]) == 1
    entry = data["summary"][0]
    assert entry["fighter_name"] == "Fighter A"
    assert entry["source_label"] == "src1"
    assert entry["score"] == pytest.approx(8.5)
    assert entry["total_cost_usd"] == pytest.approx(0.002)
    assert entry["total_latency_ms"] == 1200


@pytest.mark.asyncio
async def test_get_run_results_per_source_breakdown(client, db_path):
    """Per-source breakdown: each source item lists the fighter output."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id_a = str(uuid.uuid4())
    source_id_b = str(uuid.uuid4())
    step_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Multi-src Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id_a, battle_id, "srcA", "q1", 1),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id_b, battle_id, "srcB", "q2", 2),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Fighter B", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id, fighter_id, 0, None, "openai", "gpt-4o", "{}", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        for sid, label in [(source_id_a, "out-A"), (source_id_b, "out-B")]:
            fr_id = str(uuid.uuid4())
            sr_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO fighter_result (id, run_id, fighter_id, source_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (fr_id, run_id, fighter_id, sid, "complete", now),
            )
            await db.execute(
                "INSERT INTO step_result (id, run_id, fighter_id, step_id, source_id, input_text, output_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sr_id, run_id, fighter_id, step_id, sid, "q", label, now),
            )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    labels = {e["source_label"] for e in data["summary"]}
    assert labels == {"srcA", "srcB"}


@pytest.mark.asyncio
async def test_get_run_results_report_markdown_included(client, db_path):
    """report_markdown field is included when judge was configured."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Judge Battle", "openai", "gpt-4o", "score 1-10", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at, report_markdown) VALUES (?, ?, ?, ?, ?)",
            (run_id, battle_id, "complete", now, "# Report\nFighter A wins."),
        )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_markdown"] == "# Report\nFighter A wins."


@pytest.mark.asyncio
async def test_get_run_results_no_judge_scores_null(client, db_path):
    """Endpoint works when no judge configured — scores are null in summary."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "No Judge Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "src1", "q", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Fighter C", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        await db.execute(
            "INSERT INTO fighter_result (id, run_id, fighter_id, source_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "complete", now),
        )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_markdown"] is None
    assert len(data["summary"]) == 1
    assert data["summary"][0]["score"] is None


@pytest.mark.asyncio
async def test_get_run_results_step_drill_down(client, db_path):
    """step_results list is populated per fighter per source."""
    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    fighter_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    step_id_0 = str(uuid.uuid4())
    step_id_1 = str(uuid.uuid4())
    fr_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Step Battle", None, None, None, now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "src1", "q", 1),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fighter_id, battle_id, "Fighter D", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id_0, fighter_id, 0, None, "openai", "gpt-4o", "{}", now),
        )
        await db.execute(
            "INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id_1, fighter_id, 1, None, "openai", "gpt-4o", "{}", now),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        await db.execute(
            "INSERT INTO fighter_result (id, run_id, fighter_id, source_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fr_id, run_id, fighter_id, source_id, "complete", now),
        )
        for step_id, pos, text in [(step_id_0, 0, "step1 out"), (step_id_1, 1, "step2 out")]:
            sr_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO step_result (id, run_id, fighter_id, step_id, source_id, input_text, output_text, latency_ms, input_tokens, output_tokens, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sr_id, run_id, fighter_id, step_id, source_id, "q", text, 100 * (pos + 1), 10, 5, 0.001, now),
            )
        await db.commit()

    resp = await client.get(f"/runs/{run_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["summary"]) == 1
    step_results = data["summary"][0]["step_results"]
    assert len(step_results) == 2
    assert step_results[0]["step_index"] == 0
    assert step_results[0]["output_text"] == "step1 out"
    assert step_results[1]["step_index"] == 1
    assert step_results[1]["output_text"] == "step2 out"
