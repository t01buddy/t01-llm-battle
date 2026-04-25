"""Tests for t01_llm_battle.judge — generate_report."""
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


async def _seed_db(db_path: str, *, num_fighters: int = 2, scores: list[float | None] | None = None) -> str:
    """Seed a minimal battle + run + fighter_results. Returns run_id."""
    import uuid
    from datetime import datetime, timezone

    if scores is None:
        scores = [8.0, 6.0]

    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Test Battle", "openai", "gpt-4o", "Quality.", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "source-1", "What is AI?", 1),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        for i in range(num_fighters):
            fighter_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fighter_id, battle_id, f"Fighter {i + 1}", 0, i + 1, now),
            )
            score = scores[i] if i < len(scores) else None
            await db.execute(
                "INSERT INTO fighter_result "
                "(id, run_id, fighter_id, source_id, final_output, total_cost_usd, "
                "total_latency_ms, status, judge_score, judge_reasoning, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    run_id,
                    fighter_id,
                    source_id,
                    "AI is artificial intelligence.",
                    0.001 * (i + 1),
                    500 * (i + 1),
                    "complete",
                    score,
                    f"Good answer. SCORE: {score}" if score is not None else None,
                    now,
                ),
            )
        await db.commit()

    return run_id


@pytest.mark.asyncio
async def test_generate_report_returns_markdown(tmp_path):
    """generate_report calls the judge model and returns the markdown string."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_db(db_path)

    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("## Rankings\n1. Fighter 1\n2. Fighter 2")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "## Rankings" in report
    mock_provider.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_report_stored_in_db(tmp_path):
    """generate_report persists the markdown in run.report_markdown."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_db(db_path)

    expected_md = "## Rankings\n1. Fighter 1"
    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result(expected_md)

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        await generate_report(run_id, "openai", "gpt-4o", db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT report_markdown FROM run WHERE id = ?", (run_id,))
        row = await cursor.fetchone()

    assert row is not None
    assert row["report_markdown"] == expected_md


@pytest.mark.asyncio
async def test_generate_report_no_judged_results(tmp_path):
    """Returns an error string when no judged results exist."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    # Seed with scores=None so no judged rows exist
    run_id = await _seed_db(db_path, scores=[None, None])

    mock_provider = AsyncMock()

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "no judged results" in report.lower()
    mock_provider.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_report_single_fighter(tmp_path):
    """Works correctly with a single fighter."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_db(db_path, num_fighters=1, scores=[9.0])

    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("## Rankings\n1. Fighter 1 (9.00/10)")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "Fighter 1" in report


@pytest.mark.asyncio
async def test_generate_report_provider_raises(tmp_path):
    """Returns an error string when the provider call fails."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_db(db_path)

    mock_provider = AsyncMock()
    mock_provider.run.side_effect = RuntimeError("provider down")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "failed" in report.lower() or "error" in report.lower()


@pytest.mark.asyncio
async def test_generate_report_mixed_manual_automated_fighters(tmp_path):
    """generate_report works correctly when mix of manual (cost=0) and automated fighters."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    battle_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Mixed Battle", "openai", "gpt-4o", "Quality.", now),
        )
        await db.execute(
            "INSERT INTO battle_source (id, battle_id, label, content, position) VALUES (?, ?, ?, ?, ?)",
            (source_id, battle_id, "q1", "Explain AI.", 1),
        )
        await db.execute(
            "INSERT INTO run (id, battle_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, battle_id, "complete", now),
        )
        # Manual fighter (is_manual=1, cost=0)
        manual_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manual_id, battle_id, "Human Expert", 1, 1, now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, final_output, total_cost_usd, "
            "total_latency_ms, status, judge_score, judge_reasoning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), run_id, manual_id, source_id,
             "AI is artificial intelligence.", 0.0, 0, "complete", 9.0,
             "Excellent. SCORE: 9.0", now),
        )
        # Automated fighter
        auto_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (auto_id, battle_id, "GPT-4o", 0, 2, now),
        )
        await db.execute(
            "INSERT INTO fighter_result "
            "(id, run_id, fighter_id, source_id, final_output, total_cost_usd, "
            "total_latency_ms, status, judge_score, judge_reasoning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), run_id, auto_id, source_id,
             "AI means machines that mimic human intelligence.", 0.005, 1200,
             "complete", 7.5, "Good answer. SCORE: 7.5", now),
        )
        await db.commit()

    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result(
        "## Rankings\n1. Human Expert\n2. GPT-4o"
    )

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        report = await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert "Human Expert" in report
    assert "GPT-4o" in report
    mock_provider.run.assert_awaited_once()
    prompt = mock_provider.run.call_args[0][0].user_prompt
    assert "Human Expert" in prompt
    assert "GPT-4o" in prompt


@pytest.mark.asyncio
async def test_generate_report_prompt_includes_fighter_names(tmp_path):
    """The prompt sent to the judge includes fighter names and scores."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    run_id = await _seed_db(db_path, scores=[7.0, 5.0])

    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("## Rankings\n...")
    captured_request = []

    async def capture_run(req):
        captured_request.append(req)
        return _mock_result("## Rankings\n...")

    mock_provider.run.side_effect = capture_run

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        await generate_report(run_id, "openai", "gpt-4o", db_path)

    assert len(captured_request) == 1
    prompt = captured_request[0].user_prompt
    assert "Fighter 1" in prompt
    assert "Fighter 2" in prompt
