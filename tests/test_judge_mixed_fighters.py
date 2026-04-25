"""Tests for generate_report with mixed manual + automated fighters."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from t01_llm_battle.db import init_db, get_db
from t01_llm_battle.judge import generate_report
from t01_llm_battle.providers.base import ProviderResult


def _mock_result(content: str) -> ProviderResult:
    return ProviderResult(
        content=content,
        input_tokens=50,
        output_tokens=100,
        credits_used=None,
        cost_usd=0.002,
        model="gpt-4o",
        provider="openai",
    )


async def _seed_mixed(db_path: str) -> str:
    """Seed a run with one manual fighter (judge_score via submit) and one automated fighter."""
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    auto_fighter_id = str(uuid.uuid4())
    manual_fighter_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Mixed Battle", "openai", "gpt-4o", "Be concise.", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "Q1", "Explain gravity.", 1),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        # Automated fighter — has a judge_score
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (auto_fighter_id, battle_id, "AutoBot", 0, 1, now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, final_output, total_cost_usd, "
            "total_latency_ms, status, judge_score, judge_reasoning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), run_id, auto_fighter_id, source_id,
                "Gravity is a force.", 0.001, 400, "complete",
                8.0, "Good. SCORE: 8.0", now,
            ),
        )
        # Manual fighter — also has a judge_score (set via submit endpoint)
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (manual_fighter_id, battle_id, "HumanFighter", 1, 2, now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, final_output, total_cost_usd, "
            "total_latency_ms, status, judge_score, judge_reasoning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), run_id, manual_fighter_id, source_id,
                "Gravity pulls objects.", 0, 0, "complete",
                6.5, "Decent. SCORE: 6.5", now,
            ),
        )
        await db.commit()

    return run_id


@pytest.mark.asyncio
async def test_generate_report_mixed_fighters_calls_judge(tmp_path):
    """generate_report works when results include both manual and automated fighters."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_mixed(db_path)

    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("## Rankings\n1. AutoBot\n2. HumanFighter")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "## Rankings" in report
    mock_provider.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_report_mixed_fighters_prompt_includes_both(tmp_path):
    """The judge prompt includes both manual and automated fighter names."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_mixed(db_path)

    mock_provider = AsyncMock()
    captured = []

    async def capture(req):
        captured.append(req)
        return _mock_result("## Rankings\n...")

    mock_provider.run.side_effect = capture

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert len(captured) == 1
    prompt = captured[0].user_prompt
    assert "AutoBot" in prompt
    assert "HumanFighter" in prompt
