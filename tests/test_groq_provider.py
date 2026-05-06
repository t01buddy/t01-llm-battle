"""Unit tests for GroqProvider (FR-6)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.groq import GroqProvider
from t01_llm_battle.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = GroqProvider()
    request = ProviderRequest(
        model="llama-3.3-70b-versatile",
        system_prompt="Be brief.",
        user_prompt="Hello!",
        api_key="test-groq-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 15
    mock_usage.response_tokens = 7

    mock_result = MagicMock()
    mock_result.output = "Hi!"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.groq.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance

        result = await provider.run(request)

    assert result.content == "Hi!"
    assert result.input_tokens == 15
    assert result.output_tokens == 7
    assert result.provider == "groq"
    assert result.credits_used is None
    assert result.model == "llama-3.3-70b-versatile"


def test_models_returns_list():
    provider = GroqProvider()
    with patch("t01_llm_battle.providers.groq.get_llm_models", return_value=["llama-3.3-70b-versatile"]):
        result = provider.models()
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_cost_usd_computed():
    provider = GroqProvider()
    request = ProviderRequest(
        model="llama-3.3-70b-versatile",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-groq-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 200
    mock_usage.response_tokens = 100

    mock_result = MagicMock()
    mock_result.output = "response"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.groq.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance
        with patch("t01_llm_battle.providers.groq.get_llm_cost", return_value=0.001) as mock_cost:
            result = await provider.run(request)
            mock_cost.assert_called_once_with("groq", "llama-3.3-70b-versatile", 200, 100)

    assert result.cost_usd == 0.001
