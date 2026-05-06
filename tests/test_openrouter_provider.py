"""Unit tests for OpenRouterProvider (FR-6)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.openrouter import OpenRouterProvider
from t01_llm_battle.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = OpenRouterProvider()
    request = ProviderRequest(
        model="meta-llama/llama-3.3-70b-instruct",
        system_prompt="You are helpful.",
        user_prompt="Hello!",
        api_key="test-or-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 18
    mock_usage.response_tokens = 9

    mock_result = MagicMock()
    mock_result.output = "Hello there!"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.openrouter.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance

        result = await provider.run(request)

    assert result.content == "Hello there!"
    assert result.input_tokens == 18
    assert result.output_tokens == 9
    assert result.provider == "openrouter"
    assert result.credits_used is None
    assert result.model == "meta-llama/llama-3.3-70b-instruct"


def test_models_returns_list():
    provider = OpenRouterProvider()
    with patch("t01_llm_battle.providers.openrouter.get_llm_models", return_value=["meta-llama/llama-3.3-70b-instruct"]):
        result = provider.models()
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_uses_openrouter_base_url():
    """run() must point at openrouter.ai/api/v1."""
    provider = OpenRouterProvider()
    request = ProviderRequest(
        model="openai/gpt-4o",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 5
    mock_usage.response_tokens = 3

    mock_result = MagicMock()
    mock_result.output = "ok"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.openrouter.PAIOpenAIProvider") as MockPAI:
        mock_pai_instance = MagicMock()
        MockPAI.return_value = mock_pai_instance
        with patch("t01_llm_battle.providers.openrouter.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_instance

            await provider.run(request)

        _, kwargs = MockPAI.call_args
        assert kwargs.get("base_url") == "https://openrouter.ai/api/v1"
        assert kwargs.get("api_key") == "test-key"


@pytest.mark.asyncio
async def test_cost_usd_computed():
    provider = OpenRouterProvider()
    request = ProviderRequest(
        model="openai/gpt-4o",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 30
    mock_usage.response_tokens = 15

    mock_result = MagicMock()
    mock_result.output = "ok"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.openrouter.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance
        with patch("t01_llm_battle.providers.openrouter.get_llm_cost", return_value=0.003) as mock_cost:
            result = await provider.run(request)
            mock_cost.assert_called_once_with("openrouter", "openai/gpt-4o", 30, 15)

    assert result.cost_usd == 0.003
