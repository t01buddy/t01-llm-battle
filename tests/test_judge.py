"""Tests for t01_llm_battle.judge — score_response parsing."""
from unittest.mock import AsyncMock, patch

import pytest

from t01_llm_battle.judge import score_response
from t01_llm_battle.providers.base import ProviderResult


def _mock_result(content: str) -> ProviderResult:
    return ProviderResult(
        content=content,
        input_tokens=10,
        output_tokens=20,
        credits_used=None,
        cost_usd=0.001,
        model="gpt-4o",
        provider="openai",
    )


@pytest.mark.asyncio
async def test_score_valid_response():
    """Score is parsed correctly from a plain SCORE: line."""
    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result(
        "The response is accurate and concise.\nSCORE: 8"
    )

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        score, reasoning = await score_response(
            judge_provider="openai",
            judge_model="gpt-4o",
            judge_rubric="Quality and accuracy.",
            source_content="What is the capital of France?",
            response_content="Paris is the capital of France.",
        )

    assert score == 8.0
    assert "SCORE: 8" in reasoning


@pytest.mark.asyncio
async def test_score_clamped_above_10():
    """Scores above 10 are clamped to 10.0."""
    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("Great answer!\nSCORE: 15")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        score, _ = await score_response(
            judge_provider="openai",
            judge_model="gpt-4o",
            judge_rubric="",
            source_content="input",
            response_content="output",
        )

    assert score == 10.0


@pytest.mark.asyncio
async def test_score_float():
    """Decimal scores are parsed correctly."""
    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("Good.\nSCORE: 7.5")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        score, _ = await score_response(
            judge_provider="openai",
            judge_model="gpt-4o",
            judge_rubric="",
            source_content="input",
            response_content="output",
        )

    assert score == 7.5


@pytest.mark.asyncio
async def test_score_missing_returns_none():
    """When SCORE line is absent, score is None and reasoning is returned."""
    mock_provider = AsyncMock()
    mock_provider.run.return_value = _mock_result("No score line here.")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        score, reasoning = await score_response(
            judge_provider="openai",
            judge_model="gpt-4o",
            judge_rubric="",
            source_content="input",
            response_content="output",
        )

    assert score is None
    assert "No score line here." in reasoning


@pytest.mark.asyncio
async def test_score_provider_raises_returns_error():
    """If the provider raises, score is None and reasoning contains 'Judge error'."""
    mock_provider = AsyncMock()
    mock_provider.run.side_effect = RuntimeError("provider down")

    with patch("t01_llm_battle.judge.get_provider", return_value=mock_provider):
        score, reasoning = await score_response(
            judge_provider="openai",
            judge_model="gpt-4o",
            judge_rubric="",
            source_content="input",
            response_content="output",
        )

    assert score is None
    assert "Judge error" in reasoning
