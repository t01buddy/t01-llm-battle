"""Unit tests for GoogleProvider (FR-6)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.google import GoogleProvider
from t01_llm_battle.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = GoogleProvider()
    request = ProviderRequest(
        model="gemini-2.0-flash",
        system_prompt="Be concise.",
        user_prompt="What is 2+2?",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 20
    mock_usage.response_tokens = 5

    mock_result = MagicMock()
    mock_result.output = "4"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.google.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance

        result = await provider.run(request)

    assert result.content == "4"
    assert result.input_tokens == 20
    assert result.output_tokens == 5
    assert result.provider == "google"
    assert result.credits_used is None
    assert result.model == "gemini-2.0-flash"


def test_models_returns_list():
    provider = GoogleProvider()
    with patch("t01_llm_battle.providers.google.get_llm_models", return_value=["gemini-2.0-flash"]):
        result = provider.models()
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_cost_usd_computed():
    provider = GoogleProvider()
    request = ProviderRequest(
        model="gemini-2.0-flash",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-key",
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 50
    mock_usage.response_tokens = 25

    mock_result = MagicMock()
    mock_result.output = "response"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.google.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance
        with patch("t01_llm_battle.providers.google.get_llm_cost", return_value=0.002) as mock_cost:
            result = await provider.run(request)
            mock_cost.assert_called_once_with("google", "gemini-2.0-flash", 50, 25)

    assert result.cost_usd == 0.002


@pytest.mark.asyncio
async def test_extra_top_p_passed():
    provider = GoogleProvider()
    request = ProviderRequest(
        model="gemini-2.0-flash",
        system_prompt=None,
        user_prompt="Hi",
        api_key="test-key",
        extra={"top_p": 0.9},
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 5
    mock_usage.response_tokens = 3

    mock_result = MagicMock()
    mock_result.output = "ok"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.google.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_instance

        result = await provider.run(request)
        call_kwargs = mock_instance.run.call_args
        assert call_kwargs is not None

    assert result.content == "ok"
