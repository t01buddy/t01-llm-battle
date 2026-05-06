"""Unit tests for AnthropicProvider (FR-6)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.anthropic import AnthropicProvider
from t01_llm_battle.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = AnthropicProvider()
    request = ProviderRequest(
        model="claude-3-5-haiku-20241022",
        system_prompt="You are a helpful assistant.",
        user_prompt="Hello!",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 12
    mock_usage.response_tokens = 8

    mock_result = MagicMock()
    mock_result.output = "Hi there!"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.anthropic.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance

        result = await provider.run(request)

    assert result.content == "Hi there!"
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.provider == "anthropic"
    assert result.credits_used is None


@pytest.mark.asyncio
async def test_run_raises_without_api_key():
    provider = AnthropicProvider()
    request = ProviderRequest(
        model="claude-3-5-haiku-20241022",
        system_prompt=None,
        user_prompt="Hello!",
        api_key=None,
    )
    with patch("t01_llm_battle.providers.anthropic.os.environ.get", return_value=""):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            await provider.run(request)


def test_models_returns_list():
    provider = AnthropicProvider()
    with patch("t01_llm_battle.providers.anthropic.get_llm_models", return_value=["claude-3-5-haiku-20241022"]):
        result = provider.models()
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_cost_usd_computed():
    provider = AnthropicProvider()
    request = ProviderRequest(
        model="claude-3-5-haiku-20241022",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 100
    mock_usage.response_tokens = 50

    mock_result = MagicMock()
    mock_result.output = "response"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.anthropic.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance
        with patch("t01_llm_battle.providers.anthropic.get_llm_cost", return_value=0.005) as mock_cost:
            result = await provider.run(request)
            mock_cost.assert_called_once_with("anthropic", "claude-3-5-haiku-20241022", 100, 50)

    assert result.cost_usd == 0.005
